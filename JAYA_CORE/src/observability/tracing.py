"""
tracing.py — Thread/Context-local Correlation ID Tracing for JAYA Core Observability.
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Optional

_CORRELATION_ID_VAR: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


class TraceContext:
    """Manages correlation ID context across request execution flows."""

    @staticmethod
    def get_correlation_id() -> str:
        corr_id = _CORRELATION_ID_VAR.get()
        if not corr_id:
            corr_id = f"corr-{uuid.uuid4().hex[:8]}"
            _CORRELATION_ID_VAR.set(corr_id)
        return corr_id

    @staticmethod
    def set_correlation_id(correlation_id: str) -> None:
        _CORRELATION_ID_VAR.set(correlation_id)

    @staticmethod
    def clear() -> None:
        _CORRELATION_ID_VAR.set(None)
