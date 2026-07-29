"""Core-owned consumer for verified JAYA Research artifacts.

Research publishes immutable candidates to its outbox. A separate promotion
gate places approved candidates in Core's configured inbox. This bridge only
reads that Core-owned inbox and never imports or traverses Research internals.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from src.core_config import core_config
from src.rag.research_artifact import (
    ResearchArtifactVerificationError,
    VerifiedResearchArtifact,
    verify_research_artifact,
)

_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


class ResearchInboxError(RuntimeError):
    """Raised when the Core-owned research inbox is unsafe or invalid."""


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class ResearchBridge:
    """Ingest reviewable knowledge artifacts from a Core-owned inbox."""

    def __init__(
        self,
        *,
        inbox_path: Path | str | None = None,
        rag_db_path: Path | str | None = None,
        core_data_root: Path | str | None = None,
    ) -> None:
        self.core_data_root = (
            Path(core_data_root or core_config.DATA_DIR).expanduser().resolve()
        )
        self.inbox_path = (
            Path(inbox_path or core_config.RESEARCH_MEMORY_PATH).expanduser().resolve()
        )
        self.rag_db_path = (
            Path(rag_db_path or core_config.AGENTIC_RAG_PATH).expanduser().resolve()
        )
        for label, path in (
            ("research inbox", self.inbox_path),
            ("RAG database", self.rag_db_path),
        ):
            if not _within(path, self.core_data_root):
                raise ResearchInboxError(
                    f"{label} must remain inside the configured Core data directory"
                )
        self._ensure_rag_schema()

    def sync(self) -> dict[str, Any]:
        """Verify the complete inbox, then atomically insert new facts."""
        artifacts = self._load_verified_artifacts()
        if not artifacts:
            return {"status": "no_data", "synced": 0, "skipped": 0}

        facts = [(artifact, self._to_fact(artifact)) for artifact in artifacts]
        new_count = 0
        skipped = 0
        with sqlite3.connect(str(self.rag_db_path)) as connection:
            for artifact, fact in facts:
                if self._already_synced(connection, artifact.content_sha256):
                    skipped += 1
                    continue
                self._insert_fact(connection, artifact.content_sha256, fact)
                new_count += 1
        return {
            "status": "ok",
            "synced": new_count,
            "skipped": skipped,
            "total_artifacts": len(artifacts),
        }

    def status(self) -> dict[str, Any]:
        """Return verified inbox and ingestion counts without writing facts."""
        try:
            artifacts = self._load_verified_artifacts()
            inbox_status = "verified"
            error = None
        except ResearchInboxError as exc:
            artifacts = []
            inbox_status = "invalid"
            error = str(exc)
        with sqlite3.connect(str(self.rag_db_path)) as connection:
            synced = connection.execute(
                "SELECT COUNT(*) FROM agentic_facts WHERE source = ?",
                ("research_bridge",),
            ).fetchone()[0]
        return {
            "inbox_exists": self.inbox_path.exists(),
            "inbox_status": inbox_status,
            "verified_artifacts": len(artifacts),
            "already_synced_in_core": synced,
            "error": error,
        }

    def _artifact_paths(self) -> list[Path]:
        if not self.inbox_path.exists():
            return []
        if self.inbox_path.is_symlink():
            raise ResearchInboxError("research inbox may not be a symbolic link")
        if self.inbox_path.is_file():
            return [self.inbox_path]
        if not self.inbox_path.is_dir():
            raise ResearchInboxError("research inbox is not a file or directory")
        paths = sorted(self.inbox_path.glob("*.json"))
        for path in paths:
            if path.is_symlink() or not _within(path, self.inbox_path):
                raise ResearchInboxError("research artifact escapes the inbox")
        return paths

    def _load_verified_artifacts(self) -> list[VerifiedResearchArtifact]:
        verified: list[VerifiedResearchArtifact] = []
        seen_ids: set[str] = set()
        for path in self._artifact_paths():
            try:
                size = path.stat().st_size
            except OSError as exc:
                raise ResearchInboxError(
                    f"cannot inspect inbox artifact {path.name}"
                ) from exc
            if size <= 0 or size > _MAX_ARTIFACT_BYTES:
                raise ResearchInboxError(
                    f"inbox artifact {path.name} has an invalid size"
                )
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                artifact = verify_research_artifact(raw)
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                ResearchArtifactVerificationError,
            ) as exc:
                raise ResearchInboxError(
                    f"inbox artifact {path.name} failed verification: {exc}"
                ) from exc
            if artifact.artifact_type != "knowledge_candidate":
                raise ResearchInboxError(
                    f"inbox artifact {path.name} is not a knowledge candidate"
                )
            if artifact.payload.get("executable") is not False:
                raise ResearchInboxError(
                    f"inbox artifact {path.name} is not explicitly non-executable"
                )
            if artifact.artifact_id in seen_ids:
                raise ResearchInboxError(
                    f"duplicate artifact_id in inbox: {artifact.artifact_id}"
                )
            seen_ids.add(artifact.artifact_id)
            verified.append(artifact)
        return verified

    def _ensure_rag_schema(self) -> None:
        self.rag_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.rag_db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_facts (
                    id          TEXT PRIMARY KEY,
                    source      TEXT NOT NULL,
                    topic       TEXT,
                    content     TEXT NOT NULL,
                    confidence  REAL NOT NULL,
                    created_at  REAL NOT NULL
                )
                """
            )

    @staticmethod
    def _already_synced(connection: sqlite3.Connection, digest: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM agentic_facts WHERE id = ?", (digest,)
            ).fetchone()
            is not None
        )

    @staticmethod
    def _to_fact(artifact: VerifiedResearchArtifact) -> dict[str, Any]:
        statement = str(artifact.payload.get("statement") or "").strip()
        if not statement:
            raise ResearchInboxError(
                f"knowledge candidate {artifact.artifact_id} has no statement"
            )
        return {
            "topic": artifact.subject,
            "content": statement,
            "confidence": artifact.confidence,
        }

    @staticmethod
    def _insert_fact(
        connection: sqlite3.Connection,
        digest: str,
        fact: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO agentic_facts
                (id, source, topic, content, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                "research_bridge",
                fact["topic"],
                fact["content"],
                fact["confidence"],
                time.time(),
            ),
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify and ingest the configured Core research inbox"
    )
    parser.add_argument(
        "--status", action="store_true", help="inspect without ingesting artifacts"
    )
    arguments = parser.parse_args()
    bridge = ResearchBridge()
    result = bridge.status() if arguments.status else bridge.sync()
    print(json.dumps(result, indent=2))
