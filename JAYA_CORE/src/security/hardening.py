"""
Security Hardening for JAYA_CORE.

Provides:
- Rate limiting for API endpoints and tool usage
- Audit logging for security-sensitive operations
- Capability-based access control
- Input validation and sanitization
"""

from __future__ import annotations

import hashlib
import logging
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set

from JAYA_CORE.src.observability import get_structured_logger, record_error

logger = get_structured_logger(__name__, component="security")


# ============================================================================
# Rate Limiting
# ============================================================================

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_window: int = 100
    window_seconds: float = 60.0
    burst_allowance: int = 10  # Additional requests allowed in burst


class TokenBucketRateLimiter:
    """Token bucket rate limiter with burst support."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = float(config.requests_per_window + config.burst_allowance)
        self.max_tokens = float(config.requests_per_window + config.burst_allowance)
        self.refill_rate = config.requests_per_window / config.window_seconds
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
    
    def try_consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def get_available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


class SlidingWindowRateLimiter:
    """Sliding window rate limiter for more precise limiting."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.requests: List[float] = []
        self._lock = threading.Lock()
    
    def try_consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens within sliding window."""
        with self._lock:
            now = time.monotonic()
            window_start = now - self.config.window_seconds
            
            # Remove old requests
            self.requests = [t for t in self.requests if t > window_start]
            
            # Check if we can allow more requests
            if len(self.requests) + tokens <= self.config.requests_per_window + self.config.burst_allowance:
                self.requests.extend([now] * tokens)
                return True
            return False
    
    def get_current_count(self) -> int:
        """Get current request count in window."""
        with self._lock:
            now = time.monotonic()
            window_start = now - self.config.window_seconds
            return len([t for t in self.requests if t > window_start])


class RateLimiter:
    """Multi-tenant rate limiter with different strategies."""
    
    def __init__(self):
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._configs: Dict[str, RateLimitConfig] = {}
        self._lock = threading.Lock()
    
    def configure(self, key: str, config: RateLimitConfig):
        """Configure rate limit for a key."""
        with self._lock:
            self._configs[key] = config
            self._limiters[key] = TokenBucketRateLimiter(config)
    
    def get_limiter(self, key: str) -> TokenBucketRateLimiter:
        """Get or create limiter for key."""
        with self._lock:
            if key not in self._limiters:
                config = self._configs.get(key, RateLimitConfig())
                self._limiters[key] = TokenBucketRateLimiter(config)
            return self._limiters[key]
    
    def try_consume(self, key: str, tokens: int = 1) -> bool:
        """Try to consume tokens for key."""
        limiter = self.get_limiter(key)
        return limiter.try_consume(tokens)
    
    def get_status(self, key: str) -> Dict[str, Any]:
        """Get rate limit status for key."""
        limiter = self.get_limiter(key)
        return {
            "available_tokens": limiter.get_available_tokens(),
            "max_tokens": limiter.max_tokens,
            "refill_rate": limiter.refill_rate,
        }


# Global rate limiter instance
_global_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    return _global_rate_limiter


def rate_limit(key: str, tokens: int = 1):
    """Decorator for rate limiting function calls."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            if not limiter.try_consume(key, tokens):
                record_error("rate_limiter", "RateLimitExceeded", key)
                raise RateLimitExceededError(f"Rate limit exceeded for {key}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""
    pass


# ============================================================================
# Audit Logging
# ============================================================================

@dataclass
class AuditEvent:
    """Structured audit event."""
    timestamp: float
    event_type: str
    actor: str  # user_id, service_name, or "system"
    action: str
    resource: str
    resource_id: Optional[str] = None
    outcome: str = "success"  # success, failure, denied
    details: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"  # low, medium, high, critical
    trace_id: Optional[str] = None
    session_id: Optional[str] = None


class AuditLogger:
    """Security audit logger with structured output."""
    
    # Event types that should always be audited
    MANDATORY_AUDIT_EVENTS = {
        "authentication", "authorization", "data_access", "data_modification",
        "config_change", "model_load", "model_unload", "tool_execution",
        "privilege_escalation", "secret_access", "export", "import",
    }
    
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file
        self._file_handler = None
        if log_file:
            self._setup_file_logging()
    
    def _setup_file_logging(self):
        """Setup file handler for audit logs."""
        import logging.handlers
        self._file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10,
            encoding="utf-8",
        )
        self._file_handler.setFormatter(logging.Formatter("%(message)s"))
    
    def log(self, event: AuditEvent):
        """Log an audit event."""
        import json
        
        log_entry = {
            "timestamp": event.timestamp,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(event.timestamp)),
            "event_type": event.event_type,
            "actor": event.actor,
            "action": event.action,
            "resource": event.resource,
            "resource_id": event.resource_id,
            "outcome": event.outcome,
            "details": event.details,
            "risk_level": event.risk_level,
            "trace_id": event.trace_id,
            "session_id": event.session_id,
        }
        
        # Log to structured logger
        logger.info(
            "audit",
            f"Audit: {event.event_type}.{event.action}",
            extra_fields=log_entry,
        )
        
        # Also write to audit file if configured
        if self._file_handler:
            self._file_handler.stream.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            self._file_handler.flush()
    
    def log_authentication(self, actor: str, success: bool, details: Dict[str, Any] = None):
        """Log authentication event."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="authentication",
            actor=actor,
            action="login" if success else "login_failed",
            resource="auth",
            outcome="success" if success else "failure",
            details=details or {},
            risk_level="medium" if not success else "low",
        ))
    
    def log_authorization(self, actor: str, resource: str, action: str, allowed: bool, details: Dict[str, Any] = None):
        """Log authorization event."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="authorization",
            actor=actor,
            action=action,
            resource=resource,
            outcome="success" if allowed else "denied",
            details=details or {},
            risk_level="high" if not allowed else "low",
        ))
    
    def log_data_access(self, actor: str, resource: str, resource_id: str, action: str, details: Dict[str, Any] = None):
        """Log data access event."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="data_access",
            actor=actor,
            action=action,
            resource=resource,
            resource_id=resource_id,
            outcome="success",
            details=details or {},
            risk_level="medium",
        ))
    
    def log_tool_execution(self, actor: str, tool: str, skill: str, success: bool, details: Dict[str, Any] = None):
        """Log tool execution event."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="tool_execution",
            actor=actor,
            action="execute",
            resource=f"tool:{tool}",
            resource_id=skill,
            outcome="success" if success else "failure",
            details=details or {},
            risk_level="medium",
        ))
    
    def log_model_operation(self, actor: str, model: str, operation: str, success: bool, details: Dict[str, Any] = None):
        """Log model operation event."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="model_operation",
            actor=actor,
            action=operation,
            resource=f"model:{model}",
            outcome="success" if success else "failure",
            details=details or {},
            risk_level="low",
        ))
    
    def log_config_change(self, actor: str, config_key: str, old_value: Any, new_value: Any):
        """Log configuration change."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="config_change",
            actor=actor,
            action="update",
            resource=f"config:{config_key}",
            outcome="success",
            details={"old_value": str(old_value), "new_value": str(new_value)},
            risk_level="high",
        ))
    
    def log_secret_access(self, actor: str, secret_name: str, action: str):
        """Log secret access (always high risk)."""
        self.log(AuditEvent(
            timestamp=time.time(),
            event_type="secret_access",
            actor=actor,
            action=action,
            resource=f"secret:{secret_name}",
            outcome="success",
            details={},
            risk_level="critical",
        ))


