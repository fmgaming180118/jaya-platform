"""Integrity-checked SQLite backup and rollback for JAYA Core state."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class SnapshotFailureCode(str, Enum):
    PATH_OUTSIDE_DATA_ROOT = "PATH_OUTSIDE_DATA_ROOT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_NOT_SQLITE = "SOURCE_NOT_SQLITE"
    BACKUP_FAILED = "BACKUP_FAILED"
    SNAPSHOT_UNAVAILABLE = "SNAPSHOT_UNAVAILABLE"
    INTEGRITY_FAILED = "INTEGRITY_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class SnapshotError(RuntimeError):
    def __init__(self, code: SnapshotFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SnapshotReceipt:
    snapshot_id: str
    operation: str
    source_path: str
    snapshot_path: str
    sha256: str
    size_bytes: int
    created_at: str
    parent_snapshot_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CoreSnapshotManager:
    """Create online SQLite snapshots and offline atomic rollback receipts."""

    def __init__(self, data_root: Path | str) -> None:
        self.data_root = Path(data_root).resolve()
        if not self.data_root.exists() or not self.data_root.is_dir():
            raise SnapshotError(
                SnapshotFailureCode.SOURCE_UNAVAILABLE,
                "Core data root does not exist",
            )
        self.snapshot_dir = self.data_root / "snapshots"
        self.snapshot_dir.mkdir(exist_ok=True)

    def create(self, source: Path | str) -> SnapshotReceipt:
        source_path = self._contained(source)
        if not source_path.exists() or not source_path.is_file():
            raise SnapshotError(
                SnapshotFailureCode.SOURCE_UNAVAILABLE,
                "Core database is unavailable",
            )
        self._verify_sqlite(source_path)
        timestamp = datetime.now(timezone.utc)
        timestamp_id = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
        snapshot_path = self.snapshot_dir / f"{timestamp_id}-{source_path.stem}.db"
        try:
            with closing(sqlite3.connect(source_path)) as source_connection:
                with closing(sqlite3.connect(snapshot_path)) as destination:
                    source_connection.backup(destination)
            self._verify_sqlite(snapshot_path)
        except (OSError, sqlite3.Error) as exc:
            raise SnapshotError(
                SnapshotFailureCode.BACKUP_FAILED,
                "failed to create Core SQLite snapshot",
            ) from exc
        digest = self._sha256(snapshot_path)
        receipt = SnapshotReceipt(
            snapshot_id=f"{timestamp_id}-{digest[:12]}",
            operation="BACKUP",
            source_path=str(source_path),
            snapshot_path=str(snapshot_path),
            sha256=digest,
            size_bytes=snapshot_path.stat().st_size,
            created_at=timestamp.isoformat(),
        )
        self._write_receipt(receipt)
        return receipt

    def verify(self, receipt: SnapshotReceipt) -> bool:
        try:
            snapshot = self._contained(receipt.snapshot_path)
            if not snapshot.is_file() or snapshot.stat().st_size != receipt.size_bytes:
                return False
            if self._sha256(snapshot) != receipt.sha256:
                return False
            self._verify_sqlite(snapshot)
        except (OSError, SnapshotError):
            return False
        return True

    def rollback(self, receipt: SnapshotReceipt) -> SnapshotReceipt:
        if not self.verify(receipt):
            raise SnapshotError(
                SnapshotFailureCode.INTEGRITY_FAILED,
                "snapshot failed integrity verification",
            )
        source = self._contained(receipt.source_path)
        snapshot = self._contained(receipt.snapshot_path)
        parent = self.create(source)
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{source.name}.",
                suffix=".rollback",
                dir=source.parent,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            shutil.copy2(snapshot, temporary_path)
            if self._sha256(temporary_path) != receipt.sha256:
                raise SnapshotError(
                    SnapshotFailureCode.INTEGRITY_FAILED,
                    "rollback copy digest mismatch",
                )
            self._verify_sqlite(temporary_path)
            os.replace(temporary_path, source)
            temporary_path = None
            self._verify_sqlite(source)
        except SnapshotError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise SnapshotError(
                SnapshotFailureCode.ROLLBACK_FAILED,
                "failed to rollback Core database",
            ) from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

        restored_digest = self._sha256(source)
        rollback_receipt = SnapshotReceipt(
            snapshot_id=(
                f"rollback-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
            ),
            operation="ROLLBACK",
            source_path=str(source),
            snapshot_path=str(snapshot),
            sha256=restored_digest,
            size_bytes=source.stat().st_size,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_snapshot_id=parent.snapshot_id,
        )
        self._write_receipt(rollback_receipt)
        return rollback_receipt

    def load_receipt(self, snapshot_id: str) -> SnapshotReceipt:
        if not snapshot_id or any(
            char
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for char in snapshot_id
        ):
            raise SnapshotError(
                SnapshotFailureCode.SNAPSHOT_UNAVAILABLE,
                "snapshot id is invalid",
            )
        receipt_path = self.snapshot_dir / f"{snapshot_id}.json"
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            return SnapshotReceipt(**payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SnapshotError(
                SnapshotFailureCode.SNAPSHOT_UNAVAILABLE,
                "snapshot receipt is unavailable",
            ) from exc

    def _contained(self, path: Path | str) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.data_root)
        except ValueError as exc:
            raise SnapshotError(
                SnapshotFailureCode.PATH_OUTSIDE_DATA_ROOT,
                "snapshot path escaped Core data root",
            ) from exc
        return resolved

    def _write_receipt(self, receipt: SnapshotReceipt) -> None:
        destination = self.snapshot_dir / f"{receipt.snapshot_id}.json"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=self.snapshot_dir,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(receipt.to_dict(), handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except OSError as exc:
            raise SnapshotError(
                SnapshotFailureCode.BACKUP_FAILED,
                "failed to persist snapshot receipt",
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _verify_sqlite(path: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ) as connection:
                row = connection.execute("PRAGMA quick_check").fetchone()
        except sqlite3.Error as exc:
            raise SnapshotError(
                SnapshotFailureCode.SOURCE_NOT_SQLITE,
                "file is not a readable SQLite database",
            ) from exc
        if row is None or row[0] != "ok":
            raise SnapshotError(
                SnapshotFailureCode.SOURCE_NOT_SQLITE,
                "SQLite quick_check failed",
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


__all__ = [
    "CoreSnapshotManager",
    "SnapshotError",
    "SnapshotFailureCode",
    "SnapshotReceipt",
]
