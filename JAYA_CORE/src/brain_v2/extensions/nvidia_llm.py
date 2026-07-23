import json
import logging
import os
import urllib.request
from typing import Optional

logger = logging.getLogger("NvidiaLLM")

class NvidiaNIMClient:
    """
    Konektor ke NVIDIA NIM API (Membekali JAYA dengan vast knowledge).
    JAYA OS Constraint: ZERO DEPENDENCIES.
    Menggunakan urllib built-in Python agar sangat ringan dan portabel.
    """
    def __init__(self, api_key: Optional[str] = None, is_reasoning: bool = False):
        # Auto-fetch from Env if not provided
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")

        # Dukungan model dari .env agar dinamis (Normal / Thinking)
        if is_reasoning:
            self.model = os.getenv("NVIDIA_MODEL_REASONING", "deepseek-ai/deepseek-r1")
        else:
            self.model = os.getenv("NVIDIA_MODEL", "meta/llama3-70b-instruct")

        self.endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"

    def ask(self, system_prompt: str, user_prompt: str, max_tokens: int = 512) -> Optional[str]:
        """Tanya ke Llama-3 NVIDIA NIM secara terstruktur, dikembalikan jawaban murninya."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        # Keep historical default behavior of ask() more deterministic.
        return self.chat(messages, max_tokens=max_tokens, temperature=0.3)

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 1024, temperature: float = 0.5) -> Optional[str]:
        """Kirim serangkaian pesan percakapan (Multi-turn) ke NVIDIA NIM."""
        if not self.api_key:
            logger.warning("[NVIDIA LLM] API Key tidak ditemukan. Mode Offline AKTIF.")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method="POST"
        )

        try:
            # Meningkatkan timeout ke 90 detik untuk model reasoning yang lambat
            with urllib.request.urlopen(req, timeout=90) as response:
                result = json.loads(response.read().decode('utf-8'))
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"[NVIDIA LLM] Gagal menghubungi NIM API: {e}")
        return None

