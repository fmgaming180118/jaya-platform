"""
Local LLM Adapter for Jaya AI
Uses a lightweight quantized model (GGML/ONNX) for offline inference.
Falls back to a rule-based responder if the model cannot be loaded.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class LocalLLMAdapter:
    def __init__(self, model_path: str = "models/local_llm.gguf",
                 n_ctx: int = 128,
                 n_threads: int = 4):
        """
        Initialize the local LLM adapter.
        :param model_path: Path to the GGML model file.
        :param n_ctx: Context window size.
        :param n_threads: Number of threads to use.
        """
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.model = None
        self._load_model()

    def _load_model(self):
        """Attempt to load the model using llama.cpp or fallback."""
        try:
            # Try to import llama_cpp (the Python binding for llama.cpp)
            from llama_cpp import Llama
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model file not found: {self.model_path}")
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=False
            )
            logger.info(f"Loaded local LLM from {self.model_path}")
        except Exception as e:
            logger.warning(f"Could not load local LLM ({e}); using fallback rule-based responder.")
            self.model = None

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a response for the given prompt.
        :param prompt: The user prompt (could be enriched with context).
        :param context: Optional dict with extra info.
        :return: Generated text.
        """
        if self.model is not None:
            try:
                # Format prompt as needed; for simplicity we pass it directly.
                output = self.model(
                    prompt,
                    max_tokens=64,
                    stop=["\n", "###"],
                    echo=False
                )
                # The output is a dict with 'text' key
                text = output.get('choices', [{}])[0].get('text', '').strip()
                return text
            except Exception as e:
                logger.error(f"Error during local LLM generation: {e}")
                # Fall through to fallback
        # Fallback: rule-based or simple echo
        return self._fallback_generate(prompt, context)

    def _fallback_generate(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        """Very simple fallback: respond with a canned answer or echo."""
        # In a real implementation, you could use a tiny rule-based system or a small TF-IDF model.
        # For now, we just acknowledge the intent.
        lower_prompt = prompt.lower()
        if any(greeting in lower_prompt for greeting in ["halo", "hai", "hello", "hi"]):
            return "Halo! Ada yang bisa saya bantu?"
        if "terima kasih" in lower_prompt or "thanks" in lower_prompt:
            return "Sama-sama!"
        if "jam berapa" in lower_prompt or "what time" in lower_prompt:
            # Could use system time, but we keep it simple
            return "Saya tidak memiliki akses ke jam saat ini."
        # Default: echo back a snippet to show we heard them
        return f"Anda mengatakan: '{prompt[:50]}...'"
