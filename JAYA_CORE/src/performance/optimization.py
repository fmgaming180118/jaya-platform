"""
Performance Optimization for JAYA_CORE.

Provides:
- llama.cpp profiling and optimization
- KV cache management
- Speculative decoding support
- Model quantization recommendations
- Performance benchmarking
"""

from __future__ import annotations

import logging
import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from JAYA_CORE.src.observability import get_structured_logger, record_model_inference

logger = get_structured_logger(__name__, component="performance")


# ============================================================================
# llama.cpp Optimization
# ============================================================================

@dataclass
class LlamaCppConfig:
    """Optimized llama.cpp configuration."""
    # Model parameters
    n_ctx: int = 4096
    n_batch: int = 512
    n_ubatch: int = 512
    n_seq_max: int = 1
    
    # Threading
    n_threads: int = 0  # 0 = auto
    n_threads_batch: int = 0
    
    # GPU offloading
    n_gpu_layers: int = 0  # 0 = CPU only, -1 = all
    main_gpu: int = 0
    tensor_split: Optional[List[float]] = None
    
    # Memory
    use_mmap: bool = True
    use_mlock: bool = False
    numa: bool = False
    
    # KV Cache
    cache_type_k: str = "f16"  # f16, q8_0, q4_0
    cache_type_v: str = "f16"
    no_kv_offload: bool = False
    
    # Speculative decoding
    n_draft: int = 0  # Number of draft tokens (0 = disabled)
    n_predict: int = -1  # -1 = unlimited
    
    # Performance
    flash_attn: bool = True
    rope_scaling_type: int = 0  # 0 = none, 1 = linear, 2 = yarn
    rope_freq_base: float = 0.0
    rope_freq_scale: float = 0.0
    
    # Logging
    verbose: bool = False


def get_optimal_llama_config(
    model_path: Path,
    available_ram_gb: float,
    gpu_vram_gb: float = 0,
    prefer_speed: bool = True,
) -> LlamaCppConfig:
    """Get optimal llama.cpp configuration for hardware."""
    
    # Get model size
    model_size_gb = model_path.stat().st_size / (1024 ** 3)
    
    # CPU threads
    cpu_count = os.cpu_count() or 4
    n_threads = min(cpu_count, 8)  # Cap at 8 for most models
    
    # GPU layers
    n_gpu_layers = 0
    if gpu_vram_gb > 0:
        # Estimate layers that fit in VRAM
        # Rough estimate: ~1GB per 1B parameters for 4-bit
        model_params_b = model_size_gb * 2  # Rough conversion
        layers_per_gb = 32 / model_params_b * 1000  # Approximate
        n_gpu_layers = int(gpu_vram_gb * layers_per_gb * 0.8)  # 80% safety margin
        n_gpu_layers = max(0, min(n_gpu_layers, 100))  # Cap
    
    # Context size based on RAM
    if available_ram_gb >= 32:
        n_ctx = 8192
    elif available_ram_gb >= 16:
        n_ctx = 4096
    else:
        n_ctx = 2048
    
    # Batch size
    n_batch = 512 if available_ram_gb >= 16 else 256
    
    config = LlamaCppConfig(
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_ubatch=min(n_batch, 512),
        n_threads=n_threads,
        n_threads_batch=n_threads,
        n_gpu_layers=n_gpu_layers,
        use_mmap=True,
        use_mlock=(available_ram_gb >= 16),  # Lock memory if enough RAM
        flash_attn=True,
        cache_type_k="f16",
        cache_type_v="f16",
    )
    
    # Enable speculative decoding for larger models on good hardware
    if prefer_speed and gpu_vram_gb >= 8 and model_params_b <= 13:
        config.n_draft = 4  # 4 draft tokens
    
    return config


def apply_llama_optimizations(llama_instance, config: LlamaCppConfig):
    """Apply optimizations to loaded llama.cpp instance."""
    try:
        # Set thread counts
        if hasattr(llama_instance, 'set_n_threads'):
            llama_instance.set_n_threads(config.n_threads, config.n_threads_batch)
        
        # Enable flash attention if supported
        if config.flash_attn and hasattr(llama_instance, 'set_flash_attn'):
            llama_instance.set_flash_attn(True)
        
        logger.info("Applied llama.cpp optimizations", config=config.__dict__)
    except Exception as e:
        logger.warning("Failed to apply some optimizations", error=str(e))


# ============================================================================
# KV Cache Management
# ============================================================================

@dataclass
class KVCacheStats:
    """KV cache statistics."""
    total_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    memory_usage_mb: float = 0.0
    evictions: int = 0
    fragmentation: float = 0.0


