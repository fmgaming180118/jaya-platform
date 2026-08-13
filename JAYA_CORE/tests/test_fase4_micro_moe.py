"""
test_fase4_micro_moe.py — Unit tests for MicroMoE & ReflexionLoop (Fase 4 JAYA_CORE)

Tests cover:
  - MicroMoERouter: keyword scoring, domain hint routing, gate_score feedback
  - ExpertConfig: default values & registry
  - ReflexionLoop candidate scoring & selection
  - ReflexionLoop self-correction regeneration
  - MicroMoEEngine integration status
"""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
jaya_core_dir = repo_root / "JAYA_CORE"
sys.path.insert(0, str(jaya_core_dir))

import pytest
from src.brain_v2.engine.micro_moe import (
    MicroMoERouter,
    ExpertConfig,
    EXPERT_REGISTRY,
    ReflexionLoop,
    MicroMoEEngine,
    _score_candidate,
)


class TestMicroMoERouter:
    def test_route_thesis_keyword(self):
        router = MicroMoERouter()
        name, config, score = router.route("bantu saya menyusun bab 1 skripsi tentang iot")
        assert name == "expert_thesis"
        assert config.name == "expert_thesis"

    def test_route_code_keyword(self):
        router = MicroMoERouter()
        name, config, score = router.route("ada error nullpointer di fungsi kotlin retrofit viewmodel")
        assert name == "expert_code"

    def test_route_logic_keyword(self):
        router = MicroMoERouter()
        name, config, score = router.route("hitung integral dan derivatif dari rumus statistik ini")
        assert name == "expert_logic"

    def test_route_dialogue_fallback(self):
        router = MicroMoERouter()
        name, config, score = router.route("halo jaya apa kabar hari ini")
        assert name == "expert_dialogue"

    def test_domain_hint_routing(self):
        router = MicroMoERouter()
        name, config, score = router.route("buatkan fungsi ini", domain_hint="code")
        assert name == "expert_code"

    def test_feedback_adjusts_gate_score(self):
        router = MicroMoERouter()
        initial = router._gate_scores["expert_code"]
        router.feedback("expert_code", success=True)
        assert router._gate_scores["expert_code"] > initial


class TestReflexionLoop:
    def test_score_candidate_good_quality(self):
        prompt = "jelaskan skripsi federated learning"
        response = """Skripsi tentang Federated Learning pada IoT.

Berikut adalah 3 poin utama:
1. Latar Belakang: Privasi data pada jaringan terdistribusi.
2. Metodologi: Menggunakan arsitektur Client-Server terenkripsi.
3. Kesimpulan: Efisiensi komunikasi meningkat 40%."""
        score = _score_candidate(response, prompt, "expert_thesis")
        assert score >= 0.6

    def test_score_candidate_hallucination_penalty(self):
        prompt = "apa itu transformer?"
        response = "Maaf, sebagai AI saya tidak tahu dan saya tidak memiliki informasi mengenai itu."
        score = _score_candidate(response, prompt, "expert_dialogue")
        assert score < 0.5

    def test_select_best_candidate(self):
        loop = ReflexionLoop()
        cands = [
            "Maaf saya tidak bisa membantu",
            "Berikut penjelasan detail skripsi mengenai federated learning untuk sistem IoT: 1. Konsep..."
        ]
        best_resp, best_score, best_idx = loop.select_best(cands, "skripsi iot", "expert_thesis")
        assert best_idx == 1
        assert best_score > 0.4

    def test_reflexion_run_regeneration(self):
        loop = ReflexionLoop(n_candidates=1, quality_threshold=0.8, enable_regeneration=True)
        
        # Fake generator function
        def mock_generate(prompt, config):
            if "strict" in config.name:
                return "Ini adalah jawaban perbaikan yang sangat spesifik dan detail mengenai skripsi federated learning dengan struktur 1. 2. 3."
            return "Jawaban pendek."

        expert_cfg = EXPERT_REGISTRY["expert_thesis"]
        resp, score, was_regen = loop.run("skripsi", "expert_thesis", mock_generate, expert_cfg)
        assert was_regen is True
        assert "perbaikan" in resp


class TestMicroMoEEngine:
    def test_status_output(self):
        engine = MicroMoEEngine()
        st = engine.status()
        assert "router" in st
        assert "reflexion" in st
        assert len(st["experts"]) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
