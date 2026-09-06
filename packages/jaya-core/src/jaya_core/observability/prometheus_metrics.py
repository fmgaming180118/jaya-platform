"""
Prometheus Metrics Export for JAYA_CORE.

Provides standardized metrics for:
- Request/response latency and throughput
- Model inference performance
- Memory and resource usage
- Error rates and types
- Business metrics (intent classification, tool usage)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, Optional

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Summary,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        start_http_server,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mock classes for when prometheus_client is not available
    class _MockMetric:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def dec(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def time(self): return _MockTimer()
    
    class _MockTimer:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    Counter = Gauge = Histogram = Summary = _MockMetric
    CollectorRegistry = _MockMetric
    generate_latest = lambda *args: b""
    CONTENT_TYPE_LATEST = "text/plain"
    start_http_server = lambda *args, **kwargs: None


# Global registry
_registry: Optional[CollectorRegistry] = None


def get_registry() -> CollectorRegistry:
    """Get or create the global Prometheus registry."""
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry


# ============================================================================
# Metric Definitions
# ============================================================================

# --- Request/Response Metrics ---
REQUEST_COUNT = Counter(
    "jaya_requests_total",
    "Total number of requests processed",
    ["component", "operation", "status"],
    registry=get_registry(),
)

REQUEST_LATENCY = Histogram(
    "jaya_request_duration_seconds",
    "Request latency in seconds",
    ["component", "operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=get_registry(),
)

REQUEST_IN_FLIGHT = Gauge(
    "jaya_requests_in_flight",
    "Number of requests currently being processed",
    ["component", "operation"],
    registry=get_registry(),
)

# --- Model Inference Metrics ---
MODEL_INFERENCE_COUNT = Counter(
    "jaya_model_inference_total",
    "Total number of model inferences",
    ["model", "provider", "status"],
    registry=get_registry(),
)

MODEL_INFERENCE_LATENCY = Histogram(
    "jaya_model_inference_duration_seconds",
    "Model inference latency in seconds",
    ["model", "provider"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=get_registry(),
)

MODEL_TOKENS_GENERATED = Counter(
    "jaya_model_tokens_generated_total",
    "Total tokens generated",
    ["model", "provider"],
    registry=get_registry(),
)

MODEL_TOKENS_PER_SECOND = Gauge(
    "jaya_model_tokens_per_second",
    "Current tokens per second rate",
    ["model", "provider"],
    registry=get_registry(),
)

MODEL_LOAD_TIME = Histogram(
    "jaya_model_load_duration_seconds",
    "Model load time in seconds",
    ["model", "format"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=get_registry(),
)

# --- Memory & Resource Metrics ---
MEMORY_USAGE = Gauge(
    "jaya_memory_usage_bytes",
    "Current memory usage in bytes",
    ["type"],  # rss, vms, heap
    registry=get_registry(),
)

MEMORY_USAGE_PERCENT = Gauge(
    "jaya_memory_usage_percent",
    "Current memory usage as percentage of available",
    registry=get_registry(),
)

CPU_USAGE_PERCENT = Gauge(
    "jaya_cpu_usage_percent",
    "Current CPU usage percentage",
    registry=get_registry(),
)

GPU_MEMORY_USAGE = Gauge(
    "jaya_gpu_memory_usage_bytes",
    "GPU memory usage in bytes",
    ["device"],
    registry=get_registry(),
)

GPU_UTILIZATION = Gauge(
    "jaya_gpu_utilization_percent",
    "GPU utilization percentage",
    ["device"],
    registry=get_registry(),
)

# --- Cache Metrics ---
CACHE_HITS = Counter(
    "jaya_cache_hits_total",
    "Total cache hits",
    ["cache_name"],
    registry=get_registry(),
)

CACHE_MISSES = Counter(
    "jaya_cache_misses_total",
    "Total cache misses",
    ["cache_name"],
    registry=get_registry(),
)

CACHE_SIZE = Gauge(
    "jaya_cache_size",
    "Current cache size in entries",
    ["cache_name"],
    registry=get_registry(),
)

# --- Error Metrics ---
ERROR_COUNT = Counter(
    "jaya_errors_total",
    "Total errors by type",
    ["component", "error_type", "error_code"],
    registry=get_registry(),
)

# --- Business Metrics ---
INTENT_CLASSIFICATION_COUNT = Counter(
    "jaya_intent_classification_total",
    "Total intent classifications",
    ["intent", "confidence_bucket"],
    registry=get_registry(),
)

TOOL_USAGE_COUNT = Counter(
    "jaya_tool_usage_total",
    "Total tool invocations",
    ["tool", "skill", "status"],
    registry=get_registry(),
)

NARRATIVE_EVENTS = Counter(
    "jaya_narrative_events_total",
    "Total narrative events recorded",
    ["event_type"],
    registry=get_registry(),
)

EPISODIC_EVENTS = Counter(
    "jaya_episodic_events_total",
    "Total episodic memory events",
    ["event_type", "status"],
    registry=get_registry(),
)

TWIN_FEEDBACK_COUNT = Counter(
    "jaya_twin_feedback_total",
    "Total twin feedback received",
    ["task", "status"],
    registry=get_registry(),
)

# --- Health Metrics ---
COMPONENT_HEALTH = Gauge(
    "jaya_component_health",
    "Component health status (1=healthy, 0=unhealthy)",
    ["component"],
    registry=get_registry(),
)

MODEL_AVAILABILITY = Gauge(
    "jaya_model_availability",
    "Model availability (1=available, 0=unavailable)",
    ["model", "provider"],
    registry=get_registry(),
)


# ============================================================================
# Metric Helpers
# ============================================================================

@dataclass
class MetricLabels:
    """Standard labels for metrics."""
    component: str = "unknown"
    operation: str = "unknown"
    model: str = "unknown"
    provider: str = "unknown"
    cache_name: str = "default"
    tool: str = "unknown"
    skill: str = "unknown"
    intent: str = "unknown"
    event_type: str = "unknown"
    status: str = "success"
    error_type: str = "unknown"
    error_code: str = "unknown"
    task: str = "unknown"


def record_request(labels: MetricLabels, duration: float, success: bool = True):
    """Record request metrics."""
    status = "success" if success else "error"
    REQUEST_COUNT.labels(
        component=labels.component,
        operation=labels.operation,
        status=status,
    ).inc()
    REQUEST_LATENCY.labels(
        component=labels.component,
        operation=labels.operation,
    ).observe(duration)


def record_model_inference(
    model: str,
    provider: str,
    duration: float,
    tokens_generated: int = 0,
    success: bool = True,
):
    """Record model inference metrics."""
    status = "success" if success else "error"
    MODEL_INFERENCE_COUNT.labels(
        model=model,
        provider=provider,
        status=status,
    ).inc()
    MODEL_INFERENCE_LATENCY.labels(
        model=model,
        provider=provider,
    ).observe(duration)
    if tokens_generated > 0:
        MODEL_TOKENS_GENERATED.labels(
            model=model,
            provider=provider,
        ).inc(tokens_generated)
        if duration > 0:
            MODEL_TOKENS_PER_SECOND.labels(
                model=model,
                provider=provider,
            ).set(tokens_generated / duration)


def record_error(component: str, error_type: str, error_code: str = "unknown"):
    """Record error metric."""
    ERROR_COUNT.labels(
        component=component,
        error_type=error_type,
        error_code=error_code,
    ).inc()


def record_intent_classification(intent: str, confidence: float):
    """Record intent classification metric."""
    # Bucket confidence
    if confidence >= 0.9:
        bucket = "high"
    elif confidence >= 0.7:
        bucket = "medium"
    elif confidence >= 0.5:
        bucket = "low"
    else:
        bucket = "very_low"
    
    INTENT_CLASSIFICATION_COUNT.labels(
        intent=intent,
        confidence_bucket=bucket,
    ).inc()


def record_tool_usage(tool: str, skill: str, success: bool = True):
    """Record tool usage metric."""
    status = "success" if success else "error"
    TOOL_USAGE_COUNT.labels(
        tool=tool,
        skill=skill,
        status=status,
    ).inc()


def record_narrative_event(event_type: str):
    """Record narrative event metric."""
    NARRATIVE_EVENTS.labels(event_type=event_type).inc()


def record_episodic_event(event_type: str, success: bool = True):
    """Record episodic memory event metric."""
    status = "success" if success else "error"
    EPISODIC_EVENTS.labels(event_type=event_type, status=status).inc()


def record_twin_feedback(task: str, success: bool = True):
    """Record twin feedback metric."""
    status = "success" if success else "error"
    TWIN_FEEDBACK_COUNT.labels(task=task, status=status).inc()


def update_memory_metrics():
    """Update memory usage metrics."""
    try:
        import psutil
        process = psutil.Process()
        mem = process.memory_info()
        MEMORY_USAGE.labels(type="rss").set(mem.rss)
        MEMORY_USAGE.labels(type="vms").set(mem.vms)
        
        # System memory
        sys_mem = psutil.virtual_memory()
        MEMORY_USAGE_PERCENT.set(sys_mem.percent)
        CPU_USAGE_PERCENT.set(psutil.cpu_percent(interval=0.1))
    except Exception:
        pass


def update_gpu_metrics():
    """Update GPU metrics if available."""
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        for i, gpu in enumerate(gpus):
            GPU_MEMORY_USAGE.labels(device=f"gpu_{i}").set(gpu.memoryUsed * 1024 * 1024)
            GPU_UTILIZATION.labels(device=f"gpu_{i}").set(gpu.load * 100)
    except Exception:
        pass


def update_component_health(component: str, healthy: bool):
    """Update component health status."""
    COMPONENT_HEALTH.labels(component=component).set(1 if healthy else 0)


def update_model_availability(model: str, provider: str, available: bool):
    """Update model availability."""
    MODEL_AVAILABILITY.labels(model=model, provider=provider).set(1 if available else 0)


# ============================================================================
# Context Managers & Decorators
# ============================================================================

@contextmanager
def track_request(labels: MetricLabels):
    """Context manager to track request metrics."""
    REQUEST_IN_FLIGHT.labels(
        component=labels.component,
        operation=labels.operation,
    ).inc()
    start_time = time.perf_counter()
    success = True
    try:
        yield
    except Exception:
        success = False
        raise
    finally:
        duration = time.perf_counter() - start_time
        REQUEST_IN_FLIGHT.labels(
            component=labels.component,
            operation=labels.operation,
        ).dec()
        record_request(labels, duration, success)


def track_model_inference(model: str, provider: str):
    """Decorator to track model inference metrics."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            tokens = 0
            try:
                result = func(*args, **kwargs)
                # Try to extract token count from result
                if hasattr(result, 'usage') and result.usage:
                    tokens = getattr(result.usage, 'completion_tokens', 0)
                elif isinstance(result, dict) and 'usage' in result:
                    tokens = result['usage'].get('completion_tokens', 0)
                return result
            except Exception as e:
                record_model_inference(model, provider, time.perf_counter() - start_time, 0, False)
                raise
            finally:
                duration = time.perf_counter() - start_time
                record_model_inference(model, provider, duration, tokens, True)
        return wrapper
    return decorator


