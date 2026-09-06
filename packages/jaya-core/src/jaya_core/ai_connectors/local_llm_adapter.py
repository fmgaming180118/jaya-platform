"""
Local LLM Adapter for JAYA Cognitive Core.

Supports GGUF models via llama.cpp including:
- Llama-3 (8B, 70B)
- Nemotron (3 Ultra, 4 Ultra)
- Phi-3, Gemma, Qwen, Mistral, DeepSeek-Coder
- Any GGUF-compatible quantized model

Features:
- Automatic model configuration from registry
- Optimized parameters per model architecture
- Fail-closed design with rule-based fallback
- Context window management
- Performance optimization integration
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from jaya_core.performance import (
    get_optimal_llama_config,
    apply_llama_optimizations,
    get_kv_cache_manager,
    KVCacheManager,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Optimized configuration for specific model architectures."""
    n_ctx: int = 4096
    n_threads: int = 4
    n_gpu_layers: int = 0  # 0 = CPU only, -1 = all layers on GPU
    n_batch: int = 512
    rope_freq_base: float = 10000.0
    rope_freq_scale: float = 1.0
    stop_sequences: Optional[list] = None
    chat_template: Optional[str] = None


# Model-specific optimized configurations
MODEL_CONFIGS = {
    "llama-3": ModelConfig(
        n_ctx=8192,
        n_threads=8,
        n_gpu_layers=0,
        n_batch=512,
        rope_freq_base=500000.0,
        stop_sequences=["<|eot_id|>", "<|end_of_text|>"],
        chat_template="llama3",
    ),
    "llama-3-70b": ModelConfig(
        n_ctx=8192,
        n_threads=8,
        n_gpu_layers=0,
        n_batch=1024,
        rope_freq_base=500000.0,
        stop_sequences=["<|eot_id|>", "<|end_of_text|>"],
        chat_template="llama3",
    ),
    "nemotron": ModelConfig(
        n_ctx=4096,
        n_threads=8,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["</s>", "<|endoftext|>"],
        chat_template="chatml",
    ),
    "phi-3": ModelConfig(
        n_ctx=4096,
        n_threads=4,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["<|end|>", "<|endoftext|>"],
        chat_template="phi3",
    ),
    "gemma": ModelConfig(
        n_ctx=8192,
        n_threads=4,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["<end_of_turn>", "<eos>"],
        chat_template="gemma",
    ),
    "qwen": ModelConfig(
        n_ctx=32768,
        n_threads=4,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["<|im_end|>", "<|endoftext|>"],
        chat_template="chatml",
    ),
    "mistral": ModelConfig(
        n_ctx=32768,
        n_threads=4,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["</s>", "[INST]"],
        chat_template="mistral",
    ),
    "deepseek-coder": ModelConfig(
        n_ctx=16384,
        n_threads=4,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["<|EOT|>", "```"],
        chat_template="deepseek",
    ),
    "default": ModelConfig(
        n_ctx=4096,
        n_threads=4,
        n_gpu_layers=0,
        n_batch=512,
        stop_sequences=["\n", "###"],
        chat_template=None,
    ),
}


def _detect_model_config(model_path: str) -> ModelConfig:
    """Detect optimal configuration based on model filename."""
    path_lower = model_path.lower()
    
    if "llama-3" in path_lower and "70b" in path_lower:
        return MODEL_CONFIGS["llama-3-70b"]
    elif "llama-3" in path_lower or "llama3" in path_lower:
        return MODEL_CONFIGS["llama-3"]
    elif "nemotron" in path_lower:
        return MODEL_CONFIGS["nemotron"]
    elif "phi-3" in path_lower or "phi3" in path_lower:
        return MODEL_CONFIGS["phi-3"]
    elif "gemma" in path_lower:
        return MODEL_CONFIGS["gemma"]
    elif "qwen" in path_lower:
        return MODEL_CONFIGS["qwen"]
    elif "mistral" in path_lower:
        return MODEL_CONFIGS["mistral"]
    elif "deepseek" in path_lower and "coder" in path_lower:
        return MODEL_CONFIGS["deepseek-coder"]
    else:
        return MODEL_CONFIGS["default"]


