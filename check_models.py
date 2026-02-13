import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    with open("models_log.txt", "w", encoding="utf-8") as f:
        f.write("Error: GOOGLE_API_KEY not found in .env\n")
    exit(1)

genai.configure(api_key=api_key)

with open("models_log.txt", "w", encoding="utf-8") as log:
    log.write("--- AVAILABLE MODELS ---\n")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                log.write(f"- {m.name}\n")
    except Exception as e:
        log.write(f"Error listing models: {e}\n")

    log.write("\n--- TESTING SPECIFIC MODELS ---\n")
    target_models = [
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.5-pro",          
        "gemini-2.5-flash-lite",   
        "gemini-2.0-flash-lite",
        "gemini-2.0-pro-exp-02-05", # 2.0 Pro experimental
        "gemini-2.0-flash-lite-preview-02-05", 
        "gemma-2-27b-it",          
        "gemma-3-27b-it",          
    ]

    for model_name in target_models:
        log.write(f"\nTesting: {model_name}\n")
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Hello")
            log.write(f"✅ CONNECTED: {response.text.strip()[:50]}...\n")
        except Exception as e:
            log.write(f"❌ FAILED: {str(e)[:100]}...\n")