# ============================================================================
# HTTP Server for Metrics Export
# ============================================================================

def start_metrics_server(port: int = 9090, addr: str = "0.0.0.0"):
    """Start Prometheus metrics HTTP server."""
    if not PROMETHEUS_AVAILABLE:
        print("prometheus_client not available, metrics server not started")
        return
    
    try:
        start_http_server(port, addr=addr, registry=get_registry())
        print(f"Prometheus metrics server started on {addr}:{port}")
    except Exception as e:
        print(f"Failed to start metrics server: {e}")


def get_metrics() -> bytes:
    """Get current metrics in Prometheus format."""
    return generate_latest(get_registry())


def get_metrics_text() -> str:
    """Get current metrics as text."""
    return get_metrics().decode("utf-8")


# ============================================================================
# Periodic Metrics Collection
# ============================================================================

import threading

_metrics_thread: Optional[threading.Thread] = None
_metrics_stop_event: Optional[threading.Event] = None


def start_periodic_collection(interval_seconds: float = 10.0):
    """Start periodic metrics collection in background thread."""
    global _metrics_thread, _metrics_stop_event
    
    if _metrics_thread and _metrics_thread.is_alive():
        return
    
    _metrics_stop_event = threading.Event()
    
    def collect_loop():
        while not _metrics_stop_event.wait(interval_seconds):
            update_memory_metrics()
            update_gpu_metrics()
    
    _metrics_thread = threading.Thread(target=collect_loop, daemon=True)
    _metrics_thread.start()


def stop_periodic_collection():
    """Stop periodic metrics collection."""
    global _metrics_stop_event
    if _metrics_stop_event:
        _metrics_stop_event.set()


# ============================================================================
# Integration with Structured Logging
# ============================================================================

def log_metrics_summary(logger, interval_seconds: float = 60.0):
    """Log metrics summary periodically."""
    import threading
    
    def log_loop():
        while True:
            time.sleep(interval_seconds)
            try:
                # Log key metrics
                logger.info(
                    "metrics_summary",
                    "Periodic metrics summary",
                    # Note: Can't easily read counter values without prometheus_client internals
                    # This is a placeholder for custom summary logic
                )
            except Exception:
                pass
    
    thread = threading.Thread(target=log_loop, daemon=True)
    thread.start()