import requests
import json
import sys

def verify_flow():
    url = "http://localhost:8000/conversations"
    params = {
        "provider": "aws",
        "github_url": "https://github.com/shekharshekharraj/Tunify-Full-Stack-Music-Streaming-Social-App"
    }
    
    try:
        r = requests.post(url, params=params)
        data = r.json()
        bot_response = data.get("bot_response", "")
        with open("bot_debug.txt", "w", encoding="utf-8") as f:
            f.write(bot_response)
        print("Response written to bot_debug.txt")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_flow()
