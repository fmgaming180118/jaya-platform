"""Fail-closed HTTP security building blocks for JAYA_RESEARCH."""

from .cors import CorsPolicy
from .errors import (
    HttpSecurityError,
    SecurityConfigurationError,
    redact_sensitive,
)
from .identity import (
    ApiKeyAuthenticator,
    ApiKeyCredential,
    ApiPrincipal,
    WorkspaceIdentity,
    request_principal,
    require_scope,
    require_workspace_identity,
    workspace_identity,
)
from .integration import (
    RuntimeHttpSecurity,
    authorize_research_request,
    runtime_http_security_from_environment,
)
from .middleware import HttpSecurityMiddleware, HttpSecurityPolicy
from .rate_limit import RateLimitDecision, TokenBucketRateLimiter

__all__ = [
    "ApiKeyAuthenticator",
    "ApiKeyCredential",
    "ApiPrincipal",
    "CorsPolicy",
    "HttpSecurityError",
    "HttpSecurityMiddleware",
    "HttpSecurityPolicy",
    "RateLimitDecision",
    "RuntimeHttpSecurity",
    "SecurityConfigurationError",
    "TokenBucketRateLimiter",
    "WorkspaceIdentity",
    "authorize_research_request",
    "redact_sensitive",
    "request_principal",
    "require_scope",
    "require_workspace_identity",
    "runtime_http_security_from_environment",
    "workspace_identity",
]
