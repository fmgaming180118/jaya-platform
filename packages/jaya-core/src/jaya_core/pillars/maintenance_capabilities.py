"""Encrypted recovery, declarative bootstrapping, and legacy migration capabilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import sqlite3
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .agentic_rag_capability import AgenticRAGCapability
from .local_capabilities import LocalPillarError, LocalPillarResult

REGENERATION_CAPABILITY_ID = "core.recovery.regenerate"
BOOTSTRAP_CAPABILITY_ID = "core.bootstrap.declarative"
LEGACY_CAPABILITY_ID = "core.migration.legacy"


def _strict(request: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _text(value: object, field: str, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    candidate = value.strip()
    if not minimum <= len(candidate) <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT", f"{field} must contain {minimum}-{maximum} characters"
        )
    return candidate


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


@contextmanager
def _sqlite_connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class _ProtectedLocalStore:
    def __init__(self, root: Path, signing_key: bytes | None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.signing_key = signing_key
        self._encryption_key = (
            hashlib.sha256(signing_key + b"|jaya-local-maintenance-v1").digest()
            if signing_key
            else None
        )

    def ready(self) -> bool:
        return bool(self.signing_key and len(self.signing_key) >= 32)

    def confined(self, value: object, *, must_exist: bool) -> Path:
        raw = Path(_text(value, "path", 1_024))
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise LocalPillarError("PERMISSION_DENIED", "path escapes maintenance root") from exc
        if must_exist and not candidate.is_file():
            raise LocalPillarError("FILE_NOT_FOUND", "maintenance source was not found")
        return candidate

    def sign(self, value: bytes) -> str:
        if not self.ready() or self.signing_key is None:
            raise LocalPillarError("KEY_NOT_CONFIGURED", "maintenance key is unavailable")
        return hmac.new(self.signing_key, value, hashlib.sha256).hexdigest()

    def verify(self, value: bytes, signature: str) -> None:
        if not hmac.compare_digest(signature, self.sign(value)):
            raise LocalPillarError("SIGNATURE_INVALID", "maintenance signature is invalid")

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> dict[str, str]:
        if self._encryption_key is None:
            raise LocalPillarError("KEY_NOT_CONFIGURED", "maintenance encryption key is unavailable")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._encryption_key).encrypt(nonce, plaintext, associated_data)
        return {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def decrypt(self, envelope: Mapping[str, Any], associated_data: bytes) -> bytes:
        if self._encryption_key is None:
            raise LocalPillarError("KEY_NOT_CONFIGURED", "maintenance encryption key is unavailable")
        try:
            nonce = base64.b64decode(envelope["nonce"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
            return AESGCM(self._encryption_key).decrypt(nonce, ciphertext, associated_data)
        except (KeyError, ValueError, TypeError, Exception) as exc:
            raise LocalPillarError("ARTIFACT_DECRYPTION_FAILED", "protected artifact is invalid") from exc


class NeuralRegenerationCapability(_ProtectedLocalStore):
    """Create encrypted recovery points and restore with quarantine and canary checks."""

    def __init__(self, root: Path, database_path: Path, signing_key: bytes | None) -> None:
        super().__init__(root, signing_key)
        self.database_path = database_path.resolve()
        for name in ("recovery-points", "quarantine"):
            (self.root / name).mkdir(exist_ok=True)
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS recovery_points(
                        artifact_id TEXT NOT NULL, version INTEGER NOT NULL,
                        source_path TEXT NOT NULL, content_type TEXT NOT NULL,
                        plaintext_digest TEXT NOT NULL, envelope_path TEXT NOT NULL,
                        manifest_json TEXT NOT NULL, signature TEXT NOT NULL,
                        created_at REAL NOT NULL, PRIMARY KEY(artifact_id,version)
                    );
                    CREATE TABLE IF NOT EXISTS recovery_ledger(
                        recovery_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL,
                        version INTEGER NOT NULL, destination TEXT NOT NULL,
                        corruption_signal TEXT NOT NULL, status TEXT NOT NULL,
                        duration_ns INTEGER NOT NULL, created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS recovery_locks(
                        artifact_id TEXT PRIMARY KEY, acquired_at REAL NOT NULL
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "recovery catalog unavailable") from exc

    def health_check(self) -> bool:
        return self.ready()

    def backup(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "artifact_id", "version", "source_path", "content_type"},
            {"action", "artifact_id", "version", "source_path", "content_type"},
        )
        artifact_id = _text(request["artifact_id"], "artifact_id", 128)
        version = request["version"]
        if type(version) is not int or version < 1:
            raise LocalPillarError("INVALID_INPUT", "recovery version is invalid")
        source = self.confined(request["source_path"], must_exist=True)
        content_type = _text(request["content_type"], "content_type", 32).upper()
        if content_type not in {"BINARY", "SQLITE", "JSON"}:
            raise LocalPillarError("INVALID_INPUT", "recovery content_type is unsupported")
        try:
            plaintext = source.read_bytes()
        except OSError as exc:
            raise LocalPillarError("FILE_UNAVAILABLE", "recovery source cannot be read") from exc
        if not 1 <= len(plaintext) <= 256 * 1024 * 1024:
            raise LocalPillarError("RESOURCE_LIMIT", "recovery source size is invalid")
        associated = f"{artifact_id}|{version}".encode()
        envelope = self.encrypt(plaintext, associated)
        manifest = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "version": version,
            "source_path": str(source.relative_to(self.root)),
            "content_type": content_type,
            "plaintext_digest": _digest_bytes(plaintext),
            "ciphertext_digest": _digest_bytes(base64.b64decode(envelope["ciphertext"])),
            "size_bytes": len(plaintext),
        }
        signature = self.sign(_canonical(manifest))
        destination = self.root / "recovery-points" / f"{artifact_id}-{version}.recovery.json"
        if destination.exists():
            raise LocalPillarError("RECOVERY_POINT_EXISTS", "recovery point already exists")
        temporary = destination.with_suffix(f".tmp-{uuid.uuid4().hex}")
        wrapper = {"manifest": manifest, "envelope": envelope, "signature": signature}
        try:
            temporary.write_bytes(_canonical(wrapper))
            os.replace(temporary, destination)
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO recovery_points VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        artifact_id,
                        version,
                        manifest["source_path"],
                        content_type,
                        manifest["plaintext_digest"],
                        str(destination.relative_to(self.root)),
                        _canonical(manifest).decode(),
                        signature,
                        time.time(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise LocalPillarError("RECOVERY_POINT_EXISTS", "recovery point already exists") from exc
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise LocalPillarError("STORAGE_UNAVAILABLE", "recovery point was not written") from exc
        return LocalPillarResult("P009", "ENCRYPTED_RECOVERY_POINT_CREATED", {**manifest, "signature": signature})

    @staticmethod
    def _canary(path: Path, content_type: str) -> None:
        if content_type == "SQLITE":
            try:
                with _sqlite_connection(path) as connection:
                    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise LocalPillarError("CANARY_FAILED", "restored SQLite state is corrupt")
            except sqlite3.Error as exc:
                raise LocalPillarError("CANARY_FAILED", "restored SQLite state is invalid") from exc
        elif content_type == "JSON":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise LocalPillarError("CANARY_FAILED", "restored JSON state is invalid") from exc

    def restore(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "artifact_id", "version", "destination_path", "corruption_signal"},
            {"action", "artifact_id", "version", "destination_path", "corruption_signal"},
        )
        artifact_id = _text(request["artifact_id"], "artifact_id", 128)
        version = request["version"]
        if type(version) is not int or version < 1:
            raise LocalPillarError("INVALID_INPUT", "recovery version is invalid")
        signal = _text(request["corruption_signal"], "corruption_signal", 64).upper()
        if signal not in {"CHECKSUM_MISMATCH", "READ_FAILURE", "CONSISTENCY_FAILURE"}:
            raise LocalPillarError("INVALID_INPUT", "corruption signal is unsupported")
        destination = self.confined(request["destination_path"], must_exist=False)
        started = time.perf_counter_ns()
        recovery_id = uuid.uuid4().hex
        quarantine: Path | None = None
        status = "FAILED"
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO recovery_locks VALUES(?,?)", (artifact_id, time.time())
                )
                row = connection.execute(
                    "SELECT * FROM recovery_points WHERE artifact_id=? AND version=?",
                    (artifact_id, version),
                ).fetchone()
            if row is None:
                raise LocalPillarError("RECOVERY_POINT_NOT_FOUND", "recovery point was not found")
            wrapper_path = self.root / row["envelope_path"]
            try:
                wrapper = json.loads(wrapper_path.read_bytes())
            except (OSError, ValueError, TypeError) as exc:
                raise LocalPillarError("RECOVERY_POINT_CORRUPT", "recovery wrapper is invalid") from exc
            manifest = wrapper.get("manifest")
            if not isinstance(manifest, Mapping):
                raise LocalPillarError("RECOVERY_POINT_CORRUPT", "recovery manifest is invalid")
            self.verify(_canonical(manifest), str(wrapper.get("signature", "")))
            associated = f"{artifact_id}|{version}".encode()
            plaintext = self.decrypt(wrapper.get("envelope", {}), associated)
            if _digest_bytes(plaintext) != manifest.get("plaintext_digest"):
                raise LocalPillarError("RECOVERY_POINT_CORRUPT", "recovery plaintext digest differs")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                quarantine = self.root / "quarantine" / f"{destination.name}-{recovery_id}.previous"
                os.replace(destination, quarantine)
            temporary = destination.with_name(f".{destination.name}.restore-{recovery_id}.tmp")
            try:
                with temporary.open("xb") as output:
                    output.write(plaintext)
                    output.flush()
                    os.fsync(output.fileno())
                if _digest_bytes(temporary.read_bytes()) != manifest["plaintext_digest"]:
                    raise LocalPillarError("RESTORE_VERIFICATION_FAILED", "restored bytes differ")
                self._canary(temporary, str(manifest["content_type"]))
                os.replace(temporary, destination)
            except (OSError, LocalPillarError):
                temporary.unlink(missing_ok=True)
                if quarantine is not None and quarantine.exists() and not destination.exists():
                    os.replace(quarantine, destination)
                raise
            status = "RESTORED"
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("RECOVERY_LOCKED", "recovery is already in progress") from exc
        except LocalPillarError:
            status = "FAILED"
            raise
        except OSError as exc:
            status = "FAILED"
            raise LocalPillarError("RESTORE_IO_FAILED", "state restore failed") from exc
        finally:
            duration = max(1, time.perf_counter_ns() - started)
            try:
                with _sqlite_connection(self.database_path) as connection:
                    connection.execute("DELETE FROM recovery_locks WHERE artifact_id=?", (artifact_id,))
                    connection.execute(
                        "INSERT INTO recovery_ledger VALUES(?,?,?,?,?,?,?,?)",
                        (recovery_id, artifact_id, version, str(destination.relative_to(self.root)), signal, status, duration, time.time()),
                    )
            except sqlite3.Error as exc:
                raise LocalPillarError(
                    "RECOVERY_LEDGER_FAILED",
                    "recovery outcome could not be persisted and the capability failed closed",
                ) from exc
        return LocalPillarResult(
            "P009",
            "STATE_REGENERATED",
            {
                "recovery_id": recovery_id,
                "artifact_id": artifact_id,
                "version": version,
                "destination": str(destination.relative_to(self.root)),
                "content_digest": manifest["plaintext_digest"],
                "canary": "PASSED",
                "duration_ns": duration,
                "previous_state_quarantined": quarantine is not None,
            },
        )

    def diagnose(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "artifact_id", "target_path"},
            {"action", "artifact_id", "target_path"},
        )
        artifact_id = _text(request["artifact_id"], "artifact_id", 128)
        target = self.confined(request["target_path"], must_exist=False)
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT * FROM recovery_points WHERE artifact_id=? ORDER BY version DESC LIMIT 1",
                    (artifact_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "recovery catalog cannot be read") from exc

        if row is None:
            return LocalPillarResult(
                "P009",
                "DIAGNOSIS_COMPLETED",
                {
                    "artifact_id": artifact_id,
                    "target_path": str(target.relative_to(self.root)),
                    "diagnosis": "NO_RECOVERY_POINT_BASELINE",
                    "damaged": False,
                    "latest_version": None,
                },
            )

        manifest = json.loads(row["manifest_json"])
        expected_digest = manifest.get("plaintext_digest")
        content_type = manifest.get("content_type", "BINARY")
        latest_version = int(row["version"])

        if not target.exists():
            return LocalPillarResult(
                "P009",
                "DIAGNOSIS_COMPLETED",
                {
                    "artifact_id": artifact_id,
                    "target_path": str(target.relative_to(self.root)),
                    "diagnosis": "FILE_MISSING",
                    "damaged": True,
                    "latest_version": latest_version,
                    "expected_digest": expected_digest,
                    "recommended_action": "RESTORE_REQUIRED",
                },
            )

        try:
            raw = target.read_bytes()
            current_digest = _digest_bytes(raw)
        except OSError as exc:
            raise LocalPillarError("FILE_UNAVAILABLE", "target file cannot be read") from exc

        if current_digest != expected_digest:
            return LocalPillarResult(
                "P009",
                "DIAGNOSIS_COMPLETED",
                {
                    "artifact_id": artifact_id,
                    "target_path": str(target.relative_to(self.root)),
                    "diagnosis": "CHECKSUM_MISMATCH",
                    "damaged": True,
                    "current_digest": current_digest,
                    "expected_digest": expected_digest,
                    "latest_version": latest_version,
                    "recommended_action": "RESTORE_REQUIRED",
                },
            )

        try:
            self._canary(target, content_type)
        except LocalPillarError:
            return LocalPillarResult(
                "P009",
                "DIAGNOSIS_COMPLETED",
                {
                    "artifact_id": artifact_id,
                    "target_path": str(target.relative_to(self.root)),
                    "diagnosis": "CORRUPT_CANARY_FAILED",
                    "damaged": True,
                    "current_digest": current_digest,
                    "expected_digest": expected_digest,
                    "latest_version": latest_version,
                    "recommended_action": "RESTORE_REQUIRED",
                },
            )

        return LocalPillarResult(
            "P009",
            "DIAGNOSIS_COMPLETED",
            {
                "artifact_id": artifact_id,
                "target_path": str(target.relative_to(self.root)),
                "diagnosis": "HEALTHY",
                "damaged": False,
                "current_digest": current_digest,
                "expected_digest": expected_digest,
                "latest_version": latest_version,
                "recommended_action": "NONE",
            },
        )

    def list_recovery_points(self, request: Mapping[str, Any]) -> LocalPillarResult:
        artifact_id = request.get("artifact_id")
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                if artifact_id is not None:
                    aid = _text(artifact_id, "artifact_id", 128)
                    rows = connection.execute(
                        "SELECT artifact_id, version, content_type, plaintext_digest, created_at FROM recovery_points WHERE artifact_id=? ORDER BY version DESC",
                        (aid,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT artifact_id, version, content_type, plaintext_digest, created_at FROM recovery_points ORDER BY created_at DESC"
                    ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "recovery points cannot be listed") from exc

        points = [
            {
                "artifact_id": r["artifact_id"],
                "version": r["version"],
                "content_type": r["content_type"],
                "plaintext_digest": r["plaintext_digest"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return LocalPillarResult("P009", "RECOVERY_POINTS_LISTED", {"recovery_points": points, "count": len(points)})

    def inspect_recovery_point(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "artifact_id", "version"},
            {"action", "artifact_id", "version"},
        )
        artifact_id = _text(request["artifact_id"], "artifact_id", 128)
        version = request["version"]
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT * FROM recovery_points WHERE artifact_id=? AND version=?",
                    (artifact_id, version),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "recovery catalog cannot be read") from exc

        if row is None:
            raise LocalPillarError("RECOVERY_POINT_NOT_FOUND", "recovery point was not found")

        wrapper_path = self.root / row["envelope_path"]
        try:
            wrapper = json.loads(wrapper_path.read_bytes())
            manifest = wrapper.get("manifest", {})
            self.verify(_canonical(manifest), str(wrapper.get("signature", "")))
        except (OSError, ValueError, TypeError) as exc:
            raise LocalPillarError("RECOVERY_POINT_CORRUPT", "recovery wrapper is invalid") from exc

        return LocalPillarResult(
            "P009",
            "RECOVERY_POINT_INSPECTED",
            {
                "artifact_id": artifact_id,
                "version": version,
                "manifest": manifest,
                "signature_valid": True,
                "envelope_exists": wrapper_path.exists(),
            },
        )

    def rollback_quarantine(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "destination_path", "recovery_id"},
            {"action", "destination_path", "recovery_id"},
        )
        destination = self.confined(request["destination_path"], must_exist=False)
        recovery_id = _text(request["recovery_id"], "recovery_id", 128)
        quarantine = self.root / "quarantine" / f"{destination.name}-{recovery_id}.previous"
        if not quarantine.exists():
            raise LocalPillarError("QUARANTINE_NOT_FOUND", "quarantined state was not found")

        try:
            os.replace(quarantine, destination)
        except OSError as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "rollback of quarantine failed") from exc

        return LocalPillarResult(
            "P009",
            "QUARANTINE_RESTORED",
            {
                "destination": str(destination.relative_to(self.root)),
                "recovery_id": recovery_id,
                "status": "RESTORED_TO_PREVIOUS",
            },
        )

    def metrics(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT recovery_id, artifact_id, version, status, duration_ns, created_at FROM recovery_ledger ORDER BY created_at DESC"
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "recovery ledger cannot be read") from exc

        total = len(rows)
        successes = sum(1 for r in rows if r["status"] == "RESTORED")
        durations_ms = [r["duration_ns"] / 1_000_000.0 for r in rows if r["duration_ns"] > 0]
        mean_rto_ms = round(float(sum(durations_ms) / len(durations_ms)), 4) if durations_ms else 0.0

        return LocalPillarResult(
            "P009",
            "RECOVERY_METRICS_COMPUTED",
            {
                "total_recoveries": total,
                "successful_recoveries": successes,
                "success_rate": round(successes / total, 4) if total > 0 else 1.0,
                "mean_rto_ms": mean_rto_ms,
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action")
        if action == "backup":
            return self.backup(request)
        if action == "restore":
            return self.restore(request)
        if action == "diagnose":
            return self.diagnose(request)
        if action == "list":
            return self.list_recovery_points(request)
        if action == "inspect":
            return self.inspect_recovery_point(request)
        if action == "rollback_quarantine":
            return self.rollback_quarantine(request)
        if action == "metrics":
            return self.metrics(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", "regeneration action is unsupported")


class SelfBootstrappingCapability(_ProtectedLocalStore):
    """Build, test, approve, install, execute, and roll back declarative capabilities."""

    OPERATIONS = frozenset({"SUM", "MEAN", "MAX", "MIN"})

    def __init__(
        self,
        root: Path,
        database_path: Path,
        signing_key: bytes | None,
        rag: AgenticRAGCapability,
    ) -> None:
        super().__init__(root, signing_key)
        self.database_path = database_path.resolve()
        self.rag = rag
        for name in ("candidates", "staged", "installed", "retired"):
            (self.root / name).mkdir(exist_ok=True)
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS bootstrap_candidates(
                    candidate_id TEXT PRIMARY KEY, capability_id TEXT NOT NULL,
                    artifact_digest TEXT NOT NULL, validation_digest TEXT,
                    status TEXT NOT NULL, artifact_path TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL)"""
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "bootstrap catalog unavailable") from exc

    def health_check(self) -> bool:
        return self.ready()

    @staticmethod
    def _apply(operation: str, values: object) -> float:
        if not isinstance(values, list) or not 1 <= len(values) <= 100_000:
            raise LocalPillarError("RESOURCE_LIMIT", "values must contain 1-100000 items")
        try:
            numbers = [float(item) for item in values]
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "values must be numeric") from exc
        if not all(math.isfinite(item) for item in numbers):
            raise LocalPillarError("INVALID_INPUT", "values must be finite")
        if operation == "SUM":
            return sum(numbers)
        if operation == "MEAN":
            return sum(numbers) / len(numbers)
        if operation == "MAX":
            return max(numbers)
        if operation == "MIN":
            return min(numbers)
        raise LocalPillarError("OPERATION_UNSUPPORTED", "declarative operation is unsupported")

    def propose(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "candidate_id", "capability_id", "capability_gap", "operation", "evidence_ids", "acceptance_cases"},
            {"action", "candidate_id", "capability_id", "capability_gap", "operation", "evidence_ids", "acceptance_cases"},
        )
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        capability_id = _text(request["capability_id"], "capability_id", 128)
        gap = _text(request["capability_gap"], "capability_gap", 2_000, 8)
        operation = _text(request["operation"], "operation", 32).upper()
        if operation not in self.OPERATIONS:
            raise LocalPillarError("OPERATION_UNSUPPORTED", "candidate operation is unsupported")
        evidence = request["evidence_ids"]
        cases = request["acceptance_cases"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 32:
            raise LocalPillarError("RESOURCE_LIMIT", "evidence_ids must contain 1-32 items")
        evidence_ids = [_text(item, "evidence_id", 128) for item in evidence]
        if not all(self.rag.evidence_exists(item) for item in evidence_ids):
            raise LocalPillarError("INVALID_EVIDENCE", "candidate evidence is unavailable")
        if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
            raise LocalPillarError("RESOURCE_LIMIT", "acceptance_cases must contain 1-64 items")
        normalized_cases = []
        for case in cases:
            if not isinstance(case, Mapping) or set(case) != {"values", "expected"}:
                raise LocalPillarError("INVALID_INPUT", "acceptance case schema is invalid")
            expected = float(case["expected"])
            if not math.isfinite(expected):
                raise LocalPillarError("INVALID_INPUT", "acceptance expected must be finite")
            normalized_cases.append({"values": case["values"], "expected": expected})
        manifest = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "capability_id": capability_id,
            "capability_gap": gap,
            "operation": operation,
            "evidence_ids": evidence_ids,
            "acceptance_cases": normalized_cases,
            "required_gates": ["BUILD", "TEST", "OWNER_APPROVAL", "CANARY", "ROLLBACK"],
        }
        signature = self.sign(_canonical(manifest))
        wrapper = {"manifest": manifest, "signature": signature}
        artifact = self.root / "candidates" / f"{candidate_id}.candidate.json"
        try:
            with artifact.open("xb") as output:
                output.write(_canonical(wrapper))
            digest = _digest_bytes(artifact.read_bytes())
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO bootstrap_candidates VALUES(?,?,?,?,?,?,?,?)",
                    (candidate_id, capability_id, digest, None, "PROPOSED", str(artifact.relative_to(self.root)), time.time(), time.time()),
                )
        except sqlite3.IntegrityError as exc:
            artifact.unlink(missing_ok=True)
            raise LocalPillarError("CANDIDATE_EXISTS", "candidate_id already exists") from exc
        except FileExistsError as exc:
            raise LocalPillarError("CANDIDATE_EXISTS", "candidate_id already exists") from exc
        except OSError as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "candidate artifact was not stored") from exc
        return LocalPillarResult("P028", "BOOTSTRAP_CANDIDATE_PROPOSED", {"candidate_id": candidate_id, "artifact_digest": digest, "applied": False})

    def _load(self, candidate_id: str, directory: str = "candidates") -> tuple[dict[str, Any], bytes]:
        path = self.root / directory / f"{candidate_id}.candidate.json"
        try:
            raw = path.read_bytes()
            wrapper = json.loads(raw)
            manifest = wrapper["manifest"]
            self.verify(_canonical(manifest), wrapper["signature"])
        except LocalPillarError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise LocalPillarError("CANDIDATE_CORRUPT", "candidate artifact is invalid") from exc
        return manifest, raw

    def validate(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "candidate_id"}, {"action", "candidate_id"})
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        manifest, _ = self._load(candidate_id)
        results = []
        for index, case in enumerate(manifest["acceptance_cases"]):
            actual = self._apply(manifest["operation"], case["values"])
            passed = math.isclose(actual, float(case["expected"]), rel_tol=1e-9, abs_tol=1e-12)
            results.append({"case": index, "actual": actual, "expected": case["expected"], "passed": passed})
        validation = {"candidate_id": candidate_id, "results": results, "passed": all(item["passed"] for item in results)}
        validation_digest = _digest_bytes(_canonical(validation))
        status = "VALIDATED" if validation["passed"] else "REJECTED"
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "UPDATE bootstrap_candidates SET validation_digest=?,status=?,updated_at=? WHERE candidate_id=?",
                    (validation_digest, status, time.time(), candidate_id),
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "candidate validation was not stored") from exc
        return LocalPillarResult("P028", "BOOTSTRAP_CANDIDATE_VALIDATED", {**validation, "validation_digest": validation_digest})

    def plan_dependencies(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "candidate_id", "dependencies", "offline_policy"},
            {"action", "candidate_id", "dependencies"},
        )
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        deps_input = request["dependencies"]
        offline_policy = str(request.get("offline_policy", "DEFAULT_DENY")).upper()
        if not isinstance(deps_input, list):
            raise LocalPillarError("INVALID_INPUT", "dependencies must be a list")

        graph: dict[str, list[str]] = {}
        for item in deps_input:
            if not isinstance(item, Mapping) or "capability_id" not in item:
                raise LocalPillarError("INVALID_INPUT", "dependency item schema is invalid")
            cid = _text(item["capability_id"], "capability_id", 128)
            source = str(item.get("source", "local")).lower()
            if source != "local" and offline_policy == "DEFAULT_DENY":
                raise LocalPillarError(
                    "NETWORK_DISALLOWED",
                    f"dependency '{cid}' requests external source '{source}' but offline policy prohibits downloads",
                )
            depends_on = item.get("depends_on", [])
            if not isinstance(depends_on, list):
                raise LocalPillarError("INVALID_INPUT", "depends_on must be a list")
            graph[cid] = [_text(d, "dependency_id", 128) for d in depends_on]

        visited: dict[str, int] = {}
        order: list[str] = []

        def dfs(node: str, path: list[str]) -> None:
            state = visited.get(node, 0)
            if state == 1:
                cycle_str = " -> ".join(path + [node])
                raise LocalPillarError("DEPENDENCY_CYCLE", f"cycle detected in dependency graph: {cycle_str}")
            if state == 2:
                return
            visited[node] = 1
            for neighbor in graph.get(node, []):
                if neighbor not in graph:
                    with _sqlite_connection(self.database_path) as connection:
                        row = connection.execute(
                            "SELECT status FROM bootstrap_candidates WHERE capability_id=? AND status='INSTALLED'",
                            (neighbor,),
                        ).fetchone()
                    if row is None and neighbor not in {"core.runtime.base", "core.rag.evidence"}:
                        raise LocalPillarError("MISSING_DEPENDENCY", f"missing required dependency: {neighbor}")
                else:
                    dfs(neighbor, path + [node])
            visited[node] = 2
            order.append(node)

        for node in list(graph.keys()):
            if visited.get(node, 0) == 0:
                dfs(node, [])

        return LocalPillarResult(
            "P028",
            "DEPENDENCY_PLAN_COMPUTED",
            {
                "candidate_id": candidate_id,
                "execution_order": order,
                "total_dependencies": len(graph),
                "offline_policy": offline_policy,
                "cycle_detected": False,
            },
        )

    def stage(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "candidate_id"}, {"action", "candidate_id"})
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        with _sqlite_connection(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM bootstrap_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise LocalPillarError("CANDIDATE_NOT_FOUND", "candidate does not exist")
        if row["status"] not in {"VALIDATED", "STAGED"}:
            raise LocalPillarError("CANDIDATE_NOT_VALIDATED", f"candidate status is '{row['status']}', cannot stage")

        manifest, raw = self._load(candidate_id, "candidates")
        digest = _digest_bytes(raw)
        if digest != row["artifact_digest"]:
            raise LocalPillarError("CANDIDATE_CORRUPT", "candidate artifact digest differs")

        staged_path = self.root / "staged" / f"{candidate_id}.candidate.json"
        temporary = staged_path.with_suffix(f".tmp-{uuid.uuid4().hex}")
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, staged_path)
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "UPDATE bootstrap_candidates SET status='STAGED',updated_at=? WHERE candidate_id=?",
                    (time.time(), candidate_id),
                )
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise LocalPillarError("STORAGE_UNAVAILABLE", "candidate could not be staged") from exc

        return LocalPillarResult(
            "P028",
            "BOOTSTRAP_CANDIDATE_STAGED",
            {
                "candidate_id": candidate_id,
                "artifact_digest": digest,
                "status": "STAGED",
                "staged_path": str(staged_path.relative_to(self.root)),
            },
        )

    def install(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "candidate_id", "approval_id", "approved_by", "signature"},
            {"action", "candidate_id", "approval_id", "approved_by", "signature"},
        )
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        approval_id = _text(request["approval_id"], "approval_id", 128)
        approved_by = _text(request["approved_by"], "approved_by", 128)
        signature = _text(request["signature"], "signature", 128)
        dir_to_load = "staged" if (self.root / "staged" / f"{candidate_id}.candidate.json").exists() else "candidates"
        manifest, raw = self._load(candidate_id, dir_to_load)
        with _sqlite_connection(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM bootstrap_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None or row["status"] not in {"VALIDATED", "STAGED"} or not row["validation_digest"]:
            raise LocalPillarError("CANDIDATE_NOT_VALIDATED", "candidate has not passed validation")
        material = f"install|{candidate_id}|{row['artifact_digest']}|{row['validation_digest']}|{approval_id}|{approved_by}".encode()
        self.verify(material, signature)
        for case in manifest["acceptance_cases"]:
            actual = self._apply(manifest["operation"], case["values"])
            if not math.isclose(actual, float(case["expected"]), rel_tol=1e-9, abs_tol=1e-12):
                raise LocalPillarError("CANARY_FAILED", "candidate canary failed")
        destination = self.root / "installed" / f"{candidate_id}.candidate.json"
        if destination.exists():
            raise LocalPillarError("CANDIDATE_INSTALLED", "candidate is already installed")
        try:
            destination.write_bytes(raw)
            (self.root / "staged" / f"{candidate_id}.candidate.json").unlink(missing_ok=True)
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "UPDATE bootstrap_candidates SET status='INSTALLED',updated_at=? WHERE candidate_id=?",
                    (time.time(), candidate_id),
                )
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise LocalPillarError("INSTALL_FAILED", "candidate could not be installed") from exc
        return LocalPillarResult("P028", "BOOTSTRAP_CANDIDATE_INSTALLED", {"candidate_id": candidate_id, "capability_id": manifest["capability_id"], "canary": "PASSED"})

    def invoke(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "candidate_id", "values"}, {"action", "candidate_id", "values"})
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        manifest, _ = self._load(candidate_id, "installed")
        result = self._apply(manifest["operation"], request["values"])
        return LocalPillarResult("P028", "INSTALLED_CAPABILITY_EXECUTED", {"candidate_id": candidate_id, "capability_id": manifest["capability_id"], "operation": manifest["operation"], "result": result})

    def rollback(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "candidate_id", "rollback_id", "approved_by", "signature"},
            {"action", "candidate_id", "rollback_id", "approved_by", "signature"},
        )
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        rollback_id = _text(request["rollback_id"], "rollback_id", 128)
        approved_by = _text(request["approved_by"], "approved_by", 128)
        signature = _text(request["signature"], "signature", 128)
        with _sqlite_connection(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM bootstrap_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None or row["status"] != "INSTALLED":
            raise LocalPillarError("CANDIDATE_NOT_INSTALLED", "candidate is not installed")
        material = f"rollback_bootstrap|{candidate_id}|{row['artifact_digest']}|{rollback_id}|{approved_by}".encode()
        self.verify(material, signature)
        source = self.root / "installed" / f"{candidate_id}.candidate.json"
        safe_rb = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in rollback_id)
        destination = self.root / "retired" / f"{candidate_id}-{safe_rb}.candidate.json"
        try:
            os.replace(source, destination)
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "UPDATE bootstrap_candidates SET status='ROLLED_BACK',updated_at=? WHERE candidate_id=?",
                    (time.time(), candidate_id),
                )
        except OSError as exc:
            raise LocalPillarError("ROLLBACK_FAILED", "installed candidate could not be retired") from exc
        return LocalPillarResult(
            "P028",
            "BOOTSTRAP_CANDIDATE_ROLLED_BACK",
            {"candidate_id": candidate_id, "rollback_id": rollback_id},
        )

    def list_candidates(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        status_filter = request.get("status") if request else None
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                if status_filter:
                    rows = connection.execute(
                        "SELECT candidate_id, capability_id, artifact_digest, validation_digest, status, created_at, updated_at "
                        "FROM bootstrap_candidates WHERE status=? ORDER BY created_at DESC",
                        (status_filter.upper(),),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT candidate_id, capability_id, artifact_digest, validation_digest, status, created_at, updated_at "
                        "FROM bootstrap_candidates ORDER BY created_at DESC"
                    ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "candidate catalog cannot be read") from exc

        candidates = [
            {
                "candidate_id": r["candidate_id"],
                "capability_id": r["capability_id"],
                "status": r["status"],
                "artifact_digest": r["artifact_digest"],
                "validation_digest": r["validation_digest"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
        return LocalPillarResult(
            "P028",
            "BOOTSTRAP_CANDIDATES_LISTED",
            {"candidates": candidates, "count": len(candidates)},
        )

    def inspect_candidate(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "candidate_id"}, {"action", "candidate_id"})
        candidate_id = _text(request["candidate_id"], "candidate_id", 128)
        with _sqlite_connection(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM bootstrap_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise LocalPillarError("CANDIDATE_NOT_FOUND", "candidate was not found")

        status = row["status"]
        if status == "INSTALLED":
            manifest, _ = self._load(candidate_id, "installed")
        elif status == "ROLLED_BACK":
            retired_files = list((self.root / "retired").glob(f"{candidate_id}-*.candidate.json"))
            if retired_files:
                raw = retired_files[0].read_bytes()
                wrapper = json.loads(raw)
                manifest = wrapper["manifest"]
            else:
                manifest, _ = self._load(candidate_id, "candidates")
        elif (self.root / "staged" / f"{candidate_id}.candidate.json").exists():
            manifest, _ = self._load(candidate_id, "staged")
        else:
            manifest, _ = self._load(candidate_id, "candidates")

        return LocalPillarResult(
            "P028",
            "BOOTSTRAP_CANDIDATE_INSPECTED",
            {
                "candidate_id": candidate_id,
                "capability_id": row["capability_id"],
                "status": status,
                "manifest": manifest,
                "artifact_digest": row["artifact_digest"],
                "validation_digest": row["validation_digest"],
                "signature_verified": True,
            },
        )

    def metrics(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute("SELECT status, created_at, updated_at FROM bootstrap_candidates").fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "bootstrap metrics cannot be read") from exc

        counts: dict[str, int] = {}
        for r in rows:
            st = r["status"]
            counts[st] = counts.get(st, 0) + 1

        total = len(rows)
        return LocalPillarResult(
            "P028",
            "BOOTSTRAP_METRICS_COMPUTED",
            {
                "total_candidates": total,
                "proposed": counts.get("PROPOSED", 0),
                "validated": counts.get("VALIDATED", 0),
                "staged": counts.get("STAGED", 0),
                "installed": counts.get("INSTALLED", 0),
                "rolled_back": counts.get("ROLLED_BACK", 0),
                "rejected": counts.get("REJECTED", 0),
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        actions = {
            "propose": self.propose,
            "validate": self.validate,
            "plan_dependencies": self.plan_dependencies,
            "stage": self.stage,
            "install": self.install,
            "invoke": self.invoke,
            "rollback": self.rollback,
            "list": self.list_candidates,
            "inspect": self.inspect_candidate,
            "metrics": self.metrics,
        }
        handler = actions.get(request.get("action"))
        if handler is None:
            raise LocalPillarError("UNSUPPORTED_ACTION", "bootstrap action is unsupported")
        return handler(request)


class LegacyProtocolCapability(_ProtectedLocalStore):
    """Migrate one explicitly supported legacy format into encrypted current capsules."""

    LEGACY_MAGIC = b"JAYA_LEGACY_V1\n"
    CURRENT_MAGIC = b"JAYA_CURRENT_V2\n"
    MAX_LEGACY_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB maximum legacy payload bound

    def __init__(self, root: Path, database_path: Path, signing_key: bytes | None) -> None:
        super().__init__(root, signing_key)
        self.database_path = database_path.resolve()
        for name in ("legacy-backups", "migration-quarantine"):
            (self.root / name).mkdir(exist_ok=True)
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS migration_ledger(
                    migration_id TEXT PRIMARY KEY, source_digest TEXT UNIQUE NOT NULL,
                    output_digest TEXT NOT NULL, source_path TEXT NOT NULL,
                    output_path TEXT NOT NULL, backup_path TEXT NOT NULL,
                    owner_id TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL)"""
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "migration ledger unavailable") from exc

    def health_check(self) -> bool:
        return self.ready()

    def check_compatibility(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "source_path"}, {"action", "source_path"})
        source = self.confined(request["source_path"], must_exist=True)
        raw = source.read_bytes()
        if len(raw) > self.MAX_LEGACY_SIZE_BYTES:
            raise LocalPillarError(
                "INPUT_TOO_LARGE",
                f"legacy artifact exceeds maximum size of {self.MAX_LEGACY_SIZE_BYTES} bytes",
            )
        if not raw.startswith(self.LEGACY_MAGIC):
            raise LocalPillarError("LEGACY_VERSION_UNSUPPORTED", "legacy magic/version is unsupported")
        try:
            payload = json.loads(raw[len(self.LEGACY_MAGIC) :])
        except (ValueError, TypeError) as exc:
            raise LocalPillarError("LEGACY_TRUNCATED", "legacy payload is invalid") from exc
        required = {"schema_version", "brain_id", "identity", "memory", "policy"}
        if not isinstance(payload, Mapping) or set(payload) != required or payload["schema_version"] != 1:
            raise LocalPillarError("LEGACY_LAYOUT_UNSUPPORTED", "legacy layout is unsupported")
        if not isinstance(payload["identity"], Mapping) or not isinstance(payload["memory"], list) or not isinstance(payload["policy"], Mapping):
            raise LocalPillarError("LEGACY_LAYOUT_UNSUPPORTED", "legacy sections are invalid")
        source_digest = _digest_bytes(raw)
        with _sqlite_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT migration_id, status FROM migration_ledger WHERE source_digest=?",
                (source_digest,),
            ).fetchone()
        already_migrated = row is not None
        return LocalPillarResult(
            "P019",
            "LEGACY_COMPATIBILITY_CHECKED",
            {
                "source_path": str(source.relative_to(self.root)),
                "source_digest": source_digest,
                "brain_id": payload["brain_id"],
                "schema_version": 1,
                "compatible": not already_migrated,
                "already_migrated": already_migrated,
                "migration_id": row[0] if row else None,
                "memory_items_count": len(payload["memory"]),
                "sections": ["identity", "memory", "policy"],
            },
        )

    def migrate(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "source_path", "output_path", "owner_id", "approval_id", "signature"},
            {"action", "source_path", "output_path", "owner_id", "approval_id", "signature"},
        )
        source = self.confined(request["source_path"], must_exist=True)
        output = self.confined(request["output_path"], must_exist=False)
        if output.exists():
            raise LocalPillarError("DESTINATION_EXISTS", "migration refuses to overwrite output")
        owner = _text(request["owner_id"], "owner_id", 128)
        approval_id = _text(request["approval_id"], "approval_id", 128)
        signature = _text(request["signature"], "signature", 128)
        raw = source.read_bytes()
        if len(raw) > self.MAX_LEGACY_SIZE_BYTES:
            raise LocalPillarError(
                "INPUT_TOO_LARGE",
                f"legacy artifact exceeds maximum size of {self.MAX_LEGACY_SIZE_BYTES} bytes",
            )
        if not raw.startswith(self.LEGACY_MAGIC):
            raise LocalPillarError("LEGACY_VERSION_UNSUPPORTED", "legacy magic/version is unsupported")
        try:
            payload = json.loads(raw[len(self.LEGACY_MAGIC) :])
        except (ValueError, TypeError) as exc:
            raise LocalPillarError("LEGACY_TRUNCATED", "legacy payload is invalid") from exc
        required = {"schema_version", "brain_id", "identity", "memory", "policy"}
        if not isinstance(payload, Mapping) or set(payload) != required or payload["schema_version"] != 1:
            raise LocalPillarError("LEGACY_LAYOUT_UNSUPPORTED", "legacy layout is unsupported")
        if not isinstance(payload["identity"], Mapping) or not isinstance(payload["memory"], list) or not isinstance(payload["policy"], Mapping):
            raise LocalPillarError("LEGACY_LAYOUT_UNSUPPORTED", "legacy sections are invalid")
        source_digest = _digest_bytes(raw)
        material = f"migrate|{source_digest}|{output.relative_to(self.root)}|{approval_id}|{owner}".encode()
        self.verify(material, signature)
        migration_id = uuid.uuid4().hex
        backup_data = self.encrypt(raw, f"legacy-backup|{migration_id}".encode())
        backup_path = self.root / "legacy-backups" / f"{migration_id}.legacy.enc.json"
        now_ts = time.time()
        current_payload = {
            "schema_version": 2,
            "brain_id": payload["brain_id"],
            "identity": payload["identity"],
            "memory": payload["memory"],
            "policy": payload["policy"],
            "migration": {
                "migration_id": migration_id,
                "source_digest": source_digest,
                "source_version": 1,
                "migrated_at": now_ts,
            },
        }
        encrypted = self.encrypt(_canonical(current_payload), f"current|{migration_id}".encode())
        wrapper = {"migration_id": migration_id, "envelope": encrypted, "plaintext_digest": _digest_bytes(_canonical(current_payload))}
        output_bytes = self.CURRENT_MAGIC + _canonical(wrapper)
        temporary = output.with_name(f".{output.name}.migration-{migration_id}.tmp")
        try:
            backup_path.write_bytes(_canonical(backup_data))
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(output_bytes)
            verify_wrapper = json.loads(temporary.read_bytes()[len(self.CURRENT_MAGIC) :])
            verified = self.decrypt(verify_wrapper["envelope"], f"current|{migration_id}".encode())
            if json.loads(verified) != current_payload:
                raise LocalPillarError("MIGRATION_VALIDATION_FAILED", "current capsule differs")
            os.replace(temporary, output)
            output_digest = _digest_bytes(output_bytes)
            with _sqlite_connection(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO migration_ledger VALUES(?,?,?,?,?,?,?,?,?)",
                    (migration_id, source_digest, output_digest, str(source.relative_to(self.root)), str(output.relative_to(self.root)), str(backup_path.relative_to(self.root)), owner, "MIGRATED", now_ts),
                )
        except sqlite3.IntegrityError as exc:
            temporary.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
            raise LocalPillarError("MIGRATION_DUPLICATE", "legacy source was already migrated") from exc
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise LocalPillarError("MIGRATION_IO_FAILED", "legacy migration failed") from exc
        return LocalPillarResult("P019", "LEGACY_CAPSULE_MIGRATED", {"migration_id": migration_id, "source_digest": source_digest, "output_digest": output_digest, "output_path": str(output.relative_to(self.root)), "backup_path": str(backup_path.relative_to(self.root)), "sections_preserved": ["identity", "memory", "policy"]})

    def inspect(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "path"}, {"action", "path"})
        path = self.confined(request["path"], must_exist=True)
        raw = path.read_bytes()
        if not raw.startswith(self.CURRENT_MAGIC):
            raise LocalPillarError("CURRENT_FORMAT_INVALID", "current capsule magic is invalid")
        try:
            wrapper = json.loads(raw[len(self.CURRENT_MAGIC) :])
            migration_id = wrapper["migration_id"]
            plaintext = self.decrypt(wrapper["envelope"], f"current|{migration_id}".encode())
            payload = json.loads(plaintext)
        except (ValueError, KeyError, TypeError) as exc:
            raise LocalPillarError("CURRENT_FORMAT_INVALID", "current capsule is invalid") from exc
        return LocalPillarResult("P019", "CURRENT_CAPSULE_VERIFIED", {"migration_id": migration_id, "brain_id": payload["brain_id"], "sections": ["identity", "memory", "policy"], "content_digest": _digest_bytes(raw)})

    def list_migrations(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        status_filter = request.get("status") if request else None
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                if status_filter:
                    rows = connection.execute(
                        "SELECT * FROM migration_ledger WHERE status=? ORDER BY created_at DESC",
                        (status_filter,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT * FROM migration_ledger ORDER BY created_at DESC"
                    ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "migration ledger cannot be queried") from exc

        return LocalPillarResult(
            "P019",
            "MIGRATIONS_LISTED",
            {"migrations": [dict(r) for r in rows], "count": len(rows)},
        )

    def inspect_migration(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "migration_id"}, {"action", "migration_id"})
        migration_id = _text(request["migration_id"], "migration_id", 128)
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT * FROM migration_ledger WHERE migration_id=?", (migration_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "migration ledger cannot be read") from exc

        if row is None:
            raise LocalPillarError("MIGRATION_NOT_FOUND", "migration record was not found")

        output_file = self.root / row["output_path"]
        return LocalPillarResult(
            "P019",
            "MIGRATION_INSPECTED",
            {
                "migration_id": migration_id,
                "record": dict(row),
                "output_exists": output_file.exists(),
            },
        )

    def metrics(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute("SELECT status, created_at FROM migration_ledger").fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "migration metrics cannot be read") from exc

        total = len(rows)
        active = sum(1 for r in rows if r["status"] == "MIGRATED")
        rolled_back = sum(1 for r in rows if r["status"] == "ROLLED_BACK")
        backup_files_count = len(list((self.root / "legacy-backups").glob("*.legacy.enc.json")))
        quarantine_files_count = len(list((self.root / "migration-quarantine").glob("*.jaya")))

        return LocalPillarResult(
            "P019",
            "LEGACY_METRICS_COMPUTED",
            {
                "total_migrations": total,
                "active_migrated": active,
                "rolled_back": rolled_back,
                "backup_files_count": backup_files_count,
                "quarantine_files_count": quarantine_files_count,
            },
        )

    def rollback(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "migration_id", "rollback_id", "owner_id", "signature"},
            {"action", "migration_id", "rollback_id", "owner_id", "signature"},
        )
        migration_id = _text(request["migration_id"], "migration_id", 128)
        rollback_id = _text(request["rollback_id"], "rollback_id", 128)
        owner = _text(request["owner_id"], "owner_id", 128)
        signature = _text(request["signature"], "signature", 128)
        try:
            with _sqlite_connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT * FROM migration_ledger WHERE migration_id=?", (migration_id,)
                ).fetchone()
                if row is None or row["status"] != "MIGRATED":
                    raise LocalPillarError("MIGRATION_NOT_ACTIVE", "migration is not active")
                if row["owner_id"] != owner:
                    raise LocalPillarError("APPROVAL_DENIED", "migration owner differs")
                material = f"rollback_migration|{migration_id}|{row['output_digest']}|{rollback_id}|{owner}".encode()
                self.verify(material, signature)
                output = self.root / row["output_path"]
                safe_rb = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in rollback_id)
                quarantine = self.root / "migration-quarantine" / f"{migration_id}-{safe_rb}.jaya"
                os.replace(output, quarantine)
                connection.execute(
                    "UPDATE migration_ledger SET status='ROLLED_BACK' WHERE migration_id=?",
                    (migration_id,),
                )
        except LocalPillarError:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise LocalPillarError("ROLLBACK_FAILED", "legacy migration rollback failed") from exc
        return LocalPillarResult(
            "P019",
            "LEGACY_MIGRATION_ROLLED_BACK",
            {"migration_id": migration_id, "rollback_id": rollback_id},
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        actions = {
            "check_compatibility": self.check_compatibility,
            "migrate": self.migrate,
            "inspect": self.inspect,
            "list": self.list_migrations,
            "inspect_migration": self.inspect_migration,
            "rollback": self.rollback,
            "metrics": self.metrics,
        }
        handler = actions.get(request.get("action"))
        if handler is None:
            raise LocalPillarError("UNSUPPORTED_ACTION", "legacy action is unsupported")
        return handler(request)
