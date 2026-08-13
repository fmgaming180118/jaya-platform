"""
Observability Package for JAYA_CORE.

Provides structured logging, Prometheus metrics, and distributed tracing.
"""

from __future__ import annotations

from .structured_logging import (
    StructuredLogger,
    StructuredFormatter,
    LogContext,
    setup_structured_logging,
    get_structured_logger,
    log_performance,
    request_id_var,
    session_id_var,
    user_id_var,
    trace_id_var,
    span_id_var,
)

from .prometheus_metrics import (
    get_registry,
    start_metrics_server,
    get_metrics,
    get_metrics_text,
    start_periodic_collection,
    stop_periodic_collection,
    record_request,
    record_model_inference,
    record_error,
    record_intent_classification,
    record_tool_usage,
    record_narrative_event,
    record_episodic_event,
    record_twin_feedback,
    update_memory_metrics,
    update_gpu_metrics,
    update_component_health,
    update_model_availability,
    track_request,
    track_model_inference,
    MetricLabels,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    MODEL_INFERENCE_COUNT,
    MODEL_INFERENCE_LATENCY,
    ERROR_COUNT,
)

from .distributed_tracing import (
    init_tracing,
    get_tracer,
    start_span,
    trace_function,
    inject_context,
    extract_context,
    use_context,
    shutdown_tracing,
    trace_model_inference,
    trace_intent_classification,
    trace_tool_execution,
    trace_memory_operation,
    trace_twin_feedback,
    SpanAttributes,
    get_current_trace_id,
    get_current_span_id,
    OTEL_AVAILABLE,
)

__all__ = [
    # Structured Logging
    "StructuredLogger",
    "StructuredFormatter",
    "LogContext",
    "setup_structured_logging",
    "get_structured_logger",
    "log_performance",
    "request_id_var",
    "session_id_var",
    "user_id_var",
    "trace_id_var",
    "span_id_var",
    
    # Prometheus Metrics
    "get_registry",
    "start_metrics_server",
    "get_metrics",
    "get_metrics_text",
    "start_periodic_collection",
    "stop_periodic_collection",
    "record_request",
    "record_model_inference",
    "record_error",
    "record_intent_classification",
    "record_tool_usage",
    "record_narrative_event",
    "record_episodic_event",
    "record_twin_feedback",
    "update_memory_metrics",
    "update_gpu_metrics",
    "update_component_health",
    "update_model_availability",
    "track_request",
    "track_model_inference",
    "MetricLabels",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "MODEL_INFERENCE_COUNT",
    "MODEL_INFERENCE_LATENCY",
    "ERROR_COUNT",
    
    # Distributed Tracing
    "init_tracing",
    "get_tracer",
    "start_span",
    "trace_function",
    "inject_context",
    "extract_context",
    "use_context",
    "shutdown_tracing",
    "trace_model_inference",
    "trace_intent_classification",
    "trace_tool_execution",
    "trace_memory_operation",
    "trace_twin_feedback",
    "SpanAttributes",
    "get_current_trace_id",
    "get_current_span_id",
    "OTEL_AVAILABLE",
]


def init_observability(
    service_name: str = "jaya-core",
    log_level: int = 20,  # logging.INFO
    json_logs: bool = True,
    log_file: str = None,
    metrics_port: int = 9090,
    jaeger_endpoint: str = None,
    zipkin_endpoint: str = None,
    otlp_endpoint: str = None,
    console_tracing: bool = False,
) -> dict:
    """
    Initialize all observability components.
    
    Returns:
        Dict with initialization status for each component
    """
    import logging
    
    results = {}
    
    # 1. Structured Logging
    try:
        setup_structured_logging(level=log_level, json_output=json_logs, log_file=log_file)
        results["structured_logging"] = True
    except Exception as e:
        results["structured_logging"] = False
        results["structured_logging_error"] = str(e)
    
    # 2. Prometheus Metrics
    try:
        start_metrics_server(port=metrics_port)
        start_periodic_collection(interval_seconds=10.0)
        results["prometheus_metrics"] = True
    except Exception as e:
        results["prometheus_metrics"] = False
        results["prometheus_metrics_error"] = str(e)
    
    # 3. Distributed Tracing
    try:
        tracing_ok = init_tracing(
            service_name=service_name,
            jaeger_endpoint=jaeger_endpoint,
            zipkin_endpoint=zipkin_endpoint,
            otlp_endpoint=otlp_endpoint,
            console_export=console_tracing,
        )
        results["distributed_tracing"] = tracing_ok
    except Exception as e:
        results["distributed_tracing"] = False
        results["distributed_tracing_error"] = str(e)
    
    return results
