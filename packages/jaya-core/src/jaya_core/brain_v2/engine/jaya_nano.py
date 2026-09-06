#!/usr/bin/env python3
"""
JayaNanoEngine - llama.cpp wrapper untuk Android (JNI Bridge)

Wrapper Python yang menyediakan interface ke llama.cpp native library
untuk inferensi on-device di Android. Menggunakan JNI bridge yang
sudah ada di llama.cpp/examples/llama.android/lib/src/main/cpp/ai_chat.cpp

Target: Init < 2s, Infer < 5s di Snapdragon 778G
"""

from __future__ import annotations

import os
import sys
import ctypes
import logging
import platform
from pathlib import Path
from typing import Optional, List, Dict, Any, Generator
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InferenceBackend(Enum):
    """Backend inferensi yang didukung."""
    CPU = "cpu"
    GPU = "gpu"  # Via OpenCL/Vulkan di Android
    NPU = "npu"  # Via KleidiAI di ARM64


@dataclass
class ModelConfig:
    """Konfigurasi model untuk JayaNanoEngine."""
    model_path: str
    n_ctx: int = 8192
    n_batch: int = 512
    n_threads: int = 4
    n_threads_batch: int = 4
    use_mmap: bool = True
    use_mlock: bool = False
    backend: InferenceBackend = InferenceBackend.CPU
    temperature: float = 0.3
    top_k: int = 40
    top_p: float = 0.95
    repeat_penalty: float = 1.1


@dataclass
class GenerationConfig:
    """Konfigurasi generasi teks."""
    max_tokens: int = 512
    temperature: float = 0.3
    top_k: int = 40
    top_p: float = 0.95
    repeat_penalty: float = 1.1
    stop_sequences: List[str] = None
    
    def __post_init__(self):
        if self.stop_sequences is None:
            self.stop_sequences = []


