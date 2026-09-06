"""Canonical offline implementations for dependency-ready JAYA pillars.

These capabilities are integrated with the production runtime while remaining
local-only. They do not claim hardware acceleration or production deployment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jaya_core.capabilities.manifest import CapabilityManifest
from jaya_core.pillars.binary_cortex import BinaryCortexService
from jaya_core.pillars.local_types import LocalPillarError, LocalPillarResult
from jaya_core.security.cryptographic_skin import CryptographicSkin

LINEAGE_CAPABILITY_ID = "core.epigenetics.lineage"
BINARY_DOT_CAPABILITY_ID = "core.binary.dot"
_GENERATION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _bounded_text(
    value: object,
    field: str,
    *,
    minimum: int = 1,
    maximum: int = 4_096,
) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    normalized = " ".join(value.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT",
            f"{field} must contain {minimum}-{maximum} characters",
        )
    return normalized


def _bounded_strings(
    values: object,
    field: str,
    *,
    maximum: int = 32,
    item_maximum: int = 512,
) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be a list")
    if not 1 <= len(values) <= maximum:
        raise LocalPillarError("INVALID_INPUT", f"{field} must contain 1-{maximum} entries")
    normalized = tuple(
        _bounded_text(item, f"{field} item", maximum=item_maximum) for item in values
    )
    if len(set(normalized)) != len(normalized):
        raise LocalPillarError("INVALID_INPUT", f"{field} must not contain duplicates")
    return normalized


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise LocalPillarError("INVALID_INPUT", "value must be JSON serializable") from exc


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_fields(
    payload: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    required: frozenset[str],
) -> None:
    unknown = set(payload) - allowed
    missing = required - set(payload)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


class DigitalEpigeneticsService:
    """Persistent, append-only local lineage authenticated with cryptographic signatures."""

    SCHEMA_VERSION = 2
    MAX_PAYLOAD_BYTES = 256 * 1024
    IMMUTABLE_FIELDS = frozenset(
        {
            "brain_id",
            "dna_profile",
            "immutable_hash",
            "identity_anchor",
            "security_policy",
            "owner_goal",
            "ethics_invariants",
            "pure_logic_axioms",
            "authority",
            "risk_boundary",
        }
    )
    MUTABLE_BOUNDS = {
        "batch_size": (int, 1, 1024),
        "cache_limit_mb": (int, 1, 65536),
        "temperature": ((int, float), 0.0, 2.0),
        "timeout_seconds": ((int, float), 0.1, 300.0),
        "retention_days": (int, 1, 3650),
        "max_concurrency": (int, 1, 128),
        "metric": ((int, float), 0.0, 1.0),
    }
    _PRIVATE_PATTERNS = re.compile(
        r"(?i)(password|secret|bearer_token|private_key|api_key|ssn|credit_card|\b\d{3}-\d{2}-\d{4}\b|\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b)"
    )

    def __init__(self, database_path: Path | str, signing_key: bytes) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise LocalPillarError(
                "INVALID_CONFIG", "lineage signing key must contain at least 32 bytes"
            )
        if str(database_path) == ":memory:":
            raise LocalPillarError(
                "INVALID_CONFIG", "digital epigenetics requires persistent storage"
            )
        self.database_path = Path(database_path).expanduser().resolve()
        self._key = signing_key
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage storage directory cannot be created"
            ) from exc
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.database_path, timeout=5.0)
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be opened"
            ) from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pillar_schema (
                        component TEXT PRIMARY KEY,
                        version INTEGER NOT NULL CHECK (version > 0)
                    );
                    """
                )
                row = connection.execute(
                    "SELECT version FROM pillar_schema WHERE component = ?",
                    ("digital_epigenetics",),
                ).fetchone()

                if row is None:
                    # New database: initialize schema v2 directly
                    connection.executescript(
                        """
                        INSERT INTO pillar_schema(component, version)
                        VALUES ('digital_epigenetics', 2);

                        CREATE TABLE IF NOT EXISTS epigenetic_lineage (
                            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                            generation_id TEXT NOT NULL UNIQUE,
                            parent_generation_id TEXT,
                            parent_digest TEXT,
                            mutation_type TEXT NOT NULL DEFAULT 'MUTATION',
                            payload_json TEXT NOT NULL,
                            evidence_json TEXT NOT NULL,
                            evidence_digest TEXT NOT NULL DEFAULT '',
                            approval_ref TEXT NOT NULL,
                            policy_json TEXT NOT NULL DEFAULT '{}',
                            signer_id TEXT NOT NULL DEFAULT 'local_hmac',
                            rollback_target TEXT,
                            created_at TEXT NOT NULL,
                            entry_digest TEXT NOT NULL UNIQUE,
                            signature TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_epigenetic_parent
                        ON epigenetic_lineage(parent_digest);

                        CREATE TABLE IF NOT EXISTS epigenetic_active_state (
                            id INTEGER PRIMARY KEY CHECK (id = 1),
                            generation_id TEXT NOT NULL,
                            traits_json TEXT NOT NULL,
                            head_digest TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        """
                    )
                else:
                    current_version = int(row["version"])
                    if current_version == 1:
                        # Migrate schema v1 to schema v2
                        cols = {
                            col["name"]
                            for col in connection.execute(
                                "PRAGMA table_info(epigenetic_lineage)"
                            ).fetchall()
                        }
                        if "parent_generation_id" not in cols:
                            connection.execute(
                                "ALTER TABLE epigenetic_lineage ADD COLUMN parent_generation_id TEXT"
                            )
                        if "mutation_type" not in cols:
                            connection.execute(
                                "ALTER TABLE epigenetic_lineage ADD COLUMN mutation_type TEXT NOT NULL DEFAULT 'MUTATION'"
                            )
                        if "evidence_digest" not in cols:
                            connection.execute(
                                "ALTER TABLE epigenetic_lineage ADD COLUMN evidence_digest TEXT NOT NULL DEFAULT ''"
                            )
                        if "policy_json" not in cols:
                            connection.execute(
                                "ALTER TABLE epigenetic_lineage ADD COLUMN policy_json TEXT NOT NULL DEFAULT '{}'"
                            )
                        if "signer_id" not in cols:
                            connection.execute(
                                "ALTER TABLE epigenetic_lineage ADD COLUMN signer_id TEXT NOT NULL DEFAULT 'local_hmac'"
                            )
                        if "rollback_target" not in cols:
                            connection.execute(
                                "ALTER TABLE epigenetic_lineage ADD COLUMN rollback_target TEXT"
                            )
                        connection.execute(
                            """
                            CREATE TABLE IF NOT EXISTS epigenetic_active_state (
                                id INTEGER PRIMARY KEY CHECK (id = 1),
                                generation_id TEXT NOT NULL,
                                traits_json TEXT NOT NULL,
                                head_digest TEXT NOT NULL,
                                updated_at TEXT NOT NULL
                            )
                            """
                        )
                        connection.execute(
                            "UPDATE pillar_schema SET version = 2 WHERE component = 'digital_epigenetics'"
                        )
                        # Backfill active state from latest entry if present
                        latest = connection.execute(
                            "SELECT * FROM epigenetic_lineage ORDER BY sequence DESC LIMIT 1"
                        ).fetchone()
                        if latest is not None:
                            connection.execute(
                                """
                                INSERT OR REPLACE INTO epigenetic_active_state(
                                    id, generation_id, traits_json, head_digest, updated_at
                                ) VALUES (1, ?, ?, ?, ?)
                                """,
                                (
                                    latest["generation_id"],
                                    latest["payload_json"],
                                    latest["entry_digest"],
                                    latest["created_at"],
                                ),
                            )
                    elif current_version == 2:
                        connection.execute(
                            """
                            CREATE TABLE IF NOT EXISTS epigenetic_active_state (
                                id INTEGER PRIMARY KEY CHECK (id = 1),
                                generation_id TEXT NOT NULL,
                                traits_json TEXT NOT NULL,
                                head_digest TEXT NOT NULL,
                                updated_at TEXT NOT NULL
                            )
                            """
                        )
                    else:
                        raise LocalPillarError(
                            "SCHEMA_UNSUPPORTED", "lineage schema version is unsupported"
                        )
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be initialized"
            ) from exc

    @staticmethod
    def _validate_generation_id(value: object) -> str:
        generation = _bounded_text(value, "generation_id", maximum=128)
        if _GENERATION_PATTERN.fullmatch(generation) is None:
            raise LocalPillarError("INVALID_INPUT", "generation_id contains unsafe characters")
        return generation

    @classmethod
    def _check_immutable_fields(cls, data: Mapping[str, Any]) -> None:
        for key, val in data.items():
            if str(key).lower() in cls.IMMUTABLE_FIELDS:
                raise LocalPillarError(
                    "IMMUTABLE_FIELD_VIOLATION",
                    f"epigenetic mutation cannot alter immutable field: '{key}'",
                )
            if isinstance(val, Mapping):
                cls._check_immutable_fields(val)

    @classmethod
    def _check_privacy_scope(cls, payload: Mapping[str, Any], evidence_refs: Sequence[str]) -> None:
        def scan(obj: Any) -> None:
            if isinstance(obj, str):
                if cls._PRIVATE_PATTERNS.search(obj):
                    raise LocalPillarError(
                        "PRIVACY_VIOLATION",
                        "epigenetic candidate contains unconsented private or credential data",
                    )
            elif isinstance(obj, Mapping):
                for k, v in obj.items():
                    if cls._PRIVATE_PATTERNS.search(str(k)):
                        raise LocalPillarError(
                            "PRIVACY_VIOLATION",
                            f"epigenetic candidate contains private credential field: '{k}'",
                        )
                    scan(v)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    scan(item)

        scan(payload)
        for ev in evidence_refs:
            if cls._PRIVATE_PATTERNS.search(str(ev)):
                raise LocalPillarError(
                    "PRIVACY_VIOLATION",
                    f"evidence reference contains private data pattern: '{ev}'",
                )

    @classmethod
    def _check_mutable_bounds(cls, payload: Mapping[str, Any]) -> None:
        for key, val in payload.items():
            if key in cls.MUTABLE_BOUNDS:
                expected_type, low, high = cls.MUTABLE_BOUNDS[key]
                if isinstance(val, bool) or not isinstance(val, expected_type):
                    raise LocalPillarError(
                        "INVALID_INPUT",
                        f"mutable trait '{key}' has invalid type: {type(val).__name__}",
                    )
                if not (low <= val <= high):
                    raise LocalPillarError(
                        "INVALID_INPUT",
                        f"mutable trait '{key}' value {val} exceeds allowed bounds [{low}, {high}]",
                    )
            if key == "log_level":
                if val not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
                    raise LocalPillarError(
                        "INVALID_INPUT",
                        f"mutable trait 'log_level' has invalid value: {val}",
                    )
            if isinstance(val, Mapping):
                cls._check_mutable_bounds(val)

    def append(
        self,
        *,
        generation_id: str,
        payload: Mapping[str, Any],
        evidence_refs: Sequence[str],
        approval_ref: str,
        expected_parent_generation_id: str | None = None,
        expected_parent_digest: str | None = None,
        policy_decision: Mapping[str, Any] | None = None,
        signer_id: str = "local_hmac",
        rollback_target: str | None = None,
        mutation_type: str = "MUTATION",
    ) -> LocalPillarResult:
        generation = self._validate_generation_id(generation_id)
        if not isinstance(payload, Mapping) or not payload:
            raise LocalPillarError("INVALID_INPUT", "payload must be a non-empty object")
        if any(not isinstance(key, str) for key in payload):
            raise LocalPillarError("INVALID_INPUT", "payload keys must be text")

        self._check_immutable_fields(payload)
        self._check_privacy_scope(payload, evidence_refs)
        self._check_mutable_bounds(payload)

        evidence = _bounded_strings(evidence_refs, "evidence_refs")
        approval = _bounded_text(approval_ref, "approval_ref", maximum=256)
        payload_json = _canonical_json(dict(payload))
        if len(payload_json.encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
            raise LocalPillarError("RESOURCE_LIMIT", "payload exceeds 256 KiB")
        evidence_json = _canonical_json(evidence)
        evidence_digest = _digest(evidence_json)
        policy_dict = dict(policy_decision) if policy_decision else {}
        policy_json = _canonical_json(policy_dict)
        created_at = datetime.now(UTC).isoformat()

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing_rows = connection.execute(
                    "SELECT * FROM epigenetic_lineage ORDER BY sequence"
                ).fetchall()
                parent_digest = self._verified_head(existing_rows)
                parent_gen_id = (
                    str(existing_rows[-1]["generation_id"]) if existing_rows else None
                )

                if (
                    expected_parent_generation_id is not None
                    and expected_parent_generation_id != parent_gen_id
                ):
                    raise LocalPillarError(
                        "STALE_MUTATION",
                        f"expected parent generation '{expected_parent_generation_id}' does not match current head '{parent_gen_id}'",
                    )
                if (
                    expected_parent_digest is not None
                    and expected_parent_digest != parent_digest
                ):
                    raise LocalPillarError(
                        "LINEAGE_FORK_CONFLICT",
                        f"expected parent digest '{expected_parent_digest}' does not match current head '{parent_digest}'",
                    )

                material = {
                    "generation_id": generation,
                    "parent_generation_id": parent_gen_id,
                    "parent_digest": parent_digest,
                    "mutation_type": mutation_type,
                    "payload": json.loads(payload_json),
                    "evidence_refs": list(evidence),
                    "evidence_digest": evidence_digest,
                    "approval_ref": approval,
                    "policy_decision": policy_dict,
                    "signer_id": signer_id,
                    "rollback_target": rollback_target,
                    "created_at": created_at,
                }
                entry_digest = _digest(material)
                signature = hmac.new(
                    self._key, entry_digest.encode("ascii"), hashlib.sha256
                ).hexdigest()

                cursor = connection.execute(
                    """
                    INSERT INTO epigenetic_lineage(
                        generation_id, parent_generation_id, parent_digest,
                        mutation_type, payload_json, evidence_json, evidence_digest,
                        approval_ref, policy_json, signer_id, rollback_target,
                        created_at, entry_digest, signature
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        generation,
                        parent_gen_id,
                        parent_digest,
                        mutation_type,
                        payload_json,
                        evidence_json,
                        evidence_digest,
                        approval,
                        policy_json,
                        signer_id,
                        rollback_target,
                        created_at,
                        entry_digest,
                        signature,
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO epigenetic_active_state(id, generation_id, traits_json, head_digest, updated_at)
                    VALUES (1, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        generation_id = excluded.generation_id,
                        traits_json = excluded.traits_json,
                        head_digest = excluded.head_digest,
                        updated_at = excluded.updated_at
                    """,
                    (generation, payload_json, entry_digest, created_at),
                )
        except LocalPillarError:
            raise
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError(
                "DUPLICATE_GENERATION", "generation_id or digest already exists"
            ) from exc
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage entry could not be persisted"
            ) from exc

        return LocalPillarResult(
            pillar_id="P025",
            code="LINEAGE_ENTRY_APPENDED",
            data={
                "sequence": int(cursor.lastrowid),
                "generation_id": generation,
                "parent_generation_id": parent_gen_id,
                "parent_digest": parent_digest,
                "entry_digest": entry_digest,
                "mutation_type": mutation_type,
                "rollback_target": rollback_target,
                "evidence_digest": evidence_digest,
                "signer_id": signer_id,
            },
        )

    def rollback(
        self,
        *,
        target_generation_id: str,
        approval_ref: str,
        evidence_refs: Sequence[str] = (),
        generation_id: str | None = None,
        policy_decision: Mapping[str, Any] | None = None,
        signer_id: str = "local_hmac",
    ) -> LocalPillarResult:
        target = self._validate_generation_id(target_generation_id)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM epigenetic_lineage WHERE generation_id = ?",
                    (target,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be read"
            ) from exc
        if row is None:
            raise LocalPillarError(
                "GENERATION_NOT_FOUND",
                f"rollback target generation '{target}' does not exist",
            )
        target_data = self._row_data(row)
        restored_payload = target_data["payload"]

        rollback_gen = generation_id or f"rollback-to-{target}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        ev_refs = list(evidence_refs) if evidence_refs else [f"rollback-target:{target}"]
        pol = dict(policy_decision) if policy_decision else {
            "action": "rollback",
            "target": target,
            "approved": True,
        }

        res = self.append(
            generation_id=rollback_gen,
            payload=restored_payload,
            evidence_refs=ev_refs,
            approval_ref=approval_ref,
            policy_decision=pol,
            signer_id=signer_id,
            rollback_target=target,
            mutation_type="ROLLBACK",
        )
        return LocalPillarResult(
            pillar_id="P025",
            code="LINEAGE_ROLLBACK_APPLIED",
            data={
                **res.data,
                "restored_traits": restored_payload,
            },
        )

    def get_active_state(self) -> LocalPillarResult:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM epigenetic_active_state WHERE id = 1"
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be read"
            ) from exc
        if row is None:
            return LocalPillarResult(
                pillar_id="P025",
                code="ACTIVE_STATE_EMPTY",
                data={
                    "generation_id": None,
                    "traits": {},
                    "head_digest": None,
                    "updated_at": None,
                },
            )
        return LocalPillarResult(
            pillar_id="P025",
            code="ACTIVE_STATE_READ",
            data={
                "generation_id": str(row["generation_id"]),
                "traits": json.loads(row["traits_json"]),
                "head_digest": str(row["head_digest"]),
                "updated_at": str(row["updated_at"]),
            },
        )

    def apply_to_runtime(self, runtime: Any) -> dict[str, Any]:
        active_res = self.get_active_state()
        active = active_res.data
        traits = active.get("traits", {})
        return {
            "generation_id": active.get("generation_id"),
            "head_digest": active.get("head_digest"),
            "applied_traits": traits,
            "status": "APPLIED",
        }

    @staticmethod
    def _row_data(row: sqlite3.Row) -> dict[str, Any]:
        keys = row.keys()
        try:
            payload = json.loads(row["payload_json"])
            evidence = json.loads(row["evidence_json"])
            policy_decision = (
                json.loads(row["policy_json"])
                if "policy_json" in keys and row["policy_json"]
                else {}
            )
        except (json.JSONDecodeError, TypeError) as exc:
            raise LocalPillarError("LINEAGE_CORRUPT", "lineage JSON cannot be decoded") from exc

        return {
            "sequence": int(row["sequence"]),
            "generation_id": str(row["generation_id"]),
            "parent_generation_id": (
                str(row["parent_generation_id"])
                if "parent_generation_id" in keys and row["parent_generation_id"] is not None
                else None
            ),
            "parent_digest": row["parent_digest"],
            "mutation_type": str(row["mutation_type"]) if "mutation_type" in keys else "MUTATION",
            "payload": payload,
            "evidence_refs": evidence,
            "evidence_digest": (
                str(row["evidence_digest"]) if "evidence_digest" in keys else ""
            ),
            "approval_ref": str(row["approval_ref"]),
            "policy_decision": policy_decision,
            "signer_id": str(row["signer_id"]) if "signer_id" in keys else "local_hmac",
            "rollback_target": (
                str(row["rollback_target"])
                if "rollback_target" in keys and row["rollback_target"] is not None
                else None
            ),
            "created_at": str(row["created_at"]),
            "entry_digest": str(row["entry_digest"]),
        }

    def get(self, generation_id: str) -> LocalPillarResult:
        generation = self._validate_generation_id(generation_id)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM epigenetic_lineage WHERE generation_id = ?",
                    (generation,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be read"
            ) from exc
        if row is None:
            raise LocalPillarError("GENERATION_NOT_FOUND", "generation does not exist")
        return LocalPillarResult(
            pillar_id="P025", code="LINEAGE_ENTRY_READ", data=self._row_data(row)
        )

    def _verified_head(self, rows: Sequence[sqlite3.Row]) -> str | None:
        previous_digest: str | None = None
        for row in rows:
            data = self._row_data(row)
            if data["evidence_digest"]:
                material = {
                    "generation_id": data["generation_id"],
                    "parent_generation_id": data["parent_generation_id"],
                    "parent_digest": data["parent_digest"],
                    "mutation_type": data["mutation_type"],
                    "payload": data["payload"],
                    "evidence_refs": data["evidence_refs"],
                    "evidence_digest": data["evidence_digest"],
                    "approval_ref": data["approval_ref"],
                    "policy_decision": data["policy_decision"],
                    "signer_id": data["signer_id"],
                    "rollback_target": data["rollback_target"],
                    "created_at": data["created_at"],
                }
            else:
                material = {
                    "generation_id": data["generation_id"],
                    "parent_digest": data["parent_digest"],
                    "payload": data["payload"],
                    "evidence_refs": data["evidence_refs"],
                    "approval_ref": data["approval_ref"],
                    "created_at": data["created_at"],
                }
            expected_digest = _digest(material)
            expected_signature = hmac.new(
                self._key, expected_digest.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if data["parent_digest"] != previous_digest:
                raise LocalPillarError("LINEAGE_BROKEN", "parent digest chain is broken")
            if data["entry_digest"] != expected_digest or not hmac.compare_digest(
                str(row["signature"]), expected_signature
            ):
                raise LocalPillarError("LINEAGE_SIGNATURE_INVALID", "lineage authentication failed")
            previous_digest = expected_digest
        return previous_digest

    def list_entries(self, *, limit: int = 100, offset: int = 0) -> LocalPillarResult:
        if type(limit) is not int or not 1 <= limit <= 1_000:
            raise LocalPillarError("INVALID_INPUT", "limit must be an integer from 1-1000")
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise LocalPillarError("INVALID_INPUT", "offset must be an integer from 0-1000000")
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM epigenetic_lineage ORDER BY sequence LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be read"
            ) from exc
        return LocalPillarResult(
            pillar_id="P025",
            code="LINEAGE_ENTRIES_LISTED",
            data={"entries": [self._row_data(row) for row in rows], "offset": offset},
        )

    def verify(self) -> LocalPillarResult:
        try:
            with self._connect() as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                rows = connection.execute(
                    "SELECT * FROM epigenetic_lineage ORDER BY sequence"
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "lineage database cannot be read"
            ) from exc
        if integrity is None or integrity[0] != "ok":
            raise LocalPillarError("STORAGE_CORRUPT", "SQLite integrity check failed")
        previous_digest = self._verified_head(rows)
        return LocalPillarResult(
            pillar_id="P025",
            code="LINEAGE_VERIFIED",
            data={"entries": len(rows), "head_digest": previous_digest},
        )

    def health_check(self) -> bool:
        try:
            result = self.verify()
        except LocalPillarError:
            return False
        return result.code == "LINEAGE_VERIFIED"

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action")
        if action == "append":
            _require_fields(
                request,
                allowed=frozenset(
                    {
                        "action",
                        "generation_id",
                        "payload",
                        "evidence_refs",
                        "approval_ref",
                        "expected_parent_generation_id",
                        "expected_parent_digest",
                        "policy_decision",
                        "signer_id",
                        "rollback_target",
                        "mutation_type",
                    }
                ),
                required=frozenset(
                    {"action", "generation_id", "payload", "evidence_refs", "approval_ref"}
                ),
            )
            return self.append(
                generation_id=request["generation_id"],
                payload=request["payload"],
                evidence_refs=request["evidence_refs"],
                approval_ref=request["approval_ref"],
                expected_parent_generation_id=request.get("expected_parent_generation_id"),
                expected_parent_digest=request.get("expected_parent_digest"),
                policy_decision=request.get("policy_decision"),
                signer_id=request.get("signer_id", "local_hmac"),
                rollback_target=request.get("rollback_target"),
                mutation_type=request.get("mutation_type", "MUTATION"),
            )
        if action == "rollback":
            _require_fields(
                request,
                allowed=frozenset(
                    {
                        "action",
                        "target_generation_id",
                        "approval_ref",
                        "evidence_refs",
                        "generation_id",
                        "policy_decision",
                        "signer_id",
                    }
                ),
                required=frozenset({"action", "target_generation_id", "approval_ref"}),
            )
            return self.rollback(
                target_generation_id=request["target_generation_id"],
                approval_ref=request["approval_ref"],
                evidence_refs=request.get("evidence_refs", ()),
                generation_id=request.get("generation_id"),
                policy_decision=request.get("policy_decision"),
                signer_id=request.get("signer_id", "local_hmac"),
            )
        if action == "get_active_state":
            _require_fields(
                request,
                allowed=frozenset({"action"}),
                required=frozenset({"action"}),
            )
            return self.get_active_state()
        if action == "get":
            _require_fields(
                request,
                allowed=frozenset({"action", "generation_id"}),
                required=frozenset({"action", "generation_id"}),
            )
            return self.get(request["generation_id"])
        if action == "list":
            _require_fields(
                request,
                allowed=frozenset({"action", "limit", "offset"}),
                required=frozenset({"action"}),
            )
            return self.list_entries(
                limit=request.get("limit", 100), offset=request.get("offset", 0)
            )
        if action == "verify":
            _require_fields(
                request,
                allowed=frozenset({"action"}),
                required=frozenset({"action"}),
            )
            return self.verify()
        raise LocalPillarError("UNSUPPORTED_ACTION", "lineage action is unsupported")