class KVCacheManager:
    """Manage KV cache for efficient inference."""
    
    def __init__(self, max_size_mb: float = 1024):
        self.max_size_mb = max_size_mb
        self.cache: Dict[str, Any] = {}  # session_id -> cache_data
        self.stats = KVCacheStats()
        self._lock = threading.Lock()
        self._access_times: Dict[str, float] = {}
    
    def get_cache(self, session_id: str) -> Optional[Any]:
        """Get cache for session."""
        with self._lock:
            if session_id in self.cache:
                self._access_times[session_id] = time.time()
                self.stats.cache_hits += 1
                return self.cache[session_id]
            self.stats.cache_misses += 1
            return None
    
    def set_cache(self, session_id: str, cache_data: Any, size_mb: float):
        """Set cache for session."""
        with self._lock:
            # Check if we need to evict
            current_size = sum(
                self._estimate_cache_size(v) for v in self.cache.values()
            )
            
            while current_size + size_mb > self.max_size_mb and self.cache:
                # Evict LRU
                lru_session = min(self._access_times, key=self._access_times.get)
                del self.cache[lru_session]
                del self._access_times[lru_session]
                current_size -= self._estimate_cache_size(self.cache.get(lru_session, 0))
                self.stats.evictions += 1
            
            self.cache[session_id] = cache_data
            self._access_times[session_id] = time.time()
            self.stats.total_tokens += 1
            self.stats.memory_usage_mb = current_size + size_mb
    
    def clear_session(self, session_id: str):
        """Clear cache for session."""
        with self._lock:
            if session_id in self.cache:
                del self.cache[session_id]
                del self._access_times[session_id]
    
    def clear_all(self):
        """Clear all caches."""
        with self._lock:
            self.cache.clear()
            self._access_times.clear()
            self.stats = KVCacheStats()
    
    def get_stats(self) -> KVCacheStats:
        """Get cache statistics."""
        with self._lock:
            return KVCacheStats(
                total_tokens=self.stats.total_tokens,
                cache_hits=self.stats.cache_hits,
                cache_misses=self.stats.cache_misses,
                memory_usage_mb=self.stats.memory_usage_mb,
                evictions=self.stats.evictions,
                fragmentation=self.stats.fragmentation,
            )
    
    def _estimate_cache_size(self, cache_data: Any) -> float:
        """Estimate cache size in MB."""
        # Rough estimation based on typical KV cache
        if hasattr(cache_data, 'n_tokens'):
            # Each token ~ 2KB for f16 KV cache (key + value)
            return cache_data.n_tokens * 2 / 1024
        return 0.0


# ============================================================================
# Speculative Decoding
# ============================================================================

@dataclass
class SpeculativeConfig:
    """Configuration for speculative decoding."""
    enabled: bool = False
    draft_model_path: Optional[str] = None
    num_draft_tokens: int = 4
    acceptance_threshold: float = 0.5
    max_mismatch: int = 2


