"""
test_cognitive_model_adapter.py — Unit tests for CognitiveModelAdapter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-core" / "src"))

from jaya_core.ai_connectors.cognitive_model_adapter import CognitiveModelAdapter, CognitiveResponse
from jaya_core.models.hybrid_router import PrivacyPolicyLevel


class TestCognitiveModelAdapter:
    def test_adapter_initialization(self):
        """Test adapter initializes with correct defaults."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/test.gguf",
            enable_cloud=False,
        )
        
        # Should initialize even without model file (falls back to rule-based)
        assert adapter is not None
        assert adapter.privacy_level == PrivacyPolicyLevel.HYBRID_ALLOWED
        assert adapter._cloud_available is False
        # Local may or may not be available depending on model file
        status = adapter.get_status()
        assert "local_llm" in status
        assert "public_api" in status
        assert "router" in status

    def test_generate_fallback_response(self):
        """Test fallback rule-based response when no model available."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        # Should return fallback response
        response = adapter.generate("halo", {})
        assert isinstance(response, CognitiveResponse)
        assert response.source == "fallback_rule_based"
        assert response.confidence == 0.3
        assert "Halo" in response.text or "halo" in response.text.lower()

    def test_generate_greeting_response(self):
        """Test greeting detection in fallback."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        response = adapter.generate("hai, apa kabar?", {})
        assert response.source == "fallback_rule_based"
        assert "Halo" in response.text or "bantu" in response.text

    def test_generate_thanks_response(self):
        """Test thanks detection in fallback."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        response = adapter.generate("terima kasih", {})
        assert response.source == "fallback_rule_based"
        assert "Sama-sama" in response.text

    def test_routing_sensitive_content_local(self):
        """Test that sensitive content routes to local."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=True,  # Cloud enabled but should not be used for sensitive
        )
        
        response = adapter.generate("password saya adalah rahasia123", {})
        # Should route to local/fallback due to sensitive keyword
        assert response.source in ["local_llm", "fallback_rule_based"]
        assert response.metadata.get("routing_reason") is not None

    def test_routing_force_local(self):
        """Test force_local parameter overrides routing."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=True,
        )
        
        response = adapter.generate("apa itu python", {}, force_local=True)
        assert response.source in ["local_llm", "fallback_rule_based"]
        assert "force_local" in response.metadata.get("routing_reason", "").lower() or \
               "strict local" in response.metadata.get("routing_reason", "").lower()

    def test_chat_interface(self):
        """Test multi-turn chat interface."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        messages = [
            {"role": "user", "content": "halo"},
            {"role": "assistant", "content": "Halo! Ada yang bisa saya bantu?"},
            {"role": "user", "content": "apa kabar?"},
        ]
        
        response = adapter.chat(messages, {})
        assert isinstance(response, CognitiveResponse)
        assert response.source == "fallback_rule_based"

    def test_factual_query_detection(self):
        """Test heuristic for factual queries."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        # These should be detected as factual
        assert adapter._is_factual_query("apa itu python")
        assert adapter._is_factual_query("what is machine learning")
        assert adapter._is_factual_query("siapa presiden indonesia")
        assert adapter._is_factual_query("kapan hari kemerdekaan")
        assert adapter._is_factual_query("dimana gunung merapi")
        
        # These should NOT be detected as factual
        assert not adapter._is_factual_query("halo")
        assert not adapter._is_factual_query("terima kasih")
        assert not adapter._is_factual_query("buatkan kode python")

    def test_prompt_enrichment(self):
        """Test prompt enrichment with context."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        context = {
            "user_name": "Budi",
            "current_time": "10:00",
            "location": "Jakarta",
            "conversation_history": ["User: halo", "Assistant: Halo Budi!"],
        }
        
        enriched = adapter._enrich_prompt("apa kabar?", context)
        assert "Budi" in enriched
        assert "10:00" in enriched
        assert "Jakarta" in enriched
        assert "halo" in enriched.lower()

    def test_status_reporting(self):
        """Test status reporting for health checks."""
        adapter = CognitiveModelAdapter(
            local_model_path="models/nonexistent.gguf",
            enable_cloud=False,
        )
        
        status = adapter.get_status()
        assert "local_llm" in status
        assert "public_api" in status
        assert "router" in status
        assert status["local_llm"]["available"] is False  # No model file
        assert status["public_api"]["available"] is False
        assert status["router"]["privacy_level"] == "HYBRID_ALLOWED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])