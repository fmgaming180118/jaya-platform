"""Research-owned SQLite maintenance and review-only milestone packaging."""

from __future__ import annotations

import gc
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol


class EcosystemBoundaryError(RuntimeError):
    """Raised when Research is asked to mutate another module directly."""


class EcosystemPublisher(Protocol):
    """Public adapter implemented by a separately authorized promotion gate."""

    def publish(
        self,
        artifact_path: Path,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Publish one immutable candidate and return an audit receipt."""
        ...


class MemoryManager:
    """Maintain Research state without copying it into runtime modules."""

    def __init__(
        self,
        db_path: Path | None = None,
        packages_dir: Path | None = None,
        *,
        milestone_interval: int = 50,
    ) -> None:
        source_dir = Path(__file__).resolve().parent
        self.db_path = Path(
            db_path or source_dir.parent / "data" / "agentic_jarvis.db"
        ).resolve()
        self.packages_dir = Path(
            packages_dir or source_dir.parent / "data" / "packages"
        ).resolve()
        if int(milestone_interval) <= 0:
            raise ValueError("milestone_interval must be positive")
        self.milestone_interval = int(milestone_interval)
        self.packages_dir.mkdir(parents=True, exist_ok=True)

    def optimize_sqlite_database(self) -> dict[str, Any]:
        """Enable bounded SQLite settings and indexes on Research-owned state."""
        if not self.db_path.is_file():
            return {"success": False, "error": "Database file missing"}
        try:
            with sqlite3.connect(str(self.db_path)) as connection:
                connection.execute("PRAGMA journal_mode=WAL;")
                connection.execute("PRAGMA synchronous=NORMAL;")
                connection.execute("PRAGMA temp_store=MEMORY;")
                connection.execute("PRAGMA cache_size=-64000;")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_patches_applied_at "
                    "ON jarvis_patches(applied_at DESC);"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_patches_topic "
                    "ON jarvis_patches(topic);"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_directives_status "
                    "ON proactive_directives(status);"
                )
        except (OSError, sqlite3.Error) as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "wal_enabled": True, "indexes_active": True}

    def check_and_compile_milestone(self) -> dict[str, Any]:
        """Create a non-executable candidate at each configured milestone."""
        if not self.db_path.is_file():
            return {"compiled": False, "reason": "No DB"}
        try:
            with sqlite3.connect(str(self.db_path)) as connection:
                row = connection.execute(
                    "SELECT COUNT(*) FROM jarvis_patches"
                ).fetchone()
        except sqlite3.Error as exc:
            return {"compiled": False, "error": str(exc)}
        count = int(row[0] if row else 0)
        milestone = count // self.milestone_interval
        if count <= 0 or count % self.milestone_interval:
            return {
                "compiled": False,
                "total_patches": count,
                "next_milestone": (milestone + 1) * self.milestone_interval,
            }

        package_name = f"JAYA_MILESTONE_v{count}_m{milestone}.jay"
        package_path = self.packages_dir / package_name
        unsigned = {
            "candidate_format": "jaya-research-milestone/1",
            "package_name": package_name,
            "milestone": milestone,
            "total_patches": count,
            "compiled_at": time.time(),
            "status": "PENDING_REVIEW",
            "executable": False,
        }
        canonical = json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        payload = {
            **unsigned,
            "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
        package_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        self.prune_old_packages(keep_latest=3)
        return {
            "compiled": True,
            "package_name": package_name,
            "milestone": milestone,
            "total_patches": count,
        }

    def prune_old_packages(self, keep_latest: int = 3) -> int:
        """Remove old Research-owned snapshots and return the removal count."""
        if int(keep_latest) < 1:
            raise ValueError("keep_latest must be at least one")
        packages = sorted(
            self.packages_dir.glob("JAYA_MILESTONE_*.jay"),
            key=os.path.getmtime,
        )
        obsolete = packages[: -int(keep_latest)]
        for package in obsolete:
            package.unlink()
        return len(obsolete)

    @staticmethod
    def enforce_memory_cap(max_ram_mb: int = 200) -> dict[str, Any]:
        """Collect Python garbage and report, rather than claim, process RSS."""
        if int(max_ram_mb) <= 0:
            raise ValueError("max_ram_mb must be positive")
        collected = gc.collect()
        rss_mb = 0.0
        try:
            import psutil

            process = psutil.Process(os.getpid())
            rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except (ImportError, OSError):
            pass
        return {
            "objects_collected": collected,
            "current_rss_mb": rss_mb,
            "cap_mb": int(max_ram_mb),
            "within_cap": rss_mb <= int(max_ram_mb) if rss_mb > 0 else None,
        }

    def sync_to_ecosystem(
        self,
        publisher: EcosystemPublisher | None = None,
    ) -> dict[str, Any]:
        """Publish candidates through an injected boundary; never copy the DB."""
        if publisher is None:
            raise EcosystemBoundaryError(
                "direct ecosystem synchronization is disabled; inject an "
                "authorized artifact publisher"
            )

        receipts: list[Mapping[str, Any]] = []
        for package in sorted(self.packages_dir.glob("JAYA_MILESTONE_*.jay")):
            receipt = publisher.publish(
                package.resolve(),
                {
                    "producer": "JAYA_RESEARCH",
                    "artifact_kind": "milestone_candidate",
                    "review_required": True,
                    "database_included": False,
                },
            )
            if not isinstance(receipt, Mapping):
                raise EcosystemBoundaryError(
                    "artifact publisher returned an invalid audit receipt"
                )
            receipts.append(dict(receipt))
        return {
            "success": True,
            "artifacts_published": len(receipts),
            "database_copied": False,
            "receipts": [dict(receipt) for receipt in receipts],
        }


if __name__ == "__main__":
    manager = MemoryManager()
    print("SQLite Optimization:", manager.optimize_sqlite_database())
    print("Milestone Check:", manager.check_and_compile_milestone())
    print("RAM Cap Assurance:", manager.enforce_memory_cap(max_ram_mb=200))
    try:
        sync_result = manager.sync_to_ecosystem()
    except EcosystemBoundaryError as exc:
        sync_result = {"success": False, "error": str(exc)}
    print("Ecosystem Sync:", sync_result)
