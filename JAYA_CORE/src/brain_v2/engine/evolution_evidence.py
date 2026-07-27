"""Verified test and benchmark evidence for the JAYA evolution gate.

The verifier deliberately accepts reports from files, not caller-supplied
booleans. Each report is content-addressed and authenticated before a short-
lived, candidate-bound receipt is issued.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple


REPORT_SCHEMA_VERSION = "jaya-evolution-evidence-report-v1"
RECEIPT_SCHEMA_VERSION = "jaya-evolution-evidence-receipt-v1"
SIGNATURE_ALGORITHM = "HMAC-SHA256"
MAX_REPORT_BYTES = 1_048_576

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class EvidenceVerificationError(ValueError):
    """Raised when an evidence report or receipt cannot be trusted."""


@dataclass
class CandidateEvidence:
    """Gate metrics plus an optional cryptographic verification receipt."""

    tests_passed: bool
    benchmark_gate_passed: bool
    observed_perf_gain_pct: float
    ram_delta_pct: float
    cpu_delta_pct: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    verification_token: str = ""
    receipt: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateEvidence":
        return cls(
            tests_passed=data.get("tests_passed") is True,
            benchmark_gate_passed=data.get("benchmark_gate_passed") is True,
            observed_perf_gain_pct=float(data.get("observed_perf_gain_pct") or 0.0),
            ram_delta_pct=float(data.get("ram_delta_pct") or 0.0),
            cpu_delta_pct=float(data.get("cpu_delta_pct") or 0.0),
            metadata=dict(data.get("metadata") or {}),
            verification_token=str(data.get("verification_token") or ""),
            receipt=dict(data.get("receipt") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tests_passed": self.tests_passed,
            "benchmark_gate_passed": self.benchmark_gate_passed,
            "observed_perf_gain_pct": self.observed_perf_gain_pct,
            "ram_delta_pct": self.ram_delta_pct,
            "cpu_delta_pct": self.cpu_delta_pct,
            "metadata": dict(self.metadata),
            "verification_token": self.verification_token,
            "receipt": dict(self.receipt),
        }


def _canonical_json(data: Mapping[str, Any]) -> bytes:
    try:
        serialized = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceVerificationError(f"report is not canonical JSON: {exc}") from exc
    return serialized.encode("utf-8")


def _unsigned_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        str(key): value
        for key, value in report.items()
        if key not in {"report_digest", "signature"}
    }


def _require_text(data: Mapping[str, Any], key: str, *, max_len: int = 256) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceVerificationError(f"{key} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_len:
        raise EvidenceVerificationError(f"{key} exceeds {max_len} characters")
    return normalized


def _require_bool(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise EvidenceVerificationError(f"{key} must be a boolean")
    return value


def _require_finite_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceVerificationError(f"{key} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise EvidenceVerificationError(f"{key} must be a finite number")
    return parsed


def _require_sha256(data: Mapping[str, Any], key: str) -> str:
    value = _require_text(data, key, max_len=71).lower()
    if not _SHA256_RE.fullmatch(value):
        raise EvidenceVerificationError(f"{key} must use sha256:<64 lowercase hex>")
    return value


class EvidenceReceiptVerifier:
    """Authenticate evidence reports and issue candidate-bound receipts."""

    def __init__(
        self,
        signing_secret: bytes,
        *,
        max_age_s: float = 3600.0,
        future_skew_s: float = 300.0,
        trusted_runners: Optional[Iterable[str]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(signing_secret, bytes) or len(signing_secret) < 32:
            raise ValueError("evidence signing secret must contain at least 32 bytes")
        if max_age_s <= 0:
            raise ValueError("evidence max_age_s must be positive")
        if future_skew_s < 0:
            raise ValueError("evidence future_skew_s cannot be negative")

        self._signing_secret = signing_secret
        self._max_age_s = float(max_age_s)
        self._future_skew_s = float(future_skew_s)
        self._trusted_runners = {
            runner.strip()
            for runner in (trusted_runners or ())
            if isinstance(runner, str) and runner.strip()
        }
        self._clock = clock

    def sign_report(self, report: Mapping[str, Any]) -> Dict[str, Any]:
        """Sign one runner report.

        This is intended for a trusted CI/test runner. Runtime callers should
        only consume the resulting JSON through :meth:`verify_reports`.
        """

        signed = dict(report)
        signed.setdefault("schema_version", REPORT_SCHEMA_VERSION)
        signed.setdefault("signature_alg", SIGNATURE_ALGORITHM)
        signed.setdefault("key_id", "evidence-runner")
        signed.pop("report_digest", None)
        signed.pop("signature", None)

        canonical = _canonical_json(_unsigned_report(signed))
        signed["report_digest"] = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        signed["signature"] = hmac.new(
            self._signing_secret,
            canonical,
            hashlib.sha256,
        ).hexdigest()
        return signed

    def verify_reports(
        self,
        test_report_path: str | Path,
        benchmark_report_path: str | Path,
        *,
        candidate_id: str,
        source_hash: str,
        expected_commit: Optional[str] = None,
    ) -> CandidateEvidence:
        """Read, authenticate, and combine test and benchmark report JSON."""

        test_report = self._load_report(test_report_path)
        benchmark_report = self._load_report(benchmark_report_path)

        verified_test = self._verify_report(
            test_report,
            expected_type="test",
            candidate_id=candidate_id,
            source_hash=source_hash,
            expected_commit=expected_commit,
        )
        verified_benchmark = self._verify_report(
            benchmark_report,
            expected_type="benchmark",
            candidate_id=candidate_id,
            source_hash=source_hash,
            expected_commit=expected_commit,
        )

        if verified_test["commit"] != verified_benchmark["commit"]:
            raise EvidenceVerificationError(
                "test and benchmark reports reference different commits"
            )

        test_result = verified_test["result"]
        benchmark_result = verified_benchmark["result"]
        now = float(self._clock())
        expires_at = min(
            float(verified_test["created_at"]) + self._max_age_s,
            float(verified_benchmark["created_at"]) + self._max_age_s,
        )

        evidence_values = {
            "tests_passed": _require_bool(test_result, "passed"),
            "benchmark_gate_passed": _require_bool(benchmark_result, "passed"),
            "observed_perf_gain_pct": _require_finite_number(
                benchmark_result,
                "observed_perf_gain_pct",
            ),
            "ram_delta_pct": _require_finite_number(
                benchmark_result,
                "ram_delta_pct",
            ),
            "cpu_delta_pct": _require_finite_number(
                benchmark_result,
                "cpu_delta_pct",
            ),
        }
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "source_hash": source_hash,
            "commit": verified_test["commit"],
            "issued_at": round(now, 6),
            "expires_at": round(expires_at, 6),
            "reports": [
                self._receipt_report_entry(verified_test),
                self._receipt_report_entry(verified_benchmark),
            ],
            "evidence": dict(evidence_values),
        }
        token = self._sign_payload(receipt)

        return CandidateEvidence(
            **evidence_values,
            metadata={
                "verified": True,
                "commit": verified_test["commit"],
                "test_runner": verified_test["runner"],
                "benchmark_runner": verified_benchmark["runner"],
                "test_report_digest": verified_test["report_digest"],
                "benchmark_report_digest": verified_benchmark["report_digest"],
            },
            verification_token=token,
            receipt=receipt,
        )

    def verify_receipt(
        self,
        evidence: CandidateEvidence,
        *,
        candidate_id: str,
        source_hash: str,
    ) -> Tuple[bool, str]:
        """Validate that evidence was produced by this verifier for a candidate."""

        if not evidence.verification_token or not evidence.receipt:
            return False, "missing evidence verification receipt"

        receipt = evidence.receipt
        if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            return False, "unsupported evidence receipt schema"
        if not hmac.compare_digest(
            self._sign_payload(receipt),
            evidence.verification_token,
        ):
            return False, "evidence receipt signature mismatch"
        if receipt.get("candidate_id") != candidate_id:
            return False, "evidence receipt candidate mismatch"
        if receipt.get("source_hash") != source_hash:
            return False, "evidence receipt source mismatch"

        try:
            expires_at = _require_finite_number(receipt, "expires_at")
        except EvidenceVerificationError as exc:
            return False, str(exc)
        if float(self._clock()) > expires_at:
            return False, "evidence receipt expired"

        receipt_values = receipt.get("evidence")
        if not isinstance(receipt_values, dict):
            return False, "evidence receipt values are missing"

        expected_values = {
            "tests_passed": evidence.tests_passed,
            "benchmark_gate_passed": evidence.benchmark_gate_passed,
            "observed_perf_gain_pct": evidence.observed_perf_gain_pct,
            "ram_delta_pct": evidence.ram_delta_pct,
            "cpu_delta_pct": evidence.cpu_delta_pct,
        }
        for key, expected in expected_values.items():
            observed = receipt_values.get(key)
            if isinstance(expected, bool):
                if observed is not expected:
                    return False, f"evidence receipt {key} mismatch"
                continue
            if isinstance(observed, bool) or not isinstance(observed, (int, float)):
                return False, f"evidence receipt {key} is invalid"
            if not math.isclose(
                float(observed),
                float(expected),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                return False, f"evidence receipt {key} mismatch"

        return True, "ok"

    def _load_report(self, path_value: str | Path) -> Dict[str, Any]:
        path = Path(path_value)
        if not path.is_file():
            raise EvidenceVerificationError(f"evidence report not found: {path}")
        if path.stat().st_size > MAX_REPORT_BYTES:
            raise EvidenceVerificationError(
                f"evidence report exceeds {MAX_REPORT_BYTES} bytes: {path}"
            )
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EvidenceVerificationError(
                f"cannot read evidence report {path}: {exc}"
            ) from exc
        if not isinstance(loaded, dict):
            raise EvidenceVerificationError(f"evidence report must be an object: {path}")
        return loaded

    def _verify_report(
        self,
        report: Dict[str, Any],
        *,
        expected_type: str,
        candidate_id: str,
        source_hash: str,
        expected_commit: Optional[str],
    ) -> Dict[str, Any]:
        if report.get("schema_version") != REPORT_SCHEMA_VERSION:
            raise EvidenceVerificationError("unsupported evidence report schema")
        if report.get("report_type") != expected_type:
            raise EvidenceVerificationError(
                f"expected {expected_type} report, got {report.get('report_type')!r}"
            )
        if report.get("signature_alg") != SIGNATURE_ALGORITHM:
            raise EvidenceVerificationError("unsupported evidence signature algorithm")

        report_candidate_id = _require_text(report, "candidate_id")
        report_source_hash = _require_text(report, "source_hash")
        commit = _require_text(report, "commit")
        runner = _require_text(report, "runner")
        nonce = _require_text(report, "nonce")
        dataset_digest = _require_sha256(report, "dataset_digest")
        report_digest = _require_sha256(report, "report_digest")
        created_at = _require_finite_number(report, "created_at")
        signature = _require_text(report, "signature", max_len=128)
        _require_text(report, "key_id")

        if report_candidate_id != candidate_id:
            raise EvidenceVerificationError("evidence report candidate mismatch")
        if report_source_hash != source_hash:
            raise EvidenceVerificationError("evidence report source mismatch")
        if expected_commit is not None and commit != expected_commit:
            raise EvidenceVerificationError("evidence report commit mismatch")
        if self._trusted_runners and runner not in self._trusted_runners:
            raise EvidenceVerificationError(f"untrusted evidence runner: {runner}")

        now = float(self._clock())
        if created_at > now + self._future_skew_s:
            raise EvidenceVerificationError("evidence report timestamp is in the future")
        if now - created_at > self._max_age_s:
            raise EvidenceVerificationError("evidence report expired")

        canonical = _canonical_json(_unsigned_report(report))
        expected_digest = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        if not hmac.compare_digest(expected_digest, report_digest):
            raise EvidenceVerificationError("evidence report digest mismatch")
        expected_signature = hmac.new(
            self._signing_secret,
            canonical,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            raise EvidenceVerificationError("evidence report signature mismatch")

        result = report.get("result")
        if not isinstance(result, dict):
            raise EvidenceVerificationError("evidence report result must be an object")

        return {
            "report_type": expected_type,
            "candidate_id": report_candidate_id,
            "source_hash": report_source_hash,
            "commit": commit,
            "runner": runner,
            "nonce": nonce,
            "dataset_digest": dataset_digest,
            "report_digest": report_digest,
            "created_at": created_at,
            "result": result,
        }

    def _sign_payload(self, payload: Mapping[str, Any]) -> str:
        return hmac.new(
            self._signing_secret,
            _canonical_json(payload),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _receipt_report_entry(report: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "report_type": report["report_type"],
            "report_digest": report["report_digest"],
            "runner": report["runner"],
            "created_at": report["created_at"],
            "dataset_digest": report["dataset_digest"],
            "nonce": report["nonce"],
        }
