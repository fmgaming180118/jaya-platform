"""Phase 2 tests for evolution gate decisions."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.evolution_gate import (
    CandidateEvidence,
    EvolutionCandidate,
    EvolutionGate,
    GateDecisionCode,
)


class TestPhase2EvolutionGate(unittest.TestCase):
    def _candidate(self, payload: str = "safe optimize patch") -> EvolutionCandidate:
        return EvolutionCandidate(
            candidate_id="cand-1",
            source_hash="abc123",
            created_at=0.0,
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

    def test_accept_candidate(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence())
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.ACCEPT)

    def test_reject_on_test_failure(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence(tests_passed=False))
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_TEST)

    def test_reject_on_perf_failure(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence(perf_gain=4.0))
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_PERF)

    def test_reject_on_resource_failure(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence(ram_delta=10.0))
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_RESOURCE)

    def test_reject_on_security_failure(self):
        class DenyHeart:
            def evaluate(self, action: str):
                return False, "blocked"

        gate = EvolutionGate(ethical_heart=DenyHeart())
        cand = self._candidate()
        gate.sign_candidate(cand)
        decision = gate.evaluate(cand, self._evidence())
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_SECURITY)

    def test_reject_on_missing_signature(self):
        gate = EvolutionGate()
        decision = gate.evaluate(self._candidate(), self._evidence())
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_SECURITY)

    def test_reject_on_signature_mismatch(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)
        cand.candidate_payload = cand.candidate_payload + " tampered"
        decision = gate.evaluate(cand, self._evidence())
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, GateDecisionCode.REJECT_SECURITY)

    def test_audit_log_records_events(self):
        gate = EvolutionGate()
        cand = self._candidate()
        gate.sign_candidate(cand)
        gate.evaluate(cand, self._evidence())
        events = gate.export_audit_log()
        self.assertGreaterEqual(len(events), 2)

    def test_record_runtime_event_public_api(self):
        gate = EvolutionGate()

        ok = gate.record_runtime_event(
            "agentic_objective_update",
            {"source": "local_rag", "success": True},
        )

        self.assertTrue(ok)
        events = gate.export_audit_log(limit=10)
        self.assertTrue(events)
        self.assertEqual(events[-1].get("event"), "agentic_objective_update")

    def test_record_runtime_event_rejects_empty_event_name(self):
        gate = EvolutionGate()

        ok = gate.record_runtime_event("", {"source": "runtime"})

        self.assertFalse(ok)
        self.assertEqual(gate.export_audit_log(limit=10), [])


if __name__ == "__main__":
    unittest.main()
