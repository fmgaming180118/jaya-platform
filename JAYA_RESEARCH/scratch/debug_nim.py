import os
import requests
from pathlib import Path

# Load .env
def load_dotenv(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

JAYA_ROOT = Path(__file__).resolve().parents[1]
ENV = load_dotenv(JAYA_ROOT / ".env")

API_KEY = ENV.get("NVIDIA_API_KEY", "")
BASE_URL = ENV.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
CHAT_MODEL = ENV.get("NVIDIA_LLAMA31_MODEL", "nvidia/nemotron-3-super-120b-a12b")

print(f"API_KEY: {API_KEY[:10]}...")
print(f"BASE_URL: {BASE_URL}")
print(f"CHAT_MODEL: {CHAT_MODEL}")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": CHAT_MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"}
    ],
    "temperature": 0.0,
    "max_tokens": 200,
    "stop": [
        "PERTANYAAN:", "KONTEKS:", "ATURAN:",
        "Perhatian", "Lihat Konteks", "Penjelasan:",
        "Rasmi", "Catatan:"
    ]
}

try:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
