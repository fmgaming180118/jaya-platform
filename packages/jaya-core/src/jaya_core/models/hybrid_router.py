"""
hybrid_router.py — Privacy-Aware Local/Cloud Hybrid Model Router & Fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PrivacyPolicyLevel(str, Enum):
    STRICT_LOCAL_ONLY = "STRICT_LOCAL_ONLY"
    HYBRID_ALLOWED = "HYBRID_ALLOWED"
    ANONYMIZED_CLOUD_ALLOWED = "ANONYMIZED_CLOUD_ALLOWED"


class RoutingTarget(str, Enum):
    LOCAL_EDGE = "LOCAL_EDGE"
    CLOUD_PROVIDER = "CLOUD_PROVIDER"
    LOCAL_FALLBACK = "LOCAL_FALLBACK"


@dataclass
class HybridRoutingDecision:
    target: RoutingTarget
    selected_model: str
    reason: str
    privacy_level: PrivacyPolicyLevel
    fallback_available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.value,
            "selected_model": self.selected_model,
            "reason": self.reason,
            "privacy_level": self.privacy_level.value,
            "fallback_available": self.fallback_available,
        }


class HybridModelRouter:
    """Routes inference requests to Local Edge or Cloud based on privacy policies & offline constraints."""

    SENSITIVE_KEYWORDS = {"password", "secret", "private_key", "credential", "personal_id", "nik", "pin"}

    def __init__(self, default_local_model: str = "rule-based-edge-v1", default_cloud_model: str = "cloud-reasoner-v1") -> None:
        self.default_local_model = default_local_model
        self.default_cloud_model = default_cloud_model

    def is_prompt_sensitive(self, prompt: str) -> bool:
        p_lower = prompt.lower()
        return any(kw in p_lower for kw in self.SENSITIVE_KEYWORDS)

    def route(
        self,
        prompt: str,
        privacy_level: PrivacyPolicyLevel = PrivacyPolicyLevel.HYBRID_ALLOWED,
        network_available: bool = True,
        local_memory_mb: int = 1024,
        force_local: bool = False,
    ) -> HybridRoutingDecision:

        # 1. Strict Local / Forced Local / Offline -> LOCAL_EDGE
        if force_local or privacy_level == PrivacyPolicyLevel.STRICT_LOCAL_ONLY or not network_available:
            reason = "Offline mode or strict local privacy policy enforced"
            logger.info("Routing to LOCAL_EDGE: %s", reason)
            return HybridRoutingDecision(
                target=RoutingTarget.LOCAL_EDGE,
                selected_model=self.default_local_model,
                reason=reason,
                privacy_level=privacy_level,
                fallback_available=True,
            )

        # 2. Sensitive Keyword Check -> LOCAL_EDGE
        if self.is_prompt_sensitive(prompt):
            reason = "Sensitive prompt content detected, routing to local edge to prevent data leakage"
            logger.info("Routing to LOCAL_EDGE: %s", reason)
            return HybridRoutingDecision(
                target=RoutingTarget.LOCAL_EDGE,
                selected_model=self.default_local_model,
                reason=reason,
                privacy_level=privacy_level,
                fallback_available=True,
            )

        # 3. Hybrid Cloud Routing with explicit Local Fallback
        reason = "Prompt non-sensitive and network available; routing to cloud provider"
        logger.info("Routing to CLOUD_PROVIDER: %s", reason)
        return HybridRoutingDecision(
            target=RoutingTarget.CLOUD_PROVIDER,
            selected_model=self.default_cloud_model,
            reason=reason,
            privacy_level=privacy_level,
            fallback_available=True,
        )

    def execute_with_fallback(
        self,
        decision: HybridRoutingDecision,
        cloud_executor: Optional[callable] = None,
        local_executor: Optional[callable] = None,
    ) -> str:
        """Executes decision target; falls back to local executor if cloud execution fails."""
        if decision.target == RoutingTarget.CLOUD_PROVIDER and cloud_executor is not None:
            try:
                return cloud_executor()
            except Exception as exc:
                logger.warning("Cloud execution failed (%s), triggering LOCAL_FALLBACK", exc)
                if local_executor:
                    return local_executor()
                return "LOCAL_FALLBACK_DEFAULT_RESPONSE"

        if local_executor:
            return local_executor()
        return "LOCAL_EDGE_DEFAULT_RESPONSE"