class SpeculativeDecoder:
    """
    Speculative decoding implementation.
    
    Uses a smaller draft model to generate candidate tokens,
    then verifies with the main model.
    """
    
    def __init__(self, config: SpeculativeConfig):
        self.config = config
        self.draft_model = None
        self.main_model = None
        self._stats = {
            "total_drafted": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "speedup": 1.0,
        }
    
    def load_models(self, main_model_path: str, draft_model_path: str = None):
        """Load main and draft models."""
        try:
            from llama_cpp import Llama
            
            self.main_model = Llama(
                model_path=main_model_path,
                n_ctx=4096,
                n_threads=4,
                verbose=False,
            )
            
            if draft_model_path or self.config.draft_model_path:
                draft_path = draft_model_path or self.config.draft_model_path
                self.draft_model = Llama(
                    model_path=draft_path,
                    n_ctx=4096,
                    n_threads=2,
                    verbose=False,
                )
                logger.info("Speculative decoding enabled", draft_model=draft_path)
            else:
                logger.warning("No draft model provided, speculative decoding disabled")
                self.config.enabled = False
                
        except Exception as e:
            logger.error("Failed to load models for speculative decoding", error=str(e))
            self.config.enabled = False
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
    ) -> str:
        """Generate using speculative decoding."""
        if not self.config.enabled or not self.draft_model:
            # Fallback to regular generation
            return self._generate_main(prompt, max_tokens, temperature, top_p)
        
        # Speculative decoding loop
        generated = prompt
        tokens_generated = 0
        
        while tokens_generated < max_tokens:
            # Generate draft tokens
            draft_tokens = self._generate_draft(generated, self.config.num_draft_tokens)
            
            if not draft_tokens:
                break
            
            # Verify with main model
            accepted = self._verify_draft(generated, draft_tokens, temperature, top_p)
            
            if accepted:
                generated += accepted
                tokens_generated += len(accepted.split())
                self._stats["total_accepted"] += len(accepted.split())
            else:
                # Fallback to main model for this position
                fallback = self._generate_main(generated, 1, temperature, top_p)
                generated += fallback
                tokens_generated += 1
                self._stats["total_rejected"] += 1
            
            self._stats["total_drafted"] += self.config.num_draft_tokens
        
        # Calculate speedup
        if self._stats["total_drafted"] > 0:
            self._stats["speedup"] = (
                self._stats["total_accepted"] / self._stats["total_drafted"]
            ) * self.config.num_draft_tokens
        
        return generated[len(prompt):]
    
    def _generate_draft(self, prompt: str, num_tokens: int) -> str:
        """Generate draft tokens using draft model."""
        try:
            output = self.draft_model(
                prompt,
                max_tokens=num_tokens,
                temperature=0.1,  # Low temperature for draft
                top_p=0.9,
                echo=False,
            )
            return output['choices'][0]['text']
        except Exception as e:
            logger.warning("Draft generation failed", error=str(e))
            return ""
    
    def _verify_draft(
        self,
        prompt: str,
        draft: str,
        temperature: float,
        top_p: float,
    ) -> str:
        """Verify draft tokens with main model."""
        # For simplicity, just use main model to continue
        # Real implementation would do token-by-token verification
        try:
            output = self.main_model(
                prompt + draft,
                max_tokens=1,
                temperature=temperature,
                top_p=top_p,
                echo=False,
            )
            next_token = output['choices'][0]['text']
            
            # Check if main model agrees with draft
            # This is simplified - real implementation compares probabilities
            return draft + next_token
        except Exception as e:
            logger.warning("Draft verification failed", error=str(e))
            return ""
    
    def _generate_main(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> str:
        """Generate using main model only."""
        try:
            output = self.main_model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                echo=False,
            )
            return output['choices'][0]['text']
        except Exception as e:
            logger.error("Main model generation failed", error=str(e))
            return ""
    
    def get_stats(self) -> Dict[str, Any]:
        """Get speculative decoding statistics."""
        return dict(self._stats)


# ============================================================================
# Performance Profiler
# ============================================================================

@dataclass
class ProfileResult:
    """Performance profiling result."""
    function_name: str
    total_calls: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    memory_delta_mb: float
    tokens_per_second: Optional[float] = None


class PerformanceProfiler:
    """Profile model inference performance."""
    
    def __init__(self):
        self._profiles: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()
    
    def profile(self, func_name: str = None):
        """Decorator to profile a function."""
        def decorator(func: Callable) -> Callable:
            name = func_name or f"{func.__module__}.{func.__qualname__}"
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                start_mem = psutil.Process().memory_info().rss / 1024 / 1024
                
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    end_time = time.perf_counter()
                    end_mem = psutil.Process().memory_info().rss / 1024 / 1024
                    
                    duration_ms = (end_time - start_time) * 1000
                    mem_delta = end_mem - start_mem
                    
                    with self._lock:
                        if name not in self._profiles:
                            self._profiles[name] = []
                        self._profiles[name].append({
                            "duration_ms": duration_ms,
                            "memory_delta_mb": mem_delta,
                            "timestamp": time.time(),
                        })
                        
                        # Keep only last 1000 entries
                        if len(self._profiles[name]) > 1000:
                            self._profiles[name] = self._profiles[name][-1000:]
            
            return wrapper
        return decorator
    
    def get_profile(self, func_name: str) -> Optional[ProfileResult]:
        """Get profile statistics for a function."""
        with self._lock:
            if func_name not in self._profiles:
                return None
            
            data = self._profiles[func_name]
            durations = [d["duration_ms"] for d in data]
            memory_deltas = [d["memory_delta_mb"] for d in data]
            
            return ProfileResult(
                function_name=func_name,
                total_calls=len(data),
                total_time_ms=sum(durations),
                avg_time_ms=sum(durations) / len(durations),
                min_time_ms=min(durations),
                max_time_ms=max(durations),
                memory_delta_mb=sum(memory_deltas) / len(memory_deltas),
            )
    
    def get_all_profiles(self) -> Dict[str, ProfileResult]:
        """Get all profile statistics."""
        return {name: self.get_profile(name) for name in self._profiles}
    
    def clear(self):
        """Clear all profiles."""
        with self._lock:
            self._profiles.clear()


