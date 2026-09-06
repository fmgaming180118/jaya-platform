"""
Distributed Tracing for JAYA_CORE using OpenTelemetry.

Provides:
- Automatic trace context propagation
- Span creation for key operations
- Integration with structured logging
- Export to multiple backends (Jaeger, Zipkin, OTLP)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional, List

try:
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.zipkin.json import ZipkinExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    # Mock classes
    class _MockTracer:
        def start_span(self, *args, **kwargs): return _MockSpan()
        def start_as_current_span(self, *args, **kwargs): return _MockSpanContext()
    
    class _MockSpan:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def set_attribute(self, *args, **kwargs): pass
        def set_status(self, *args, **kwargs): pass
        def record_exception(self, *args, **kwargs): pass
        def end(self): pass
    
    class _MockSpanContext:
        def __enter__(self): return _MockSpan()
        def __exit__(self, *args): pass
    
    trace = type('trace', (), {
        'get_tracer': lambda *args: _MockTracer(),
        'get_current_span': lambda: _MockSpan(),
        'set_span_in_context': lambda *args: None,
        'SpanKind': type('SpanKind', (), {'INTERNAL': 'internal', 'SERVER': 'server', 'CLIENT': 'client'}),
        'Status': type('Status', (), {}),
        'StatusCode': type('StatusCode', (), {'OK': 'ok', 'ERROR': 'error'}),
    })()
    
    TracerProvider = BatchSpanProcessor = ConsoleSpanExporter = Resource = SERVICE_NAME = None
    JaegerExporter = ZipkinExporter = OTLPSpanExporter = None
    TraceContextTextMapPropagator = None
    LoggingInstrumentor = None


# Global tracer provider
_tracer_provider: Optional[TracerProvider] = None
_tracer = None


def init_tracing(
    service_name: str = "jaya-core",
    jaeger_endpoint: Optional[str] = None,
    zipkin_endpoint: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
    console_export: bool = False,
    sample_rate: float = 1.0,
) -> bool:
    """
    Initialize OpenTelemetry tracing.
    
    Args:
        service_name: Service name for traces
        jaeger_endpoint: Jaeger collector endpoint (e.g., "http://localhost:14268/api/traces")
        zipkin_endpoint: Zipkin endpoint (e.g., "http://localhost:9411/api/v2/spans")
        otlp_endpoint: OTLP endpoint (e.g., "http://localhost:4317")
        console_export: Export to console for debugging
        sample_rate: Trace sampling rate (0.0 to 1.0)
    
    Returns:
        True if tracing initialized successfully
    """
    global _tracer_provider, _tracer
    
    if not OTEL_AVAILABLE:
        print("OpenTelemetry not available, tracing disabled")
        return False
    
    try:
        # Create resource
        resource = Resource.create({
            SERVICE_NAME: service_name,
            "service.version": os.getenv("JAYA_VERSION", "dev"),
            "deployment.environment": os.getenv("JAYA_ENVIRONMENT", "development"),
        })
        
        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(_tracer_provider)
        
        # Add span processors
        if console_export:
            _tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
        
        if jaeger_endpoint:
            jaeger_exporter = JaegerExporter(
                agent_host_name=jaeger_endpoint.replace("http://", "").split(":")[0],
                agent_port=int(jaeger_endpoint.split(":")[-1]) if ":" in jaeger_endpoint else 6831,
            )
            _tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
        
        if zipkin_endpoint:
            zipkin_exporter = ZipkinExporter(endpoint=zipkin_endpoint)
            _tracer_provider.add_span_processor(BatchSpanProcessor(zipkin_exporter))
        
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        
        # Get tracer
        _tracer = trace.get_tracer(__name__)
        
        # Instrument logging
        LoggingInstrumentor().instrument(set_logging_format=True)
        
        print(f"OpenTelemetry tracing initialized for {service_name}")
        return True
        
    except Exception as e:
        print(f"Failed to initialize tracing: {e}")
        return False


def get_tracer(name: str = "jaya-core"):
    """Get a tracer instance."""
    if not OTEL_AVAILABLE:
        return trace.get_tracer(name)
    return trace.get_tracer(name)


# ============================================================================
# Span Helpers
# ============================================================================

@contextmanager
def start_span(
    name: str,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
    tracer_name: str = "jaya-core",
):
    """Context manager to start a span."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise
        else:
            span.set_status(trace.Status(trace.StatusCode.OK))


