"""Trusted-runner CLI for producing signed evolution evidence reports.

This producer executes pytest itself and consumes a complete benchmark observation.
It never accepts caller-supplied pass booleans, never invents metrics, and refuses
to operate without an explicit runner identity, real commit/dataset digests, and a
secret supplied by the runner environment or its mounted secret file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.engine.evolution_evidence import (  # noqa: E402
    EvidenceReceiptVerifier,
    EvidenceVerificationError,
)

REPORT_SCHEMA_VERSION = "jaya-evolution-evidence-report-v1"
BENCHMARK_OBSERVATION_SCHEMA = "jaya-evolution-benchmark-observation-v1"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_DIGEST = f"sha256:{'0' * 64}"
_MAX_OBSERVATION_BYTES = 1_048_576
_MAX_SECRET_FILE_BYTES = 4_096


class EvidenceGenerationError(RuntimeError):
    """Typed, secret-free evidence producer rejection."""


@dataclass(frozen=True)
class RunnerIdentity:
    runner_id: str
    key_id: str
    commit: str
    dataset_digest: str

    @classmethod
    def validated(
        cls,
        *,
        runner_id: str,
        key_id: str,
        commit: str,
        dataset_digest: str,
    ) -> "RunnerIdentity":
        return cls(
            runner_id=_identifier(runner_id, "runner_id"),
            key_id=_identifier(key_id, "key_id"),
            commit=_commit(commit),
            dataset_digest=_digest(dataset_digest, "dataset_digest"),
        )


@dataclass(frozen=True)
class TestObservation:
    passed: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    tests_error: int
    tests_skipped: int
    exit_code: int
    command_digest: str
    stdout_digest: str
    stderr_digest: str


@dataclass(frozen=True)
class BenchmarkObservation:
    created_at: float
    exit_code: int
    gate_failures: tuple[str, ...]
    observed_perf_gain_pct: float
    ram_delta_pct: float
    cpu_delta_pct: float
    command_digest: str
    stdout_digest: str
    stderr_digest: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.gate_failures


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise EvidenceGenerationError(f"{field} must be a safe explicit identifier")
    return value


def _commit(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _COMMIT_RE.fullmatch(normalized) or set(normalized) == {"0"}:
        raise EvidenceGenerationError(
            "expected_commit must be a full non-zero Git SHA-1 or SHA-256 commit"
        )
    return normalized


def _digest(value: Any, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _DIGEST_RE.fullmatch(normalized) or normalized == _ZERO_DIGEST:
        raise EvidenceGenerationError(
            f"{field} must be a non-zero sha256:<64 lowercase hex> digest"
        )
    return normalized


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceGenerationError(f"{field} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise EvidenceGenerationError(f"{field} must be a finite number")
    return parsed


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _command_digest(command: Sequence[str]) -> str:
    encoded = json.dumps(
        list(command),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def load_signing_secret(
    environment: Mapping[str, str] | None = None,
    *,
    direct_variable: str = "JAYA_EVIDENCE_SIGNING_SECRET",
    file_variable: str = "JAYA_EVIDENCE_SIGNING_SECRET_FILE",
) -> bytes:
    """Load exactly one secret source; there is deliberately no fallback key."""
    source = environment if environment is not None else os.environ
    direct = source.get(direct_variable, "")
    secret_file = source.get(file_variable, "")
    if bool(direct) == bool(secret_file):
        raise EvidenceGenerationError(
            f"configure exactly one of {direct_variable} or {file_variable}"
        )
    if direct:
        secret = direct.encode("utf-8")
    else:
        path = Path(secret_file)
        if path.is_symlink() or not path.is_file():
            raise EvidenceGenerationError("evidence signing secret file is not regular")
        if path.stat().st_size > _MAX_SECRET_FILE_BYTES:
            raise EvidenceGenerationError("evidence signing secret file is too large")
        try:
            secret = path.read_bytes().strip()
        except OSError as exc:
            raise EvidenceGenerationError(
                "evidence signing secret file cannot be read"
            ) from exc
    if len(secret) < 32:
        raise EvidenceGenerationError(
            "evidence signing secret must contain at least 32 bytes"
        )
    return secret


def repository_head(cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceGenerationError("cannot resolve repository HEAD") from exc
    return _commit(result.stdout.strip())


def _parse_junit(path: Path) -> tuple[int, int, int, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise EvidenceGenerationError("pytest did not produce valid JUnit XML") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise EvidenceGenerationError("pytest JUnit XML contains no test suite")

    def total(attribute: str) -> int:
        try:
            return sum(int(suite.attrib.get(attribute, "0")) for suite in suites)
        except ValueError as exc:
            raise EvidenceGenerationError("pytest JUnit counters are invalid") from exc

    return total("tests"), total("failures"), total("errors"), total("skipped")


def run_pytest(
    test_paths: Sequence[str],
    *,
    cwd: Path,
    timeout_s: float,
) -> TestObservation:
    """Execute pytest without a shell and derive pass/fail from exit + JUnit."""
    if not test_paths or any(
        not isinstance(path, str) or not path for path in test_paths
    ):
        raise EvidenceGenerationError("at least one explicit pytest path is required")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise EvidenceGenerationError("test timeout must be positive")
    with tempfile.TemporaryDirectory(prefix="jaya-evidence-") as temporary:
        junit_path = Path(temporary) / "pytest-junit.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            *test_paths,
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit_path}",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise EvidenceGenerationError("pytest evidence command timed out") from exc
        except OSError as exc:
            raise EvidenceGenerationError(
                "pytest evidence command could not start"
            ) from exc
        tests_run, failed, errors, skipped = _parse_junit(junit_path)

    tests_passed = tests_run - failed - errors - skipped
    passed = (
        result.returncode == 0
        and tests_run > 0
        and failed == 0
        and errors == 0
        and tests_passed > 0
    )
    return TestObservation(
        passed=passed,
        tests_run=tests_run,
        tests_passed=tests_passed,
        tests_failed=failed,
        tests_error=errors,
        tests_skipped=skipped,
        exit_code=result.returncode,
        command_digest=_command_digest(command),
        stdout_digest=_sha256_bytes(result.stdout),
        stderr_digest=_sha256_bytes(result.stderr),
    )


def load_benchmark_observation(
    path_value: str | Path,
    *,
    identity: RunnerIdentity,
    candidate_id: str,
    source_hash: str,
) -> BenchmarkObservation:
    """Validate a complete machine observation; missing metrics never default."""
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise EvidenceGenerationError("benchmark observation is not a regular file")
    if path.stat().st_size > _MAX_OBSERVATION_BYTES:
        raise EvidenceGenerationError("benchmark observation is too large")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceGenerationError("benchmark observation is invalid JSON") from exc
    expected_keys = {
        "schema_version",
        "candidate_id",
        "source_hash",
        "commit",
        "runner",
        "dataset_digest",
        "created_at",
        "exit_code",
        "gate_failures",
        "metrics",
        "command_digest",
        "stdout_digest",
        "stderr_digest",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise EvidenceGenerationError(
            "benchmark observation contains missing or unsupported fields"
        )
    if document["schema_version"] != BENCHMARK_OBSERVATION_SCHEMA:
        raise EvidenceGenerationError("unsupported benchmark observation schema")
    if document["candidate_id"] != candidate_id:
        raise EvidenceGenerationError("benchmark candidate mismatch")
    if document["source_hash"] != source_hash:
        raise EvidenceGenerationError("benchmark source mismatch")
    if _commit(document["commit"]) != identity.commit:
        raise EvidenceGenerationError("benchmark commit mismatch")
    if _identifier(document["runner"], "benchmark runner") != identity.runner_id:
        raise EvidenceGenerationError("benchmark runner mismatch")
    if (
        _digest(document["dataset_digest"], "benchmark dataset_digest")
        != identity.dataset_digest
    ):
        raise EvidenceGenerationError("benchmark dataset mismatch")
    created_at = _finite_number(document["created_at"], "benchmark created_at")
    if created_at <= 0:
        raise EvidenceGenerationError("benchmark created_at must be positive")
    exit_code = document["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise EvidenceGenerationError("benchmark exit_code must be an integer")
    failures = document["gate_failures"]
    if not isinstance(failures, list) or any(
        not isinstance(item, str) or not item.strip() for item in failures
    ):
        raise EvidenceGenerationError("benchmark gate_failures must be a string list")
    metrics = document["metrics"]
    required_metrics = {
        "observed_perf_gain_pct",
        "ram_delta_pct",
        "cpu_delta_pct",
    }
    if not isinstance(metrics, dict) or set(metrics) != required_metrics:
        raise EvidenceGenerationError(
            "benchmark metrics must contain all measured gate fields without defaults"
        )
    return BenchmarkObservation(
        created_at=created_at,
        exit_code=exit_code,
        gate_failures=tuple(failures),
        observed_perf_gain_pct=_finite_number(
            metrics["observed_perf_gain_pct"],
            "observed_perf_gain_pct",
        ),
        ram_delta_pct=_finite_number(metrics["ram_delta_pct"], "ram_delta_pct"),
        cpu_delta_pct=_finite_number(metrics["cpu_delta_pct"], "cpu_delta_pct"),
        command_digest=_digest(document["command_digest"], "command_digest"),
        stdout_digest=_digest(document["stdout_digest"], "stdout_digest"),
        stderr_digest=_digest(document["stderr_digest"], "stderr_digest"),
    )


def create_test_report(
    observation: TestObservation,
    *,
    identity: RunnerIdentity,
    candidate_id: str,
    source_hash: str,
    created_at: float,
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "test",
        "candidate_id": candidate_id,
        "source_hash": source_hash,
        "commit": identity.commit,
        "runner": identity.runner_id,
        "created_at": created_at,
        "dataset_digest": identity.dataset_digest,
        "nonce": f"test-{uuid.uuid4().hex}",
        "result": {
            "passed": observation.passed,
            "tests_run": observation.tests_run,
            "tests_passed": observation.tests_passed,
            "tests_failed": observation.tests_failed,
            "tests_error": observation.tests_error,
            "tests_skipped": observation.tests_skipped,
            "exit_code": observation.exit_code,
            "command_digest": observation.command_digest,
            "stdout_digest": observation.stdout_digest,
            "stderr_digest": observation.stderr_digest,
        },
        "key_id": identity.key_id,
        "signature_alg": "HMAC-SHA256",
    }


def create_benchmark_report(
    observation: BenchmarkObservation,
    *,
    identity: RunnerIdentity,
    candidate_id: str,
    source_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "benchmark",
        "candidate_id": candidate_id,
        "source_hash": source_hash,
        "commit": identity.commit,
        "runner": identity.runner_id,
        "created_at": observation.created_at,
        "dataset_digest": identity.dataset_digest,
        "nonce": f"benchmark-{uuid.uuid4().hex}",
        "result": {
            "passed": observation.passed,
            "observed_perf_gain_pct": observation.observed_perf_gain_pct,
            "ram_delta_pct": observation.ram_delta_pct,
            "cpu_delta_pct": observation.cpu_delta_pct,
            "exit_code": observation.exit_code,
            "gate_failures": list(observation.gate_failures),
            "command_digest": observation.command_digest,
            "stdout_digest": observation.stdout_digest,
            "stderr_digest": observation.stderr_digest,
        },
        "key_id": identity.key_id,
        "signature_alg": "HMAC-SHA256",
    }


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        document,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate trusted, signed evolution evidence reports"
    )
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--source-hash", required=True)
    parser.add_argument("--runner-id", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--dataset-digest", required=True)
    parser.add_argument("--test-paths", nargs="+", required=True)
    parser.add_argument("--benchmark-observation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--test-timeout-s", type=float, default=600.0)
    parser.add_argument(
        "--secret-env",
        default="JAYA_EVIDENCE_SIGNING_SECRET",
        help="environment variable holding the runner signing secret",
    )
    parser.add_argument(
        "--secret-file-env",
        default="JAYA_EVIDENCE_SIGNING_SECRET_FILE",
        help="environment variable holding a mounted secret-file path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        candidate_id = _identifier(args.candidate_id, "candidate_id")
        source_hash = str(args.source_hash or "").strip()
        if not source_hash or len(source_hash) > 256:
            raise EvidenceGenerationError("source_hash must be explicit and bounded")
        identity = RunnerIdentity.validated(
            runner_id=args.runner_id,
            key_id=args.key_id,
            commit=args.expected_commit,
            dataset_digest=args.dataset_digest,
        )
        if repository_head(Path.cwd()) != identity.commit:
            raise EvidenceGenerationError(
                "expected_commit does not match repository HEAD"
            )
        secret = load_signing_secret(
            direct_variable=args.secret_env,
            file_variable=args.secret_file_env,
        )
        test_observation = run_pytest(
            args.test_paths,
            cwd=Path.cwd(),
            timeout_s=args.test_timeout_s,
        )
        benchmark_observation = load_benchmark_observation(
            args.benchmark_observation,
            identity=identity,
            candidate_id=candidate_id,
            source_hash=source_hash,
        )
        now = time.time()
        signer = EvidenceReceiptVerifier(
            secret,
            trusted_signers={identity.runner_id: {identity.key_id}},
            clock=lambda: now,
        )
        test_report = signer.sign_report(
            create_test_report(
                test_observation,
                identity=identity,
                candidate_id=candidate_id,
                source_hash=source_hash,
                created_at=now,
            )
        )
        benchmark_report = signer.sign_report(
            create_benchmark_report(
                benchmark_observation,
                identity=identity,
                candidate_id=candidate_id,
                source_hash=source_hash,
            )
        )
        with tempfile.TemporaryDirectory(prefix="jaya-evidence-verify-") as temporary:
            test_temp = Path(temporary) / "test.json"
            benchmark_temp = Path(temporary) / "benchmark.json"
            test_temp.write_text(json.dumps(test_report), encoding="utf-8")
            benchmark_temp.write_text(json.dumps(benchmark_report), encoding="utf-8")
            signer.verify_reports(
                test_temp,
                benchmark_temp,
                candidate_id=candidate_id,
                source_hash=source_hash,
                expected_commit=identity.commit,
            )

        output_dir = Path(args.output_dir)
        _atomic_json(output_dir / f"{candidate_id}-tests.json", test_report)
        _atomic_json(output_dir / f"{candidate_id}-benchmark.json", benchmark_report)
        return 0
    except (EvidenceGenerationError, EvidenceVerificationError, ValueError) as exc:
        print(f"evidence generation rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
