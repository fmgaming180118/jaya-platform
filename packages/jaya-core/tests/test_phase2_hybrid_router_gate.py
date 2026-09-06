"""Prototype tests for Pillar 37 — Hybrid Consciousness & Router.

Strict compliance checks according to AGENTS.md:
- Dynamic connectivity probing with graceful offline fallback
- Feature boundary isolation between offline base tier and online distributed tier
- Routing metrics and transition state persistence
- Explicit quarantine from IronEngine
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from jaya_core.brain_v2.engine.hybrid_mode import HybridRouter
from jaya_core.brain_v2.engine.runtime import IronEngine


def test_hybrid_router_offline_gating(tmp_path: Path):
    storage = tmp_path / "hybrid_state.json"
    router = HybridRouter(force_offline=True, storage_path=storage)

    assert router.is_online is False
    features = router.available_features()
    assert "ternary_model" in features
    assert "local_rag" in features
    assert "narrative" in features
    assert "collective_pulse" not in features
    assert "agentic_search" not in features

    # Routing checks
    assert router.route("local_rag") is True
    assert router.route("collective_pulse") is False

    st = router.status()
    assert st["is_online"] is False
    assert st["force_offline"] is True
    assert st["route_counts"]["local_rag"] == 1
    assert st["route_counts"]["collective_pulse"] == 1
    assert storage.exists()


def test_hybrid_router_transitions_and_persistence(tmp_path: Path):
    storage = tmp_path / "hybrid_reboot.json"
    router1 = HybridRouter(force_offline=True, storage_path=storage)
    router1.route("ternary_model")
    router1.route("ternary_model")
    router1.save_state()

    # Re-instantiate
    router2 = HybridRouter(force_offline=True, storage_path=storage)
    st = router2.status()
    assert st["route_counts"]["ternary_model"] == 2


def test_hybrid_router_remains_quarantined_from_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    storage = tmp_path / "engine_hybrid.json"
    monkeypatch.setenv("JAYA_HYBRID_STORAGE_PATH", str(storage))
    monkeypatch.setenv("JAYA_HYBRID_FORCE_OFFLINE", "true")

    engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
    engine.ignite()

    assert engine.is_hybrid_online() is False
    assert engine.available_hybrid_features() == []
    assert engine.route_hybrid_feature("local_rag") is False
    assert engine.route_hybrid_feature("collective_pulse") is False

    st = engine.status()
    assert st["hybrid_router"] is None
    assert st["hybrid_online"] is None
    assert storage.exists() is False
