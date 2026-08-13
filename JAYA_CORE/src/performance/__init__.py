"""
Performance Package for JAYA_CORE.

Provides llama.cpp optimization, KV cache management, speculative decoding, and benchmarking.
"""

from __future__ import annotations

from .optimization import (
    LlamaCppConfig,
    get_optimal_llama_config,
    apply_llama_optimizations,
    KVCacheStats,
    KVCacheManager,
    get_kv_cache_manager,
    SpeculativeConfig,
    SpeculativeDecoder,
    PerformanceProfiler,
    get_performance_profiler,
    ProfileResult,
    BenchmarkConfig,
    BenchmarkResult,
    benchmark_model,
    create_optimized_local_adapter,
)

__all__ = [
    "LlamaCppConfig",
    "get_optimal_llama_config",
    "apply_llama_optimizations",
    "KVCacheStats",
    "KVCacheManager",
    "get_kv_cache_manager",
    "SpeculativeConfig",
    "SpeculativeDecoder",
    "PerformanceProfiler",
    "get_performance_profiler",
    "ProfileResult",
    "BenchmarkConfig",
    "BenchmarkResult",
    "benchmark_model",
    "create_optimized_local_adapter",
]