# Global audit logger
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def init_audit_logging(log_file: Optional[str] = None):
    """Initialize audit logging with optional file output."""
    global _audit_logger
    _audit_logger = AuditLogger(log_file=log_file)
    return _audit_logger


# ============================================================================
# Input Validation & Sanitization
# ============================================================================

class InputValidator:
    """Input validation and sanitization utilities."""
    
    # Maximum lengths for different input types
    MAX_PROMPT_LENGTH = 10000
    MAX_CONTEXT_LENGTH = 50000
    MAX_FILE_PATH_LENGTH = 4096
    MAX_TOOL_PARAM_LENGTH = 10000
    
    # Dangerous patterns to detect
    DANGEROUS_PATTERNS = [
        r"(?i)(exec|eval|compile|subprocess|os\.system|shell)",
        r"(?i)(__import__|getattr|setattr|delattr)",
        r"(?i)(open\(|file\(|read\(|write\()",
        r"(?i)(rm\s+-rf|del\s+/|format\s+)",
        r"(?i)(drop\s+table|delete\s+from|truncate)",
        r"(?i)(union\s+select|insert\s+into|update\s+set)",
        r"(?i)(<script|javascript:|onerror=|onload=)",
    ]
    
    @classmethod
    def validate_prompt(cls, prompt: str) -> tuple[bool, Optional[str]]:
        """Validate user prompt."""
        if not prompt or not prompt.strip():
            return False, "Prompt cannot be empty"
        
        if len(prompt) > cls.MAX_PROMPT_LENGTH:
            return False, f"Prompt exceeds maximum length of {cls.MAX_PROMPT_LENGTH}"
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            import re
            if re.search(pattern, prompt):
                return False, f"Prompt contains potentially dangerous pattern"
        
        return True, None
    
    @classmethod
    def validate_file_path(cls, path: str, allowed_dirs: List[str] = None) -> tuple[bool, Optional[str]]:
        """Validate file path for safety."""
        if not path:
            return False, "Path cannot be empty"
        
        if len(path) > cls.MAX_FILE_PATH_LENGTH:
            return False, f"Path exceeds maximum length"
        
        # Check for path traversal
        import os
        normalized = os.path.normpath(path)
        if ".." in normalized.split(os.sep):
            return False, "Path traversal detected"
        
        # Check against allowed directories
        if allowed_dirs:
            allowed = False
            for allowed_dir in allowed_dirs:
                if normalized.startswith(os.path.normpath(allowed_dir)):
                    allowed = True
                    break
            if not allowed:
                return False, f"Path not in allowed directories"
        
        return True, None
    
    @classmethod
    def sanitize_for_logging(cls, data: Any) -> Any:
        """Sanitize data for safe logging."""
        if isinstance(data, str):
            # Truncate long strings
            if len(data) > 1000:
                return data[:1000] + "...[truncated]"
            return data
        elif isinstance(data, dict):
            return {k: cls.sanitize_for_logging(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize_for_logging(item) for item in data[:100]]  # Limit list size
        return data


# ============================================================================
# Capability-Based Access Control
# ============================================================================

@dataclass
class Capability:
    """Represents a capability grant."""
    name: str
    resource: str
    actions: Set[str] = field(default_factory=set)
    conditions: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[float] = None
    granted_by: str = "system"
    granted_at: float = field(default_factory=time.time)


class CapabilityManager:
    """Manages capability grants and verification."""
    
    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}  # key: "actor:capability_name"
        self._lock = threading.Lock()
    
    def grant(self, actor: str, capability: Capability) -> bool:
        """Grant a capability to an actor."""
        with self._lock:
            key = f"{actor}:{capability.name}"
            # Check if expired
            if capability.expires_at and capability.expires_at < time.time():
                return False
            self._capabilities[key] = capability
            return True
    
    def revoke(self, actor: str, capability_name: str) -> bool:
        """Revoke a capability from an actor."""
        with self._lock:
            key = f"{actor}:{capability_name}"
            if key in self._capabilities:
                del self._capabilities[key]
                return True
            return False
    
    def check(self, actor: str, capability_name: str, action: str = None, resource: str = None) -> bool:
        """Check if actor has capability."""
        with self._lock:
            key = f"{actor}:{capability_name}"
            capability = self._capabilities.get(key)
            
            if not capability:
                return False
            
            # Check expiration
            if capability.expires_at and capability.expires_at < time.time():
                del self._capabilities[key]
                return False
            
            # Check action
            if action and capability.actions and action not in capability.actions:
                return False
            
            # Check resource
            if resource and capability.resource != "*" and capability.resource != resource:
                return False
            
            # Check conditions
            for cond_key, cond_value in capability.conditions.items():
                # Custom condition evaluation would go here
                pass
            
            return True
    
    def get_capabilities(self, actor: str) -> List[Capability]:
        """Get all capabilities for an actor."""
        with self._lock:
            return [
                cap for key, cap in self._capabilities.items()
                if key.startswith(f"{actor}:")
            ]


