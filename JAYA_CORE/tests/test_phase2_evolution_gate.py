"""Phase 2 tests for evolution gate decisions."""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.evolution_evidence import (  # noqa: E402
    EvidenceReceiptVerifier,
    EvidenceVerificationError,
)
from src.brain_v2.engine.evolution_gate import (  # noqa: E402
    CandidateEvidence,
    EvolutionCandidate,
    EvolutionGate,
    EvolutionGateConfigurationError,
    GateDecisionCode,
)


class TestPhase2EvolutionGate(unittest.TestCase):
    def _candidate(self, payload: str = "safe optimize patch") -> EvolutionCandidate:
        return EvolutionCandidate(
            candidate_id="cand-1",
            source_hash="abc123",
            created_at=time.time(),
            candidate_payload=payload,
            expected_perf_gain_pct=10.0,
            rollback_target="stable-v1",
        )

    def _evidence(
        self,
        tests_passed: bool = True,
        benchmark_gate_passed: bool = True,
        perf_gain: float = 12.0,
        ram_delta: float = 2.0,
        cpu_delta: float = 3.0,
    ) -> CandidateEvidence:
        return CandidateEvidence(
            tests_passed=tests_passed,
            benchmark_gate_passed=benchmark_gate_passed,
            observed_perf_gain_pct=perf_gain,
            ram_delta_pct=ram_delta,
            cpu_delta_pct=cpu_delta,
        )

    @staticmethod
    def _report(
        report_type: str,
        *,
        created_at: float,
        runner: str = "ci-phase2",
    ) -> dict:
        result = {"passed": True}
        if report_type == "benchmark":
            result.update(
                {
                    "observed_perf_gain_pct": 12.0,
                    "ram_delta_pct": 2.0,
                    "cpu_delta_pct": 3.0,
                }
            )
        return {
            "schema_version": "jaya-evolution-evidence-report-v1",
            "report_type": report_type,
            "candidate_id": "cand-1",
            "source_hash": "abc123",
            "commit": "a" * 40,
            "runner": runner,
            "created_at": created_at,
            "dataset_digest": f"sha256:{'d' * 64}",
            "nonce": f"{report_type}-nonce",
            "result": result,
            "key_id": "ci-phase2-key",
            "signature_alg": "HMAC-SHA256",
        }

    def test_accept_candidate(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence())
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.ACCEPT)

    def test_reject_on_test_failure(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence(tests_passed=False))
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_TEST)

    def test_reject_on_perf_failure(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence(perf_gain=4.0))
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_PERF)

    def test_reject_on_resource_failure(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence(ram_delta=10.0))
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_RESOURCE)

    def test_reject_on_security_failure(self):
        class DenyHeart:
            def evaluate(self, action: str):
                return False, "blocked"

        gate = EvolutionGate(ethical_heart=DenyHeart(), test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence())
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_SECURITY)

    def test_reject_on_missing_signature(self):
        gate = EvolutionGate(test_mode=True)
        decision = gate.evaluate(self._candidate(), self._evidence())
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_SECURITY)

    def test_reject_on_signature_mismatch(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        cand.candidate_payload = cand.candidate_payload + " tampered"
        decision = gate.evaluate(cand, self._evidence())
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_SECURITY)

    def test_audit_log_records_events(self):
        gate = EvolutionGate(test_mode=True)
        cand = self._candidate()
        gate.sign_candidate(cand)
        gate.evaluate(cand, self._evidence())
        events = gate.export_audit_log()
        self.assertGreaterEqual(len(events), 2)

    def test_record_runtime_event_public_api(self):
        gate = EvolutionGate(test_mode=True)

        ok = gate.record_runtime_event(
            "agentic_objective_update",
            {"source": "local_rag", "success": True},
        )

        self.assertTrue(ok)
        events = gate.export_audit_log(limit=10)
        self.assertTrue(events)
        self.assertEqual(events[-1].get("event"), "agentic_objective_update")

    def test_record_runtime_event_rejects_empty_event_name(self):
        gate = EvolutionGate(test_mode=True)

        ok = gate.record_runtime_event("", {"source": "runtime"})

        self.assertFalse(ok)
        self.assertEqual(gate.export_audit_log(limit=10), [])

    def test_default_gate_rejects_manual_evidence(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)

        decision = gate.evaluate(cand, self._evidence())

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_EVIDENCE)
        self.assertIn("missing", decision.details["evidence_reason"])

    def test_production_requires_configured_signing_keys(self):
        with self.assertRaises(EvolutionGateConfigurationError):
            EvolutionGate(
                environment="production",
                signing_secret="",
                evidence_signing_secret=b"e" * 32,
            )

        with self.assertRaises(EvolutionGateConfigurationError):
            EvolutionGate(
                environment="production",
                signing_secret=b"s" * 32,
                evidence_signing_secret="",
            )

    def test_ephemeral_key_is_shared_only_within_process(self):
        signer = EvolutionGate(test_mode=True)
        verifier = EvolutionGate(test_mode=True)
        cand = self._candidate()
        signer.sign_candidate(cand)

        ok, reason = verifier.verify_candidate_signature(cand)

        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(signer.status()["signing_key_source"], "ephemeral-process")

    def test_candidate_signature_from_wrong_key_is_rejected(self):
        signer = EvolutionGate(
            environment="production",
            signing_secret=b"a" * 32,
            evidence_signing_secret=b"e" * 32,
        )
        verifier = EvolutionGate(
            environment="production",
            signing_secret=b"b" * 32,
            evidence_signing_secret=b"e" * 32,
        )
        cand = self._candidate()
        signer.sign_candidate(cand)

        ok, reason = verifier.verify_candidate_signature(cand)

        self.assertFalse(ok)
        self.assertEqual(reason, "signature mismatch")

    def test_verified_reports_can_reach_gate_and_replay_is_rejected(self):
        signing_key = b"s" * 32
        evidence_key = b"e" * 32
        gate = EvolutionGate(
            environment="production",
            signing_secret=signing_key,
            evidence_signing_secret=evidence_key,
            trusted_evidence_runners={"ci-phase2"},
        )
        report_signer = EvidenceReceiptVerifier(evidence_key)
        cand = self._candidate()
        gate.sign_candidate(cand)
        now = time.time()

        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "tests.json"
            benchmark_path = Path(temp_dir) / "benchmark.json"
            test_path.write_text(
                json.dumps(
                    report_signer.sign_report(self._report("test", created_at=now))
                ),
                encoding="utf-8",
            )
            benchmark_path.write_text(
                json.dumps(
                    report_signer.sign_report(self._report("benchmark", created_at=now))
                ),
                encoding="utf-8",
            )
            evidence = gate.verify_evidence_reports(
                test_path,
                benchmark_path,
                candidate=cand,
                expected_commit="a" * 40,
            )

        decision = gate.evaluate(cand, evidence)
        replay = gate.evaluate(cand, evidence)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.ACCEPT)
        self.assertFalse(replay.accepted)
        self.assertEqual(replay.code, GateDecisionCode.REJECT_SECURITY)
        self.assertIn("replay", replay.reason)

    def test_tampered_report_is_rejected(self):
        evidence_key = b"e" * 32
        gate = EvolutionGate(
            environment="production",
            signing_secret=b"s" * 32,
            evidence_signing_secret=evidence_key,
        )
        report_signer = EvidenceReceiptVerifier(evidence_key)
        now = time.time()
        cand = self._candidate()
        test_report = report_signer.sign_report(self._report("test", created_at=now))
        test_report["result"]["passed"] = False

        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "tests.json"
            benchmark_path = Path(temp_dir) / "benchmark.json"
            test_path.write_text(json.dumps(test_report), encoding="utf-8")
            benchmark_path.write_text(
                json.dumps(
                    report_signer.sign_report(self._report("benchmark", created_at=now))
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                EvidenceVerificationError,
                "digest mismatch",
            ):
                gate.verify_evidence_reports(
                    test_path,
                    benchmark_path,
                    candidate=cand,
                )

    def test_expired_report_is_rejected(self):
        evidence_key = b"e" * 32
        gate = EvolutionGate(
            environment="production",
            signing_secret=b"s" * 32,
            evidence_signing_secret=evidence_key,
            evidence_max_age_s=10.0,
        )
        report_signer = EvidenceReceiptVerifier(evidence_key)
        expired_at = time.time() - 11.0
        cand = self._candidate()

        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "tests.json"
            benchmark_path = Path(temp_dir) / "benchmark.json"
            test_path.write_text(
                json.dumps(
                    report_signer.sign_report(
                        self._report("test", created_at=expired_at)
                    )
                ),
                encoding="utf-8",
            )
            benchmark_path.write_text(
                json.dumps(
                    report_signer.sign_report(
                        self._report("benchmark", created_at=expired_at)
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                EvidenceVerificationError,
                "expired",
            ):
                gate.verify_evidence_reports(
                    test_path,
                    benchmark_path,
                    candidate=cand,
                )


if __name__ == "__main__":
    unittest.main()
