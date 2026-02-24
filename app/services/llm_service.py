"""
llm_service.py — Gemini LLM service for TerraBot.

Design principles:
  - Single source of truth for history building, safety settings, and JSON extraction
  - Retry with exponential backoff for transient Gemini errors
  - Strict separation between sync (LLMService) and async (AsyncLLMService) surfaces
  - JSON extraction is tolerant but honest: logs and raises rather than silently corrupting
  - No magic integers — use google.generativeai FinishReason enum names
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from typing import Any, Dict, List, Optional, Union, AsyncIterator

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, GenerateContentResponse

from app.core import config
from app.core.logger import get_logger
from app.services import langfuse_service

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_JSON_MODE_UNSUPPORTED_PREFIXES = ("gemma-",)

# FinishReason: 0=UNSPECIFIED, 1=STOP, 2=MAX_TOKENS
_ACCEPTABLE_FINISH_REASONS = {0, 1, 2}

_RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError, OSError)

_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT",       "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

_MAX_RETRIES      = 3
_RETRY_BASE_DELAY = 1.5   # seconds; doubles each retry


# ── JSON extraction ───────────────────────────────────────────────────────────

def _try_parse(text: str) -> Optional[Any]:
    """Return parsed JSON or None — never raises."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def extract_json_object(text: str) -> str:
    """
    Extract the first valid JSON object from LLM output.

    Strategy (stops at first success):
      1. Strip markdown fences → try parse
      2. Find first {...} block → try parse
      3. Fix trailing commas / structural issues → try parse
      4. Try json_repair library if available
      5. Close truncated JSON (unmatched braces/brackets)
      6. Raise ValueError with position, message, and 160-char context

    Returns a JSON *string* — callers call json.loads() themselves.
    """
    if not text:
        raise ValueError("LLM returned empty response.")

    # Step 1 — strip markdown fences
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()
    if _try_parse(cleaned) is not None:
        return cleaned

    # Step 2 — extract first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    start = cleaned.find("{")
    if not match and start == -1:
        raise ValueError(f"No JSON object in LLM output. First 300 chars: {cleaned[:300]!r}")
    candidate = match.group(0) if match else cleaned[start:]
    if _try_parse(candidate) is not None:
        return candidate

    # Step 3 — structural fixes
    fixed = re.sub(r",\s*(?=[\}\]])", "", candidate)           # trailing commas
    fixed = re.sub(r"(\}|\])\s*\n\s*(\{|\[)", r"\1,\n\2", fixed)  # missing comma between objects
    fixed = re.sub(r'("\s*:\s*"[^"]*")\s*\n\s*"', r'\1,\n"', fixed)  # missing comma after string value
    if _try_parse(fixed) is not None:
        logger.debug("extract_json_object: fixed structural issues.")
        return fixed

    # Step 4 — json_repair library
    try:
        from json_repair import repair_json  # type: ignore[import]
        repaired = repair_json(candidate)
        if _try_parse(repaired) is not None:
            logger.warning("extract_json_object: used json_repair.")
            return repaired
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("json_repair failed: %s", exc)

    # Step 5 — close truncated JSON
    truncated = fixed
    if len(re.findall(r'(?<!\\)"', truncated)) % 2 != 0:
        truncated += '"'
    open_sq  = truncated.count("[") - truncated.count("]")
    open_b   = truncated.count("{") - truncated.count("}")
    if open_sq > 0:
        truncated += "]" * open_sq
    if open_b > 0:
        truncated += "}" * open_b
    if _try_parse(truncated) is not None:
        logger.warning("extract_json_object: closed truncated JSON.")
        return truncated

    # Step 6 — raise with context
    try:
        json.loads(candidate)
    except json.JSONDecodeError as exc:
        ctx = candidate[max(0, exc.pos - 80): exc.pos + 80]
        raise ValueError(
            f"Cannot parse JSON — error at pos {exc.pos}: {exc.msg}\nContext: ...{ctx}..."
        ) from exc
    raise ValueError("Unknown JSON extraction failure.")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _model_supports_json_mode(model_name: str) -> bool:
    return not any(model_name.lower().startswith(p) for p in _JSON_MODE_UNSUPPORTED_PREFIXES)


