"""
production_backup_rollback.py — Production Backup & Automated Rollback Engine.

Manages immutable database snapshots, SHA-256 integrity verification,
and clean zero-downtime rollback recovery for JAYA OS in Production Stage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ProductionBackupRollback")


@dataclass
class BackupSnapshot:
    snapshot_id: str
    timestamp: float
    source_path: str
    backup_path: str
    sha256: str
    size_bytes: int


class ProductionBackupManager:
    """Manages persistent database backups and rollback snapshots."""

    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or (Path.home() / ".jaya" / "production_backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.backup_dir / "backup_index.json"
        self._snapshots: List[BackupSnapshot] = self._load_index()

    def _load_index(self) -> List[BackupSnapshot]:
        if not self.index_file.exists():
            return []
        try:
            raw = json.loads(self.index_fs.read_text(encoding="utf-8"))
            return [BackupSnapshot(**item) for item in raw]
        except Exception as err:
            logger.warning("Failed to load backup index: %s", err)
            return []

    def _save_index(self) -> None:
        raw = [asdict(snap) for snap in self._snapshots]
        self.index_fs.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def _compute_hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def create_backup(self, target_file: Path) -> BackupSnapshot:
        """Create a cryptographically verified snapshot of a production database or file."""
        if not target_file.exists():
            raise FileNotFoundError(f"Target file missing for backup: {target_file}")

        snapshot_id = f"snap_{int(time.time())}_{target_file.stem}"
        backup_filename = f"{snapshot_id}{target_file.suffix}"
        backup_path = self.backup_dir / backup_filename

        shutil.copy2(target_file, backup_path)
        sha256_hash = self._compute_hash(backup_path)
        size_bytes = backup_path.stat().st_size

        snapshot = BackupSnapshot(
            snapshot_id=snapshot_id,
            timestamp=time.time(),
            source_path=str(target_file.resolve()),
            backup_path=str(backup_path.resolve()),
            sha256=sha256_hash,
            size_bytes=size_bytes,
        )

        self._snapshots.append(snapshot)
        self._save_index()
        logger.info("Created production backup snapshot: %s (SHA256: %s)", snapshot_id, sha256_hash[:16])
        return snapshot

    def verify_snapshot(self, snapshot: BackupSnapshot) -> bool:
        """Verify the cryptographic integrity of a backup snapshot."""
        path = Path(snapshot.backup_path)
        if not path.exists():
            return False
        current_hash = self._compute_hash(path)
        return current_hash == snapshot.sha256

    def rollback(self, snapshot_id: Optional[str] = None) -> bool:
        """Rollback target file to last known good snapshot or specific snapshot_id."""
        if not self._snapshots:
            logger.error("No backup snapshots available for rollback.")
            return False

        if snapshot_id:
            target_snap = next((s for s in self._snapshots if s.snapshot_id == snapshot_id), None)
        else:
            target_snap = self._snapshots[-1]

        if not target_snap:
            logger.error("Snapshot ID not found: %s", snapshot_id)
            return False

        if not self.verify_snapshot(target_snap):
            logger.error("Snapshot integrity verification failed for %s!", target_snap.snapshot_id)
            return False

        source = Path(target_snap.backup_path)
        dest = Path(target_snap.source_path)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        logger.info("Successfully rolled back %s to snapshot %s", dest.name, target_snap.snapshot_id)
        return True

    def list_snapshots(self) -> List[BackupSnapshot]:
        return list(self._snapshots)