# Global capability manager
_capability_manager: Optional[CapabilityManager] = None


def get_capability_manager() -> CapabilityManager:
    """Get global capability manager."""
    global _capability_manager
    if _capability_manager is None:
        _capability_manager = CapabilityManager()
    return _capability_manager


def require_capability(capability_name: str, action: str = None, resource: str = None):
    """Decorator to require a capability for function execution."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract actor from context (would need integration with auth system)
            actor = kwargs.get("_actor", "anonymous")
            
            manager = get_capability_manager()
            if not manager.check(actor, capability_name, action, resource):
                audit_logger = get_audit_logger()
                audit_logger.log_authorization(
                    actor=actor,
                    resource=resource or capability_name,
                    action=action or "execute",
                    allowed=False,
                    details={"function": func.__name__}
                )
                raise PermissionError(f"Capability required: {capability_name}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# Security Middleware Integration
# ============================================================================

class SecurityMiddleware:
    """Security middleware for request processing."""
    
    def __init__(
        self,
        rate_limiter: RateLimiter = None,
        audit_logger: AuditLogger = None,
        capability_manager: CapabilityManager = None,
        input_validator: InputValidator = None,
    ):
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.audit_logger = audit_logger or get_audit_logger()
        self.capability_manager = capability_manager or get_capability_manager()
        self.input_validator = input_validator or InputValidator()
    
    def process_request(
        self,
        actor: str,
        operation: str,
        resource: str,
        input_data: Any = None,
        required_capability: str = None,
    ) -> Dict[str, Any]:
        """Process request through security checks."""
        result = {
            "allowed": True,
            "errors": [],
            "warnings": [],
        }
        
        # 1. Rate limiting
        rate_key = f"{actor}:{operation}"
        if not self.rate_limiter.try_consume(rate_key):
            result["allowed"] = False
            result["errors"].append("Rate limit exceeded")
            self.audit_logger.log_authorization(
                actor=actor, resource=resource, action=operation, allowed=False
            )
            return result
        
        # 2. Input validation
        if input_data is not None:
            if isinstance(input_data, str):
                valid, error = self.input_validator.validate_prompt(input_data)
                if not valid:
                    result["allowed"] = False
                    result["errors"].append(f"Input validation failed: {error}")
        
        # 3. Capability check
        if required_capability:
            if not self.capability_manager.check(actor, required_capability, operation, resource):
                result["allowed"] = False
                result["errors"].append(f"Missing capability: {required_capability}")
                self.audit_logger.log_authorization(
                    actor=actor, resource=resource, action=operation, allowed=False
                )
                return result
        
        # 4. Audit log successful authorization
        self.audit_logger.log_authorization(
            actor=actor, resource=resource, action=operation, allowed=True
        )
        
        return result


# ============================================================================
# Default Security Configuration
# ============================================================================

def configure_default_security():
    """Configure default security policies."""
    limiter = get_rate_limiter()
    
    # Default rate limits
    limiter.configure("default", RateLimitConfig(requests_per_window=100, window_seconds=60))
    limiter.configure("model_inference", RateLimitConfig(requests_per_window=20, window_seconds=60))
    limiter.configure("tool_execution", RateLimitConfig(requests_per_window=50, window_seconds=60))
    limiter.configure("file_operation", RateLimitConfig(requests_per_window=30, window_seconds=60))
    limiter.configure("web_search", RateLimitConfig(requests_per_window=10, window_seconds=60))
    
    # Default capabilities
    manager = get_capability_manager()
    
    # Grant basic capabilities to authenticated users
    basic_caps = [
        Capability("chat", "model:*", {"generate", "chat"}),
        Capability("search", "tool:web_search", {"execute"}),
        Capability("file_read", "tool:file_ops", {"read"}),
        Capability("file_write", "tool:file_ops", {"write"}),
        Capability("system_info", "tool:system", {"get_status"}),
    ]
    
    for cap in basic_caps:
        manager.grant("authenticated_user", cap)
    
    # Admin capabilities
    admin_caps = [
        Capability("admin", "*", {"*"}),
        Capability("model_management", "model:*", {"load", "unload", "configure"}),
        Capability("config_management", "config:*", {"read", "write"}),
        Capability("audit_access", "audit:*", {"read"}),
    ]
    
    for cap in admin_caps:
        manager.grant("admin", cap)


# Initialize default security on import
configure_default_security()