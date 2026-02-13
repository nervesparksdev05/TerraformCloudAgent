"""Quick test: verify the current LLM connection from .env settings."""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
llm_provider = os.getenv("LLM_PROVIDER", "gemini")

print(f"LLM Provider : {llm_provider}")
print(f"Model        : {model_name}")
print(f"API Key      : {'***' + api_key[-4:] if api_key else 'NOT SET'}")
print(f"OpenAI Key   : {'SET' if os.getenv('OPENAI_API_KEY', '').startswith('sk-') else 'NOT SET'}")
print("-" * 40)

if not api_key:
    print("ERROR: No GOOGLE_API_KEY found.")
    exit(1)

genai.configure(api_key=api_key)

print(f"Testing {model_name}...")
try:
    model = genai.GenerativeModel(model_name)
    response = model.generate_content("Say hello in one sentence.")
    print(f"✅ Connection OK: {response.text.strip()[:80]}")
except Exception as e:
    print(f"❌ Connection FAILED: {e}")