def _build_gemini_history(
    messages: List[Dict[str, str]],
    json_requested: bool,
) -> tuple[Optional[str], list[dict], str]:
    """Convert OpenAI-style messages → (system_instruction, history, last_user_prompt)."""
    system_instruction: Optional[str] = None
    history: list[dict] = []

    for msg in messages:
        role    = (msg.get("role") or "").strip()
        content = (msg.get("content") or "").strip()
        if role == "system":
            system_instruction = content
        elif role == "user":
            history.append({"role": "user",  "parts": [content]})
        elif role == "assistant":
            history.append({"role": "model", "parts": [content]})

    json_hint = (
        "\n\nIMPORTANT: Your entire response MUST be a single valid JSON object. "
        "No markdown, no code fences, no explanation outside the JSON."
    )
    if json_requested and system_instruction:
        system_instruction += json_hint

    # Pull last user message out of history (Gemini requires it as the prompt arg)
    if history and history[-1]["role"] == "user":
        last_user = history[-1]["parts"][0]
        history   = history[:-1]
    else:
        last_user = "Hello"

    if json_requested:
        last_user += "\n\nRespond ONLY with a valid JSON object."

    return system_instruction, history, last_user


def _build_model(
    model_name: str, 
    system_instruction: Optional[str],
    tools: Optional[List[Any]] = None
) -> genai.GenerativeModel:
    kwargs: dict[str, Any] = {"model_name": model_name, "safety_settings": _SAFETY_SETTINGS}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if tools:
        kwargs["tools"] = tools
    return genai.GenerativeModel(**kwargs)


def _build_generation_config(
    temperature: float, 
    max_tokens: int, 
    json_requested: bool, 
    model_name: str,
    tool_choice: Optional[str] = None
) -> GenerationConfig:
    cfg = GenerationConfig(temperature=temperature, max_output_tokens=max_tokens)
    if json_requested and _model_supports_json_mode(model_name):
        cfg.response_mime_type = "application/json"
    return cfg


def _check_candidate(response: GenerateContentResponse, max_tokens: int) -> str:
    """Validate response and extract text. Raises ValueError on blocked/empty responses."""
    if not response.candidates:
        raise ValueError("Gemini returned no candidates — request may have been blocked.")

    candidate     = response.candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)

    if finish_reason == 3:  # SAFETY
        ratings = getattr(candidate, "safety_ratings", [])
        detail  = ", ".join(f"{r.category.name}={r.probability.name}" for r in ratings) or "no detail"
        raise ValueError(f"Response blocked by safety filters ({detail}).")

    if finish_reason not in _ACCEPTABLE_FINISH_REASONS and finish_reason is not None:
        logger.warning("Unexpected Gemini finish_reason: %s", finish_reason)
    if finish_reason == 2:
        logger.warning("Gemini hit max_output_tokens=%d — response may be truncated.", max_tokens)

    text = ""
    try:
        text = response.text or ""
    except (ValueError, AttributeError):
        if candidate.content and candidate.content.parts:
            text = "".join(p.text for p in candidate.content.parts if hasattr(p, "text"))

    if not text and finish_reason == 2:
        raise ValueError(f"Gemini hit max_output_tokens={max_tokens} with no usable text.")

    return text


# ── Core sync call with retry ─────────────────────────────────────────────────
def _call_gemini_sync(
    model_name: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict[str, str]],
    timeout: int,
    _trace: Optional[Any] = None,
) -> str:
    json_requested = bool(response_format and response_format.get("type") == "json_object")
    system_instruction, history, last_user = _build_gemini_history(messages, json_requested)
    model = _build_model(model_name, system_instruction)
    gen_cfg = _build_generation_config(temperature, max_tokens, json_requested, model_name)

    last_exc: Exception = RuntimeError("No attempts made.")
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            t0 = time.time()
            chat = model.start_chat(history=history)
            response = chat.send_message(
                last_user,
                generation_config=gen_cfg,
                safety_settings=_SAFETY_SETTINGS,
                request_options={"timeout": timeout},
            )

            text = _check_candidate(response, max_tokens)

            usage_metadata = getattr(response, "usage_metadata", None)
            usage = None
            if usage_metadata:
                usage = {
                    "input": getattr(usage_metadata, "prompt_token_count", 0),
                    "output": getattr(usage_metadata, "candidates_token_count", 0),
                    "total": getattr(usage_metadata, "total_token_count", 0),
                    "unit": "TOKENS",
                }

            result = extract_json_object(text) if json_requested else text

            if _trace:
                langfuse_service.log_generation(
                    _trace,
                    name="gemini-chat",
                    model=model_name,
                    input_messages=messages,
                    output=result[:10000],
                    usage=usage,
                    start_time=t0,
                )

            return result

        except ValueError:
            raise

        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Gemini transient error attempt %d/%d: %s — retrying in %.1fs",
                attempt, _MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)

        except Exception as exc:
            logger.error("Gemini unexpected error: %s", exc, exc_info=True)
            raise

    raise last_exc

# ── Public service classes ────────────────────────────────────────────────────

