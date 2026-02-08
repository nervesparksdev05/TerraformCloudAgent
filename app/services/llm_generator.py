"""
LLM service for generating Terraform code using OpenAI
"""
import json
import requests
from typing import Optional, Dict, Any

from openai import OpenAI
from langfuse.decorators import observe, langfuse_context
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class LLMGenerator:
    """Service for generating Terraform code using OpenAI LLM"""
    
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        
        # Initialize OpenAI client with timeout to prevent indefinite hangs
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TIMEOUT
        )
        self._supports_json_response_format: Optional[bool] = None
        self._supports_custom_temperature: Optional[bool] = None
        
        # Load both AWS and GCP focused prompts
        self.prompts = {
            "aws": self._load_prompt("aws_focused_system_prompt.txt"),
            "gcp": self._load_prompt("gcp_focused_system_prompt.txt")
        }
        
        logger.info(f"LLM Generator initialized with model: {config.OPENAI_MODEL}")
        logger.info(f"Loaded prompts for providers: {list(self.prompts.keys())}")
    
    @observe(name="generate_terraform")
    def generate_terraform(
        self, 
        request: str, 
        provider: str = "aws"
    ) -> TerraformBundle:
        """Generate Terraform configuration from natural language request"""
        
        if provider not in self.prompts:
            raise ValueError(f"Unsupported provider: {provider}. Supported: {list(self.prompts.keys())}")
        
        system_prompt = self.prompts[provider]
        user_prompt = self._get_user_prompt(request)
        
        # Add tags to Langfuse trace
        if config.ENABLE_TRACING:
            langfuse_context.update_current_trace(
                tags=[provider, "terraform_generation"],
                input=request
            )
        
        try:
            logger.debug(f"Generating {provider.upper()} Terraform code with OpenAI: {request}")

            terraform_data = self._openai_json_response(system_prompt, user_prompt)
            
            logger.debug(f"Successfully generated {provider.upper()} Terraform code with OpenAI")
            return TerraformBundle(**terraform_data)
            
        except Exception as e:
            logger.warning(f"OpenAI generation failed: {str(e)}. Attempting fallback to Gemini...")
            
            try:
                # Add metadata about fallback
                if config.ENABLE_TRACING:
                    langfuse_context.update_current_trace(
                        metadata={"fallback_triggered": True, "primary_error": str(e)}
                    )
                
                content = self._call_gemini(system_prompt, user_prompt)
                terraform_data = self._clean_json_content(content)
                logger.info(f"Successfully generated {provider.upper()} Terraform code with Gemini fallback")
                return TerraformBundle(**terraform_data)
                
            except Exception as gemini_error:
                logger.error(f"Gemini fallback also failed: {str(gemini_error)}")
                raise Exception(f"All LLM generation failed. OpenAI: {str(e)}. Gemini: {str(gemini_error)}")
    
    @observe(name="gemini_fallback")
    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Call Google Gemini API as fallback"""
        if not config.GOOGLE_API_KEY or config.GOOGLE_API_KEY == "PLACEHOLDER_KEY":
            raise ValueError("GOOGLE_API_KEY not configured or is placeholder")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={config.GOOGLE_API_KEY}"
        
        # Combine system and user prompt for Gemini as it handles system instructions differently in some versions
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "temperature": config.OPENAI_TEMPERATURE,
                "responseMimeType": "application/json"
            }
        }
        
        response = requests.post(
            url, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=config.OPENAI_TIMEOUT
        )
        
        if response.status_code != 200:
            raise Exception(f"Gemini API Error {response.status_code}: {response.text}")
            
        try:
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to parse Gemini response: {str(e)}. Response: {response.text}")

    def _openai_json_response(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Get JSON from OpenAI, retrying without response_format if model does not support it."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if self._supports_json_response_format is not False:
            try:
                response = self._create_openai_completion(messages, use_response_format=True)
                self._supports_json_response_format = True
                content = response.choices[0].message.content or "{}"
                return self._clean_json_content(content)
            except Exception as exc:
                message = str(exc).lower()
                unsupported = (
                    "response_format" in message
                    and ("not supported" in message or "invalid parameter" in message)
                )
                if not unsupported:
                    raise
                self._supports_json_response_format = False
                logger.warning("Model does not support response_format=json_object; retrying without it.")

        response = self._create_openai_completion(messages, use_response_format=False)
        content = response.choices[0].message.content or "{}"
        return self._clean_json_content(content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
        reraise=True
    )
    def _create_openai_completion(self, messages: list[dict], use_response_format: bool):
        kwargs = {
            "model": config.OPENAI_MODEL,
            "messages": messages,
        }
        if use_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        if self._supports_custom_temperature is not False:
            kwargs["temperature"] = config.OPENAI_TEMPERATURE

        try:
            response = self.client.chat.completions.create(**kwargs)
            if "temperature" in kwargs:
                self._supports_custom_temperature = True
            return response
        except Exception as exc:
            message = str(exc).lower()
            temperature_unsupported = (
                "temperature" in kwargs
                and "temperature" in message
                and ("unsupported" in message or "does not support" in message)
            )
            if not temperature_unsupported:
                raise

            self._supports_custom_temperature = False
            logger.warning("Model does not support custom temperature; retrying with default temperature.")
            kwargs.pop("temperature", None)
            return self.client.chat.completions.create(**kwargs)

    def _clean_json_content(self, content: str) -> Dict[str, Any]:
        """Clean JSON content from LLM response (remove markdown blocks)"""
        content = content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
            
        if content.endswith("```"):
            content = content[:-3]

        cleaned = content.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(cleaned[start : end + 1])

    @observe(name="refine_terraform")
    def refine_terraform(
        self,
        base_request: str,
        current_code: Dict[str, Any],
        feedback: str,
        provider: str = "aws"
    ) -> TerraformBundle:
        """Refine existing Terraform code based on user feedback"""
        
        if provider not in self.prompts:
            raise ValueError(f"Unsupported provider: {provider}")
            
        system_prompt = self.prompts[provider]
        
        # customized prompt for refinement
        user_prompt = f"""
