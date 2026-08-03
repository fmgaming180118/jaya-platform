"""
cognitive_model_adapter.py — Production LLM Integration for JAYA Cognitive Core.

Integrates LocalLLMAdapter (llama.cpp), PublicAPIClient, and HybridModelRouter
into a unified interface for the IronEngine to perform real cognitive inference.

STATUS: PRODUCTION ADAPTER - connects real LLMs to JAYA Core.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .local_llm_adapter import LocalLLMAdapter
from .public_api_client import PublicAPIClient
from JAYA_CORE.src.models.hybrid_router import HybridModelRouter, PrivacyPolicyLevel, RoutingTarget

logger = logging.getLogger(__name__)


@dataclass
class CognitiveResponse:
    """Structured response from cognitive model."""
    text: str
    source: str  # "local_llm", "cloud_api", "public_api", "fallback"
    model_used: str
    confidence: float
    metadata: Dict[str, Any]


class CognitiveModelAdapter:
    """
    Production adapter that routes cognitive requests to appropriate LLM backend.
    
    Integrates:
    - LocalLLMAdapter (llama.cpp GGUF) for offline/private inference
    - PublicAPIClient (Wikipedia/DuckDuckGo) for factual queries
    - HybridModelRouter for privacy-aware routing decisions
    
    Provides a unified interface for IronEngine to perform real cognitive tasks.
    """

    def __init__(
        self,
        local_model_path: str = "models/local_llm.gguf",
        n_ctx: int = 2048,
        n_threads: int = 4,
        enable_cloud: bool = True,
        privacy_level: PrivacyPolicyLevel = PrivacyPolicyLevel.HYBRID_ALLOWED,
    ):
        self.local_adapter = LocalLLMAdapter(
            model_path=local_model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
        )
        self.public_api = PublicAPIClient() if enable_cloud else None
        self.router = HybridModelRouter(
            default_local_model="local_gguf",
            default_cloud_model="cloud_reasoner",
        )
        self.privacy_level = privacy_level
        self._local_available = self.local_adapter.model is not None
        self._cloud_available = enable_cloud and self.public_api is not None

        logger.info(
            "CognitiveModelAdapter initialized: local=%s, cloud=%s, privacy=%s",
            self._local_available, self._cloud_available, privacy_level.value
        )

    def is_local_available(self) -> bool:
        return self._local_available

    def is_cloud_available(self) -> bool:
        return self._cloud_available

    def generate(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        force_local: bool = False,
        network_available: bool = True,
    ) -> CognitiveResponse:
        """
        Generate a cognitive response using the best available backend.
        
        Routing logic:
        1. If force_local or privacy requires local → LocalLLMAdapter
        2. If sensitive content detected → LocalLLMAdapter
        3. If factual query → PublicAPIClient (Wikipedia/DuckDuckGo)
        4. If cloud available and not sensitive → Cloud (via PublicAPIClient for now)
        5. Fallback → LocalLLMAdapter fallback or rule-based
        """
        ctx = context or {}
        
        # Check if prompt is sensitive
        is_sensitive = self.router.is_prompt_sensitive(prompt)
        
        # Route decision
        decision = self.router.route(
            prompt=prompt,
            privacy_level=self.privacy_level,
            network_available=network_available,
            force_local=force_local or is_sensitive,
        )
        
        logger.debug("Routing decision: target=%s, model=%s, reason=%s",
                     decision.target.value, decision.selected_model, decision.reason)

        # Execute based on routing
        if decision.target == RoutingTarget.LOCAL_EDGE:
            return self._generate_local(prompt, ctx, decision)
        
        elif decision.target == RoutingTarget.CLOUD_PROVIDER:
            # Try public API first for factual queries
            if self._is_factual_query(prompt):
                public_resp = self._try_public_api(prompt, ctx)
                if public_resp:
                    return public_resp
            
            # Fallback to local if cloud executor not available
            if self._cloud_available:
                return self._generate_cloud(prompt, ctx, decision)
            else:
                logger.warning("Cloud requested but not available, falling back to local")
                return self._generate_local(prompt, ctx, decision)
        
        else:
            return self._generate_local(prompt, ctx, decision)

    def _generate_local(
        self, 
        prompt: str, 
        context: Dict[str, Any], 
        decision
    ) -> CognitiveResponse:
        """Generate using local LLM (llama.cpp)."""
        if self._local_available:
            try:
                # Enrich prompt with context if available
                enriched_prompt = self._enrich_prompt(prompt, context)
                text = self.local_adapter.generate(enriched_prompt, context)
                
                if text and len(text.strip()) > 3:
                    return CognitiveResponse(
                        text=text.strip(),
                        source="local_llm",
                        model_used=os.path.basename(self.local_adapter.model_path),
                        confidence=0.8,
                        metadata={"routing_reason": decision.reason}
                    )
            except Exception as e:
                logger.error(f"Local LLM generation failed: {e}")
        
        # Fallback to rule-based
        fallback_text = self.local_adapter._fallback_generate(prompt, context)
        return CognitiveResponse(
            text=fallback_text,
            source="fallback_rule_based",
            model_used="rule_based_fallback",
            confidence=0.3,
            metadata={"routing_reason": decision.reason, "fallback": True}
        )

    def _generate_cloud(
        self, 
        prompt: str, 
        context: Dict[str, Any], 
        decision
    ) -> CognitiveResponse:
        """Generate using cloud provider (placeholder for future OpenAI/Ollama integration)."""
        # For now, use public API as cloud proxy
        public_resp = self._try_public_api(prompt, context)
        if public_resp:
            return public_resp
        
        # Ultimate fallback to local
        return self._generate_local(prompt, context, decision)

    def _try_public_api(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> Optional[CognitiveResponse]:
        """Try public API (Wikipedia/DuckDuckGo) for factual queries."""
        if not self.public_api:
            return None
        
        try:
            result = self.public_api.query(prompt, context)
            if result and len(result.strip()) > 10:
                return CognitiveResponse(
                    text=result.strip(),
                    source="public_api",
                    model_used="wikipedia/duckduckgo",
                    confidence=0.7,
                    metadata={"query_type": "factual"}
                )
        except Exception as e:
            logger.warning(f"Public API query failed: {e}")
        
        return None

    def _is_factual_query(self, prompt: str) -> bool:
        """Heuristic to detect factual queries suitable for public API."""
        factual_patterns = [
            "apa itu", "what is", "who is", "siapa", "kapan", "when",
            "dimana", "where", "berapa", "how many", "how much",
            "definisi", "definition", "artinya", "meaning",
            "sejarah", "history", "biografi", "biography",
        ]
        prompt_lower = prompt.lower()
        return any(pattern in prompt_lower for pattern in factual_patterns)

    def _enrich_prompt(self, prompt: str, context: Dict[str, Any]) -> str:
        """Enrich prompt with context for better LLM responses."""
        if not context:
            return prompt
        
        enrichment = []
        if "user_name" in context:
            enrichment.append(f"User: {context['user_name']}")
        if "current_time" in context:
            enrichment.append(f"Time: {context['current_time']}")
        if "location" in context:
            enrichment.append(f"Location: {context['location']}")
        if "conversation_history" in context:
            history = context["conversation_history"]
            if isinstance(history, list) and history:
                enrichment.append("Recent context: " + " | ".join(str(h) for h in history[-3:]))
        
        if enrichment:
            return f"[Context: {'; '.join(enrichment)}]\nUser: {prompt}"
        return prompt

    def chat(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveResponse:
        """
        Multi-turn chat interface.
        Converts message history to a single prompt for current backends.
        """
        # Simple conversion: concatenate messages
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        full_prompt = "\n".join(prompt_parts) + "\nAssistant:"
        return self.generate(full_prompt, context)

    def get_status(self) -> Dict[str, Any]:
        """Get adapter status for health checks."""
        return {
            "local_llm": {
                "available": self._local_available,
                "model_path": self.local_adapter.model_path if self._local_available else None,
                "n_ctx": self.local_adapter.n_ctx,
                "n_threads": self.local_adapter.n_threads,
            },
            "public_api": {
                "available": self._cloud_available,
            },
            "router": {
                "privacy_level": self.privacy_level.value,
                "sensitive_keywords": list(self.router.SENSITIVE_KEYWORDS),
            },
        }


def create_cognitive_adapter_from_env() -> CognitiveModelAdapter:
    """Factory to create adapter from environment variables."""
    model_path = os.getenv("JAYA_LOCAL_MODEL_PATH", "models/local_llm.gguf")
    n_ctx = int(os.getenv("JAYA_MODEL_N_CTX", "2048"))
    n_threads = int(os.getenv("JAYA_MODEL_N_THREADS", "4"))
    enable_cloud = os.getenv("JAYA_ENABLE_CLOUD", "true").lower() == "true"
    privacy_str = os.getenv("JAYA_PRIVACY_LEVEL", "HYBRID_ALLOWED")
    privacy_level = PrivacyPolicyLevel(privacy_str)
    
    return CognitiveModelAdapter(
        local_model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        enable_cloud=enable_cloud,
        privacy_level=privacy_level,
    )