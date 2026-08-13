"""Contained, read-only episodic memory access for JAYA_AGENT."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

_DATABASE_NAME = "agentic_jarvis.db"
_MAX_QUERY_CHARACTERS = 2_000
_MAX_RESULTS = 20


class MemoryQueryError(RuntimeError):
    """Raised when an installed memory database cannot be queried safely."""


class RAGMemoryEngine:
    """Query only the verified database installed in the Agent data root."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        storage_root: str | Path | None = None,
    ) -> None:
        agent_root = Path(__file__).resolve().parents[2]
        root = Path(storage_root or (agent_root / "data")).resolve(strict=False)
        candidate = Path(db_path or (root / _DATABASE_NAME))
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "Memory database must remain inside Agent storage"
            ) from exc
        if resolved.name != _DATABASE_NAME:
            raise ValueError("Memory database must use the canonical filename")
        self.storage_root = root
        self.db_path = resolved

    def query_relevant_patches(
        self,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return bounded rows without creating or modifying the database."""

        if not isinstance(query, str) or len(query) > _MAX_QUERY_CHARACTERS:
            raise ValueError("Memory query must be a bounded string")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("Memory result limit must be an integer")
        if not 1 <= limit <= _MAX_RESULTS:
            raise ValueError("Memory result limit is outside policy")
        if not self.db_path.exists():
            return []
        if not self.db_path.is_file() or self.db_path.is_symlink():
            raise MemoryQueryError("Installed memory path is not a regular file")
        resolved = self.db_path.resolve(strict=True)
        try:
            resolved.relative_to(self.storage_root)
        except ValueError as exc:
            raise MemoryQueryError(
                "Installed memory path escaped Agent storage"
            ) from exc

        keywords = [
            word.lower()
            for word in re.findall(r"[\w-]+", query, flags=re.UNICODE)
            if len(word) > 3
        ][:20]
        database_uri = f"{resolved.as_uri()}?mode=ro"
        try:
            with closing(
                sqlite3.connect(
                    database_uri,
                    uri=True,
                    timeout=1.0,
                )
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA query_only = ON")
                if keywords:
                    clauses = ["topic LIKE ?"] * len(keywords)
                    clauses.extend(["statement LIKE ?"] * len(keywords))
                    parameters = [f"%{keyword}%" for keyword in keywords] * 2
                    parameters.append(limit)
                    rows = connection.execute(
                        "SELECT patch_id, topic, statement, bayes_confidence "
                        "FROM jarvis_patches WHERE "
                        + " OR ".join(clauses)
                        + " ORDER BY bayes_confidence DESC LIMIT ?",
                        parameters,
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT patch_id, topic, statement, bayes_confidence "
                        "FROM jarvis_patches "
                        "ORDER BY bayes_confidence DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
        except sqlite3.Error as exc:
            raise MemoryQueryError(
                f"Installed memory database query failed ({type(exc).__name__})"
            ) from exc

        return [
            {
                "patch_id": row["patch_id"],
                "topic": row["topic"],
                "statement": row["statement"],
                "confidence": round(float(row["bayes_confidence"]) * 100, 1),
            }
            for row in rows
        ]