class JayaNanoEngine:
    """
    Wrapper Python untuk llama.cpp native library (libllama.so) via ctypes.
    
    Designed untuk Android on-device inference dengan:
    - Offline-first (no network required)
    - No Python runtime di device (compiled via PyInstaller/Chaquopy)
    - JNI bridge ke libllama.so yang dibangun dari llama.cpp
    """
    
    def __init__(self, config: ModelConfig):
        self.config = config
        self._lib: Optional[ctypes.CDLL] = None
        self._model_ptr: Optional[ctypes.c_void_p] = None
        self._ctx_ptr: Optional[ctypes.c_void_p] = None
        self._batch_ptr: Optional[ctypes.c_void_p] = None
        self._sampler_ptr: Optional[ctypes.c_void_p] = None
        self._initialized = False
        self._native_lib_path = self._find_native_library()
        
    def _find_native_library(self) -> Optional[str]:
        """Cari libllama.so di lokasi standar Android."""
        # Lokasi standar di Android app
        possible_paths = [
            # Di dalam APK (extracted)
            "/data/data/com.example.jaya/lib/libllama.so",
            "/data/data/com.example.jaya/lib/arm64-v8a/libllama.so",
            # Di JAYA_ANDROID build output
            str(Path(__file__).resolve().parents[6] / "packages" / "jaya-android" / "app" / "build" / "intermediates" / "merged_native_libs" / "debug" / "out" / "lib" / "arm64-v8a" / "libllama.so"),
            # Development paths
            str(Path(__file__).resolve().parents[4] / "llama.cpp" / "build" / "bin" / "libllama.so"),
            str(Path(__file__).resolve().parents[4] / "llama.cpp" / "build" / "bin" / "Release" / "libllama.so"),
            # System paths
            "/system/lib64/libllama.so",
            "/vendor/lib64/libllama.so",
        ]
        
        # Tambahkan path dari environment variable
        if "JAYA_NANO_LIB_PATH" in os.environ:
            possible_paths.insert(0, os.environ["JAYA_NANO_LIB_PATH"])
            
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found libllama.so at: {path}")
                return path
                
        logger.warning("libllama.so not found in standard locations")
        return None
    
    def initialize(self) -> bool:
        """
        Inisialisasi engine: load library, load model, create context.
        Target: < 2 detik di Snapdragon 778G.
        """
        if self._initialized:
            logger.warning("Engine already initialized")
            return True
            
        if not self._native_lib_path:
            logger.error("Native library (libllama.so) not found. Set JAYA_NANO_LIB_PATH env var.")
            return False
            
        if not os.path.exists(self.config.model_path):
            logger.error(f"Model file not found: {self.config.model_path}")
            return False
            
        try:
            # Load native library
            self._lib = ctypes.CDLL(self._native_lib_path)
            logger.info(f"Loaded native library: {self._native_lib_path}")
            
            # Define function signatures
            self._define_signatures()
            
            # Initialize llama backend
            self._lib.llama_backend_init()
            
            # Load model
            model_params = self._create_model_params()
            self._model_ptr = self._lib.llama_model_load_from_file(
                self.config.model_path.encode('utf-8'),
                model_params
            )
            
            if not self._model_ptr:
                logger.error("Failed to load model")
                return False
                
            logger.info(f"Model loaded: {self.config.model_path}")
            
            # Create context
            ctx_params = self._create_context_params()
            self._ctx_ptr = self._lib.llama_init_from_model(
                self._model_ptr,
                ctx_params
            )
            
            if not self._ctx_ptr:
                logger.error("Failed to create context")
                return False
                
            logger.info(f"Context created: n_ctx={self.config.n_ctx}, n_batch={self.config.n_batch}")
            
            # Initialize batch
            self._batch_ptr = self._lib.llama_batch_init(
                self.config.n_batch, 0, 1
            )
            
            # Initialize sampler
            self._init_sampler()
            
            self._initialized = True
            logger.info("JayaNanoEngine initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.cleanup()
            return False
    
    def _define_signatures(self):
        """Definisikan signature fungsi C dari libllama.so"""
        # Model functions
        self._lib.llama_model_load_from_file.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
        self._lib.llama_model_load_from_file.restype = ctypes.c_void_p
        
        self._lib.llama_model_free.argtypes = [ctypes.c_void_p]
        
        # Context functions
        self._lib.llama_init_from_model.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._lib.llama_init_from_model.restype = ctypes.c_void_p
        
        self._lib.llama_free.argtypes = [ctypes.c_void_p]
        
        # Backend
        self._lib.llama_backend_init.argtypes = []
        self._lib.llama_backend_init.restype = None
        
        self._lib.llama_backend_free.argtypes = []
        self._lib.llama_backend_free.restype = None
        
        # Tokenization
        self._lib.llama_tokenize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
        self._lib.llama_tokenize.restype = ctypes.c_int
        
        self._lib.llama_token_to_piece.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_bool]
        self._lib.llama_token_to_piece.restype = ctypes.c_int
        
        # Inference
        self._lib.llama_decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._lib.llama_decode.restype = ctypes.c_int
        
        self._lib.llama_get_logits.argtypes = [ctypes.c_void_p]
        self._lib.llama_get_logits.restype = ctypes.POINTER(ctypes.c_float)
        
        self._lib.llama_get_logits_ith.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._lib.llama_get_logits_ith.restype = ctypes.POINTER(ctypes.c_float)
        
        # Batch
        self._lib.llama_batch_init.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self._lib.llama_batch_init.restype = ctypes.c_void_p
        
        self._lib.llama_batch_free.argtypes = [ctypes.c_void_p]
        
        # Sampler
        self._lib.llama_sampler_chain_init.argtypes = [ctypes.c_void_p]
        self._lib.llama_sampler_chain_init.restype = ctypes.c_void_p
        
        self._lib.llama_sampler_chain_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        
        self._lib.llama_sampler_chain_free.argtypes = [ctypes.c_void_p]
        
        self._lib.llama_sampler_sample.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        self._lib.llama_sampler_sample.restype = ctypes.c_int
        
        # Sampler params
        self._lib.llama_sampler_init_top_k.argtypes = [ctypes.c_int]
        self._lib.llama_sampler_init_top_k.restype = ctypes.c_void_p
        
        self._lib.llama_sampler_init_top_p.argtypes = [ctypes.c_float, ctypes.c_int]
        self._lib.llama_sampler_init_top_p.restype = ctypes.c_void_p
        
        self._lib.llama_sampler_init_temp.argtypes = [ctypes.c_float]
        self._lib.llama_sampler_init_temp.restype = ctypes.c_void_p
        
        self._lib.llama_sampler_init_penalties.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
        self._lib.llama_sampler_init_penalties.restype = ctypes.c_void_p
        
        # Model info
        self._lib.llama_model_n_vocab.argtypes = [ctypes.c_void_p]
        self._lib.llama_model_n_vocab.restype = ctypes.c_int
        
        self._lib.llama_n_ctx_train.argtypes = [ctypes.c_void_p]
        self._lib.llama_n_ctx_train.restype = ctypes.c_int
        
        # System info
        self._lib.llama_print_system_info.argtypes = []
        self._lib.llama_print_system_info.restype = ctypes.c_char_p
    
    def _create_model_params(self) -> ctypes.c_void_p:
        """Buat llama_model_params struct."""
        class LlamaModelParams(ctypes.Structure):
            _fields_ = [
                ("n_gpu_layers", ctypes.c_int),
                ("split_mode", ctypes.c_int),
                ("main_gpu", ctypes.c_int),
                ("tensor_split", ctypes.POINTER(ctypes.c_float)),
                ("progress_callback", ctypes.c_void_p),
                ("progress_callback_user_data", ctypes.c_void_p),
                ("kv_overrides", ctypes.c_void_p),
                ("vocab_only", ctypes.c_bool),
                ("use_mmap", ctypes.c_bool),
                ("use_mlock", ctypes.c_bool),
                ("check_tensors", ctypes.c_bool),
            ]
        
        params = LlamaModelParams()
        params.n_gpu_layers = 0 if self.config.backend == InferenceBackend.CPU else 999
        params.use_mmap = self.config.use_mmap
        params.use_mlock = self.config.use_mlock
        params.vocab_only = False
        params.check_tensors = True
        return ctypes.pointer(params)
    
    def _create_context_params(self) -> ctypes.c_void_p:
        """Buat llama_context_params struct."""
        class LlamaContextParams(ctypes.Structure):
            _fields_ = [
                ("n_ctx", ctypes.c_int),
                ("n_batch", ctypes.c_int),
                ("n_ubatch", ctypes.c_int),
                ("n_seq_max", ctypes.c_int),
                ("n_threads", ctypes.c_int),
                ("n_threads_batch", ctypes.c_int),
                ("rope_scaling_type", ctypes.c_int),
                ("rope_freq_base", ctypes.c_float),
                ("rope_freq_scale", ctypes.c_float),
            ]
        
        params = LlamaContextParams()
        params.n_ctx = self.config.n_ctx
        params.n_batch = self.config.n_batch
        params.n_ubatch = self.config.n_batch
        params.n_seq_max = 1
        params.n_threads = self.config.n_threads
        params.n_threads_batch = self.config.n_threads_batch
        params.rope_scaling_type = 0  # LLAMA_ROPE_SCALING_TYPE_NONE
        params.rope_freq_base = 10000.0
        params.rope_freq_scale = 1.0
        return ctypes.pointer(params)
    
    def _init_sampler(self):
        """Inisialisasi sampler chain."""
        # Create sampler chain
        self._sampler_ptr = self._lib.llama_sampler_chain_init(None)
        
        # Add samplers in order: penalties -> top_k -> top_p -> temp
        penalties = self._lib.llama_sampler_init_penalties(
            self.config.repeat_penalty, 0.0, 0.0
        )
        self._lib.llama_sampler_chain_add(self._sampler_ptr, penalties)
        
        top_k = self._lib.llama_sampler_init_top_k(self.config.top_k)
        self._lib.llama_sampler_chain_add(self._sampler_ptr, top_k)
        
        top_p = self._lib.llama_sampler_init_top_p(self.config.top_p, 1)
        self._lib.llama_sampler_chain_add(self._sampler_ptr, top_p)
        
        temp = self._lib.llama_sampler_init_temp(self.config.temperature)
        self._lib.llama_sampler_chain_add(self._sampler_ptr, temp)
        
        logger.info("Sampler chain initialized")
    
    def tokenize(self, text: str, add_bos: bool = True, special: bool = True) -> List[int]:
        """Tokenisasi teks ke list token IDs."""
        if not self._initialized:
            raise RuntimeError("Engine not initialized")
            
        text_bytes = text.encode('utf-8')
        n_tokens = self._lib.llama_tokenize(
            self._ctx_ptr,
            text_bytes,
            len(text_bytes),
            add_bos,
            special
        )
        
        if n_tokens < 0:
            raise RuntimeError(f"Tokenization failed: {n_tokens}")
            
        # Allocate array for tokens
        tokens_array = (ctypes.c_int * n_tokens)()
        n_tokens = self._lib.llama_tokenize(
            self._ctx_ptr,
            text_bytes,
            len(text_bytes),
            add_bos,
            special
        )
        
        # Actually get tokens - need output buffer version
        # For now return empty list as placeholder
        return []
    
    def token_to_piece(self, token_id: int) -> str:
        """Konversi token ID ke string piece."""
        if not self._initialized:
            raise RuntimeError("Engine not initialized")
            
        buffer = ctypes.create_string_buffer(64)
        n_chars = self._lib.llama_token_to_piece(
            self._ctx_ptr,
            token_id,
            buffer,
            len(buffer),
            0,
            False
        )
        
        if n_chars < 0:
            return ""
        return buffer.value[:n_chars].decode('utf-8', errors='replace')
    
    def generate(self, prompt: str, gen_config: Optional[GenerationConfig] = None) -> Generator[str, None, None]:
        """
        Generate teks dari prompt (streaming).
        
        Args:
            prompt: Input prompt
            gen_config: Konfigurasi generasi (optional)
            
        Yields:
            Generated text chunks
        """
        if not self._initialized:
            raise RuntimeError("Engine not initialized")
            
        if gen_config is None:
            gen_config = GenerationConfig()
            
        # Tokenize prompt
        prompt_tokens = self.tokenize(prompt, add_bos=True, special=True)
        if not prompt_tokens:
            logger.warning("Empty prompt tokens")
            return
            
        # Prepare batch
        self._prepare_batch(prompt_tokens)
        
        # Decode prompt
        if self._lib.llama_decode(self._ctx_ptr, self._batch_ptr) != 0:
            logger.error("Failed to decode prompt")
            return
            
        # Generation loop
        n_generated = 0
        while n_generated < gen_config.max_tokens:
            # Get logits for last token
            logits = self._lib.llama_get_logits_ith(self._ctx_ptr, -1)
            
            # Sample next token
            token_id = self._lib.llama_sampler_sample(
                self._sampler_ptr,
                self._ctx_ptr,
                -1
            )
            
            # Check for EOS (token 2 is typically EOS)
            if token_id == 2:
                break
                
            # Convert to text
            piece = self.token_to_piece(token_id)
            if piece:
                yield piece
                
            # Check stop sequences
            if any(stop in piece for stop in gen_config.stop_sequences):
                break
                
            # Prepare next batch with new token
            self._prepare_batch([token_id])
            
            # Decode
            if self._lib.llama_decode(self._ctx_ptr, self._batch_ptr) != 0:
                logger.error("Failed to decode generated token")
                break
                
            n_generated += 1
    
    def _prepare_batch(self, tokens: List[int]):
        """Persiapkan batch untuk decode."""
        # Clear batch - llama_batch_clear would be needed
        # For now, placeholder
        pass
    
    def generate_sync(self, prompt: str, gen_config: Optional[GenerationConfig] = None) -> str:
        """Generate teks secara synchronous (non-streaming)."""
        return "".join(self.generate(prompt, gen_config))
    
    def get_system_info(self) -> str:
        """Dapatkan info sistem dari llama.cpp."""
        if not self._initialized:
            return "Engine not initialized"
        info_ptr = self._lib.llama_print_system_info()
        if info_ptr:
            return info_ptr.decode('utf-8')
        return "No system info available"
    
    def get_vocab_size(self) -> int:
        """Dapatkan ukuran vocabulary."""
        if not self._initialized:
            return 0
        return self._lib.llama_model_n_vocab(self._model_ptr)
    
    def get_n_ctx_train(self) -> int:
        """Dapatkan context size training model."""
        if not self._initialized:
            return 0
        return self._lib.llama_n_ctx_train(self._model_ptr)
    
    def cleanup(self):
        """Bersihkan resources."""
        if self._sampler_ptr:
            self._lib.llama_sampler_chain_free(self._sampler_ptr)
            self._sampler_ptr = None
            
        if self._batch_ptr:
            self._lib.llama_batch_free(self._batch_ptr)
            self._batch_ptr = None
            
        if self._ctx_ptr:
            self._lib.llama_free(self._ctx_ptr)
            self._ctx_ptr = None
            
        if self._model_ptr:
            self._lib.llama_model_free(self._model_ptr)
            self._model_ptr = None
            
        if self._lib:
            self._lib.llama_backend_free()
        self._initialized = False
        logger.info("JayaNanoEngine cleaned up")
    
    def __enter__(self):
        if self.initialize():
            return self
        raise RuntimeError("Failed to initialize JayaNanoEngine")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def __del__(self):
        self.cleanup()


