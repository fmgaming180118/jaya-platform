"""Manual NVIDIA VLM reachability smoke test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from jaya_research.config import config
from jaya_research.provider_errors import ProviderPolicy, ensure_http_success

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.network
@pytest.mark.manual
def test_manual_nvidia_vlm_smoke() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        pytest.skip("NVIDIA_API_KEY not found in environment")

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

    policy = ProviderPolicy.from_env("NVIDIA_VLM_PROVIDER")
    response = requests.post(
        invoke_url,
        headers=headers,
        json=payload,
        timeout=policy.requests_timeout,
    )
    ensure_http_success("nvidia_vlm", response)
    assert response.status_code == 200