ORIGINAL REQUEST: {base_request}

CURRENT TERRAFORM CODE:
```json
{json.dumps(current_code, indent=2)}
```

USER FEEDBACK / REQUESTED CHANGES:
{feedback}

INSTRUCTIONS:
1. Update the Terraform code to address the user's feedback.
2. Keep the rest of the configuration intact unless changes are necessary for the request.
3. Return the COMPLETE updated Terraform configuration as valid JSON.
"""

        # Add tags to Langfuse trace
        if config.ENABLE_TRACING:
            langfuse_context.update_current_trace(
                tags=[provider, "terraform_refinement"],
                input=feedback
            )
            
        try:
            logger.debug(f"Refining {provider.upper()} Terraform code: {feedback}")

            terraform_data = self._openai_json_response(system_prompt, user_prompt)
            
            logger.debug(f"Successfully refined {provider.upper()} Terraform code")
            return TerraformBundle(**terraform_data)
            
        except Exception as e:
            logger.warning(f"Refinement failed: {str(e)}. Attempting fallback...")
            # Reuse fallback logic but with new prompt
            try:
                content = self._call_gemini(system_prompt, user_prompt)
                terraform_data = self._clean_json_content(content)
                return TerraformBundle(**terraform_data)
            except Exception as gemini_error:
                 raise Exception(f"All LLM generation failed. OpenAI: {str(e)}. Gemini: {str(gemini_error)}")

    def _load_prompt(self, filename: str) -> str:
        """Load system prompt from external file"""
        prompt_file = config.PROMPTS_DIR / filename
        
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"Loaded prompt from {filename} ({len(content)} chars)")
                return content
        except FileNotFoundError:
            raise FileNotFoundError(
                f"System prompt file not found at {prompt_file}"
            )
    
    def _get_user_prompt(self, request: str) -> str:
        """Format user request as prompt"""
        return f"User Request: {request}\n\nGenerate complete Terraform configuration. Return ONLY valid JSON."
    
    @observe(name="chat_response")
    async def generate_chat_response(self, context: str, question: str) -> str:
        """Generate intelligent response to user questions about infrastructure"""
        
        messages = [
            {"role": "system", "content": "You are a helpful cloud infrastructure expert. Answer questions about Terraform configurations concisely and accurately."},
            {"role": "user", "content": context}
        ]
        
        # Add tags to Langfuse trace
        if config.ENABLE_TRACING:
            langfuse_context.update_current_trace(
                tags=["chat", "infrastructure_qa"],
                input=question
            )
        
        try:
            response = self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500  # Keep responses concise
            )
            
            answer = response.choices[0].message.content or "I couldn't generate a response."
            logger.debug(f"Generated chat response for question: {question[:50]}...")
            return answer
            
        except Exception as e:
            logger.warning(f"Chat response generation failed: {e}")
            raise

