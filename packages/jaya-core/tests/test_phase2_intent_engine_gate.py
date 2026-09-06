"""Prototype regression tests for the explicit-learning intent engine.

Strict compliance checks according to AGENTS.md:
- Real N-gram + TF-IDF semantic learning
- Partial input prediction and confidence ranking
- ACID persistence and reboot restoration
- Runtime learning requires explicit consent
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from jaya_core.brain_v2.engine.intent_engine import IntentEngine
from jaya_core.brain_v2.engine.runtime import IronEngine


def test_intent_engine_learning_and_prediction(tmp_path: Path):
    storage = tmp_path / "intent_test.json"
    engine = IntentEngine(storage_path=storage)

    # Empty prediction
    assert engine.predict_intent("buka") == []
    assert engine.best_prediction("buka") is None

    # Learn several commands
    engine.learn("buka browser sekarang")
    engine.learn("buka aplikasi terminal")
    engine.learn("buka file konfigurasi")
    engine.learn("jalankan simulasi fisika")

    st = engine.status()
    assert st["learned"] == 4
    assert st["tfidf_docs"] == 4
    assert st["prefixes"] > 0
    assert storage.exists()

    # Query with prefix
    preds = engine.predict_intent("buka", top_k=3)
    assert len(preds) > 0
    completions = [p[0] for p in preds]
    assert any("browser" in c or "aplikasi" in c or "file" in c for c in completions)

    best = engine.best_prediction("jalankan")
    assert best is not None
    assert "simulasi" in best


def test_intent_engine_persistence_reboot(tmp_path: Path):
    storage = tmp_path / "intent_reboot.json"
    engine1 = IntentEngine(storage_path=storage)
    engine1.learn("periksa status sistem")
    engine1.learn("periksa memori ram")
    engine1.save()

    # Re-instantiate from disk
    engine2 = IntentEngine(storage_path=storage)
    assert engine2.status()["learned"] == 2
    assert engine2.status()["tfidf_docs"] == 2
    best = engine2.best_prediction("periksa")
    assert best is not None
    assert "status" in best or "memori" in best


def test_intent_engine_runtime_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    storage = tmp_path / "engine_intent.json"
    monkeypatch.setenv("JAYA_INTENT_MODEL_PATH", str(storage))

    engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
    engine.ignite()

    # Test explicit learn
    assert engine.learn_intent("deploy project to production") is False
    learned = engine.learn_intent("deploy project to production", consent=True)
    assert learned is True

    preds = engine.predict_intent("deploy project", top_k=3)
    assert len(preds) >= 1
    assert any("production" in p[0] or "to" in p[0] for p in preds)

    # Test best prediction helper
    best = engine.best_intent_prediction("deploy")
    assert best is not None
    assert "project" in best

    # Status check
    st = engine.status()
    assert st["intent"] is not None
    assert st["intent"]["learned"] >= 1