# ============================================================================
# Benchmarking
# ============================================================================

@dataclass
class BenchmarkConfig:
    """Benchmark configuration."""
    prompt: str = "Explain quantum computing in simple terms."
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.95
    num_runs: int = 10
    warmup_runs: int = 2


@dataclass
class BenchmarkResult:
    """Benchmark result."""
    config: BenchmarkConfig
    avg_latency_ms: float
    avg_tokens_per_second: float
    peak_memory_mb: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    success_rate: float
    errors: List[str]


def benchmark_model(
    generate_func: Callable,
    config: BenchmarkConfig = None,
) -> BenchmarkResult:
    """Benchmark model inference performance."""
    config = config or BenchmarkConfig()
    
    latencies = []
    token_counts = []
    memory_usage = []
    errors = []
    
    # Warmup
    for _ in range(config.warmup_runs):
        try:
            generate_func(config.prompt, config.max_tokens, config.temperature, config.top_p)
        except Exception:
            pass
    
    # Benchmark runs
    for i in range(config.num_runs):
        start_mem = psutil.Process().memory_info().rss / 1024 / 1024
        start_time = time.perf_counter()
        
        try:
            result = generate_func(
                config.prompt,
                config.max_tokens,
                config.temperature,
                config.top_p,
            )
            
            end_time = time.perf_counter()
            end_mem = psutil.Process().memory_info().rss / 1024 / 1024
            
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)
            memory_usage.append(end_mem)
            
            # Estimate tokens
            tokens = len(result.split()) * 1.3
            token_counts.append(tokens)
            
        except Exception as e:
            errors.append(f"Run {i}: {str(e)}")
    
    if not latencies:
        return BenchmarkResult(
            config=config,
            avg_latency_ms=0,
            avg_tokens_per_second=0,
            peak_memory_mb=0,
            p50_latency_ms=0,
            p95_latency_ms=0,
            p99_latency_ms=0,
            success_rate=0,
            errors=errors,
        )
    
    # Calculate statistics
    latencies.sort()
    n = len(latencies)
    
    avg_latency = sum(latencies) / n
    avg_tokens = sum(token_counts) / n if token_counts else 0
    avg_tps = (avg_tokens / avg_latency) * 1000 if avg_latency > 0 else 0
    
    p50 = latencies[n // 2]
    p95 = latencies[int(n * 0.95)]
    p99 = latencies[int(n * 0.99)]
    
    return BenchmarkResult(
        config=config,
        avg_latency_ms=avg_latency,
        avg_tokens_per_second=avg_tps,
        peak_memory_mb=max(memory_usage) if memory_usage else 0,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        success_rate=len(latencies) / config.num_runs,
        errors=errors,
    )


# ============================================================================
# Global Instances
# ============================================================================

_kv_cache_manager: Optional[KVCacheManager] = None
_performance_profiler: Optional[PerformanceProfiler] = None


def get_kv_cache_manager(max_size_mb: float = 1024) -> KVCacheManager:
    """Get global KV cache manager."""
    global _kv_cache_manager
    if _kv_cache_manager is None:
        _kv_cache_manager = KVCacheManager(max_size_mb)
    return _kv_cache_manager


def get_performance_profiler() -> PerformanceProfiler:
    """Get global performance profiler."""
    global _performance_profiler
    if _performance_profiler is None:
        _performance_profiler = PerformanceProfiler()
    return _performance_profiler


# ============================================================================
# Integration with Cognitive Model Adapter
# ============================================================================

def create_optimized_local_adapter(
    model_path: str,
    prefer_speed: bool = True,
) -> Tuple[Any, LlamaCppConfig]:
    """Create optimized LocalLLMAdapter with performance config."""
    from JAYA_CORE.src.ai_connectors.local_llm_adapter import LocalLLMAdapter
    
    model_file = Path(model_path)
    available_ram = psutil.virtual_memory().total / (1024 ** 3)
    
    # Try to detect GPU VRAM
    gpu_vram = 0
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_vram = max(g.memoryTotal for g in gpus) / 1024  # GB
    except Exception:
        pass
    
    config = get_optimal_llama_config(
        model_file,
        available_ram,
        gpu_vram,
        prefer_speed,
    )
    
    adapter = LocalLLMAdapter(
        model_path=model_path,
        n_ctx=config.n_ctx,
        n_threads=config.n_threads,
        n_gpu_layers=config.n_gpu_layers,
        n_batch=config.n_batch,
        verbose=config.verbose,
    )
    
    # Apply optimizations
    if adapter.model:
        apply_llama_optimizations(adapter.model, config)
    
    return adapter, config