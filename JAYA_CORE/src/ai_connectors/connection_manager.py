"""
Connection Manager for Jaya AI
Implements hierarchy: Local -> LAN -> Internet (with fallback)
"""

import logging
from typing import Any, Dict, Optional

from JAYA_CORE.src.protection.filters import filter_inbound, sanitize_outbound
from JAYA_CORE.src.soul.value_scoring import evaluate_intent_value

from .lan_sync_client import LANSyncClient
from .local_llm_adapter import LocalLLMAdapter
from .public_api_client import PublicAPIClient

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(
        self,
        local_model_path: str = "models/local_llm.gguf",
        lan_server_addr: Optional[str] = None,
        internet_allowed: bool = True,
        value_threshold: float = 0.5,
    ):
        """
        Initialize connection manager.
        :param local_model_path: Path to the local GGML/ONNX model.
        :param lan_server_addr: Address of LAN peer (e.g., laptop) for sync; None to disable.
        :param internet_allowed: Whether to allow internet fallback.
        :param value_threshold: Minimum soul value score to allow internet usage.
        """
        self.local_adapter = LocalLLMAdapter(model_path=local_model_path)
        self.lan_client = (
            LANSyncClient(server_addr=lan_server_addr) if lan_server_addr else None
        )
        self.internet_client = PublicAPIClient() if internet_allowed else None
        self.value_threshold = value_threshold

    def get_response(
        self, user_intent: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get a response for the user intent using the best available connection.
        :param user_intent: The user's expressed intent (natural language).
        :param context: Optional dict with extra context (e.g., location, time).
        :return: Response string (already filtered and value-checked).
        """
        ctx = context or {}
        # 1. Evaluate intent value to see if we are allowed to use external resources
        value_score = evaluate_intent_value(user_intent, ctx)
        allow_internet = value_score >= self.value_threshold
        logger.info(
            f"Intent value score: {value_score:.2f}, allow_internet: {allow_internet}"
        )

        # 2. Try local first (always allowed)
        try:
            local_resp = self.local_adapter.generate(user_intent, ctx)
            if local_resp and self._is_sufficient(local_resp, user_intent):
                logger.info("Using local response")
                return filter_inbound(local_resp)
        except Exception as e:
            logger.warning(f"Local adapter failed: {e}")

        # 3. Try LAN if available and allowed
        if self.lan_client:
            try:
                lan_resp = self.lan_client.query(user_intent, ctx)
                if lan_resp and self._is_sufficient(lan_resp, user_intent):
                    logger.info("Using LAN response")
                    return filter_inbound(lan_resp)
            except Exception as e:
                logger.warning(f"LAN client failed: {e}")

        # 4. Try internet if allowed and value permits
        if self.internet_client and allow_internet:
            try:
                # sanitize outbound request
                safe_intent = sanitize_outbound(user_intent)
                int_resp = self.internet_client.query(safe_intent, ctx)
                if int_resp and self._is_sufficient(int_resp, user_intent):
                    logger.info("Using internet response")
                    return filter_inbound(int_resp)
            except Exception as e:
                logger.warning(f"Internet client failed: {e}")

        # 5. Fallback: return a polite apology or cached response
        logger.warning("All sources failed; returning fallback.")
        return self._fallback_response(user_intent, ctx)

    def _is_sufficient(self, response: str, intent: str) -> bool:
        """Simple heuristic: non-empty and not just an error message."""
        if not response or len(response.strip()) < 5:
            return False
        lower = response.lower()
        if any(err in lower for err in ["error", "failed", "unavailable", "try again"]):
            return False
        return True

    def _fallback_response(self, intent: str, context: Dict[str, Any]) -> str:
        """Provide a safe fallback when no source could answer."""
        return ("Maaf, saya tidak dapat menemukan jawaban yang memuaskan saat ini. "
                "Anda bisa mencoba lagi nanti atau menyampaikan pertanyaan dengan cara lain.")
