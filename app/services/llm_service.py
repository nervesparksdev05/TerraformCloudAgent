import os
import json
import asyncio
import re
from typing import List, Dict, Optional
import google.generativeai as genai
from openai import OpenAI, AsyncOpenAI
from app.core import config
from app.core.logger import get_logger

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
        raise ValueError(f"No JSON object found in output: {t[:300]}")

    candidate = m.group(0)
    json.loads(candidate)  # validate
    return candidate


class LLMService:
    """
    Unified LLM service supporting Google Gemini and OpenAI.
    Handles authentication, fallback logic, and provider switching.
    """

    def __init__(self):
        self.provider = config.DEFAULT_PROVIDER  # cloud provider, NOT LLM provider
        self.llm_provider = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

        # Initialize Gemini
        self.gemini_api_key = config.GOOGLE_API_KEY
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel(config.GEMINI_MODEL)
        else:
            logger.warning("GOOGLE_API_KEY not set. Gemini will not be available.")
            self.gemini_model = None

        # Initialize OpenAI
        self.openai_api_key = config.OPENAI_API_KEY
        if self.openai_api_key:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        else:
            logger.warning("OPENAI_API_KEY not set. OpenAI will not be available.")
            self.openai_client = None

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ) -> str:
        """
        Synchronous chat completion.
        """
        current_provider = self.llm_provider

        try:
            if current_provider == "openai" and self.openai_client:
                return self._call_openai(messages, temperature, max_tokens, response_format, timeout)

            if current_provider == "gemini" and self.gemini_model:
                return self._call_gemini(messages, temperature, max_tokens, response_format)

            # Fallback
            if self.gemini_model:
                logger.info("Falling back to Gemini...")
                return self._call_gemini(messages, temperature, max_tokens, response_format)

            if self.openai_client:
                logger.info("Falling back to OpenAI...")
                return self._call_openai(messages, temperature, max_tokens, response_format, timeout)

            raise ValueError("No LLM provider configured or available.")

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            raise

    def _call_openai(self, messages, temperature, max_tokens, response_format, timeout) -> str:
        kwargs = {
            "model": config.OPENAI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = self.openai_client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        logger.debug("OpenAI raw response (first 500): %s", content[:500])

        if response_format and response_format.get("type") == "json_object":
            return extract_json_object(content)

        return content

    # Models that do NOT support JSON response mode
    _NO_JSON_MODE_PREFIXES = ("gemma-",)

    def _model_supports_json_mode(self) -> bool:
        """Check if the current Gemini model supports response_mime_type JSON."""
        model_name = (config.GEMINI_MODEL or "").lower()
        return not any(model_name.startswith(p) for p in self._NO_JSON_MODE_PREFIXES)

    def _call_gemini(self, messages, temperature, max_tokens, response_format) -> str:
        json_requested = bool(response_format and response_format.get("type") == "json_object")

        # Build Gemini history safely: keep a clean history and a final user prompt
        history = []
        system_instruction = None
        last_user = None

        for msg in messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()

            if role == "system":
                system_instruction = content
            elif role == "user":
                # keep user turns in history; we will send the LAST user as prompt
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})

        # Pull last user out of history as send_message prompt
        if history and history[-1]["role"] == "user":
            last_user = history[-1]["parts"][0]
            history = history[:-1]
        else:
            last_user = "Hello"

        # Configure generation config
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Strong JSON instruction (works even if JSON mime type is ignored)
        if json_requested:
            json_hint = (
                "\n\nIMPORTANT: Respond ONLY with a single valid JSON object. "
                "No markdown, no code fences, no extra text."
            )
            if system_instruction:
                system_instruction += json_hint
            else:
                last_user = (last_user or "Hello") + json_hint

        # Only set JSON mime type for supported models
        if json_requested and self._model_supports_json_mode():
            generation_config.response_mime_type = "application/json"

        # Create model with system instruction if present
        model = self.gemini_model
        if system_instruction:
            model = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL,
                system_instruction=system_instruction
            )

        chat = model.start_chat(history=history)
        response = chat.send_message(last_user, generation_config=generation_config)
        text = response.text or ""

        logger.debug("Gemini raw response (first 500): %s", text[:500])

        if json_requested:
            return extract_json_object(text)

        return text


class AsyncLLMService(LLMService):
    """
    Asynchronous wrapper/implementation for LLM Service.
    """
    def __init__(self):
        super().__init__()
        if self.openai_api_key:
            self.async_openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        else:
            self.async_openai_client = None

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ) -> str:
        try:
            if self.llm_provider == "openai" and self.async_openai_client:
                return await self._call_openai_async(messages, temperature, max_tokens, response_format, timeout)

            if self.llm_provider == "gemini" and self.gemini_model:
                return await asyncio.to_thread(
                    self._call_gemini, messages, temperature, max_tokens, response_format
                )

            # fallback
            if self.gemini_model:
                return await asyncio.to_thread(
                    self._call_gemini, messages, temperature, max_tokens, response_format
                )

            if self.async_openai_client:
                return await self._call_openai_async(messages, temperature, max_tokens, response_format, timeout)

            raise ValueError("No LLM provider configured or available.")

        except Exception as e:
            logger.error(f"Async LLM generation failed: {e}", exc_info=True)
            raise

    async def _call_openai_async(self, messages, temperature, max_tokens, response_format, timeout) -> str:
        kwargs = {
            "model": config.OPENAI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.async_openai_client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        logger.debug("OpenAI async raw response (first 500): %s", content[:500])

        if response_format and response_format.get("type") == "json_object":
            return extract_json_object(content)

        return content