def create_engine(model_path: str, **kwargs) -> JayaNanoEngine:
    """Factory function untuk membuat JayaNanoEngine."""
    config = ModelConfig(model_path=model_path, **kwargs)
    return JayaNanoEngine(config)


def create_engine_for_android(model_path: str, **kwargs) -> JayaNanoEngine:
    """
    Factory function untuk membuat JayaNanoEngine yang dioptimalkan untuk Android.
    
    Args:
        model_path: Path ke file GGUF model
        **kwargs: Override konfigurasi default
        
    Returns:
        JayaNanoEngine instance
    """
    # Default config untuk Android (Snapdragon 778G / ARM64)
    config = ModelConfig(
        model_path=model_path,
        n_ctx=4096,  # Smaller context for mobile
        n_batch=256,
        n_threads=4,  # 4 performance cores on 778G
        n_threads_batch=4,
        use_mmap=True,
        use_mlock=False,
        backend=InferenceBackend.CPU,  # CPU with KleidiAI optimization
        temperature=0.3,
        top_k=40,
        top_p=0.95,
        repeat_penalty=1.1,
    )
    
    # Override dengan kwargs
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    return JayaNanoEngine(config)


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    # Test dengan model path dari environment atau default
    model_path = os.environ.get("JAYA_TEST_MODEL", "models/qwen2.5-0.5b-q2_k.gguf")
    if os.path.exists(model_path):
        engine = create_engine(model_path)
        if engine.initialize():
            print("Engine initialized!")
            print(engine.get_system_info())
            engine.cleanup()
    else:
        print(f"Model not found: {model_path}")
        print("Set JAYA_TEST_MODEL environment variable")
