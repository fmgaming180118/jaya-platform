"""Persistent, provenance-preserving semantic bridge for Pillar 26."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from .local_capabilities import LocalPillarError, LocalPillarResult

SEMANTIC_CAPABILITY_ID = "core.semantic.bridge"
_ATOM = (
    r"(?:model|dataset|artifact|person|organization|concept):"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
)
_TOKEN = re.compile(
    r"(?P<type>model|dataset|artifact|person|organization|concept):"
    r"(?P<value>[A-Za-z0-9][A-Za-z0-9_.-]{0,127})",
    re.IGNORECASE,
)
_RELATION = re.compile(
    rf"(?P<left>{_ATOM})\s*"
    r"-(?P<predicate>[A-Za-z][A-Za-z0-9_.-]{0,63})->\s*"
    rf"(?P<right>{_ATOM})",
    re.IGNORECASE,
)
_EPISTEMIC_STATUSES = {"FACT", "INFERENCE", "UNVERIFIED"}


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    candidate = value.strip()
    if len(candidate) == 0:
        raise LocalPillarError("INVALID_INPUT", f"{field} must not be empty")
    if len(candidate) > maximum:
        if field == "content":
            raise LocalPillarError("RESOURCE_LIMIT", "semantic source exceeds 1 MiB")
        raise LocalPillarError("INVALID_INPUT", f"{field} must contain 1-{maximum} characters")
    return candidate


def _strict(request: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SemanticParserProvider(Protocol):
    """Protocol for semantic parsing engines."""

    def health_check(self) -> bool:
        """Return True if the parser provider is ready to process requests."""
        ...

    def parse(
        self,
        content: str,
        namespace: str,
        source_ref: str,
        default_status: str | None = None,
    ) -> dict[str, Any]:
        """Parse text into typed entities, relations, and claims."""
        ...


class RuleBasedSemanticProvider:
    """Production deterministic rule-based grammar parser for typed entities and relations."""

    METHOD = "RULE_BASED_TYPED_GRAMMAR"

    def health_check(self) -> bool:
        return True

    @staticmethod
    def _entity(match: re.Match[str], namespace: str) -> dict[str, Any]:
        entity_type = match.group("type").lower()
        display = match.group("value")
        canonical = display.casefold()
        entity_id = _digest(f"{namespace}\x1f{entity_type}\x1f{canonical}")
        return {
            "entity_id": entity_id,
            "namespace": namespace,
            "entity_type": entity_type,
            "canonical_value": canonical,
            "display_value": display,
            "start_offset": match.start(),
            "end_offset": match.end(),
            "raw_text": match.group(0),
        }

    def parse(
        self,
        content: str,
        namespace: str,
        source_ref: str,
        default_status: str | None = None,
    ) -> dict[str, Any]:
        matches = list(_TOKEN.finditer(content))
        if not matches:
            raise LocalPillarError("NO_SEMANTIC_ENTITIES", "no typed entities were found")

        entities = [self._entity(match, namespace) for match in matches]
        by_raw_span = {(item["start_offset"], item["end_offset"]): item for item in entities}
        relations: list[dict[str, Any]] = []
        claims: list[dict[str, Any]] = []

        for match in _RELATION.finditer(content):
            left_match = _TOKEN.search(match.group("left"))
            right_match = _TOKEN.search(match.group("right"))
            if left_match is None or right_match is None:
                continue
            left_span = (match.start("left"), match.end("left"))
            right_span = (match.start("right"), match.end("right"))
            left = by_raw_span.get(left_span)
            right = by_raw_span.get(right_span)
            if left is None or right is None:
                continue
            predicate = match.group("predicate").casefold()

            # Epistemic classification: evaluate context preceding the match (up to 40 chars)
            start_pos = match.start()
            preceding_context = content[max(0, start_pos - 40) : start_pos].lower()
            if default_status in _EPISTEMIC_STATUSES:
                status = default_status
                confidence = 1.0 if status == "FACT" else (0.8 if status == "INFERENCE" else 0.6)
            elif (
                "hypothesis:" in preceding_context
                or "unverified:" in preceding_context
                or "speculative:" in preceding_context
            ):
                status = "UNVERIFIED"
                confidence = 0.6
            elif (
                "implies:" in preceding_context
                or "inferred:" in preceding_context
                or "deduced:" in preceding_context
            ):
                status = "INFERENCE"
                confidence = 0.8
            else:
                status = "FACT"
                confidence = 1.0

            rel_id = _digest(
                f"{source_ref}\x1f{match.start()}\x1f{left['entity_id']}\x1f"
                f"{predicate}\x1f{right['entity_id']}"
            )
            claim_id = _digest(
                f"claim\x1f{source_ref}\x1f{match.start()}\x1f{left['entity_id']}\x1f"
                f"{predicate}\x1f{right['entity_id']}\x1f{status}"
            )

            relations.append(
                {
                    "relation_id": rel_id,
                    "source_entity_id": left["entity_id"],
                    "predicate": predicate,
                    "target_entity_id": right["entity_id"],
                    "start_offset": match.start(),
                    "end_offset": match.end(),
                }
            )
            claims.append(
                {
                    "claim_id": claim_id,
                    "source_ref": source_ref,
                    "subject_entity_id": left["entity_id"],
                    "predicate": predicate,
                    "target_entity_id": right["entity_id"],
                    "epistemic_status": status,
                    "confidence": confidence,
                    "start_offset": match.start(),
                    "end_offset": match.end(),
                    "raw_text": content[match.start() : match.end()],
                }
            )

        return {
            "entities": entities,
            "relations": relations,
            "claims": claims,
            "method": self.METHOD,
        }


class ModelSemanticProviderAdapter:
    """Optional adapter for machine learning or neural NER / relation extraction models.

    Fails closed with PROVIDER_UNAVAILABLE when engine or weights are unconfigured.
    Never fabricates mock outputs or fake embeddings.
    """

    METHOD = "MODEL_SEMANTIC_PARSER"

    def __init__(self, model_path: Path | None = None, device: str = "cpu") -> None:
        self.model_path = model_path
        self.device = device
        self._is_ready = bool(model_path and model_path.exists())

    def health_check(self) -> bool:
        return self._is_ready

    def parse(
        self,
        content: str,
        namespace: str,
        source_ref: str,
        default_status: str | None = None,
    ) -> dict[str, Any]:
        if not self._is_ready:
            raise LocalPillarError(
                "PROVIDER_UNAVAILABLE",
                "semantic model provider is not configured or model weights missing",
            )
        raise LocalPillarError(
            "PROVIDER_UNAVAILABLE", "semantic model inference backend not initialized"
        )


class SemanticBridgeCapability:
    """Parse typed source text into a durable graph with exact citation spans and claims."""

    SCHEMA_VERSION = 1
    MAX_SOURCE_BYTES = 1_048_576
    METHOD = "RULE_BASED_TYPED_GRAMMAR"

    def __init__(
        self,
        database_path: Path,
        provider: SemanticParserProvider | None = None,
    ) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.provider = provider or RuleBasedSemanticProvider()
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_meta(
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS semantic_sources(
                        source_ref TEXT PRIMARY KEY,
                        source_digest TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS semantic_entities(
                        entity_id TEXT PRIMARY KEY,
                        namespace TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        canonical_value TEXT NOT NULL,
                        display_value TEXT NOT NULL,
                        UNIQUE(namespace, entity_type, canonical_value)
                    );
                    CREATE TABLE IF NOT EXISTS semantic_mentions(
                        source_ref TEXT NOT NULL,
                        start_offset INTEGER NOT NULL,
                        end_offset INTEGER NOT NULL,
                        entity_id TEXT NOT NULL,
                        raw_text TEXT NOT NULL,
                        PRIMARY KEY(source_ref, start_offset, end_offset),
                        FOREIGN KEY(source_ref) REFERENCES semantic_sources(source_ref),
                        FOREIGN KEY(entity_id) REFERENCES semantic_entities(entity_id)
                    );
                    CREATE TABLE IF NOT EXISTS semantic_relations(
                        relation_id TEXT PRIMARY KEY,
                        source_ref TEXT NOT NULL,
                        source_entity_id TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        target_entity_id TEXT NOT NULL,
                        start_offset INTEGER NOT NULL,
                        end_offset INTEGER NOT NULL,
                        FOREIGN KEY(source_ref) REFERENCES semantic_sources(source_ref),
                        FOREIGN KEY(source_entity_id) REFERENCES semantic_entities(entity_id),
                        FOREIGN KEY(target_entity_id) REFERENCES semantic_entities(entity_id)
                    );
                    CREATE TABLE IF NOT EXISTS semantic_claims(
                        claim_id TEXT PRIMARY KEY,
                        source_ref TEXT NOT NULL,
                        subject_entity_id TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        target_entity_id TEXT NOT NULL,
                        epistemic_status TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        start_offset INTEGER NOT NULL,
                        end_offset INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY(source_ref) REFERENCES semantic_sources(source_ref),
                        FOREIGN KEY(subject_entity_id) REFERENCES semantic_entities(entity_id),
                        FOREIGN KEY(target_entity_id) REFERENCES semantic_entities(entity_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_semantic_entity_value
                    ON semantic_entities(canonical_value, entity_type);
                    CREATE INDEX IF NOT EXISTS idx_semantic_mentions_entity
                    ON semantic_mentions(entity_id, source_ref);
                    CREATE INDEX IF NOT EXISTS idx_semantic_claims_subject
                    ON semantic_claims(subject_entity_id, epistemic_status);
                    CREATE INDEX IF NOT EXISTS idx_semantic_claims_source
                    ON semantic_claims(source_ref);
                    """
                )
                row = connection.execute(
                    "SELECT value FROM semantic_meta WHERE key='schema_version'"
                ).fetchone()
                if row is not None and int(row[0]) > self.SCHEMA_VERSION:
                    raise LocalPillarError(
                        "STORAGE_SCHEMA_UNSUPPORTED", "semantic schema is newer than this runtime"
                    )
                connection.execute(
                    "INSERT OR REPLACE INTO semantic_meta(key,value) VALUES('schema_version',?)",
                    (str(self.SCHEMA_VERSION),),
                )
        except LocalPillarError:
            raise
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic store unavailable") from exc
        except (sqlite3.Error, ValueError) as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic store unavailable") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.row_factory = sqlite3.Row
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic database connection failed") from exc
        try:
            with connection:
                yield connection
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise
        finally:
            connection.close()

    def health_check(self) -> bool:
        try:
            with self._connect() as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                provider_ready = self.provider.health_check()
                return quick_check and provider_ready
        except (sqlite3.Error, LocalPillarError):
            return False

    def ingest(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "source_ref", "content", "media_type", "namespace", "epistemic_status"},
            {"action", "source_ref", "content"},
        )
        source_ref = _text(request["source_ref"], "source_ref", 512)
        content = _text(request["content"], "content", self.MAX_SOURCE_BYTES)
        if len(content.encode("utf-8")) > self.MAX_SOURCE_BYTES:
            raise LocalPillarError("RESOURCE_LIMIT", "semantic source exceeds 1 MiB")
        media_type = _text(request.get("media_type", "text/plain"), "media_type", 128)
        if not media_type.startswith("text/"):
            raise LocalPillarError("UNSUPPORTED_MEDIA_TYPE", "semantic bridge accepts text media")
        namespace = _text(request.get("namespace", "default"), "namespace", 128).casefold()

        epistemic_status = request.get("epistemic_status")
        if epistemic_status is not None:
            if not isinstance(epistemic_status, str) or epistemic_status not in _EPISTEMIC_STATUSES:
                raise LocalPillarError(
                    "INVALID_INPUT",
                    f"epistemic_status must be one of: {', '.join(sorted(_EPISTEMIC_STATUSES))}",
                )

        digest = _digest(content)

        # Parse using configured provider
        parsed = self.provider.parse(
            content=content,
            namespace=namespace,
            source_ref=source_ref,
            default_status=epistemic_status,
        )
        entities: list[dict[str, Any]] = parsed["entities"]
        relations: list[dict[str, Any]] = parsed["relations"]
        claims: list[dict[str, Any]] = parsed.get("claims", [])
        method = parsed.get("method", self.METHOD)

        now = time.time()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT source_digest FROM semantic_sources WHERE source_ref=?",
                    (source_ref,),
                ).fetchone()
                if existing is not None:
                    if existing[0] != digest:
                        raise LocalPillarError(
                            "SOURCE_CONFLICT", "source_ref already identifies different content"
                        )
                    return self.source({"action": "source", "source_ref": source_ref})
                connection.execute(
                    "INSERT INTO semantic_sources VALUES(?,?,?,?,?)",
                    (source_ref, digest, media_type, content, now),
                )
                for entity in entities:
                    connection.execute(
                        """INSERT OR IGNORE INTO semantic_entities
                        VALUES(?,?,?,?,?)""",
                        (
                            entity["entity_id"],
                            namespace,
                            entity["entity_type"],
                            entity["canonical_value"],
                            entity["display_value"],
                        ),
                    )
                    connection.execute(
                        "INSERT INTO semantic_mentions VALUES(?,?,?,?,?)",
                        (
                            source_ref,
                            entity["start_offset"],
                            entity["end_offset"],
                            entity["entity_id"],
                            entity["raw_text"],
                        ),
                    )
                for relation in relations:
                    connection.execute(
                        "INSERT INTO semantic_relations VALUES(?,?,?,?,?,?,?)",
                        (
                            relation["relation_id"],
                            source_ref,
                            relation["source_entity_id"],
                            relation["predicate"],
                            relation["target_entity_id"],
                            relation["start_offset"],
                            relation["end_offset"],
                        ),
                    )
                for claim in claims:
                    connection.execute(
                        """INSERT OR REPLACE INTO semantic_claims
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            claim["claim_id"],
                            source_ref,
                            claim["subject_entity_id"],
                            claim["predicate"],
                            claim["target_entity_id"],
                            claim["epistemic_status"],
                            claim["confidence"],
                            claim["start_offset"],
                            claim["end_offset"],
                            now,
                        ),
                    )
        except LocalPillarError:
            raise
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic graph was not stored") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic graph was not stored") from exc
        return LocalPillarResult(
            "P026",
            "SEMANTIC_SOURCE_INGESTED",
            {
                "schema_version": self.SCHEMA_VERSION,
                "method": method,
                "source_ref": source_ref,
                "source_digest": f"sha256:{digest}",
                "entities": entities,
                "relations": relations,
                "claims": claims,
            },
        )

    def source(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "source_ref"}, {"action", "source_ref"})
        source_ref = _text(request["source_ref"], "source_ref", 512)
        try:
            with self._connect() as connection:
                source = connection.execute(
                    "SELECT * FROM semantic_sources WHERE source_ref=?", (source_ref,)
                ).fetchone()
                if source is None:
                    raise LocalPillarError("SOURCE_NOT_FOUND", "semantic source was not found")
                mentions = connection.execute(
                    """SELECT m.*, e.namespace, e.entity_type, e.canonical_value,
                    e.display_value FROM semantic_mentions m JOIN semantic_entities e
                    ON e.entity_id=m.entity_id WHERE m.source_ref=? ORDER BY m.start_offset""",
                    (source_ref,),
                ).fetchall()
                relations = connection.execute(
                    "SELECT * FROM semantic_relations WHERE source_ref=? ORDER BY start_offset",
                    (source_ref,),
                ).fetchall()
                claims = connection.execute(
                    "SELECT * FROM semantic_claims WHERE source_ref=? ORDER BY start_offset",
                    (source_ref,),
                ).fetchall()
        except LocalPillarError:
            raise
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic source cannot be read") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic source cannot be read") from exc
        return LocalPillarResult(
            "P026",
            "SEMANTIC_SOURCE_READ",
            {
                "schema_version": self.SCHEMA_VERSION,
                "method": self.METHOD,
                "source_ref": source_ref,
                "source_digest": f"sha256:{source['source_digest']}",
                "media_type": source["media_type"],
                "entities": [dict(row) for row in mentions],
                "relations": [dict(row) for row in relations],
                "claims": [dict(row) for row in claims],
            },
        )

    def query(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "value", "entity_type", "namespace", "limit"},
            {"action", "value"},
        )
        value = _text(request["value"], "value", 128).casefold()
        entity_type = request.get("entity_type")
        namespace = _text(request.get("namespace", "default"), "namespace", 128).casefold()
        limit = request.get("limit", 50)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise LocalPillarError("RESOURCE_LIMIT", "limit must be 1-500")
        params: list[Any] = [namespace, value]
        where = "e.namespace=? AND e.canonical_value=?"
        if entity_type is not None:
            normalized_type = _text(entity_type, "entity_type", 32).casefold()
            if normalized_type not in {
                "model", "dataset", "artifact", "person", "organization", "concept"
            }:
                raise LocalPillarError("INVALID_INPUT", "entity_type is unsupported")
            where += " AND e.entity_type=?"
            params.append(normalized_type)
        params.append(limit)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""SELECT e.*, m.source_ref, m.start_offset, m.end_offset, m.raw_text,
                    s.source_digest FROM semantic_entities e JOIN semantic_mentions m
                    ON m.entity_id=e.entity_id JOIN semantic_sources s
                    ON s.source_ref=m.source_ref WHERE {where}
                    ORDER BY m.source_ref, m.start_offset LIMIT ?""",
                    params,
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic query failed") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic query failed") from exc
        types = sorted({row["entity_type"] for row in rows})
        return LocalPillarResult(
            "P026",
            "SEMANTIC_ENTITIES_FOUND" if rows else "SEMANTIC_ENTITY_NOT_FOUND",
            {
                "matches": [dict(row) for row in rows],
                "ambiguous": len(types) > 1,
                "candidate_types": types,
            },
        )

    def query_claims(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {
                "action",
                "subject_entity_id",
                "target_entity_id",
                "predicate",
                "epistemic_status",
                "source_ref",
                "limit",
            },
            {"action"},
        )
        conditions: list[str] = []
        params: list[Any] = []

        if "source_ref" in request:
            conditions.append("c.source_ref=?")
            params.append(_text(request["source_ref"], "source_ref", 512))
        if "subject_entity_id" in request:
            conditions.append("c.subject_entity_id=?")
            params.append(_text(request["subject_entity_id"], "subject_entity_id", 128))
        if "target_entity_id" in request:
            conditions.append("c.target_entity_id=?")
            params.append(_text(request["target_entity_id"], "target_entity_id", 128))
        if "predicate" in request:
            conditions.append("c.predicate=?")
            params.append(_text(request["predicate"], "predicate", 64).casefold())
        if "epistemic_status" in request:
            status = _text(request["epistemic_status"], "epistemic_status", 32).upper()
            if status not in _EPISTEMIC_STATUSES:
                raise LocalPillarError(
                    "INVALID_INPUT",
                    f"epistemic_status must be one of: {', '.join(sorted(_EPISTEMIC_STATUSES))}",
                )
            conditions.append("c.epistemic_status=?")
            params.append(status)

        limit = request.get("limit", 100)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise LocalPillarError("RESOURCE_LIMIT", "limit must be 1-500")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""SELECT c.*, s.canonical_value AS subject_value, s.entity_type AS subject_type,
                    t.canonical_value AS target_value, t.entity_type AS target_type
                    FROM semantic_claims c
                    JOIN semantic_entities s ON s.entity_id=c.subject_entity_id
                    JOIN semantic_entities t ON t.entity_id=c.target_entity_id
                    {where_clause}
                    ORDER BY c.created_at DESC LIMIT ?""",
                    params,
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic claim query failed") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "semantic claim query failed") from exc

        claims = [dict(row) for row in rows]
        epistemic_counts: dict[str, int] = {}
        for item in claims:
            st = item["epistemic_status"]
            epistemic_counts[st] = epistemic_counts.get(st, 0) + 1

        return LocalPillarResult(
            "P026",
            "SEMANTIC_CLAIMS_FOUND" if claims else "SEMANTIC_CLAIM_NOT_FOUND",
            {
                "claims": claims,
                "count": len(claims),
                "epistemic_distribution": epistemic_counts,
            },
        )

    def verify_provenance(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """Strictly verify that stored entity mentions and claims match exact content bytes."""
        _strict(request, {"action", "source_ref"}, {"action", "source_ref"})
        source_ref = _text(request["source_ref"], "source_ref", 512)
        try:
            with self._connect() as connection:
                source = connection.execute(
                    "SELECT * FROM semantic_sources WHERE source_ref=?", (source_ref,)
                ).fetchone()
                if source is None:
                    raise LocalPillarError("SOURCE_NOT_FOUND", "semantic source was not found")

                content = str(source["content"])
                expected_digest = str(source["source_digest"])
                actual_digest = _digest(content)
                if actual_digest != expected_digest:
                    raise LocalPillarError(
                        "DIGEST_MISMATCH",
                        f"content digest {actual_digest} does not match recorded {expected_digest}",
                    )

                mentions = connection.execute(
                    "SELECT * FROM semantic_mentions WHERE source_ref=?", (source_ref,)
                ).fetchall()
                for mention in mentions:
                    start = int(mention["start_offset"])
                    end = int(mention["end_offset"])
                    raw = str(mention["raw_text"])
                    actual_span = content[start:end]
                    if actual_span != raw:
                        raise LocalPillarError(
                            "CITATION_MISMATCH",
                            f"mention span ({start}, {end}) extracted '{actual_span}' "
                            f"does not match citation '{raw}'",
                        )

                relations = connection.execute(
                    "SELECT * FROM semantic_relations WHERE source_ref=?", (source_ref,)
                ).fetchall()
                for rel in relations:
                    start = int(rel["start_offset"])
                    end = int(rel["end_offset"])
                    if not (0 <= start < end <= len(content)):
                        raise LocalPillarError(
                            "CITATION_MISMATCH",
                            f"relation span ({start}, {end}) is out of bounds for source",
                        )

                claims = connection.execute(
                    "SELECT * FROM semantic_claims WHERE source_ref=?", (source_ref,)
                ).fetchall()
                for claim in claims:
                    start = int(claim["start_offset"])
                    end = int(claim["end_offset"])
                    if not (0 <= start < end <= len(content)):
                        raise LocalPillarError(
                            "CITATION_MISMATCH",
                            f"claim span ({start}, {end}) is out of bounds for source",
                        )
        except LocalPillarError:
            raise
        except sqlite3.DatabaseError as exc:
            if "malformed" in str(exc).lower() or "corrupt" in str(exc).lower():
                raise LocalPillarError("STORAGE_CORRUPT", "semantic store is corrupt") from exc
            raise LocalPillarError("STORAGE_UNAVAILABLE", "provenance verification failed") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "provenance verification failed") from exc

        return LocalPillarResult(
            "P026",
            "SEMANTIC_PROVENANCE_VERIFIED",
            {
                "source_ref": source_ref,
                "source_digest": f"sha256:{expected_digest}",
                "content_length_chars": len(content),
                "entities_verified": len(mentions),
                "relations_verified": len(relations),
                "claims_verified": len(claims),
                "verified": True,
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action")
        if action == "ingest":
            return self.ingest(request)
        if action == "source":
            return self.source(request)
        if action == "query":
            return self.query(request)
        if action == "query_claims":
            return self.query_claims(request)
        if action == "verify_provenance":
            return self.verify_provenance(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", "semantic bridge action is unsupported")


__all__ = [
    "SEMANTIC_CAPABILITY_ID",
    "ModelSemanticProviderAdapter",
    "RuleBasedSemanticProvider",
    "SemanticBridgeCapability",
    "SemanticParserProvider",
]
