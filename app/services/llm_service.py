
import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Union
import google.generativeai as genai
from openai import OpenAI, AsyncOpenAI
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

class LLMService:
    """
    Unified LLM service supporting Google Gemini and OpenAI.
    Handles authentication, fallback logic, and provider switching.
    """
    
    def __init__(self):
        self.provider = config.DEFAULT_PROVIDER  # This is cloud provider, NOT LLM provider.
        # Check env/config for LLM provider preference
        self.llm_provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
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
        try:
            current_provider = self.llm_provider
            
            if current_provider == "openai" and self.openai_client:
                return self._call_openai(messages, temperature, max_tokens, response_format, timeout)
            elif current_provider == "gemini" and self.gemini_model:
                return self._call_gemini(messages, temperature, max_tokens, response_format)
            else:
                # Fallback or error
                if self.gemini_model:
                     logger.info("Falling back to Gemini...")
                     return self._call_gemini(messages, temperature, max_tokens, response_format)
                elif self.openai_client:
                     logger.info("Falling back to OpenAI...")
                     return self._call_openai(messages, temperature, max_tokens, response_format, timeout)
                else:
                    raise ValueError("No LLM provider configured or available.")
                    
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
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
        return response.choices[0].message.content

    # Models that do NOT support JSON response mode
    _NO_JSON_MODE_PREFIXES = ("gemma-",)

    def _model_supports_json_mode(self) -> bool:
        """Check if the current Gemini model supports response_mime_type JSON."""
        model_name = (config.GEMINI_MODEL or "").lower()
        return not any(model_name.startswith(p) for p in self._NO_JSON_MODE_PREFIXES)

    def _call_gemini(self, messages, temperature, max_tokens, response_format) -> str:
        # Convert OpenAI-style messages to Gemini history
        gemini_hist = []
        system_instruction = None
        json_requested = response_format and response_format.get("type") == "json_object"
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content
            elif role == "user":
                gemini_hist.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_hist.append({"role": "model", "parts": [content]})
        
        # Configure generation config
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        # Only set JSON mime type for models that support it
        if json_requested and self._model_supports_json_mode():
            generation_config.response_mime_type = "application/json"
        elif json_requested:
            # Fallback: instruct the model via prompt to return JSON
            logger.info(f"Model {config.GEMINI_MODEL} does not support JSON mode; using prompt-based JSON.")
            json_hint = "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation, just the JSON object."
            if system_instruction:
                system_instruction += json_hint
            elif gemini_hist:
                # Append hint to the last user message
                last = gemini_hist[-1]
                last["parts"] = [last["parts"][0] + json_hint]

        # Create model with system instruction if present
        model = self.gemini_model
        if system_instruction:
             model = genai.GenerativeModel(
                 model_name=config.GEMINI_MODEL,
                 system_instruction=system_instruction
             )

        chat = model.start_chat(history=gemini_hist[:-1] if gemini_hist else [])
        last_msg = gemini_hist[-1]["parts"][0] if gemini_hist else "Hello"
        
        response = chat.send_message(
            last_msg,
            generation_config=generation_config
        )
        return response.text


class AsyncLLMService(LLMService):
    """
    Asynchronous wrapper/implementation for LLM Service.
    """
    def __init__(self):
        super().__init__()
        # Initialize Async OpenAI Client
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
        """
        Asynchronous chat completion.
        """
        try:
            if self.llm_provider == "openai" and self.async_openai_client:
                return await self._call_openai_async(messages, temperature, max_tokens, response_format, timeout)
            elif self.llm_provider == "gemini" and self.gemini_model:
                # Gemini SDK async support is ... partial/different. 
                # Simplest is to run sync method in a thread executor for now 
                # unless using the distinct async methods which might need newer SDK.
                # Let's check if we can run in thread.
                return await asyncio.to_thread(
                    self._call_gemini, messages, temperature, max_tokens, response_format
                )
            else:
                 # Fallback logic
                if self.gemini_model:
                     return await asyncio.to_thread(
                        self._call_gemini, messages, temperature, max_tokens, response_format
                    )
                elif self.async_openai_client:
                     return await self._call_openai_async(messages, temperature, max_tokens, response_format, timeout)
                else:
                    raise ValueError("No LLM provider configured or available.")

        except Exception as e:
            logger.error(f"Async LLM generation failed: {e}")
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
        return response.choices[0].message.content
