"""
test_phase_c_edge_hybrid.py — Unit tests for Phase C Edge Model Registry & Privacy-Aware Hybrid Router.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.models.hybrid_router import HybridModelRouter, PrivacyPolicyLevel, RoutingTarget
from src.models.registry import EdgeModelManifest, EdgeModelRegistry


class TestEdgeModelRegistry:
    def test_model_registration_and_signature_verification(self):
        reg = EdgeModelRegistry(max_allowed_size_mb=300.0)
        content = b"DUMMY_GGUF_MODEL_DATA_BYTES"
        sig = hashlib.sha256(content).hexdigest()

        manifest = EdgeModelManifest(
            model_id="student-gguf-v1",
            version="1.0",
            format="GGUF_Q4",
            size_mb=250.0,
            sha256_signature=sig,
            min_ram_mb=384,
        )

        # Valid registration
        success = reg.register_model(manifest, file_bytes=content)
        assert success is True

        retrieved = reg.get_model("student-gguf-v1", version="1.0")
        assert retrieved is not None
        assert retrieved.format == "GGUF_Q4"

    def test_rejection_of_oversized_or_corrupted_model(self):
        reg = EdgeModelRegistry(max_allowed_size_mb=300.0)

        # Oversized model (> 300MB)
        manifest_large = EdgeModelManifest(
            model_id="huge-model",
            version="1.0",
            format="GGUF_Q4",
            size_mb=450.0,
            sha256_signature="dummy",
        )
        assert reg.register_model(manifest_large) is False

        # Corrupted signature
        manifest_bad_sig = EdgeModelManifest(
            model_id="bad-sig-model",
            version="1.0",
            format="GGUF_Q4",
            size_mb=100.0,
            sha256_signature="wrong_hash_value",
        )
        assert reg.register_model(manifest_bad_sig, file_bytes=b"actual_data") is False

    def test_model_rollback(self):
        reg = EdgeModelRegistry()
        m1 = EdgeModelManifest(model_id="edge-m1", version="1.0", format="GGUF_Q4", size_mb=150.0, sha256_signature="sig1")
        m2 = EdgeModelManifest(model_id="edge-m1", version="2.0", format="GGUF_Q4", size_mb=160.0, sha256_signature="sig2")

        reg.register_model(m1)
        reg.register_model(m2)

        active_v2 = reg.get_model("edge-m1")
        assert active_v2.version == "2.0"

        # Execute rollback
        previous = reg.rollback_model("edge-m1")
        assert previous is not None
        assert previous.version == "1.0"
        assert previous.is_active is True


class TestHybridModelRouter:
    def test_strict_local_routing(self):
        router = HybridModelRouter()
        decision = router.route(
            prompt="Bantu analisis file ini",
            privacy_level=PrivacyPolicyLevel.STRICT_LOCAL_ONLY,
            network_available=True,
        )
        assert decision.target == RoutingTarget.LOCAL_EDGE
        assert decision.fallback_available is True

    def test_sensitive_prompt_routes_to_local(self):
        router = HybridModelRouter()
        decision = router.route(
            prompt="Masukkan password dan secret token pengguna",
            privacy_level=PrivacyPolicyLevel.HYBRID_ALLOWED,
            network_available=True,
        )
        assert decision.target == RoutingTarget.LOCAL_EDGE

    def test_cloud_routing_with_fallback(self):
        router = HybridModelRouter()
        decision = router.route(
            prompt="Jelaskan konsep dasar fisika kuantum",
            privacy_level=PrivacyPolicyLevel.HYBRID_ALLOWED,
            network_available=True,
        )
        assert decision.target == RoutingTarget.CLOUD_PROVIDER

        # Test execution fallback when cloud fails
        def failing_cloud():
            raise TimeoutError("Cloud service unreachable")

        def local_fallback():
            return "Local Edge Fallback Response"

        res = router.execute_with_fallback(decision, cloud_executor=failing_cloud, local_executor=local_fallback)
        assert res == "Local Edge Fallback Response"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