class LocalLLMAdapter:
    """
    Local LLM Adapter using llama.cpp for GGUF model inference.
    
    Supports a wide range of quantized models with automatic
    configuration optimization per model architecture.
    """

    def __init__(
        self,
        model_path: str = "models/local_llm.gguf",
        n_ctx: Optional[int] = None,
        n_threads: Optional[int] = None,
        n_gpu_layers: Optional[int] = None,
        n_batch: Optional[int] = None,
        verbose: bool = False,
        config: Optional[ModelConfig] = None,
    ):
        """
        Initialize the local LLM adapter.
        
        :param model_path: Path to the GGUF model file.
        :param n_ctx: Context window size (auto-detected if None).
        :param n_threads: Number of CPU threads (auto-detected if None).
        :param n_gpu_layers: Number of layers to offload to GPU (auto-detected if None).
        :param n_batch: Batch size for prompt processing (auto-detected if None).
        :param verbose: Enable llama.cpp verbose output.
        :param config: Explicit ModelConfig (overrides auto-detection).
        """
        self.model_path = model_path
        self.verbose = verbose
        
        # Use explicit config or auto-detect
        if config:
            self.config = config
        else:
            self.config = _detect_model_config(model_path)
        
        # Override with explicit parameters if provided
        if n_ctx is not None:
            self.config.n_ctx = n_ctx
        if n_threads is not None:
            self.config.n_threads = n_threads
        if n_gpu_layers is not None:
            self.config.n_gpu_layers = n_gpu_layers
        if n_batch is not None:
            self.config.n_batch = n_batch

        self.model = None
        self._load_model()

    def _load_model(self):
        """Attempt to load the model using llama.cpp or fallback."""
        try:
            from llama_cpp import Llama
            
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model file not found: {self.model_path}")

            # Log model info
            file_size_mb = os.path.getsize(self.model_path) / (1024 * 1024)
            logger.info(f"Loading model: {self.model_path} ({file_size_mb:.0f}MB)")
            logger.info(f"Config: ctx={self.config.n_ctx}, threads={self.config.n_threads}, "
                       f"gpu_layers={self.config.n_gpu_layers}, batch={self.config.n_batch}")

            self.model = Llama(
                model_path=self.model_path,
                n_ctx=self.config.n_ctx,
                n_threads=self.config.n_threads,
                n_gpu_layers=self.config.n_gpu_layers,
                n_batch=self.config.n_batch,
                rope_freq_base=self.config.rope_freq_base,
                rope_freq_scale=self.config.rope_freq_scale,
                verbose=self.verbose,
                use_mmap=True,
                use_mlock=False,
            )
            
            # Apply performance optimizations
            apply_llama_optimizations(self.model, self.config)
            
            logger.info(f"Successfully loaded local LLM from {self.model_path}")
        except ImportError:
            logger.warning("llama_cpp not installed; using fallback rule-based responder.")
            self.model = None
        except Exception as e:
            logger.warning(f"Could not load local LLM ({e}); using fallback rule-based responder.")
            self.model = None

    def generate(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
    ) -> str:
        """
        Generate a response for the given prompt.
        
        :param prompt: The user prompt (could be enriched with context).
        :param context: Optional dict with extra info.
        :param max_tokens: Maximum tokens to generate.
        :param temperature: Sampling temperature.
        :param top_p: Top-p sampling.
        :param top_k: Top-k sampling.
        :param repeat_penalty: Repetition penalty.
        :return: Generated text.
        """
        if self.model is not None:
            try:
                # Apply chat template if available
                formatted_prompt = self._apply_chat_template(prompt, context)
                
                stop_sequences = self.config.stop_sequences or ["\n", "###"]
                
                output = self.model(
                    formatted_prompt,
                    max_tokens=max_tokens,
                    stop=stop_sequences,
                    echo=False,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repeat_penalty=repeat_penalty,
                )
                
                text = output.get('choices', [{}])[0].get('text', '').strip()
                
                # Post-process: remove any trailing stop sequences
                for stop_seq in stop_sequences:
                    if text.endswith(stop_seq):
                        text = text[:-len(stop_seq)].rstrip()
                
                if text:
                    return text
                    
            except Exception as e:
                logger.error(f"Error during local LLM generation: {e}")
                # Fall through to fallback
        
        # Fallback: rule-based
        return self._fallback_generate(prompt, context)

    def _apply_chat_template(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        """Apply model-specific chat template if available."""
        template = self.config.chat_template
        
        if not template:
            return prompt
        
        # Get conversation history from context
        history = []
        if context and "conversation_history" in context:
            hist = context["conversation_history"]
            if isinstance(hist, list):
                history = hist[-10:]  # Last 10 turns
        
        if template == "llama3":
            return self._format_llama3(prompt, history)
        elif template == "chatml":
            return self._format_chatml(prompt, history)
        elif template == "phi3":
            return self._format_phi3(prompt, history)
        elif template == "gemma":
            return self._format_gemma(prompt, history)
        elif template == "mistral":
            return self._format_mistral(prompt, history)
        elif template == "deepseek":
            return self._format_deepseek(prompt, history)
        
        return prompt

    def _format_llama3(self, prompt: str, history: list) -> str:
        """Format for Llama-3 chat template."""
        parts = ["<|begin_of_text|>"]
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "system":
                parts.append(f"<|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>")
            elif role == "user":
                parts.append(f"<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>")
            elif role == "assistant":
                parts.append(f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>")
        parts.append(f"<|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|>")
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return "".join(parts)

    def _format_chatml(self, prompt: str, history: list) -> str:
        """Format for ChatML template (Qwen, Nemotron, etc.)."""
        parts = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "system":
                parts.append(f"<|im_start|>system\n{content}<|im_end|>")
            elif role == "user":
                parts.append(f"<|im_start|>user\n{content}<|im_end|>")
            elif role == "assistant":
                parts.append(f"<|im_start|>assistant\n{content}<|im_end|>")
        parts.append(f"<|im_start|>user\n{prompt}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def _format_phi3(self, prompt: str, history: list) -> str:
        """Format for Phi-3 chat template."""
        parts = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "system":
                parts.append(f"<|system|>\n{content}<|end|>")
            elif role == "user":
                parts.append(f"<|user|>\n{content}<|end|>")
            elif role == "assistant":
                parts.append(f"<|assistant|>\n{content}<|end|>")
        parts.append(f"<|user|>\n{prompt}<|end|>")
        parts.append("<|assistant|>\n")
        return "\n".join(parts)

    def _format_gemma(self, prompt: str, history: list) -> str:
        """Format for Gemma chat template."""
        parts = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                parts.append(f"<start_of_turn>user\n{content}<end_of_turn>")
            elif role == "assistant":
                parts.append(f"<start_of_turn>model\n{content}<end_of_turn>")
        parts.append(f"<start_of_turn>user\n{prompt}<end_of_turn>")
        parts.append("<start_of_turn>model\n")
        return "\n".join(parts)

    def _format_mistral(self, prompt: str, history: list) -> str:
        """Format for Mistral chat template."""
        parts = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                parts.append(f"[INST] {content} [/INST]")
            elif role == "assistant":
                parts.append(f" {content} </s>")
        parts.append(f"[INST] {prompt} [/INST]")
        return "".join(parts)

    def _format_deepseek(self, prompt: str, history: list) -> str:
        """Format for DeepSeek-Coder chat template."""
        parts = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                parts.append(f"### Instruction:\n{content}\n\n### Response:\n")
            elif role == "assistant":
                parts.append(f"{content}<|EOT|>")
        parts.append(f"### Instruction:\n{prompt}\n\n### Response:\n")
        return "".join(parts)

    def _fallback_generate(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        """Rule-based fallback when model is unavailable."""
        lower_prompt = prompt.lower()
        
        # Greeting responses
        if any(greeting in lower_prompt for greeting in ["halo", "hai", "hello", "hi", "selamat"]):
            return "Halo! Ada yang bisa saya bantu?"
        
        if any(thanks in lower_prompt for thanks in ["terima kasih", "thanks", "makasih"]):
            return "Sama-sama! Ada lagi yang bisa saya bantu?"
        
        # Time/date queries
        if any(time_q in lower_prompt for time_q in ["jam berapa", "what time", "tanggal", "date"]):
            from datetime import datetime
            now = datetime.now()
            return f"Sekarang jam {now.strftime('%H:%M')} tanggal {now.strftime('%d %B %Y')}."
        
        # Identity queries
        if any(id_q in lower_prompt for id_q in ["siapa kamu", "who are you", "nama kamu", "your name"]):
            return "Saya adalah JAYA, asisten AI lokal yang berjalan di perangkat Anda."
        
        # Capability queries
        if any(cap_q in lower_prompt for cap_q in ["apa yang bisa", "what can you", "kemampuan", "capabilities"]):
            return ("Saya bisa membantu dengan: menjawab pertanyaan, menulis kode, "
                   "menganalisis teks, merangkum informasi, dan tugas penalaran umum. "
                   "Semua diproses secara lokal di perangkat Anda.")
        
        # Default: acknowledge with context
        return f"Saya memahami pertanyaan Anda: '{prompt[:100]}...'. Model LLM lokal tidak tersedia, sehingga saya menggunakan respons berbasis aturan."

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        info = {
            "model_path": self.model_path,
            "loaded": self.model is not None,
            "config": {
                "n_ctx": self.config.n_ctx,
                "n_threads": self.config.n_threads,
                "n_gpu_layers": self.config.n_gpu_layers,
                "n_batch": self.config.n_batch,
                "chat_template": self.config.chat_template,
                "stop_sequences": self.config.stop_sequences,
            },
        }
        
        if self.model is not None:
            try:
                # Get model metadata from llama.cpp
                info["model_metadata"] = {
                    "n_vocab": self.model.n_vocab(),
                    "n_embd": self.model.n_embd(),
                    "n_layer": self.model.n_layer(),
                    "n_head": self.model.n_head(),
                    "n_rot": self.model.n_rot(),
                }
            except Exception:
                pass
        
        return info

    def is_ready(self) -> bool:
        """Check if model is loaded and ready for inference."""
        return self.model is not None
