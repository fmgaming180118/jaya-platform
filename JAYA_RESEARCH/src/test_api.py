import requests
import base64
import os
import sys
from pathlib import Path

# Load env safely
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    print("NVIDIA_API_KEY not found")
    sys.exit(1)

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = False

headers = {
  "Authorization": f"Bearer {api_key}",
  "Accept": "text/event-stream" if stream else "application/json"
}

# Simple text-only test first to verify model reachability
payload = {
  "model": "qwen/qwen3.5-397b-a17b",
  "messages": [{"role":"user","content":"Hello, are you a VLM?"}],
  "max_tokens": 1024,
  "temperature": 0.60,
  "top_p": 0.95,
  "stream": stream,
  # "chat_template_kwargs": {"enable_thinking":True}, 
}

print(f"Testing Model: {payload['model']} at {invoke_url}")
try:
    response = requests.post(invoke_url, headers=headers, json=payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Success!")
        print(response.json())
    else:
        print("Failed.")
        print(response.text)
except Exception as e:
    print(f"Exception: {e}")
