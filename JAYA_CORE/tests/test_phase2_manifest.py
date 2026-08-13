"""Phase 2 tests for signed manifest create/load/verify flow."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.evolution_gate import EvolutionCandidate, EvolutionGate  # noqa: E402
from src.brain_v2.engine.evolution_manifest import (  # noqa: E402
    build_signed_manifest,
    load_manifest,
    save_manifest,
    verify_manifest,
)
from src.brain_v2.engine.runtime import IronEngine  # noqa: E402


class TestPhase2Manifest(unittest.TestCase):
    def _candidate(self) -> EvolutionCandidate:
        return EvolutionCandidate(
            candidate_id="cand-man-1",
            source_hash="hash-x",
            created_at=1.0,
            candidate_payload="safe optimize patch",
            expected_perf_gain_pct=11.0,
            rollback_target="stable-v1",
        )

    def test_manifest_build_and_verify(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        manifest = build_signed_manifest(cand, gate=gate, baseline_ref="phase1-closed-v0.1", notes="smoke")

        ok, reason = verify_manifest(manifest, gate)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_manifest_tamper_rejected(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        manifest = build_signed_manifest(cand, gate=gate, baseline_ref="phase1")
        manifest["candidate"]["candidate_payload"] = "tampered payload"

        ok, reason = verify_manifest(manifest, gate)
        self.assertFalse(ok)
        self.assertIn("mismatch", reason)

    def test_manifest_file_roundtrip(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        manifest = build_signed_manifest(cand, gate=gate, baseline_ref="phase1")

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "candidate_manifest.json"
            save_manifest(manifest, str(p))
            loaded = load_manifest(str(p))
            ok, reason = verify_manifest(loaded, gate)

        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_runtime_manifest_hooks_smoke(self):
        engine = IronEngine(
            model_path="missing.jay",
            password="x",
            enable_twin=False,
            evolution_test_mode=True,
        )
        engine._init_security()
        engine._init_intelligence()

        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "candidate.json")
            out = engine.create_evolution_manifest(
                candidate={
                    "candidate_id": "cand-runtime-manifest",
                    "source_hash": "hash-runtime",
                    "candidate_payload": "safe optimize payload",
                    "expected_perf_gain_pct": 9.0,
                    "rollback_target": "stable-v1",
                },
                baseline_ref="phase1-closed-v0.1",
                out_path=path,
                notes="runtime test",
            )
            self.assertTrue(out["ok"])
            verify = engine.verify_evolution_manifest(path)
            self.assertTrue(verify["ok"])
            self.assertEqual(verify["reason"], "ok")


if __name__ == "__main__":
    unittest.main()