class LocalPillarCapabilityService:
    """Runtime dispatch and health boundary for implemented-local pillars."""

    def __init__(
        self,
        *,
        data_dir: Path | str,
        lineage_signing_key: bytes | None = None,
        cryptographic_skin: CryptographicSkin | None = None,
        binary_kernel_timeout_seconds: float = 2.0,
    ) -> None:
        root = Path(data_dir).expanduser().resolve()
        self.binary_cortex = BinaryCortexService(
            artifact_root=root / "binary_cortex",
            cryptographic_skin=cryptographic_skin,
            kernel_timeout_seconds=binary_kernel_timeout_seconds,
        )
        if lineage_signing_key is None:
            self.digital_epigenetics = None
        else:
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise LocalPillarError(
                    "STORAGE_UNAVAILABLE", "local pillar data directory cannot be created"
                ) from exc
            self.digital_epigenetics = DigitalEpigeneticsService(
                root / "digital_epigenetics.sqlite3", lineage_signing_key
            )

    def manifests(self) -> tuple[CapabilityManifest, ...]:
        lineage_healthy = bool(
            self.digital_epigenetics is not None and self.digital_epigenetics.health_check()
        )
        return (
            CapabilityManifest(
                capability_id=LINEAGE_CAPABILITY_ID,
                version="1.0",
                provider="local_pillar_service",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if lineage_healthy else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=BINARY_DOT_CAPABILITY_ID,
                version="2.0",
                provider="authenticated_binary_cortex_service",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["persistent_storage", "cryptographic_envelope"],
                offline_available=True,
                health_status=("HEALTHY" if self.binary_cortex.health_check() else "UNHEALTHY"),
            ),
        )

    def execute(self, capability_id: str, request: Mapping[str, Any]) -> LocalPillarResult:
        if capability_id == LINEAGE_CAPABILITY_ID:
            if self.digital_epigenetics is None:
                raise LocalPillarError(
                    "CAPABILITY_UNAVAILABLE",
                    "digital epigenetics signing key is not configured",
                )
            return self.digital_epigenetics.execute(request)
        if capability_id == BINARY_DOT_CAPABILITY_ID:
            return self.binary_cortex.execute(request)
        raise LocalPillarError("CAPABILITY_UNAVAILABLE", "local pillar is not registered")

    def health_snapshot(self) -> dict[str, Any]:
        manifests = self.manifests()
        return {
            "status": "INTEGRATED",
            "capabilities": {
                manifest.capability_id: manifest.health_status for manifest in manifests
            },
        }
