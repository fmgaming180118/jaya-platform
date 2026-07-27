"""Phase 2 tests for deterministic rollback behavior."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.evolution_evidence import EvidenceReceiptVerifier  # noqa: E402
from src.brain_v2.engine.evolution_gate import EvolutionGate  # noqa: E402
from src.brain_v2.engine.runtime import IronEngine  # noqa: E402


class TestPhase2Rollback(unittest.TestCase):
    def test_rollback_idempotent(self):
        gate = EvolutionGate(test_mode=True)
        gate.register_stable_snapshot("stable-v1", {"topk_ratio": 0.10, "mode": "safe"})

        ok1, payload1 = gate.rollback("stable-v1")
        ok2, payload2 = gate.rollback("stable-v1")

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertEqual(payload1["snapshot"], payload2["snapshot"])
        self.assertTrue(payload2["idempotent"])

    def test_rollback_unknown_target(self):
        gate = EvolutionGate(test_mode=True)
        ok, payload = gate.rollback("missing")
        self.assertFalse(ok)
        self.assertEqual(payload["error"], "unknown_snapshot")

    def test_runtime_evolution_hooks_smoke(self):
        engine = IronEngine(
            model_path="missing.jay",
            password="x",
            enable_twin=False,
            evolution_test_mode=True,
        )
        engine._init_security()
        engine._init_intelligence()

        reg = engine.register_stable_state("stable-v1", {"version": 1})
        self.assertTrue(reg["ok"])

        signed = engine.sign_evolution_candidate(
            {
                "candidate_id": "cand-rt-1",
                "source_hash": "h123",
                "candidate_payload": "safe optimize candidate",
                "expected_perf_gain_pct": 10.0,
            },
            key_id="local",
        )
        self.assertTrue(signed["ok"])

        decision = engine.evaluate_evolution_candidate(
            signed["candidate"],
            {
                "tests_passed": True,
                "benchmark_gate_passed": True,
                "observed_perf_gain_pct": 10.0,
                "ram_delta_pct": 2.0,
                "cpu_delta_pct": 2.0,
            },
        )
        self.assertTrue(decision["ok"])
        self.assertTrue(decision["decision"]["accepted"])

        rollback = engine.rollback_stable_state("stable-v1")
        self.assertTrue(rollback["ok"])
        self.assertEqual(rollback["target_label"], "stable-v1")

        audit = engine.evolution_audit_log(limit=20)
        self.assertTrue(audit["ok"])
        self.assertGreaterEqual(len(audit["events"]), 3)

    def test_runtime_verified_report_flow(self):
        signing_key = "s" * 32
        evidence_key = b"e" * 32
        environment = {
            "JAYA_ENVIRONMENT": "development",
            "JAYA_EVOLUTION_SIGNING_KEY": signing_key,
            "JAYA_EVOLUTION_EVIDENCE_SIGNING_KEY": evidence_key.decode("ascii"),
        }
        with patch.dict(os.environ, environment):
            engine = IronEngine(
                model_path="missing.jay",
                password="x",
                enable_twin=False,
            )
            engine._init_security()
            engine._init_intelligence()

        candidate = {
            "candidate_id": "cand-runtime-receipt",
            "source_hash": "runtime-source-hash",
            "created_at": time.time(),
            "candidate_payload": "safe optimize candidate",
            "expected_perf_gain_pct": 12.0,
        }
        signed = engine.sign_evolution_candidate(candidate)
        self.assertTrue(signed["ok"])

        report_signer = EvidenceReceiptVerifier(evidence_key)
        now = time.time()
        common = {
            "schema_version": "jaya-evolution-evidence-report-v1",
            "candidate_id": candidate["candidate_id"],
            "source_hash": candidate["source_hash"],
            "commit": "abcdef1234567890",
            "runner": "ci-runtime",
            "created_at": now,
            "dataset_digest": f"sha256:{'d' * 64}",
            "key_id": "ci-runtime-key",
            "signature_alg": "HMAC-SHA256",
        }
        test_report = report_signer.sign_report(
            {
                **common,
                "report_type": "test",
                "nonce": "runtime-test-nonce",
                "result": {"passed": True},
            }
        )
        benchmark_report = report_signer.sign_report(
            {
                **common,
                "report_type": "benchmark",
                "nonce": "runtime-benchmark-nonce",
                "result": {
                    "passed": True,
                    "observed_perf_gain_pct": 12.0,
                    "ram_delta_pct": 2.0,
                    "cpu_delta_pct": 2.0,
                },
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "tests.json"
            benchmark_path = Path(temp_dir) / "benchmark.json"
            test_path.write_text(json.dumps(test_report), encoding="utf-8")
            benchmark_path.write_text(
                json.dumps(benchmark_report),
                encoding="utf-8",
            )
            verified = engine.verify_evolution_evidence_reports(
                signed["candidate"],
                str(test_path),
                str(benchmark_path),
                expected_commit="abcdef1234567890",
            )

        self.assertTrue(verified["ok"])
        decision = engine.evaluate_evolution_candidate(
            signed["candidate"],
            verified["evidence"],
        )
        self.assertTrue(decision["ok"])
        self.assertTrue(decision["decision"]["accepted"])


if __name__ == "__main__":
    unittest.main()
