"""
Structured JSON Logging for JAYA_CORE.

Provides consistent, structured logging across all components with:
- JSON format for log aggregation
- Context enrichment (request_id, session_id, user_id)
- Privacy-aware logging (redacts sensitive fields)
- Performance metrics integration
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Context variables for request tracing
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)


@dataclass
class LogContext:
    """Structured log context."""
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    component: str = ""
    operation: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(cls, component: str = "", operation: str = "") -> "LogContext":
        """Create context from context variables."""
        return cls(
            request_id=request_id_var.get(),
            session_id=session_id_var.get(),
            user_id=user_id_var.get(),
            trace_id=trace_id_var.get(),
            span_id=span_id_var.get(),
            component=component,
            operation=operation,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "component": self.component,
            "operation": self.operation,
            **self.extra,
        }.items() if v is not None}


class StructuredFormatter(logging.Formatter):
    """JSON formatter with context enrichment and privacy redaction."""

    # Fields that should be redacted in logs
    SENSITIVE_FIELDS = {
        "password", "secret", "api_key", "token", "credential",
        "private_key", "ssn", "credit_card", "passport",
        "authorization", "cookie", "session_id", "csrf",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hostname = self._get_hostname()

    def _get_hostname(self) -> str:
        import socket
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _redact_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive fields from log data."""
        if not isinstance(data, dict):
            return data

        redacted = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_FIELDS):
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self._redact_sensitive(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted

    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "hostname": self.hostname,
            "process_id": record.process,
            "thread_id": record.thread,
        }

        # Add context from context variables
        context = LogContext.from_context()
        log_entry.update(context.to_dict())

        # Add extra fields from record
        if hasattr(record, "extra_fields"):
            log_entry.update(self._redact_sensitive(record.extra_fields))

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add performance metrics if present
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "memory_mb"):
            log_entry["memory_mb"] = record.memory_mb

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class StructuredLogger:
    """Wrapper for structured logging with context management."""

    def __init__(self, name: str, component: str = ""):
        self.logger = logging.getLogger(name)
        self.component = component

    def _log(self, level: int, message: str, **kwargs):
        """Internal log method with context."""
        operation = kwargs.pop("operation", "log")
        extra = {"extra_fields": kwargs}
        context = LogContext.from_context(component=self.component, operation=operation)
        extra["extra_fields"].update(context.to_dict())
        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    # Context managers for request/session tracing
    def with_request_id(self, request_id: str):
        """Context manager to set request_id."""
        return _ContextManager(request_id_var, request_id)

    def with_session_id(self, session_id: str):
        return _ContextManager(session_id_var, session_id)

    def with_user_id(self, user_id: str):
        return _ContextManager(user_id_var, user_id)

    def with_trace(self, trace_id: str, span_id: str):
        return _TraceContextManager(trace_id, span_id)


class _ContextManager:
    """Context manager for setting context variables."""

    def __init__(self, var: ContextVar, value: str):
        self.var = var
        self.value = value
        self.token = None

    def __enter__(self):
        self.token = self.var.set(self.value)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            self.var.reset(self.token)


class _TraceContextManager:
    """Context manager for distributed tracing."""

    def __init__(self, trace_id: str, span_id: str):
        self.trace_id = trace_id
        self.span_id = span_id
        self.trace_token = None
        self.span_token = None

    def __enter__(self):
        self.trace_token = trace_id_var.set(self.trace_id)
        self.span_token = span_id_var.set(self.span_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.trace_token:
            trace_id_var.reset(self.trace_token)
        if self.span_token:
            span_id_var.reset(self.span_token)


def setup_structured_logging(
    level: int = logging.INFO,
    json_output: bool = True,
    log_file: Optional[str] = None,
) -> None:
    """Configure structured logging for the application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if json_output:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_structured_logger(name: str, component: str = "") -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name, component)


# Performance logging decorator
def log_performance(logger: StructuredLogger, operation: str):
    """Decorator to log function performance."""
    def decorator(func):
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            start_memory = _get_memory_mb()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                end_memory = _get_memory_mb()
                logger.info(
                    operation,
                    f"{operation} completed",
                    duration_ms=round(duration_ms, 2),
                    memory_delta_mb=round(end_memory - start_memory, 2),
                    success=True,
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    operation,
                    f"{operation} failed: {e}",
                    duration_ms=round(duration_ms, 2),
                    error_type=type(e).__name__,
                    success=False,
                )
                raise
        return wrapper
    return decorator


def _get_memory_mb() -> float:
    """Get current process memory in MB."""
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0