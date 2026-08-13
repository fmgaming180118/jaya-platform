"""Manual NVIDIA VLM reachability smoke test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    from config import config
    from provider_errors import ProviderPolicy, ensure_http_success
except ImportError:
    from src.config import config
    from src.provider_errors import ProviderPolicy, ensure_http_success


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    print("NVIDIA_API_KEY not found")
    sys.exit(1)

invoke_url = config.NVIDIA_VLM_ENDPOINT
stream = False
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "text/event-stream" if stream else "application/json",
}
payload = {
    "model": os.getenv("VIDEO_VLM_MODEL", config.NVIDIA_VISION_MODEL),
    "messages": [{"role": "user", "content": "Hello, are you a VLM?"}],
    "max_tokens": int(os.getenv("VIDEO_VLM_MAX_TOKENS", "1024")),
    "temperature": float(os.getenv("VIDEO_VLM_TEMPERATURE", "0.2")),
    "top_p": float(os.getenv("VIDEO_VLM_TOP_P", "0.7")),
    "stream": stream,
}

print(f"Testing model {payload['model']} at {invoke_url}")
try:
    policy = ProviderPolicy.from_env("NVIDIA_VLM_PROVIDER")
    response = requests.post(
        invoke_url,
        headers=headers,
        json=payload,
        timeout=policy.requests_timeout,
    )
    ensure_http_success("nvidia_vlm", response)
    print(f"Success (HTTP {response.status_code})")
    print(response.json())
except Exception as error:
    print(f"Exception: {type(error).__name__}")
