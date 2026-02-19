import os
import json
import asyncio
import re
import time
from typing import List, Dict, Optional
from google import genai
from google.genai import types
from app.core import config
from app.core.logger import get_logger
from app.services import langfuse_service

logger = get_logger(__name__)


def extract_json_object(text: str) -> str:
    """
    Best-effort extraction of a single JSON object from LLM output.
    Handles:
    - ```json ... ```
    - extra text before/after JSON
    """
    if not text:
        raise ValueError("Empty LLM response")

    t = text.strip()

    # Strip markdown fences
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s*```$", "", t).strip()

    # If already valid JSON
    try:
        json.loads(t)
        return t
    except Exception:
        pass

    # Extract first {...} block
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        logger.error(f"No JSON object found in LLM output (first 1000 chars): {t[:1000]}")
        raise ValueError(f"No JSON object found in output: {t[:300]}")

    candidate = m.group(0)
    
    # Try to validate and provide detailed error
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError as json_err:
        logger.error(f"Invalid JSON from LLM. Error: {json_err}")
        logger.error(f"JSON snippet around error (chars {max(0, json_err.pos-100)}-{json_err.pos+100}): {candidate[max(0, json_err.pos-100):json_err.pos+100]}")
        
        # Try to fix common issues
        # 1. Trailing commas before closing braces/brackets
        fixed = re.sub(r',\s*([\}\]])', r'\1', candidate)
        
        # 2. Missing commas between properties (heuristic)
        # Fix: "key": "value" "next_key": ...
        fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
        fixed = re.sub(r'(\}|\])\s*"', r'\1, "', fixed)  # object/array end followed by key
        fixed = re.sub(r'(\}|\])\s*(\{)', r'\1, \2', fixed)  # object end followed by object start
        fixed = re.sub(r'("\s*:\s*(?:true|false|null|[0-9\.]+))\s*"', r'\1, "', fixed) # literal value followed by key

        try:
            from json_repair import repair_json
            fixed = repair_json(candidate)
            logger.warning("Repaired JSON using json_repair library")
            return fixed
        except Exception as repair_err:
            logger.warning(f"json_repair failed: {repair_err}")
            pass

        try:
            json.loads(fixed)
            logger.warning("Successfully fixed JSON by removing trailing commas and adding missing commas")
            return fixed
        except:
            pass
        
        # If we still can't parse it, raise the original error with context
        logger.error(f"Full JSON (first 2000 chars): {candidate[:2000]}")
        raise ValueError(
            f"Invalid JSON from LLM at position {json_err.pos}: {json_err.msg}. "
            f"Context: ...{candidate[max(0, json_err.pos-50):json_err.pos+50]}..."
        )


class LLMService:
    """
    LLM service using Google GenAI SDK (v0.3.0+).
    Handles authentication and chat completion requests.
    """

    def __init__(self):
        self.provider = config.DEFAULT_PROVIDER  # cloud provider, NOT LLM provider
        
        # Initialize Gemini Client
        self.gemini_api_key = config.GEMINI_API_KEY
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required but not set.")
        
        self.client = genai.Client(api_key=self.gemini_api_key)
        self.model_name = config.GEMINI_MODEL
        logger.info(f"LLMService initialized with Gemini model: {self.model_name}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        _trace=None,
    ) -> str:
        """
        Synchronous chat completion using Gemini.
        """
        try:
            return self._call_gemini(messages, temperature, max_tokens, response_format, _trace=_trace)
        except Exception as e:
            logger.error(f"Gemini LLM generation failed: {e}", exc_info=True)
            raise

    def _call_gemini(self, messages, temperature, max_tokens, response_format, _trace=None) -> str:
        json_requested = bool(response_format and response_format.get("type") == "json_object")
        t0 = time.time()

        # Build contents for Gemini
        # The new SDK uses a simplified content structure
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()

            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=content)]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=content)]))

        # Configure generation config
        config_params = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        # Strong JSON instruction
        if json_requested:
            json_hint = (
                "\n\nIMPORTANT: Respond ONLY with a single valid JSON object. "
                "No markdown, no code fences, no extra text."
            )
            if system_instruction:
                system_instruction += json_hint
            else:
                # If no system instruction, append to last user message if possible
                if contents and contents[-1].role == "user":
                    contents[-1].parts[0].text += json_hint
            
            config_params["response_mime_type"] = "application/json"

        # Safety settings - less restrictive for dev/analysis
        # New SDK uses simplified safety settings config
        # We'll stick to defaults unless specific blocking issues arise, 
        # or map old categories if needed. For now, we omit explicit safety config 
        # to rely on model defaults which are usually reasonable for this API version.

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    **config_params
                )
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

        if not response.text:
            raise ValueError("Gemini API returned empty response")

        text = response.text
        logger.debug("Gemini raw response (first 500): %s", text[:500])

        result = extract_json_object(text) if json_requested else text

        # Extract usage metadata
        usage = None
        if hasattr(response, "usage_metadata"):
            try:
                prompt_tokens = response.usage_metadata.prompt_token_count
                completion_tokens = response.usage_metadata.candidates_token_count
                total_tokens = response.usage_metadata.total_token_count
                
                usage = {
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": total_tokens,
                    "unit": "TOKENS"
                }
                logger.debug(f"Gemini usage: {usage}")
            except Exception as e:
                logger.warning(f"Failed to extract usage metadata: {e}")

        # Log to Langfuse
        langfuse_service.log_generation(
            _trace,
            name="gemini-chat",
            model=self.model_name,
            input_messages=messages,
            output=result[:2000],
            usage=usage,
            start_time=t0,
        )

        return result


class AsyncLLMService(LLMService):
    """
    Asynchronous wrapper for LLM Service using Gemini.
    """
    def __init__(self):
        super().__init__()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        _trace=None,
    ) -> str:
        """
        Asynchronous chat completion using Gemini.
        """
        try:
            return await asyncio.to_thread(
                self._call_gemini, messages, temperature, max_tokens, response_format, _trace
            )
        except Exception as e:
            logger.error(f"Async Gemini LLM generation failed: {e}", exc_info=True)
            raise

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """
        Stream chat completion using Gemini's streaming API.
        Yields text chunks as they're generated.
        """
        # Note: The synchronous client also supports streaming via generate_content_stream
        # We wrap it in asyncio.to_thread for the generator creation, but iterating 
        # a synchronous generator in async context is tricky.
        # Ideally, we'd use the async client if available, but google-genai 0.3.0 
        # exposes a synchronous Client. We'll use a threaded approach.
        
        # Build contents (same logic as _call_gemini)
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()

            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=content)]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=content)]))

        config_params = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        def _stream():
            return self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    **config_params
                )
            )

        try:
            # Create the stream generator in a thread
            stream = await asyncio.to_thread(_stream)
            
            # Iterate through the stream - since it's a sync generator, 
            # we iterate directly. The chunks arrive as network packets.
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
                    # Small yield to let event loop breathe
                    await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Streaming Gemini LLM generation failed: {e}", exc_info=True)
            raise