def trace_function(
    name: Optional[str] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
    tracer_name: str = "jaya-core",
):
    """Decorator to trace a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            span_name = name or f"{func.__module__}.{func.__qualname__}"
            with start_span(span_name, kind, attributes, tracer_name) as span:
                # Add function args as attributes (be careful with sensitive data)
                if attributes is None or "args" not in attributes:
                    span.set_attribute("function.name", func.__name__)
                    span.set_attribute("function.module", func.__module__)
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# Context Propagation
# ============================================================================

def inject_context(carrier: Dict[str, str]) -> Dict[str, str]:
    """Inject trace context into carrier (headers)."""
    if not OTEL_AVAILABLE:
        return carrier
    propagator = TraceContextTextMapPropagator()
    propagator.inject(carrier)
    return carrier


def extract_context(carrier: Dict[str, str]):
    """Extract trace context from carrier (headers)."""
    if not OTEL_AVAILABLE:
        return None
    propagator = TraceContextTextMapPropagator()
    return propagator.extract(carrier)


@contextmanager
def use_context(context):
    """Use extracted context as current context."""
    if not OTEL_AVAILABLE or context is None:
        yield
        return
    
    token = trace.set_span_in_context(trace.get_current_span(context))
    try:
        yield
    finally:
        trace.set_span_in_context(token)


# ============================================================================
# Common Span Attributes
# ============================================================================

class SpanAttributes:
    """Standard span attribute keys."""
    
    # HTTP
    HTTP_METHOD = "http.method"
    HTTP_URL = "http.url"
    HTTP_STATUS_CODE = "http.status_code"
    HTTP_USER_AGENT = "http.user_agent"
    
    # Database
    DB_SYSTEM = "db.system"
    DB_OPERATION = "db.operation"
    DB_STATEMENT = "db.statement"
    DB_NAME = "db.name"
    
    # Messaging
    MESSAGING_SYSTEM = "messaging.system"
    MESSAGING_DESTINATION = "messaging.destination"
    MESSAGING_OPERATION = "messaging.operation"
    
    # JAYA-specific
    JAYA_COMPONENT = "jaya.component"
    JAYA_OPERATION = "jaya.operation"
    JAYA_MODEL = "jaya.model"
    JAYA_PROVIDER = "jaya.provider"
    JAYA_INTENT = "jaya.intent"
    JAYA_SESSION_ID = "jaya.session_id"
    JAYA_REQUEST_ID = "jaya.request_id"
    JAYA_USER_ID = "jaya.user_id"
    JAYA_TOKENS_GENERATED = "jaya.tokens_generated"
    JAYA_DURATION_MS = "jaya.duration_ms"
    JAYA_ERROR_TYPE = "jaya.error_type"
    JAYA_ERROR_CODE = "jaya.error_code"


def set_jaya_attributes(span, **kwargs):
    """Set JAYA-specific attributes on a span."""
    for key, value in kwargs.items():
        if value is not None:
            span.set_attribute(key, value)


# ============================================================================
# Integration with Structured Logging
# ============================================================================

def get_current_trace_id() -> Optional[str]:
    """Get current trace ID for logging correlation."""
    if not OTEL_AVAILABLE:
        return None
    span = trace.get_current_span()
    if span and span.get_span_context():
        return format(span.get_span_context().trace_id, '032x')
    return None


def get_current_span_id() -> Optional[str]:
    """Get current span ID for logging correlation."""
    if not OTEL_AVAILABLE:
        return None
    span = trace.get_current_span()
    if span and span.get_span_context():
        return format(span.get_span_context().span_id, '016x')
    return None


# ============================================================================
# Pre-configured Span Context Managers
# ============================================================================

@contextmanager
def trace_model_inference(model: str, provider: str, operation: str = "generate"):
    """Trace model inference operation."""
    with start_span(
        f"model.{operation}",
        kind=trace.SpanKind.CLIENT,
        attributes={
            SpanAttributes.JAYA_COMPONENT: "cognitive_model",
            SpanAttributes.JAYA_OPERATION: operation,
            SpanAttributes.JAYA_MODEL: model,
            SpanAttributes.JAYA_PROVIDER: provider,
        },
    ) as span:
        yield span


@contextmanager
def trace_intent_classification(intent: str, confidence: float):
    """Trace intent classification."""
    with start_span(
        "intent.classify",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            SpanAttributes.JAYA_COMPONENT: "intent_engine",
            SpanAttributes.JAYA_OPERATION: "classify",
            SpanAttributes.JAYA_INTENT: intent,
            "jaya.confidence": confidence,
        },
    ) as span:
        yield span


@contextmanager
def trace_tool_execution(tool: str, skill: str):
    """Trace tool execution."""
    with start_span(
        f"tool.{tool}",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            SpanAttributes.JAYA_COMPONENT: "agent",
            SpanAttributes.JAYA_OPERATION: "execute_tool",
            "jaya.tool": tool,
            "jaya.skill": skill,
        },
    ) as span:
        yield span


@contextmanager
def trace_memory_operation(operation: str, memory_type: str):
    """Trace memory operation (narrative, episodic, working)."""
    with start_span(
        f"memory.{operation}",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            SpanAttributes.JAYA_COMPONENT: "memory",
            SpanAttributes.JAYA_OPERATION: operation,
            "jaya.memory_type": memory_type,
        },
    ) as span:
        yield span


@contextmanager
def trace_twin_feedback(task: str):
    """Trace twin feedback processing."""
    with start_span(
        "twin.feedback",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            SpanAttributes.JAYA_COMPONENT: "twin",
            SpanAttributes.JAYA_OPERATION: "feedback",
            "jaya.task": task,
        },
    ) as span:
        yield span


# ============================================================================
# Shutdown
# ============================================================================

def shutdown_tracing():
    """Shutdown tracer provider and flush spans."""
    global _tracer_provider
    if _tracer_provider and OTEL_AVAILABLE:
        _tracer_provider.shutdown()
        _tracer_provider = None