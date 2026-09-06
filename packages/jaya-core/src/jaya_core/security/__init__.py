"""
Security Package for JAYA_CORE.

Provides rate limiting, audit logging, input validation, and capability-based access control.
"""

from __future__ import annotations

from .hardening import (
    RateLimitConfig,
    TokenBucketRateLimiter,
    SlidingWindowRateLimiter,
    RateLimiter,
    get_rate_limiter,
    rate_limit,
    RateLimitExceededError,
    AuditEvent,
    AuditLogger,
    get_audit_logger,
    init_audit_logging,
    InputValidator,
    Capability,
    CapabilityManager,
    get_capability_manager,
    require_capability,
    SecurityMiddleware,
    configure_default_security,
)

__all__ = [
    "RateLimitConfig",
    "TokenBucketRateLimiter",
    "SlidingWindowRateLimiter",
    "RateLimiter",
    "get_rate_limiter",
    "rate_limit",
    "RateLimitExceededError",
    "AuditEvent",
    "AuditLogger",
    "get_audit_logger",
    "init_audit_logging",
    "InputValidator",
    "Capability",
    "CapabilityManager",
    "get_capability_manager",
    "require_capability",
    "SecurityMiddleware",
    "configure_default_security",
]