import os
import json
import asyncio
import re
from typing import List, Dict, Optional
import google.generativeai as genai
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
    LLM service using Google Gemini API.
    Handles authentication and chat completion requests.
    """

    def __init__(self):
        self.provider = config.DEFAULT_PROVIDER  # cloud provider, NOT LLM provider
        
        # Initialize Gemini
        self.gemini_api_key = config.GEMINI_API_KEY
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required but not set.")
        
        genai.configure(api_key=self.gemini_api_key)
        self.gemini_model = genai.GenerativeModel(config.GEMINI_MODEL)
        logger.info(f"LLMService initialized with Gemini model: {config.GEMINI_MODEL}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ) -> str:
        """
        Synchronous chat completion using Gemini.
        """
        try:
            return self._call_gemini(messages, temperature, max_tokens, response_format)
        except Exception as e:
            logger.error(f"Gemini LLM generation failed: {e}", exc_info=True)
            raise

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

        # Configure safety settings to be less restrictive
        # This helps avoid false positives when analyzing technical documentation
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_ONLY_HIGH"
            }
        ]

        # Create model with system instruction if present
        model = self.gemini_model
        if system_instruction:
            model = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL,
                system_instruction=system_instruction,
                safety_settings=safety_settings
            )

        chat = model.start_chat(history=history)
        response = chat.send_message(
            last_user, 
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Handle different finish reasons
        # 0 = FINISH_REASON_UNSPECIFIED
        # 1 = STOP (normal completion)
        # 2 = MAX_TOKENS
        # 3 = SAFETY (blocked by safety filters)
        # 4 = RECITATION
        # 5 = OTHER
        
        # Check if response was blocked or had issues
        if not response.candidates:
            raise ValueError("Gemini API returned no candidates. The request may have been blocked.")
        
        candidate = response.candidates[0]
        finish_reason = candidate.finish_reason
        
        # Handle safety blocks (finish_reason 3)
        if finish_reason == 3:  # SAFETY
            safety_ratings = candidate.safety_ratings if hasattr(candidate, 'safety_ratings') else []
            safety_info = ", ".join([f"{r.category.name}: {r.probability.name}" for r in safety_ratings]) if safety_ratings else "Unknown"
            logger.warning(f"Gemini response blocked by safety filters: {safety_info}")
            raise ValueError(
                f"Content was blocked by Gemini safety filters. "
                f"This may be due to sensitive content in the README or prompt. "
                f"Safety ratings: {safety_info}"
            )
        
        # Handle max tokens (finish_reason 2)
        if finish_reason == 2:  # MAX_TOKENS
            logger.warning(f"Gemini response hit max token limit ({max_tokens}). Response may be truncated.")
        
        # Handle other non-successful finish reasons
        if finish_reason not in [0, 1, 2]:  # Not UNSPECIFIED, STOP, or MAX_TOKENS
            logger.warning(f"Gemini finished with unexpected reason: {finish_reason}")
        
        # Try to get text safely
        text = ""
        try:
            text = response.text or ""
        except (ValueError, AttributeError) as e:
            # If we can't get text, try to extract from parts directly
            if candidate.content and candidate.content.parts:
                try:
                    text = "".join([part.text for part in candidate.content.parts if hasattr(part, 'text')])
                except Exception as parts_err:
                    logger.error(f"Failed to extract text from parts: {parts_err}")
            
            # If we still have no text
            if not text:
                # If finish_reason is MAX_TOKENS, provide a more helpful error
                if finish_reason == 2:
                    logger.error(f"Gemini hit max_tokens ({max_tokens}) and returned no content. Response completely truncated.")
                    raise ValueError(
                        f"Response exceeded max_tokens ({max_tokens}) and was completely truncated. "
                        f"No valid content was returned. Please increase max_tokens or simplify the prompt."
                    )
                else:
                    logger.error(f"Could not extract text from Gemini response. Finish reason: {finish_reason}")
                    raise ValueError(
                        f"Gemini API did not return valid content. Finish reason: {finish_reason}. "
                        f"Original error: {str(e)}"
                    )

        logger.debug("Gemini raw response (first 500): %s", text[:500])

        if json_requested:
            return extract_json_object(text)

        return text


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
        timeout: int = 30
    ) -> str:
        """
        Asynchronous chat completion using Gemini.
        """
        try:
            return await asyncio.to_thread(
                self._call_gemini, messages, temperature, max_tokens, response_format
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
        try:
            # Build Gemini history
            history = []
            system_instruction = None
            last_user = None

            for msg in messages:
                role = msg.get("role")
                content = (msg.get("content") or "").strip()

                if role == "system":
                    system_instruction = content
                elif role == "user":
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

            # Configure safety settings
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]

            # Create model with system instruction if present
            model = self.gemini_model
            if system_instruction:
                model = genai.GenerativeModel(
                    model_name=config.GEMINI_MODEL,
                    system_instruction=system_instruction,
                    safety_settings=safety_settings
                )

            chat = model.start_chat(history=history)
            
            # Stream the response
            response_stream = chat.send_message(
                last_user,
                generation_config=generation_config,
                safety_settings=safety_settings,
                stream=True
            )

            # Yield chunks as they arrive
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error(f"Streaming Gemini LLM generation failed: {e}", exc_info=True)
            raise
