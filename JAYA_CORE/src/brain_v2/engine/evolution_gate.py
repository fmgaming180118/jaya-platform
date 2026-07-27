"""Phase 2 — Safe Evolution Gate.

This module evaluates self-upgrade candidates in the resident layer
(`brain_v2`) while preserving the Home-vs-Resident boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .evolution_evidence import (
    CandidateEvidence,
    EvidenceReceiptVerifier,
    EvidenceVerificationError,
)

__all__ = [
    "CandidateEvidence",
    "EvidenceVerificationError",
    "EvolutionCandidate",
    "EvolutionGate",
    "EvolutionGateConfigurationError",
    "GateDecision",
    "GateDecisionCode",
    "GateThresholds",
]


_PRODUCTION_ENVIRONMENTS = {"prod", "production"}
_EPHEMERAL_PROCESS_SIGNING_KEY = secrets.token_bytes(32)
_EPHEMERAL_PROCESS_EVIDENCE_KEY = secrets.token_bytes(32)


class EvolutionGateConfigurationError(RuntimeError):
    """Raised when a secure evolution gate cannot be configured."""


class GateDecisionCode(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REJECT_SECURITY = "REJECT_SECURITY"
    REJECT_PERF = "REJECT_PERF"
    REJECT_RESOURCE = "REJECT_RESOURCE"
    REJECT_TEST = "REJECT_TEST"
    REJECT_EVIDENCE = "REJECT_EVIDENCE"


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
        signing_secret: Optional[str | bytes] = None,
        evidence_signing_secret: Optional[str | bytes] = None,
        require_signed: bool = True,
        require_verified_evidence: Optional[bool] = None,
        test_mode: bool = False,
        environment: Optional[str] = None,
        evidence_max_age_s: float = 3600.0,
        candidate_max_age_s: float = 86400.0,
        trusted_evidence_runners: Optional[Iterable[str]] = None,
    ) -> None:
        self.thresholds = thresholds or GateThresholds()
        self._ethical_heart = ethical_heart
        self._zero_trust = zero_trust
        self._environment = (
            environment
            or os.getenv("JAYA_ENVIRONMENT")
            or os.getenv("JAYA_ENV")
            or "development"
        ).strip().lower()
        self._production = self._environment in _PRODUCTION_ENVIRONMENTS
        self._test_mode = bool(test_mode)

        if self._production and self._test_mode:
            raise EvolutionGateConfigurationError(
                "test_mode cannot be enabled in a production environment"
            )
        if self._production and not require_signed:
            raise EvolutionGateConfigurationError(
                "candidate signatures are mandatory in production"
            )

        if require_verified_evidence is None:
            self._require_verified_evidence = not self._test_mode
        else:
            self._require_verified_evidence = bool(require_verified_evidence)
        if not self._require_verified_evidence and not self._test_mode:
            raise EvolutionGateConfigurationError(
                "unverified evidence is allowed only with explicit test_mode=True"
            )

        self._signing_secret, self._signing_key_source = self._resolve_secret(
            explicit=signing_secret,
            env_name="JAYA_EVOLUTION_SIGNING_KEY",
            ephemeral=_EPHEMERAL_PROCESS_SIGNING_KEY,
        )
        evidence_secret, self._evidence_key_source = self._resolve_secret(
            explicit=evidence_signing_secret,
            env_name="JAYA_EVOLUTION_EVIDENCE_SIGNING_KEY",
            ephemeral=_EPHEMERAL_PROCESS_EVIDENCE_KEY,
        )
        trusted_runners = trusted_evidence_runners
        if trusted_runners is None:
            trusted_runners = (
                value.strip()
                for value in os.getenv(
                    "JAYA_EVOLUTION_TRUSTED_RUNNERS",
                    "",
                ).split(",")
                if value.strip()
            )
        self._evidence_verifier = EvidenceReceiptVerifier(
            evidence_secret,
            max_age_s=evidence_max_age_s,
            trusted_runners=trusted_runners,
        )
        self._candidate_max_age_s = float(candidate_max_age_s)
        if self._candidate_max_age_s <= 0:
            raise EvolutionGateConfigurationError(
                "candidate_max_age_s must be positive"
            )

        self._require_signed = bool(require_signed)
        self._decisions: List[GateDecision] = []
        self._audit_events: List[Dict[str, Any]] = []
        self._stable_snapshots: Dict[str, Dict[str, Any]] = {}
        self._active_stable_label: Optional[str] = None
        self._consumed_candidate_signatures: set[str] = set()

    def _resolve_secret(
        self,
        *,
        explicit: Optional[str | bytes],
        env_name: str,
        ephemeral: bytes,
    ) -> Tuple[bytes, str]:
        configured: Optional[str | bytes] = explicit
        source = "constructor"
        if configured is None:
            configured = os.getenv(env_name)
            source = env_name

        if configured is None or configured == "" or configured == b"":
            if self._production:
                raise EvolutionGateConfigurationError(
                    f"{env_name} is required in production"
                )
            return ephemeral, "ephemeral-process"

        secret = (
            configured
            if isinstance(configured, bytes)
            else configured.encode("utf-8")
        )
        if len(secret) < 32:
            raise EvolutionGateConfigurationError(
                f"{env_name} must contain at least 32 bytes"
            )
        return secret, source

    def _record_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self._audit_events.append(
            {
                "ts": round(time.time(), 6),
                "event": event_type,
                "payload": payload,
            }
        )

    def record_runtime_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> bool:
        safe_event = str(event_type or "").strip()
        if not safe_event:
            return False

        try:
            self._record_event(safe_event, dict(payload or {}))
            return True
        except Exception:
            return False

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

    def sign_evidence_report(self, report: Mapping[str, Any]) -> Dict[str, Any]:
        """Sign a report only in explicit test mode.

        Production reports must be signed by a trusted external runner rather
        than by the runtime that consumes them.
        """

        if not self._test_mode:
            raise EvolutionGateConfigurationError(
                "runtime evidence report signing is available only in test_mode"
            )
        return self._evidence_verifier.sign_report(report)

    def verify_evidence_reports(
        self,
        test_report_path: str | Path,
        benchmark_report_path: str | Path,
        *,
        candidate: EvolutionCandidate,
        expected_commit: Optional[str] = None,
    ) -> CandidateEvidence:
        """Build verified evidence from authenticated test and benchmark JSON."""

        evidence = self._evidence_verifier.verify_reports(
            test_report_path,
            benchmark_report_path,
            candidate_id=candidate.candidate_id,
            source_hash=candidate.source_hash,
            expected_commit=expected_commit,
        )
        self._record_event(
            "evidence_verified",
            {
                "candidate_id": candidate.candidate_id,
                "commit": evidence.metadata.get("commit"),
                "test_report_digest": evidence.metadata.get(
                    "test_report_digest"
                ),
                "benchmark_report_digest": evidence.metadata.get(
                    "benchmark_report_digest"
                ),
            },
        )
        return evidence

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

        if not self._test_mode:
            now = time.time()
            if candidate.created_at <= 0:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "candidate timestamp is invalid",
                    candidate_id=candidate.candidate_id,
                )
            if candidate.created_at > now + 300.0:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "candidate timestamp is in the future",
                    candidate_id=candidate.candidate_id,
                )
            if now - candidate.created_at > self._candidate_max_age_s:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "candidate signature expired",
                    candidate_id=candidate.candidate_id,
                )
            if candidate.signature in self._consumed_candidate_signatures:
                return self._reject(
                    GateDecisionCode.REJECT_SECURITY,
                    "candidate signature replay detected",
                    candidate_id=candidate.candidate_id,
                )

        if not candidate.candidate_payload.strip():
            return self._reject(
                GateDecisionCode.REJECT,
                "candidate payload is empty",
                candidate_id=candidate.candidate_id,
            )

        if self._require_verified_evidence:
            ok_evidence, reason_evidence = self._evidence_verifier.verify_receipt(
                evidence,
                candidate_id=candidate.candidate_id,
                source_hash=candidate.source_hash,
            )
            if not ok_evidence:
                return self._reject(
                    GateDecisionCode.REJECT_EVIDENCE,
                    "candidate evidence verification failed",
                    candidate_id=candidate.candidate_id,
                    evidence_reason=reason_evidence,
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
        if candidate.signature:
            self._consumed_candidate_signatures.add(candidate.signature)
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
            "require_verified_evidence": self._require_verified_evidence,
            "environment": self._environment,
            "test_mode": self._test_mode,
            "signing_key_source": self._signing_key_source,
            "evidence_key_source": self._evidence_key_source,
            "audit_events": len(self._audit_events),
            "active_stable_label": self._active_stable_label,
            "stable_snapshots": len(self._stable_snapshots),
            "thresholds": {
                "min_perf_gain_pct": self.thresholds.min_perf_gain_pct,
                "max_ram_delta_pct": self.thresholds.max_ram_delta_pct,
                "max_cpu_delta_pct": self.thresholds.max_cpu_delta_pct,
            },
        }
