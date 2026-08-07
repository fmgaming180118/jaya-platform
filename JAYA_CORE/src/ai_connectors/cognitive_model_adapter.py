"""
cognitive_model_adapter.py — Production LLM Integration for JAYA Cognitive Core.

Integrates LocalLLMAdapter (llama.cpp), PublicAPIClient, CloudLLMAdapter,
and HybridModelRouter into a unified interface for the IronEngine to perform
real cognitive inference.

STATUS: PRODUCTION ADAPTER - connects real LLMs to JAYA Core.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .local_llm_adapter import LocalLLMAdapter
from .public_api_client import PublicAPIClient
from .cloud_llm_adapter import CloudLLMAdapter, CloudLLMConfig, create_cloud_adapter_from_env
from JAYA_CORE.src.models.hybrid_router import HybridModelRouter, PrivacyPolicyLevel, RoutingTarget
from JAYA_CORE.src.observability import (
    get_structured_logger,
    record_model_inference,
    record_error,
    trace_model_inference,
    SpanAttributes,
)
from JAYA_CORE.src.security import (
    get_rate_limiter,
    get_audit_logger,
    InputValidator,
)

logger = get_structured_logger(__name__, component="cognitive_model_adapter")


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
        cloud_configs: Optional[List[CloudLLMConfig]] = None,
        cloud_default_provider: str = "openai",
    ):
        self.local_adapter = LocalLLMAdapter(
            model_path=local_model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
        )
        self.public_api = PublicAPIClient() if enable_cloud else None
        self.cloud_adapter = create_cloud_adapter_from_env() if enable_cloud else None
        if cloud_configs and enable_cloud:
            # Override with explicit configs if provided
            self.cloud_adapter = CloudLLMAdapter(
                configs=cloud_configs,
                default_provider=cloud_default_provider,
            )
        self.router = HybridModelRouter(
            default_local_model="local_gguf",
            default_cloud_model="cloud_reasoner",
        )
        self.privacy_level = privacy_level
        self._local_available = self.local_adapter.model is not None
        self._cloud_available = enable_cloud and (
            self.public_api is not None or 
            (self.cloud_adapter and self.cloud_adapter.get_available_providers())
        )

        logger.info(
            "CognitiveModelAdapter initialized",
            local=self._local_available,
            cloud=self._cloud_available,
            privacy=privacy_level.value,
            cloud_providers=self.cloud_adapter.get_available_providers() if self.cloud_adapter else []
        )

    def is_local_available(self) -> bool:
        return self._local_available

    def is_cloud_available(self) -> bool:
        return self._cloud_available

    def has_local_reasoning_provider(self) -> bool:
        return self._local_available

    def has_cloud_reasoning_provider(self) -> bool:
        return self.cloud_adapter is not None and bool(self.cloud_adapter.get_available_providers())

    def has_reasoning_provider(self) -> bool:
        """
        Check if a real reasoning provider is available.
        Public search (Wikipedia/DuckDuckGo) is NOT a reasoning provider.
        """
        return self.has_local_reasoning_provider() or self.has_cloud_reasoning_provider()

    def generate(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        force_local: bool = False,
        network_available: bool = True,
        actor: str = "anonymous",
        temperature: Optional[float] = None,
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
        # Input validation
        valid, error = InputValidator.validate_prompt(prompt)
        if not valid:
            record_error("cognitive_model_adapter", "ValidationError", "invalid_prompt")
            return CognitiveResponse(
                text=f"Input validation failed: {error}",
                source="error",
                model_used="none",
                confidence=0.0,
                metadata={"error": error}
            )
        
        # Rate limiting
        rate_limiter = get_rate_limiter()
        if not rate_limiter.try_consume(f"{actor}:model_inference"):
            record_error("cognitive_model_adapter", "RateLimitExceeded", "model_inference")
            get_audit_logger().log_authorization(
                actor=actor, resource="model_inference", action="generate", allowed=False
            )
            return CognitiveResponse(
                text="Rate limit exceeded. Please try again later.",
                source="error",
                model_used="none",
                confidence=0.0,
                metadata={"error": "rate_limit_exceeded"}
            )
        
        # Audit log
        get_audit_logger().log_model_operation(actor, "cognitive_model", "generate", True)
        
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
        
        logger.debug("Routing decision", target=decision.target.value, model=decision.selected_model, reason=decision.reason)

        # Execute based on routing
        if decision.target == RoutingTarget.LOCAL_EDGE:
            return self._generate_local(prompt, ctx, decision, temperature=temperature)
        
        elif decision.target == RoutingTarget.CLOUD_PROVIDER:
            # Try public API first for factual queries
            if self._is_factual_query(prompt):
                public_resp = self._try_public_api(prompt, ctx)
                if public_resp:
                    return public_resp
            
            # Fallback to local if cloud executor not available
            if self._cloud_available:
                return self._generate_cloud(prompt, ctx, decision, temperature=temperature)
            else:
                logger.warning("Cloud requested but not available, falling back to local")
                return self._generate_local(prompt, ctx, decision, temperature=temperature)
        
        else:
            return self._generate_local(prompt, ctx, decision, temperature=temperature)

    def _generate_local(
        self, 
        prompt: str, 
        context: Dict[str, Any], 
        decision,
        temperature: Optional[float] = None,
    ) -> CognitiveResponse:
        """Generate using local LLM (llama.cpp)."""
        model_name = os.path.basename(self.local_adapter.model_path) if self._local_available else "none"
        
        start_time = time.perf_counter()
        try:
            with trace_model_inference(model_name, "local", "generate") as span:
                if self._local_available:
                    # Enrich prompt with context if available
                    enriched_prompt = self._enrich_prompt(prompt, context)
                    gen_kwargs = {"context": context}
                    if temperature is not None:
                        gen_kwargs["temperature"] = temperature
                    text = self.local_adapter.generate(enriched_prompt, **gen_kwargs)
                    
                    if text and len(text.strip()) > 3:
                        duration = time.perf_counter() - start_time
                        # Estimate tokens (rough approximation)
                        tokens = len(text.split()) * 1.3
                        record_model_inference(model_name, "local", duration, int(tokens), True)
                        span.set_attribute(SpanAttributes.JAYA_TOKENS_GENERATED, int(tokens))
                        span.set_attribute(SpanAttributes.JAYA_DURATION_MS, duration * 1000)
                        
                        return CognitiveResponse(
                            text=text.strip(),
                            source="local_llm",
                            model_used=model_name,
                            confidence=0.8,
                            metadata={"routing_reason": decision.reason}
                        )
        except Exception as e:
            duration = time.perf_counter() - start_time
            record_model_inference(model_name, "local", duration, 0, False)
            record_error("cognitive_model_adapter", type(e).__name__, "local_generation_failed")
            logger.error("Local LLM generation failed", error=str(e))
        
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
        decision,
        temperature: Optional[float] = None,
    ) -> CognitiveResponse:
        """Generate using real cloud LLM provider."""
        if not self.cloud_adapter or not self.cloud_adapter.get_available_providers():
            logger.warning("Cloud adapter not available, falling back to public API or local")
            public_resp = self._try_public_api(prompt, context)
            if public_resp:
                return public_resp
            return self._generate_local(prompt, context, decision, temperature=temperature)

        # Get provider info for metrics
        providers = self.cloud_adapter.get_available_providers()
        provider = providers[0] if providers else "unknown"
        model = self.cloud_adapter.providers[provider].config.model if provider in self.cloud_adapter.providers else "unknown"

        start_time = time.perf_counter()
        try:
            with trace_model_inference(model, provider, "generate") as span:
                # Convert prompt to chat messages format
                messages = [{"role": "user", "content": prompt}]
                if context and "conversation_history" in context:
                    history = context["conversation_history"]
                    if isinstance(history, list):
                        for h in history[-5:]:  # Last 5 turns
                            if isinstance(h, dict) and "role" in h and "content" in h:
                                messages.insert(-1, h)

                # Run async generation in sync context
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                cloud_resp = loop.run_until_complete(
                    self.cloud_adapter.generate(messages, force_local=False)
                )

                duration = time.perf_counter() - start_time
                tokens = cloud_resp.usage.get("completion_tokens", 0) if cloud_resp.usage else 0
                
                # Record metrics
                record_model_inference(model, provider, duration, tokens, True)
                
                # Add span attributes
                span.set_attribute(SpanAttributes.JAYA_TOKENS_GENERATED, tokens)
                span.set_attribute(SpanAttributes.JAYA_DURATION_MS, duration * 1000)

                return CognitiveResponse(
                    text=cloud_resp.text,
                    source="cloud_llm",
                    model_used=f"{cloud_resp.provider}:{cloud_resp.model}",
                    confidence=0.85,
                    metadata={
                        "routing_reason": decision.reason,
                        "provider": cloud_resp.provider,
                        "latency_ms": cloud_resp.latency_ms,
                        "usage": cloud_resp.usage,
                    }
                )
        except Exception as e:
            duration = time.perf_counter() - start_time
            record_model_inference(model, provider, duration, 0, False)
            record_error("cognitive_model_adapter", type(e).__name__, "cloud_generation_failed")
            logger.error("Cloud LLM generation failed", error=str(e))
            # Fallback to public API then local
            public_resp = self._try_public_api(prompt, context)
            if public_resp:
                return public_resp
            return self._generate_local(prompt, context, decision)

    def _try_public_api(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> Optional[CognitiveResponse]:
        """Try public API (Wikipedia/DuckDuckGo) for factual queries."""
        if not self.public_api:
            return None
        
        start_time = time.perf_counter()
        try:
            with trace_model_inference("public_api", "wikipedia/duckduckgo", "query") as span:
                result = self.public_api.query(prompt, context)
                if result and len(result.strip()) > 10:
                    duration = time.perf_counter() - start_time
                    tokens = len(result.split()) * 1.3
                    record_model_inference("public_api", "wikipedia/duckduckgo", duration, int(tokens), True)
                    span.set_attribute(SpanAttributes.JAYA_TOKENS_GENERATED, int(tokens))
                    span.set_attribute(SpanAttributes.JAYA_DURATION_MS, duration * 1000)

                    return CognitiveResponse(
                        text=result.strip(),
                        source="public_api",
                        model_used="wikipedia/duckduckgo",
                        confidence=0.7,
                        metadata={"query_type": "factual"}
                    )
        except Exception as e:
            duration = time.perf_counter() - start_time
            record_model_inference("public_api", "wikipedia/duckduckgo", duration, 0, False)
            record_error("cognitive_model_adapter", type(e).__name__, "public_api_failed")
            logger.warning("Public API query failed", error=str(e))
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
        Uses cloud adapter directly if available for better conversation handling.
        """
        if self.cloud_adapter and self.cloud_adapter.get_available_providers():
            try:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                providers = self.cloud_adapter.get_available_providers()
                provider = providers[0] if providers else "unknown"
                model = self.cloud_adapter.providers[provider].config.model if provider in self.cloud_adapter.providers else "unknown"

                start_time = time.perf_counter()
                with trace_model_inference(model, provider, "chat") as span:
                    cloud_resp = loop.run_until_complete(
                        self.cloud_adapter.chat(messages)
                    )

                    duration = time.perf_counter() - start_time
                    tokens = cloud_resp.usage.get("completion_tokens", 0) if cloud_resp.usage else 0
                    record_model_inference(model, provider, duration, tokens, True)
                    span.set_attribute(SpanAttributes.JAYA_TOKENS_GENERATED, tokens)
                    span.set_attribute(SpanAttributes.JAYA_DURATION_MS, duration * 1000)

                    return CognitiveResponse(
                        text=cloud_resp.text,
                        source="cloud_llm",
                        model_used=f"{cloud_resp.provider}:{cloud_resp.model}",
                        confidence=0.85,
                        metadata={
                            "provider": cloud_resp.provider,
                            "latency_ms": cloud_resp.latency_ms,
                            "usage": cloud_resp.usage,
                        }
                    )
            except Exception as e:
                logger.warning("Cloud chat failed, falling back to generate", error=str(e))

        # Fallback: simple conversion to single prompt
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
        status = {
            "local_llm": {
                "available": self._local_available,
                "model_path": self.local_adapter.model_path if self._local_available else None,
                "n_ctx": self.local_adapter.config.n_ctx if hasattr(self.local_adapter, 'config') else 2048,
                "n_threads": self.local_adapter.config.n_threads if hasattr(self.local_adapter, 'config') else 4,
            },
            "public_api": {
                "available": self.public_api is not None,
            },
            "cloud_llm": {
                "available": self.cloud_adapter is not None and bool(self.cloud_adapter.get_available_providers()),
                "providers": self.cloud_adapter.get_provider_status() if self.cloud_adapter else {},
            },
            "router": {
                "privacy_level": self.privacy_level.value,
                "sensitive_keywords": list(self.router.SENSITIVE_KEYWORDS),
            },
        }
        return status


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