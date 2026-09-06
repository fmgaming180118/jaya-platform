"""
backup.py — SQLite Hot-Backup, Integrity Verification, & Crash Recovery Engine.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Tuple

from jaya_core.security.capsule import CapsuleKind, JayaCapsuleCodec

logger = logging.getLogger(__name__)


class SQLiteBackupEngine:
    """Manage SQLite hot-backups, integrity checks, and recovery drills."""

    def create_backup(self, source_db_path: str, backup_dest_path: str) -> bool:
        if not os.path.exists(source_db_path):
            raise FileNotFoundError(f"Source database not found: {source_db_path}")

        os.makedirs(os.path.dirname(backup_dest_path), exist_ok=True)

        source_conn = None
        backup_conn = None
        try:
            source_conn = sqlite3.connect(source_db_path)
            backup_conn = sqlite3.connect(backup_dest_path)
            with backup_conn:
                source_conn.backup(backup_conn)
            logger.info(
                "Successfully backed up %s to %s", source_db_path, backup_dest_path
            )
            return True
        except Exception as exc:
            logger.error("Failed to create backup of %s: %s", source_db_path, exc)
            return False
        finally:
            if source_conn:
                source_conn.close()
            if backup_conn:
                backup_conn.close()

    def verify_integrity(self, db_path: str) -> bool:
        if not os.path.exists(db_path):
            return False

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            return bool(res and res[0] == "ok")
        except Exception as exc:
            logger.error("Database integrity check failed for %s: %s", db_path, exc)
            return False
        finally:
            if conn:
                conn.close()

    def restore_from_backup(self, backup_path: str, target_db_path: str) -> bool:
        if not self.verify_integrity(backup_path):
            logger.error(
                "Cannot restore: Backup file %s is invalid or corrupted", backup_path
            )
            return False

        try:
            os.makedirs(os.path.dirname(target_db_path), exist_ok=True)
            shutil.copy2(backup_path, target_db_path)
            logger.info(
                "Successfully restored database to %s from %s",
                target_db_path,
                backup_path,
            )
            return True
        except Exception as exc:
            logger.error("Failed to restore database from %s: %s", backup_path, exc)
            return False

    def run_crash_recovery_drill(
        self, active_db_path: str, backup_db_path: str
    ) -> Tuple[bool, str]:
        """Simulate corruption and prove that the backup restores cleanly."""
        # 1. Create backup
        if not self.create_backup(active_db_path, backup_db_path):
            return False, "Failed to create initial backup for drill"

        # 2. Simulate corruption on active DB
        with open(active_db_path, "wb") as f:
            f.write(b"CORRUPTED_HEADER_DATA_FAIL")

        # 3. Detect corruption
        is_intact = self.verify_integrity(active_db_path)
        if is_intact:
            return False, "Failed to simulate corruption"

        # 4. Perform crash recovery restore
        restored = self.restore_from_backup(backup_db_path, active_db_path)
        if not restored:
            return False, "Failed to restore from backup during drill"

        # 5. Verify restored integrity
        final_ok = self.verify_integrity(active_db_path)
        if not final_ok:
            return False, "Restored database failed final integrity check"

        return True, "Crash recovery drill PASSED successfully"

    def create_secure_backup(
        self,
        source_db_path: str | Path,
        capsule_path: str | Path,
        codec: JayaCapsuleCodec,
        *,
        subject: str,
    ) -> Path:
        """Create a consistent SQLite hot-backup sealed as one P13 capsule."""

        source = Path(source_db_path).resolve()
        destination = Path(capsule_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Source database not found: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".jaya-backup-",
            suffix=".sqlite3",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        source_connection: sqlite3.Connection | None = None
        backup_connection: sqlite3.Connection | None = None
        try:
            source_connection = sqlite3.connect(source)
            backup_connection = sqlite3.connect(temporary)
            with backup_connection:
                source_connection.backup(backup_connection)
            if not self.verify_integrity(str(temporary)):
                raise RuntimeError("temporary SQLite backup failed integrity check")
            return codec.seal_file(
                temporary,
                destination,
                kind=CapsuleKind.BACKUP,
                subject=subject,
            )
        finally:
            if backup_connection is not None:
                backup_connection.close()
            if source_connection is not None:
                source_connection.close()
            temporary.unlink(missing_ok=True)

    def restore_secure_backup(
        self,
        capsule_path: str | Path,
        target_db_path: str | Path,
        codec: JayaCapsuleCodec,
        *,
        subject: str,
    ) -> Path:
        """Verify/decrypt a capsule, then atomically restore a healthy database."""

        target = Path(target_db_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = codec.open_file(
            capsule_path,
            expected_kind=CapsuleKind.BACKUP,
            expected_subject=subject,
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".restore", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if not self.verify_integrity(str(temporary)):
                raise RuntimeError("decrypted SQLite backup failed integrity check")
            os.replace(temporary, target)
            return target
        finally:
            temporary.unlink(missing_ok=True)