class LLMService:
    """
    Synchronous Gemini LLM service.

    Usage:
        svc  = LLMService()
        text = svc.chat_completion(messages=[...])
        obj  = svc.chat_completion(messages=[...], response_format={"type": "json_object"})
        # obj is a JSON string — call json.loads(obj) to get a dict
    """

    def __init__(self) -> None:
        api_key = config.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        genai.configure(api_key=api_key)
        self._model_name: str = config.GEMINI_MODEL
        logger.info("LLMService ready (model: %s)", self._model_name)

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        _trace: Optional[Any] = None,
    ) -> str:
        """
        Synchronous chat completion.
        Returns raw text, or a JSON string if response_format={"type":"json_object"}.
        """
        return _call_gemini_sync(
            model_name=self._model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout=timeout,
            _trace=_trace,
        )


class AsyncLLMService(LLMService):
    """
    Asynchronous Gemini LLM service.
    """

    async def chat_completion(  # type: ignore[override]
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        _trace: Optional[Any] = None,
        use_mcp: Union[bool, List[str]] = False,
    ) -> str:

        enabled_any = config.ENABLE_TERRAFORM_MCP or config.ENABLE_AWS_MCP

        # Fast path (no MCP)
        if not use_mcp or not enabled_any:
            return await asyncio.to_thread(
                _call_gemini_sync,
                self._model_name,
                messages,
                temperature,
                max_tokens,
                response_format,
                timeout,
                _trace,
            )

        from app.services.mcp_service import mcp_manager

        requested_servers = use_mcp if isinstance(use_mcp, list) else ["terraform", "aws"]
        all_mcp_tools = []

        fetch_tasks = []
        if "terraform" in requested_servers and config.ENABLE_TERRAFORM_MCP:
            fetch_tasks.append(
                mcp_manager.list_tools("terraform", config.TERRAFORM_MCP_SERVER)
            )
        if "aws" in requested_servers and config.ENABLE_AWS_MCP:
            fetch_tasks.append(
                mcp_manager.list_tools("aws", config.AWS_MCP_SERVER)
            )

        if fetch_tasks:
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    all_mcp_tools.extend(res)
                else:
                    logger.error("Error fetching MCP tools: %s", res)

        if not all_mcp_tools:
            return await asyncio.to_thread(
                _call_gemini_sync,
                self._model_name,
                messages,
                temperature,
                max_tokens,
                response_format,
                timeout,
                _trace,
            )

        gemini_tools = [{
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                }
                for t in all_mcp_tools
            ]
        }]

        json_requested = bool(response_format and response_format.get("type") == "json_object")
        system_instruction, history, last_user = _build_gemini_history(messages, json_requested)

        model = _build_model(self._model_name, system_instruction, tools=gemini_tools)

        gen_cfg = _build_generation_config(
            temperature,
            max_tokens,
            False,
            self._model_name,
        )

        chat = model.start_chat(history=history)

        response = await asyncio.to_thread(
            chat.send_message,
            last_user,
            generation_config=gen_cfg,
            safety_settings=_SAFETY_SETTINGS,
            request_options={"timeout": timeout},
        )

        for _ in range(10):
            if not response.candidates or not response.candidates[0].content.parts:
                break

            tool_calls = [
                p.function_call
                for p in response.candidates[0].content.parts
                if p.function_call
            ]

            if not tool_calls:
                break

            tool_responses = []

            for tc in tool_calls:
                try:
                    mcp_res = await asyncio.wait_for(
                        mcp_manager.call_tool_by_name(tc.name, tc.args),
                        timeout=10.0,
                    )
                    tool_responses.append({
                        "function_response": {
                            "name": tc.name,
                            "response": {"result": str(mcp_res.content)},
                        }
                    })
                except asyncio.TimeoutError:
                    tool_responses.append({
                        "function_response": {
                            "name": tc.name,
                            "response": {"error": "Tool timed out after 10s"},
                        }
                    })
                except Exception as e:
                    tool_responses.append({
                        "function_response": {
                            "name": tc.name,
                            "response": {"error": str(e)},
                        }
                    })

            response = await asyncio.to_thread(
                chat.send_message,
                tool_responses,
                generation_config=gen_cfg,
                safety_settings=_SAFETY_SETTINGS,
                request_options={"timeout": timeout},
            )

        text = _check_candidate(response, max_tokens)
        return extract_json_object(text) if json_requested else text

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8000,
        timeout: int = 60,
    ) -> AsyncIterator[str]:

        system_instruction, history, last_user = _build_gemini_history(
            messages, json_requested=False
        )

        model = _build_model(self._model_name, system_instruction)
        gen_cfg = _build_generation_config(
            temperature, max_tokens, False, self._model_name
        )

        def _run_stream():
            chat = model.start_chat(history=history)
            return chat.send_message(
                last_user,
                generation_config=gen_cfg,
                safety_settings=_SAFETY_SETTINGS,
                stream=True,
            )

        stream = await asyncio.to_thread(_run_stream)

        for chunk in stream:
            if getattr(chunk, "text", None):
                yield chunk.text
         