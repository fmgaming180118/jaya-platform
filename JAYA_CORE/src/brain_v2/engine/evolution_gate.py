"""Phase 2 — Safe Evolution Gate.

This module evaluates self-upgrade candidates in the resident layer
(`brain_v2`) while preserving the Home-vs-Resident boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class GateDecisionCode(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REJECT_SECURITY = "REJECT_SECURITY"
    REJECT_PERF = "REJECT_PERF"
    REJECT_RESOURCE = "REJECT_RESOURCE"
    REJECT_TEST = "REJECT_TEST"


@dataclass
class EvolutionCandidate:
    candidate_id: str
    source_hash: str
    created_at: float
    candidate_payload: str
    expected_perf_gain_pct: float = 0.0
    rollback_target: str = "stable"
    key_id: str = "local"
    signature_alg: str = "HMAC-SHA256"
    signature: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def canonical_for_signature(self) -> str:
        payload = {
            "candidate_id": self.candidate_id,
            "source_hash": self.source_hash,
            "created_at": round(float(self.created_at), 6),
            "candidate_payload": self.candidate_payload,
            "expected_perf_gain_pct": float(self.expected_perf_gain_pct),
            "rollback_target": self.rollback_target,
            "key_id": self.key_id,
            "signature_alg": self.signature_alg,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionCandidate":
        return cls(
            candidate_id=str(data.get("candidate_id") or "candidate-unknown"),
            source_hash=str(data.get("source_hash") or "unknown-hash"),
            created_at=float(data.get("created_at") or time.time()),
            candidate_payload=str(data.get("candidate_payload") or ""),
            expected_perf_gain_pct=float(data.get("expected_perf_gain_pct") or 0.0),
            rollback_target=str(data.get("rollback_target") or "stable"),
            key_id=str(data.get("key_id") or "local"),
            signature_alg=str(data.get("signature_alg") or "HMAC-SHA256"),
            signature=str(data.get("signature") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_hash": self.source_hash,
            "created_at": self.created_at,
            "candidate_payload": self.candidate_payload,
            "expected_perf_gain_pct": self.expected_perf_gain_pct,
            "rollback_target": self.rollback_target,
            "key_id": self.key_id,
            "signature_alg": self.signature_alg,
            "signature": self.signature,
            "metadata": dict(self.metadata),
        }


@dataclass
class CandidateEvidence:
    tests_passed: bool
    benchmark_gate_passed: bool
    observed_perf_gain_pct: float
    ram_delta_pct: float
    cpu_delta_pct: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateEvidence":
        return cls(
            tests_passed=bool(data.get("tests_passed", False)),
            benchmark_gate_passed=bool(data.get("benchmark_gate_passed", False)),
            observed_perf_gain_pct=float(data.get("observed_perf_gain_pct") or 0.0),
            ram_delta_pct=float(data.get("ram_delta_pct") or 0.0),
            cpu_delta_pct=float(data.get("cpu_delta_pct") or 0.0),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class GateThresholds:
    min_perf_gain_pct: float = 8.0
    max_ram_delta_pct: float = 5.0
    max_cpu_delta_pct: float = 10.0


@dataclass
class GateDecision:
    accepted: bool
    code: GateDecisionCode
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "code": self.code.value,
            "reason": self.reason,
            "details": self.details,
        }


class EvolutionGate:
    """Deterministic multi-gate evaluator for evolution candidates."""

    def __init__(
        self,
        thresholds: Optional[GateThresholds] = None,
        ethical_heart: Optional[Any] = None,
        zero_trust: Optional[Any] = None,
        signing_secret: Optional[str] = None,
        require_signed: bool = True,
    ):
        self.thresholds = thresholds or GateThresholds()
        self._ethical_heart = ethical_heart
        self._zero_trust = zero_trust
        # Development fallback key: can be replaced with env var in deployment.
        self._signing_secret = (signing_secret or os.getenv("JAYA_EVOLUTION_SIGNING_KEY")
                                or "jaya-phase2-dev-key").encode("utf-8")
        self._require_signed = bool(require_signed)
        self._decisions: List[GateDecision] = []
        self._audit_events: List[Dict[str, Any]] = []
        self._stable_snapshots: Dict[str, Dict[str, Any]] = {}
        self._active_stable_label: Optional[str] = None

    def _record_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self._audit_events.append(
            {
                "ts": round(time.time(), 6),
                "event": event_type,
                "payload": payload,
            }
        )

    def _compute_signature(self, candidate: EvolutionCandidate) -> str:
        data = candidate.canonical_for_signature().encode("utf-8")
        return hmac.new(self._signing_secret, data, hashlib.sha256).hexdigest()

    def sign_candidate(self, candidate: EvolutionCandidate, key_id: str = "local") -> str:
        candidate.key_id = key_id
        candidate.signature_alg = "HMAC-SHA256"
        sig = self._compute_signature(candidate)
        candidate.signature = sig
        self._record_event(
            "candidate_signed",
            {
                "candidate_id": candidate.candidate_id,
                "key_id": key_id,
                "signature_alg": candidate.signature_alg,
            },
        )
        return sig

    def verify_candidate_signature(self, candidate: EvolutionCandidate) -> Tuple[bool, str]:
        if not candidate.signature:
            return False, "missing signature"
        if candidate.signature_alg != "HMAC-SHA256":
            return False, "unsupported signature algorithm"
        expected = self._compute_signature(candidate)
        if not hmac.compare_digest(expected, candidate.signature):
            return False, "signature mismatch"
        return True, "ok"

    def _reject(self, code: GateDecisionCode, reason: str, **details: Any) -> GateDecision:
        d = GateDecision(accepted=False, code=code, reason=reason, details=details)
        self._decisions.append(d)
        self._record_event("decision", d.to_dict())
        return d

    def evaluate(self, candidate: EvolutionCandidate, evidence: CandidateEvidence) -> GateDecision:
        if self._require_signed:
            ok_sig, reason_sig = self.verify_candidate_signature(candidate)
            if not ok_sig:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "candidate signature validation failed",
                    candidate_id=candidate.candidate_id,
                    signature_reason=reason_sig,
                )

        if not candidate.candidate_payload.strip():
            return self._reject(
                GateDecisionCode.REJECT,
                "candidate payload is empty",
                candidate_id=candidate.candidate_id,
            )

        if not evidence.tests_passed:
            return self._reject(
                GateDecisionCode.REJECT_TEST,
                "functional tests failed",
                candidate_id=candidate.candidate_id,
            )

        if self._ethical_heart is not None:
            ok, reason = self._ethical_heart.evaluate(candidate.candidate_payload)
            if not ok:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "ethical heart rejected candidate",
                    candidate_id=candidate.candidate_id,
                    ethical_reason=reason,
                )

        if self._zero_trust is not None:
            ok, reason = self._zero_trust.validate("evolution_candidate", candidate.candidate_payload)
            if not ok:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "zero-trust rejected candidate",
                    candidate_id=candidate.candidate_id,
                    zero_trust_reason=reason,
                )

        if not evidence.benchmark_gate_passed:
            return self._reject(
                GateDecisionCode.REJECT_PERF,
                "benchmark gate failed",
                candidate_id=candidate.candidate_id,
            )

        if evidence.observed_perf_gain_pct < self.thresholds.min_perf_gain_pct:
            return self._reject(
                GateDecisionCode.REJECT_PERF,
                "insufficient performance gain",
                candidate_id=candidate.candidate_id,
                observed=evidence.observed_perf_gain_pct,
                minimum=self.thresholds.min_perf_gain_pct,
            )

        if evidence.ram_delta_pct > self.thresholds.max_ram_delta_pct:
            return self._reject(
                GateDecisionCode.REJECT_RESOURCE,
                "ram delta exceeds threshold",
                candidate_id=candidate.candidate_id,
                observed=evidence.ram_delta_pct,
                maximum=self.thresholds.max_ram_delta_pct,
            )

        if evidence.cpu_delta_pct > self.thresholds.max_cpu_delta_pct:
            return self._reject(
                GateDecisionCode.REJECT_RESOURCE,
                "cpu delta exceeds threshold",
                candidate_id=candidate.candidate_id,
                observed=evidence.cpu_delta_pct,
                maximum=self.thresholds.max_cpu_delta_pct,
            )

        decision = GateDecision(
            accepted=True,
            code=GateDecisionCode.ACCEPT,
            reason="candidate accepted",
            details={
                "candidate_id": candidate.candidate_id,
                "observed_perf_gain_pct": evidence.observed_perf_gain_pct,
                "ram_delta_pct": evidence.ram_delta_pct,
                "cpu_delta_pct": evidence.cpu_delta_pct,
            },
        )
        self._decisions.append(decision)
        self._record_event("decision", decision.to_dict())
        return decision

    def register_stable_snapshot(self, label: str, snapshot: Dict[str, Any]) -> None:
        # Store a shallow-copy by value for deterministic rollback behavior.
        self._stable_snapshots[label] = dict(snapshot)
        self._active_stable_label = label
        self._record_event("stable_snapshot_registered", {"label": label})

    def rollback(self, target_label: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        label = target_label or self._active_stable_label
        if label is None:
            return False, {"error": "no_stable_snapshot_registered"}
        snapshot = self._stable_snapshots.get(label)
        if snapshot is None:
            return False, {"error": "unknown_snapshot", "target_label": label}

        # Idempotent: repeatedly returning the same snapshot is valid.
        self._active_stable_label = label
        payload = {
            "target_label": label,
            "snapshot": dict(snapshot),
            "idempotent": True,
        }
        self._record_event("rollback", dict(payload))
        return True, payload

    def export_audit_log(self, limit: int = 200) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return self._audit_events[-limit:]

    def status(self) -> Dict[str, Any]:
        accepted = sum(1 for d in self._decisions if d.accepted)
        rejected = len(self._decisions) - accepted
        return {
            "decisions": len(self._decisions),
            "accepted": accepted,
            "rejected": rejected,
            "require_signed": self._require_signed,
            "audit_events": len(self._audit_events),
            "active_stable_label": self._active_stable_label,
            "stable_snapshots": len(self._stable_snapshots),
            "thresholds": {
                "min_perf_gain_pct": self.thresholds.min_perf_gain_pct,
                "max_ram_delta_pct": self.thresholds.max_ram_delta_pct,
                "max_cpu_delta_pct": self.thresholds.max_cpu_delta_pct,
            },
        }
