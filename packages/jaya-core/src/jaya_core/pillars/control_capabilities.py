"""Persistent control-room capabilities for Pillars 40, 39, and 37."""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .agentic_rag_capability import AgenticRAGCapability
from .foundation_capabilities import SandboxedImaginationCapability
from .local_capabilities import LocalPillarError, LocalPillarResult
from .media_capability import MediaObservationCapability

INTENT_CAPABILITY_ID = "core.intent.extrapolate"
OBJECTIVE_CAPABILITY_ID = "core.objective.dynamic"
HYBRID_CAPABILITY_ID = "core.routing.hybrid"


@contextmanager
def _connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path, timeout=5.0)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


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
    candidate = " ".join(value.strip().split())
    if not minimum <= len(candidate) <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT", f"{field} must contain {minimum}-{maximum} characters"
        )
    return candidate


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class IntentExtrapolationCapability:
    """Learn local intent transitions only after explicit, expiring consent."""

    SCHEMA_VERSION = 2

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    PRAGMA journal_mode=WAL;
                    PRAGMA synchronous=NORMAL;
                    CREATE TABLE IF NOT EXISTS intent_schema(
                        version INTEGER PRIMARY KEY,
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS intent_consent(
                        owner_id TEXT PRIMARY KEY,
                        receipt_id TEXT NOT NULL,
                        granted_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        opted_out INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS intent_transitions(
                        owner_id TEXT NOT NULL,
                        current_intent TEXT NOT NULL,
                        next_intent TEXT NOT NULL,
                        observations INTEGER NOT NULL,
                        corrected INTEGER NOT NULL DEFAULT 0,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY(owner_id, current_intent, next_intent)
                    );
                    CREATE TABLE IF NOT EXISTS intent_predictions(
                        prediction_id TEXT PRIMARY KEY,
                        owner_id TEXT NOT NULL,
                        current_intent TEXT NOT NULL,
                        candidate TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        confirmed INTEGER,
                        created_at REAL NOT NULL,
                        explanation TEXT
                    );
                    CREATE TABLE IF NOT EXISTS intent_audit_log(
                        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_id TEXT,
                        event_type TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS intent_state_receipts(
                        receipt_id TEXT PRIMARY KEY,
                        state_digest TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO intent_schema VALUES(?, ?) ON CONFLICT(version) DO UPDATE SET updated_at=excluded.updated_at",
                    (self.SCHEMA_VERSION, time.time()),
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent store unavailable") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def health_check(self) -> bool:
        try:
            with self._connect() as connection:
                row = connection.execute("PRAGMA quick_check").fetchone()
                if row is None or row[0] != "ok":
                    return False
                schema_row = connection.execute("SELECT version FROM intent_schema ORDER BY version DESC LIMIT 1").fetchone()
                return schema_row is not None and int(schema_row["version"]) == self.SCHEMA_VERSION
        except sqlite3.Error:
            return False

    def _compute_state_digest(self, connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            "SELECT owner_id, current_intent, next_intent, observations, corrected FROM intent_transitions ORDER BY owner_id, current_intent, next_intent"
        ).fetchall()
        serialized = [
            (r["owner_id"], r["current_intent"], r["next_intent"], int(r["observations"]), int(r["corrected"]))
            for r in rows
        ]
        return hashlib.sha256(_canonical(serialized).encode("utf-8")).hexdigest()

    def _update_receipt(self, connection: sqlite3.Connection) -> str:
        digest = self._compute_state_digest(connection)
        receipt_id = f"receipt-{uuid.uuid4().hex[:12]}"
        connection.execute(
            "INSERT INTO intent_state_receipts VALUES(?, ?, ?) ON CONFLICT(receipt_id) DO UPDATE SET state_digest=excluded.state_digest, created_at=excluded.created_at",
            (receipt_id, digest, time.time()),
        )
        return digest

    def verify_integrity(self) -> bool:
        try:
            with self._connect() as connection:
                check = connection.execute("PRAGMA quick_check").fetchone()
                if check is None or check[0] != "ok":
                    raise LocalPillarError("STORAGE_CORRUPT", "sqlite database corrupted")
                latest_receipt = connection.execute(
                    "SELECT state_digest FROM intent_state_receipts ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if latest_receipt is not None:
                    computed = self._compute_state_digest(connection)
                    if computed != latest_receipt["state_digest"]:
                        raise LocalPillarError("STORAGE_CORRUPT", "intent transition storage corrupted or modified without receipt")
                return True
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "storage verification failed") from exc

    def _log_audit(self, connection: sqlite3.Connection, owner_id: str | None, event_type: str, details: Mapping[str, Any]) -> None:
        try:
            connection.execute(
                "INSERT INTO intent_audit_log(owner_id, event_type, details_json, created_at) VALUES(?, ?, ?, ?)",
                (owner_id, event_type, _canonical(details), time.time()),
            )
        except sqlite3.Error:
            pass

    def consent(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "owner_id", "receipt_id", "granted_at", "expires_at"},
            {"action", "owner_id", "receipt_id", "granted_at", "expires_at"},
        )
        owner = _text(request["owner_id"], "owner_id", 128)
        receipt = _text(request["receipt_id"], "receipt_id", 128)
        try:
            granted = float(request["granted_at"])
            expires = float(request["expires_at"])
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "consent timestamps must be numeric") from exc
        now = time.time()
        if not all(math.isfinite(item) for item in (granted, expires)):
            raise LocalPillarError("INVALID_INPUT", "consent timestamps must be finite")
        if granted > now + 300 or expires <= now or expires - granted > 365 * 86400:
            raise LocalPillarError("INVALID_CONSENT", "consent window is invalid")
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO intent_consent VALUES(?,?,?,?,0)
                    ON CONFLICT(owner_id) DO UPDATE SET receipt_id=excluded.receipt_id,
                    granted_at=excluded.granted_at,expires_at=excluded.expires_at,opted_out=0""",
                    (owner, receipt, granted, expires),
                )
                self._log_audit(
                    connection, owner, "CONSENT_RECORDED",
                    {"receipt_id": receipt, "granted_at": granted, "expires_at": expires}
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "consent was not stored") from exc
        return LocalPillarResult(
            "P040",
            "INTENT_CONSENT_RECORDED",
            {"owner_id": owner, "expires_at": expires, "receipt_id": receipt},
        )

    def consent_status(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "owner_id"}, {"action", "owner_id"})
        owner = _text(request["owner_id"], "owner_id", 128)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT receipt_id, granted_at, expires_at, opted_out FROM intent_consent WHERE owner_id=?",
                    (owner,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "consent status cannot be read") from exc
        if row is None:
            return LocalPillarResult(
                "P040",
                "INTENT_CONSENT_STATUS",
                {"owner_id": owner, "has_consent": False, "active": False, "opted_out": False, "expires_at": None, "receipt_id": None},
            )
        now = time.time()
        is_opted_out = bool(row["opted_out"])
        expires_at = float(row["expires_at"])
        is_active = (not is_opted_out) and (expires_at > now)
        return LocalPillarResult(
            "P040",
            "INTENT_CONSENT_STATUS",
            {
                "owner_id": owner,
                "has_consent": True,
                "active": is_active,
                "opted_out": is_opted_out,
                "expires_at": expires_at,
                "receipt_id": row["receipt_id"],
            },
        )

    def _require_consent(self, owner: str) -> None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT expires_at, opted_out FROM intent_consent WHERE owner_id=?", (owner,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "consent cannot be read") from exc
        if row is None:
            raise LocalPillarError("CONSENT_REQUIRED", "active profiling consent is required")
        if row["opted_out"]:
            raise LocalPillarError("CONSENT_REQUIRED", "profiling has been opted out")
        if float(row["expires_at"]) <= time.time():
            raise LocalPillarError("CONSENT_EXPIRED", "profiling consent has expired")

    def observe(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "owner_id", "sequence"}, {"action", "owner_id", "sequence"})
        owner = _text(request["owner_id"], "owner_id", 128)
        self._require_consent(owner)
        sequence = request["sequence"]
        if not isinstance(sequence, list) or not 2 <= len(sequence) <= 256:
            raise LocalPillarError("RESOURCE_LIMIT", "intent sequence must contain 2-256 items")
        intents = [_text(item, "sequence intent", 128).casefold() for item in sequence]
        transitions = list(itertools.pairwise(intents))
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                now = time.time()
                for current, following in transitions:
                    connection.execute(
                        """INSERT INTO intent_transitions VALUES(?,?,?,1,0,?)
                        ON CONFLICT(owner_id,current_intent,next_intent)
                        DO UPDATE SET observations=observations+1,updated_at=excluded.updated_at""",
                        (owner, current, following, now),
                    )
                self._update_receipt(connection)
                self._log_audit(
                    connection, owner, "INTENT_SEQUENCE_OBSERVED",
                    {"transition_count": len(transitions)}
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent observations were not stored") from exc
        return LocalPillarResult("P040", "INTENT_SEQUENCE_OBSERVED", {"transitions": len(transitions)})

    def predict(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "owner_id", "current_intent", "minimum_observations", "ttl_seconds", "max_staleness_seconds", "top_k"},
            {"action", "owner_id", "current_intent"},
        )
        owner = _text(request["owner_id"], "owner_id", 128)
        self._require_consent(owner)
        current = _text(request["current_intent"], "current_intent", 128).casefold()
        minimum = request.get("minimum_observations", 2)
        ttl = request.get("ttl_seconds", 300)
        max_staleness = request.get("max_staleness_seconds")
        if type(minimum) is not int or not 1 <= minimum <= 1000:
            raise LocalPillarError("INVALID_INPUT", "minimum_observations must be 1-1000")
        if type(ttl) is not int or not 1 <= ttl <= 86400:
            raise LocalPillarError("INVALID_INPUT", "ttl_seconds must be 1-86400")
        if max_staleness is not None and (type(max_staleness) is not int or not 1 <= max_staleness <= 31536000):
            raise LocalPillarError("INVALID_INPUT", "max_staleness_seconds must be 1-31536000")
        now = time.time()
        try:
            with self._connect() as connection:
                query = """SELECT next_intent, observations, corrected, updated_at FROM intent_transitions
                        WHERE owner_id=? AND current_intent=?"""
                params: list[Any] = [owner, current]
                if max_staleness is not None:
                    query += " AND updated_at >= ?"
                    params.append(now - max_staleness)
                query += " ORDER BY observations DESC, next_intent"
                rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent transition cannot be read") from exc
        effective = [
            (row["next_intent"], max(0, int(row["observations"]) - int(row["corrected"])))
            for row in rows
        ]
        total = sum(count for _, count in effective)
        if total < minimum or not effective or effective[0][1] == 0:
            raise LocalPillarError("INSUFFICIENT_HISTORY", "intent history is insufficient")
        top = effective[0]
        tied = [intent for intent, count in effective if count == top[1]]
        if len(tied) > 1:
            raise LocalPillarError("AMBIGUOUS_INTENT", "intent history has tied candidates")
        expires_at = now + ttl
        prediction_id = uuid.uuid4().hex
        confidence = round(top[1] / total, 4)
        explanation = f"Inferred '{top[0]}' after '{current}' based on {top[1]}/{total} effective historical transitions"
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO intent_predictions VALUES(?,?,?,?,?,?,NULL,?,?)",
                    (prediction_id, owner, current, top[0], confidence, expires_at, now, explanation),
                )
                self._log_audit(
                    connection, owner, "INTENT_PREDICTION_CREATED",
                    {"prediction_id": prediction_id, "current": current, "candidate": top[0], "confidence": confidence}
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent prediction was not stored") from exc
        return LocalPillarResult(
            "P040",
            "INTENT_INFERENCE_CREATED",
            {
                "prediction_id": prediction_id,
                "candidate": top[0],
                "confidence": confidence,
                "source": "INFERENCE",
                "confirmation_required": True,
                "executed": False,
                "explanation": explanation,
                "expires_at": expires_at,
            },
        )

    def feedback(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "prediction_id", "confirmed", "alternative_intent"},
            {"action", "prediction_id", "confirmed"},
        )
        prediction_id = _text(request["prediction_id"], "prediction_id", 128)
        confirmed = request["confirmed"]
        if type(confirmed) is not bool:
            raise LocalPillarError("INVALID_INPUT", "confirmed must be boolean")
        alt = request.get("alternative_intent")
        alt_intent = _text(alt, "alternative_intent", 128).casefold() if alt is not None else None
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM intent_predictions WHERE prediction_id=?", (prediction_id,)
                ).fetchone()
                if row is None or row["confirmed"] is not None:
                    raise LocalPillarError("PREDICTION_NOT_FOUND", "prediction is missing or closed")
                connection.execute(
                    "UPDATE intent_predictions SET confirmed=? WHERE prediction_id=?",
                    (int(confirmed), prediction_id),
                )
                if not confirmed:
                    connection.execute(
                        """UPDATE intent_transitions SET corrected=corrected+1
                        WHERE owner_id=? AND current_intent=? AND next_intent=?""",
                        (row["owner_id"], row["current_intent"], row["candidate"]),
                    )
                    if alt_intent:
                        connection.execute(
                            """INSERT INTO intent_transitions VALUES(?,?,?,1,0,?)
                            ON CONFLICT(owner_id,current_intent,next_intent)
                            DO UPDATE SET observations=observations+1,updated_at=excluded.updated_at""",
                            (row["owner_id"], row["current_intent"], alt_intent, time.time()),
                        )
                self._update_receipt(connection)
                self._log_audit(
                    connection, row["owner_id"], "INTENT_FEEDBACK_RECORDED",
                    {"prediction_id": prediction_id, "confirmed": confirmed, "alternative": alt_intent}
                )
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent feedback was not stored") from exc
        return LocalPillarResult("P040", "INTENT_FEEDBACK_RECORDED", {"confirmed": confirmed, "prediction_id": prediction_id})

    def opt_out(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "owner_id"}, {"action", "owner_id"})
        owner = _text(request["owner_id"], "owner_id", 128)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE intent_consent SET opted_out=1 WHERE owner_id=?", (owner,)
                )
                connection.execute("DELETE FROM intent_transitions WHERE owner_id=?", (owner,))
                self._update_receipt(connection)
                self._log_audit(connection, owner, "INTENT_PROFILING_DISABLED", {})
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent opt-out failed") from exc
        return LocalPillarResult("P040", "INTENT_PROFILING_DISABLED", {"owner_id": owner})

    def delete(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "owner_id"}, {"action", "owner_id"})
        owner = _text(request["owner_id"], "owner_id", 128)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM intent_transitions WHERE owner_id=?", (owner,))
                connection.execute("DELETE FROM intent_predictions WHERE owner_id=?", (owner,))
                connection.execute("DELETE FROM intent_consent WHERE owner_id=?", (owner,))
                connection.execute("DELETE FROM intent_audit_log WHERE owner_id=?", (owner,))
                self._update_receipt(connection)
                self._log_audit(connection, None, "INTENT_DATA_PURGED", {"owner_id": owner})
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "intent data deletion failed") from exc
        return LocalPillarResult("P040", "INTENT_DATA_PURGED", {"owner_id": owner, "purged": True})

    def _verify_integrity_action(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action"}, {"action"})
        self.verify_integrity()
        return LocalPillarResult("P040", "INTENT_INTEGRITY_VERIFIED", {"status": "ok"})

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        actions = {
            "record_consent": self.consent,
            "consent": self.consent,
            "consent_status": self.consent_status,
            "get_consent": self.consent_status,
            "observe": self.observe,
            "predict": self.predict,
            "feedback": self.feedback,
            "opt_out": self.opt_out,
            "revoke_consent": self.opt_out,
            "delete": self.delete,
            "purge_data": self.delete,
            "verify_integrity": self._verify_integrity_action,
        }
        handler = actions.get(request.get("action"))
        if handler is None:
            raise LocalPillarError("UNSUPPORTED_ACTION", "intent action is unsupported")
        return handler(request)


class DynamicObjectiveCapability:
    """Persist immutable owner goals and apply only signed, bounded reprioritizations."""

    def __init__(
        self,
        database_path: Path,
        approval_key: bytes | None,
        rag: AgenticRAGCapability,
        sandbox: SandboxedImaginationCapability,
        dampening_window_seconds: float = 5.0,
    ) -> None:
        self.database_path = database_path.resolve()
        self.approval_key = approval_key
        self.rag = rag
        self.sandbox = sandbox
        self.dampening_window_seconds = float(dampening_window_seconds)
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS objective_schema(
                        schema_version INTEGER PRIMARY KEY,
                        applied_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS owner_goals(
                        objective_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                        owner_goal TEXT NOT NULL, goal_digest TEXT NOT NULL,
                        invariants_json TEXT NOT NULL, created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS objective_versions(
                        objective_id TEXT NOT NULL, version INTEGER NOT NULL,
                        weights_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                        policy_decision TEXT NOT NULL, proposal_digest TEXT NOT NULL,
                        approved INTEGER NOT NULL, expires_at REAL NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY(objective_id,version)
                    );
                    CREATE TABLE IF NOT EXISTS objective_rollbacks(
                        rollback_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL,
                        from_version INTEGER NOT NULL, to_version INTEGER NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS objective_approvals(
                        approval_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL,
                        version INTEGER NOT NULL, approved_by TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS objective_audit_log(
                        audit_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL,
                        action TEXT NOT NULL, version INTEGER,
                        details_json TEXT NOT NULL, created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS objective_state_receipts(
                        receipt_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL,
                        version INTEGER NOT NULL, state_digest TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
                row = connection.execute("SELECT schema_version FROM objective_schema LIMIT 1").fetchone()
                if row is None:
                    connection.execute("INSERT INTO objective_schema VALUES(?,?)", (2, time.time()))
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "objective store unavailable") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def health_check(self) -> bool:
        return bool(self.approval_key and len(self.approval_key) >= 32 and self.sandbox.health_check())

    def _signature(self, material: str) -> str:
        if self.approval_key is None:
            raise LocalPillarError("APPROVAL_NOT_CONFIGURED", "objective approval key is unavailable")
        return hmac.new(self.approval_key, material.encode("utf-8"), hashlib.sha256).hexdigest()

    def _log_audit(
        self,
        connection: sqlite3.Connection,
        objective_id: str,
        action: str,
        version: int | None,
        details: Mapping[str, Any],
    ) -> None:
        audit_id = f"aud-{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO objective_audit_log VALUES(?,?,?,?,?,?)",
            (audit_id, objective_id, action, version, _canonical(details), time.time()),
        )

    def _save_receipt(
        self,
        connection: sqlite3.Connection,
        objective_id: str,
        version: int,
        weights: Mapping[str, float],
        proposal_digest: str,
    ) -> str:
        material = {
            "objective_id": objective_id,
            "version": version,
            "weights": weights,
            "proposal_digest": proposal_digest,
        }
        state_digest = _digest(material)
        receipt_id = f"rcpt-{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO objective_state_receipts VALUES(?,?,?,?,?)",
            (receipt_id, objective_id, version, state_digest, time.time()),
        )
        return state_digest

    def create(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "objective_id", "owner_id", "owner_goal", "invariants", "weights"},
            {"action", "objective_id", "owner_id", "owner_goal", "invariants", "weights"},
        )
        objective_id = _text(request["objective_id"], "objective_id", 128)
        owner = _text(request["owner_id"], "owner_id", 128)
        goal = _text(request["owner_goal"], "owner_goal", 2_000, 8)
        invariants = request["invariants"]
        if not isinstance(invariants, list) or not 1 <= len(invariants) <= 16:
            raise LocalPillarError("RESOURCE_LIMIT", "invariants must contain 1-16 expressions")
        for invariant in invariants:
            if self.sandbox.evaluate(invariant).data["result"] is not True:
                raise LocalPillarError("INVARIANT_VIOLATION", "owner invariant is not true")
        weights = self._weights(request["weights"])
        digest = _digest({"owner_id": owner, "owner_goal": goal, "invariants": invariants})
        now = time.time()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO owner_goals VALUES(?,?,?,?,?,?)",
                    (objective_id, owner, goal, digest, _canonical(invariants), now),
                )
                material = {"objective_id": objective_id, "version": 1, "weights": weights}
                initial_digest = _digest(material)
                connection.execute(
                    "INSERT INTO objective_versions VALUES(?,?,?,?,?,?,?,?,?)",
                    (objective_id, 1, _canonical(weights), "[]", "OWNER_INITIAL", initial_digest, 1, now + 10 * 365 * 86400, now),
                )
                state_digest = self._save_receipt(connection, objective_id, 1, weights, initial_digest)
                self._log_audit(
                    connection,
                    objective_id,
                    "CREATE",
                    1,
                    {"owner_id": owner, "goal_digest": digest, "weights": weights},
                )
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("OBJECTIVE_EXISTS", "objective_id already exists") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "objective was not stored") from exc
        return LocalPillarResult(
            "P039",
            "OWNER_OBJECTIVE_CREATED",
            {
                "objective_id": objective_id,
                "goal_digest": digest,
                "version": 1,
                "weights": weights,
                "state_digest": state_digest,
            },
        )

    @staticmethod
    def _weights(raw: object) -> dict[str, float]:
        if not isinstance(raw, Mapping) or not 1 <= len(raw) <= 32:
            raise LocalPillarError("INVALID_INPUT", "weights must contain 1-32 entries")
        output: dict[str, float] = {}
        for key, value in raw.items():
            name = _text(key, "weight name", 128)
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise LocalPillarError("INVALID_INPUT", "weight values must be numeric") from exc
            if not math.isfinite(number) or number < 0:
                raise LocalPillarError("INVALID_INPUT", "weights must be finite and non-negative")
            output[name] = number
        total = sum(output.values())
        if total <= 0:
            raise LocalPillarError("INVALID_INPUT", "at least one weight must be positive")
        return {key: value / total for key, value in sorted(output.items())}

    def propose(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "objective_id", "signals", "learning_rate", "evidence_ids", "policy_decision", "expires_at"},
            {"action", "objective_id", "signals", "learning_rate", "evidence_ids", "policy_decision", "expires_at"},
        )
        objective_id = _text(request["objective_id"], "objective_id", 128)
        signals = request["signals"]
        if not isinstance(signals, Mapping):
            raise LocalPillarError("INVALID_INPUT", "signals must be an object")
        try:
            rate = float(request["learning_rate"])
            expires = float(request["expires_at"])
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "learning_rate and expires_at must be numeric") from exc
        if not math.isfinite(rate) or not 0 < rate <= 0.25:
            raise LocalPillarError("INVALID_INPUT", "learning_rate must be within (0,0.25]")
        if not math.isfinite(expires) or not time.time() < expires <= time.time() + 30 * 86400:
            raise LocalPillarError("INVALID_INPUT", "proposal expiry is invalid")
        policy = _text(request["policy_decision"], "policy_decision", 32).upper()
        if policy != "ALLOW":
            raise LocalPillarError("POLICY_DENIED", "objective change was not allowed")
        evidence_ids = request["evidence_ids"]
        if not isinstance(evidence_ids, list) or not 1 <= len(evidence_ids) <= 32:
            raise LocalPillarError("RESOURCE_LIMIT", "evidence_ids must contain 1-32 items")
        normalized_evidence = [_text(item, "evidence_id", 128) for item in evidence_ids]
        if not all(self.rag.evidence_exists(item) for item in normalized_evidence):
            raise LocalPillarError("INVALID_EVIDENCE", "objective evidence is unavailable")
        now = time.time()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    """SELECT v.* FROM objective_versions v WHERE v.objective_id=? AND v.approved=1
                    ORDER BY v.version DESC LIMIT 1""",
                    (objective_id,),
                ).fetchone()
                if current is None:
                    raise LocalPillarError("OBJECTIVE_NOT_FOUND", "objective was not found")
                weights = json.loads(current["weights_json"])
                if set(signals) != set(weights):
                    raise LocalPillarError("INVALID_INPUT", "signals must match existing subgoals")

                # Anti-Oscillation Guard: Check if opposing signals are proposed within dampening horizon
                if int(current["version"]) >= 2:
                    prev_row = connection.execute(
                        "SELECT weights_json, created_at FROM objective_versions WHERE objective_id=? AND version=?",
                        (objective_id, int(current["version"]) - 1),
                    ).fetchone()
                    if prev_row is not None:
                        dwell = now - float(current["created_at"])
                        if dwell < self.dampening_window_seconds:
                            prev_weights = json.loads(prev_row["weights_json"])
                            for key, raw_sig in signals.items():
                                sig = float(raw_sig)
                                delta_prev = weights.get(key, 0.0) - prev_weights.get(key, 0.0)
                                if abs(delta_prev) > 1e-4 and (delta_prev * sig) < -1e-4:
                                    raise LocalPillarError(
                                        "OSCILLATION_DETECTED",
                                        f"subgoal weight oscillation detected for '{key}' within dampening horizon ({dwell:.2f}s < {self.dampening_window_seconds}s)",
                                    )

                proposed = {}
                for key, weight in weights.items():
                    signal = float(signals[key])
                    if not math.isfinite(signal) or not -1 <= signal <= 1:
                        raise LocalPillarError("INVALID_INPUT", "signals must be finite and within -1..1")
                    proposed[key] = max(0.0, float(weight) + rate * signal)
                normalized = self._weights(proposed)
                version = int(current["version"]) + 1

                # Clean up expired unapproved proposal if any exists
                connection.execute(
                    "DELETE FROM objective_versions WHERE objective_id=? AND version=? AND approved=0 AND expires_at<=?",
                    (objective_id, version, now),
                )

                material = {
                    "objective_id": objective_id,
                    "version": version,
                    "weights": normalized,
                    "evidence_ids": normalized_evidence,
                    "policy_decision": policy,
                    "expires_at": expires,
                }
                proposal_digest = _digest(material)
                connection.execute(
                    "INSERT INTO objective_versions VALUES(?,?,?,?,?,?,?,?,?)",
                    (objective_id, version, _canonical(normalized), _canonical(normalized_evidence), policy, proposal_digest, 0, expires, now),
                )
                self._log_audit(
                    connection,
                    objective_id,
                    "PROPOSE",
                    version,
                    {
                        "proposal_digest": proposal_digest,
                        "weights": normalized,
                        "rate": rate,
                        "evidence_ids": normalized_evidence,
                    },
                )
        except LocalPillarError:
            raise
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "objective proposal failed") from exc
        return LocalPillarResult(
            "P039",
            "OBJECTIVE_CHANGE_PROPOSED",
            {
                "objective_id": objective_id,
                "version": version,
                "proposal_digest": proposal_digest,
                "weights": normalized,
                "approval_required": True,
            },
        )

    def approve(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "objective_id", "version", "approval_id", "approved_by", "signature"},
            {"action", "objective_id", "version", "approval_id", "approved_by", "signature"},
        )
        objective_id = _text(request["objective_id"], "objective_id", 128)
        version = request["version"]
        if type(version) is not int or version < 2:
            raise LocalPillarError("INVALID_INPUT", "proposal version is invalid")
        approval_id = _text(request["approval_id"], "approval_id", 128)
        approved_by = _text(request["approved_by"], "approved_by", 128)
        signature = _text(request["signature"], "signature", 128)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                # Check for replayed approval_id
                replayed = connection.execute(
                    "SELECT 1 FROM objective_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
                if replayed is not None:
                    raise LocalPillarError("APPROVAL_DENIED", "approval_id has already been used")

                row = connection.execute(
                    """SELECT v.*,g.owner_id FROM objective_versions v JOIN owner_goals g
                    ON g.objective_id=v.objective_id WHERE v.objective_id=? AND v.version=?""",
                    (objective_id, version),
                ).fetchone()
                if row is None or row["approved"]:
                    raise LocalPillarError("PROPOSAL_NOT_FOUND", "proposal is missing or approved")
                if row["owner_id"] != approved_by:
                    raise LocalPillarError("APPROVAL_DENIED", "only the objective owner can approve")
                if float(row["expires_at"]) <= time.time():
                    raise LocalPillarError("PROPOSAL_EXPIRED", "objective proposal expired")
                material = f"approve|{objective_id}|{version}|{row['proposal_digest']}|{approval_id}|{approved_by}"
                if not hmac.compare_digest(signature, self._signature(material)):
                    raise LocalPillarError("APPROVAL_DENIED", "objective approval signature is invalid")

                connection.execute(
                    "INSERT INTO objective_approvals VALUES(?,?,?,?,?)",
                    (approval_id, objective_id, version, approved_by, time.time()),
                )
                connection.execute(
                    "UPDATE objective_versions SET approved=1 WHERE objective_id=? AND version=?",
                    (objective_id, version),
                )
                weights = json.loads(row["weights_json"])
                state_digest = self._save_receipt(
                    connection, objective_id, version, weights, row["proposal_digest"]
                )
                self._log_audit(
                    connection,
                    objective_id,
                    "APPROVE",
                    version,
                    {"approval_id": approval_id, "approved_by": approved_by, "state_digest": state_digest},
                )
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "objective approval failed") from exc
        return LocalPillarResult(
            "P039",
            "OBJECTIVE_CHANGE_APPROVED",
            {"objective_id": objective_id, "version": version, "state_digest": state_digest},
        )

    def active(self, objective_id: str) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """SELECT g.owner_goal,g.goal_digest,g.invariants_json,v.*
                    FROM owner_goals g JOIN objective_versions v ON v.objective_id=g.objective_id
                    WHERE g.objective_id=? AND v.approved=1 ORDER BY v.version DESC LIMIT 1""",
                    (objective_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "objective cannot be read") from exc
        if row is None:
            raise LocalPillarError("OBJECTIVE_NOT_FOUND", "objective was not found")
        return {
            "objective_id": objective_id,
            "owner_goal": row["owner_goal"],
            "goal_digest": row["goal_digest"],
            "invariants": json.loads(row["invariants_json"]),
            "version": int(row["version"]),
            "weights": json.loads(row["weights_json"]),
        }

    def rollback(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "objective_id", "to_version", "rollback_id", "approved_by", "signature"},
            {"action", "objective_id", "to_version", "rollback_id", "approved_by", "signature"},
        )
        objective_id = _text(request["objective_id"], "objective_id", 128)
        to_version = request["to_version"]
        if type(to_version) is not int or to_version < 1:
            raise LocalPillarError("INVALID_INPUT", "rollback version is invalid")
        rollback_id = _text(request["rollback_id"], "rollback_id", 128)
        approved_by = _text(request["approved_by"], "approved_by", 128)
        signature = _text(request["signature"], "signature", 128)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                owner = connection.execute(
                    "SELECT owner_id FROM owner_goals WHERE objective_id=?", (objective_id,)
                ).fetchone()
                current = connection.execute(
                    "SELECT max(version) FROM objective_versions WHERE objective_id=? AND approved=1",
                    (objective_id,),
                ).fetchone()[0]
                target = connection.execute(
                    "SELECT * FROM objective_versions WHERE objective_id=? AND version=? AND approved=1",
                    (objective_id, to_version),
                ).fetchone()
                if owner is None or target is None or current is None or to_version >= int(current):
                    raise LocalPillarError("ROLLBACK_TARGET_INVALID", "rollback target is unavailable")
                if owner["owner_id"] != approved_by:
                    raise LocalPillarError("APPROVAL_DENIED", "only the owner can roll back")
                material = f"rollback|{objective_id}|{current}|{to_version}|{rollback_id}|{approved_by}"
                if not hmac.compare_digest(signature, self._signature(material)):
                    raise LocalPillarError("APPROVAL_DENIED", "rollback signature is invalid")
                new_version = int(current) + 1
                cloned = {
                    "objective_id": objective_id,
                    "version": new_version,
                    "weights": json.loads(target["weights_json"]),
                    "rollback_from": int(current),
                    "rollback_to": to_version,
                }
                new_digest = _digest(cloned)
                now = time.time()
                connection.execute(
                    "INSERT INTO objective_versions VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        objective_id,
                        new_version,
                        target["weights_json"],
                        target["evidence_json"],
                        "OWNER_ROLLBACK",
                        new_digest,
                        1,
                        now + 10 * 365 * 86400,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO objective_rollbacks VALUES(?,?,?,?,?)",
                    (rollback_id, objective_id, int(current), to_version, now),
                )
                state_digest = self._save_receipt(
                    connection, objective_id, new_version, json.loads(target["weights_json"]), new_digest
                )
                self._log_audit(
                    connection,
                    objective_id,
                    "ROLLBACK",
                    new_version,
                    {
                        "rollback_id": rollback_id,
                        "from_version": int(current),
                        "to_version": to_version,
                        "state_digest": state_digest,
                    },
                )
        except LocalPillarError:
            raise
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("DUPLICATE_ROLLBACK", "rollback_id was already used") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "objective rollback failed") from exc
        return LocalPillarResult(
            "P039",
            "OBJECTIVE_ROLLED_BACK",
            {
                "objective_id": objective_id,
                "version": new_version,
                "restored_from": to_version,
                "state_digest": state_digest,
            },
        )

    def history(self, objective_id: str) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                owner = connection.execute(
                    "SELECT * FROM owner_goals WHERE objective_id=?", (objective_id,)
                ).fetchone()
                if owner is None:
                    raise LocalPillarError("OBJECTIVE_NOT_FOUND", "objective was not found")
                versions = connection.execute(
                    "SELECT * FROM objective_versions WHERE objective_id=? ORDER BY version ASC",
                    (objective_id,),
                ).fetchall()
                rollbacks = connection.execute(
                    "SELECT * FROM objective_rollbacks WHERE objective_id=? ORDER BY created_at ASC",
                    (objective_id,),
                ).fetchall()
                audits = connection.execute(
                    "SELECT * FROM objective_audit_log WHERE objective_id=? ORDER BY created_at ASC",
                    (objective_id,),
                ).fetchall()
                receipts = connection.execute(
                    "SELECT * FROM objective_state_receipts WHERE objective_id=? ORDER BY created_at ASC",
                    (objective_id,),
                ).fetchall()
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read history") from exc

        return {
            "objective_id": objective_id,
            "owner_id": owner["owner_id"],
            "owner_goal": owner["owner_goal"],
            "goal_digest": owner["goal_digest"],
            "invariants": json.loads(owner["invariants_json"]),
            "versions": [
                {
                    "version": row["version"],
                    "weights": json.loads(row["weights_json"]),
                    "approved": bool(row["approved"]),
                    "policy_decision": row["policy_decision"],
                    "proposal_digest": row["proposal_digest"],
                    "expires_at": row["expires_at"],
                    "created_at": row["created_at"],
                }
                for row in versions
            ],
            "rollbacks": [
                {
                    "rollback_id": row["rollback_id"],
                    "from_version": row["from_version"],
                    "to_version": row["to_version"],
                    "created_at": row["created_at"],
                }
                for row in rollbacks
            ],
            "receipts": [
                {
                    "receipt_id": row["receipt_id"],
                    "version": row["version"],
                    "state_digest": row["state_digest"],
                    "created_at": row["created_at"],
                }
                for row in receipts
            ],
            "audit_events": [
                {
                    "audit_id": row["audit_id"],
                    "action": row["action"],
                    "version": row["version"],
                    "details": json.loads(row["details_json"]),
                    "created_at": row["created_at"],
                }
                for row in audits
            ],
        }

    def verify_integrity(self, objective_id: str | None = None) -> LocalPillarResult:
        try:
            with self._connect() as connection:
                check = connection.execute("PRAGMA quick_check").fetchone()
                if not check or check[0] != "ok":
                    raise LocalPillarError("STORAGE_CORRUPT", "sqlite pragma quick_check failed")

                goals = (
                    connection.execute("SELECT * FROM owner_goals WHERE objective_id=?", (objective_id,)).fetchall()
                    if objective_id
                    else connection.execute("SELECT * FROM owner_goals").fetchall()
                )
                for g in goals:
                    expected_digest = _digest(
                        {"owner_id": g["owner_id"], "owner_goal": g["owner_goal"], "invariants": json.loads(g["invariants_json"])}
                    )
                    if g["goal_digest"] != expected_digest:
                        raise LocalPillarError("STORAGE_CORRUPT", f"owner goal digest mismatch for {g['objective_id']}")

                receipts = (
                    connection.execute("SELECT * FROM objective_state_receipts WHERE objective_id=?", (objective_id,)).fetchall()
                    if objective_id
                    else connection.execute("SELECT * FROM objective_state_receipts").fetchall()
                )
                for r in receipts:
                    v_row = connection.execute(
                        "SELECT weights_json, proposal_digest FROM objective_versions WHERE objective_id=? AND version=?",
                        (r["objective_id"], r["version"]),
                    ).fetchone()
                    if v_row is None:
                        raise LocalPillarError("STORAGE_CORRUPT", f"missing version {r['version']} for receipt {r['receipt_id']}")
                    expected_state = _digest(
                        {
                            "objective_id": r["objective_id"],
                            "version": r["version"],
                            "weights": json.loads(v_row["weights_json"]),
                            "proposal_digest": v_row["proposal_digest"],
                        }
                    )
                    if r["state_digest"] != expected_state:
                        raise LocalPillarError("STORAGE_CORRUPT", f"state digest mismatch for receipt {r['receipt_id']}")
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "storage verification error") from exc

        return LocalPillarResult(
            "P039",
            "INTEGRITY_VERIFIED",
            {"status": "HEALTHY", "goals_checked": len(goals), "receipts_checked": len(receipts)},
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "create":
            return self.create(request)
        if action == "propose":
            return self.propose(request)
        if action == "approve":
            return self.approve(request)
        if action == "rollback":
            return self.rollback(request)
        if action == "get_active":
            _strict(request, {"action", "objective_id"}, {"action", "objective_id"})
            return LocalPillarResult("P039", "ACTIVE_OBJECTIVE_READ", self.active(_text(request["objective_id"], "objective_id", 128)))
        if action == "history":
            _strict(request, {"action", "objective_id"}, {"action", "objective_id"})
            return LocalPillarResult("P039", "OBJECTIVE_HISTORY_READ", self.history(_text(request["objective_id"], "objective_id", 128)))
        if action == "verify_integrity":
            allowed = {"action"}
            optional = {"objective_id"}
            _strict(request, allowed | optional, allowed)
            oid = _text(request["objective_id"], "objective_id", 128) if "objective_id" in request else None
            return self.verify_integrity(oid)
        raise LocalPillarError("UNSUPPORTED_ACTION", "objective action is unsupported")


class RemoteModelProviderProtocol:
    """Interface for remote model providers."""

    provider_type: str = "REMOTE_MODEL"

    def health_check(self) -> bool:
        return True

    def ask(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise NotImplementedError


class HybridRoutingCapability:
    """Probe and invoke real local rule, retrieval, model, remote, and media adapters."""

    def __init__(
        self,
        database_path: Path,
        rag: AgenticRAGCapability,
        sandbox: SandboxedImaginationCapability,
        media: MediaObservationCapability,
        remote_provider: Any | None = None,
        offline_mode: bool = False,
    ) -> None:
        self.database_path = database_path.resolve()
        self.rag = rag
        self.sandbox = sandbox
        self.media = media
        self.remote_provider = remote_provider
        self.offline_mode = bool(offline_mode)
        self.provider_ttl_seconds = 60.0
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS hybrid_routing_schema(
                        schema_version INTEGER PRIMARY KEY,
                        applied_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS hybrid_routes(
                        route_id TEXT PRIMARY KEY,
                        request_kind TEXT NOT NULL,
                        provider_type TEXT NOT NULL,
                        sensitivity TEXT NOT NULL,
                        latency_ns INTEGER NOT NULL,
                        result_digest TEXT NOT NULL,
                        failover_history_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS hybrid_providers(
                        provider_name TEXT PRIMARY KEY,
                        provider_type TEXT NOT NULL,
                        endpoint TEXT,
                        health_status TEXT NOT NULL,
                        last_health_check REAL NOT NULL,
                        health_ttl_seconds REAL NOT NULL,
                        capabilities_json TEXT NOT NULL,
                        registered_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS hybrid_routing_audit_log(
                        audit_id TEXT PRIMARY KEY,
                        route_id TEXT,
                        action TEXT NOT NULL,
                        provider_type TEXT,
                        details_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS hybrid_route_receipts(
                        receipt_id TEXT PRIMARY KEY,
                        route_id TEXT NOT NULL,
                        provider_type TEXT NOT NULL,
                        result_digest TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
                # Ensure backward-compatible columns in hybrid_routes if table existed
                cols = {row[1] for row in connection.execute("PRAGMA table_info(hybrid_routes)").fetchall()}
                if "sensitivity" not in cols:
                    connection.execute("ALTER TABLE hybrid_routes ADD COLUMN sensitivity TEXT DEFAULT 'INTERNAL'")
                if "failover_history_json" not in cols:
                    connection.execute("ALTER TABLE hybrid_routes ADD COLUMN failover_history_json TEXT DEFAULT '[]'")

                row = connection.execute("SELECT schema_version FROM hybrid_routing_schema LIMIT 1").fetchone()
                if row is None:
                    connection.execute("INSERT INTO hybrid_routing_schema VALUES(?,?)", (2, time.time()))

                # Register default local providers
                now = time.time()
                default_providers = [
                    ("rule_sandbox", "RULE_BASED", "local://sandbox", "HEALTHY", now, 300.0, ["expression"]),
                    ("rag_retrieval", "RETRIEVAL", "local://rag", "HEALTHY", now, 60.0, ["retrieval"]),
                    ("rag_local_model", "LOCAL_MODEL", "local://model", "HEALTHY", now, 60.0, ["grounded_answer"]),
                    ("media_tool", "TOOL", "local://media", "HEALTHY", now, 300.0, ["media"]),
                ]
                for p_name, p_type, p_ep, p_stat, p_last, p_ttl, p_caps in default_providers:
                    connection.execute(
                        """INSERT OR IGNORE INTO hybrid_providers VALUES(?,?,?,?,?,?,?,?)""",
                        (p_name, p_type, p_ep, p_stat, p_last, p_ttl, _canonical(p_caps), now),
                    )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "hybrid route store unavailable") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def health_check(self) -> bool:
        return self.sandbox.health_check()

    def _log_audit(
        self,
        connection: sqlite3.Connection,
        route_id: str | None,
        action: str,
        provider_type: str | None,
        details: Mapping[str, Any],
    ) -> None:
        audit_id = f"aud-{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO hybrid_routing_audit_log VALUES(?,?,?,?,?,?)",
            (audit_id, route_id, action, provider_type, _canonical(details), time.time()),
        )

    def _save_receipt(
        self,
        connection: sqlite3.Connection,
        route_id: str,
        provider_type: str,
        result_digest: str,
    ) -> str:
        receipt_id = f"rcpt-{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO hybrid_route_receipts VALUES(?,?,?,?,?)",
            (receipt_id, route_id, provider_type, result_digest, time.time()),
        )
        return receipt_id

    def route(self, request: Mapping[str, Any]) -> LocalPillarResult:
        allowed = {
            "action",
            "request_kind",
            "sensitivity",
            "payload",
            "allow_degraded",
            "allow_fallback",
            "objective_id",
            "offline_only",
            "preferred_route",
        }
        required = {"action", "request_kind", "sensitivity", "payload"}
        _strict(request, allowed, required)

        kind = _text(request["request_kind"], "request_kind", 64).upper()
        sensitivity = _text(request["sensitivity"], "sensitivity", 32).upper()
        if sensitivity not in {"PUBLIC", "INTERNAL", "RESTRICTED"}:
            raise LocalPillarError("INVALID_INPUT", "sensitivity is unsupported")
        payload = request["payload"]
        if not isinstance(payload, Mapping):
            raise LocalPillarError("INVALID_INPUT", "payload must be an object")

        allow_fallback = bool(request.get("allow_fallback") or request.get("allow_degraded", False))
        request_offline = bool(request.get("offline_only", False)) or self.offline_mode
        objective_id = _text(request["objective_id"], "objective_id", 128) if "objective_id" in request else None

        started = time.perf_counter_ns()
        failover_history: list[dict[str, Any]] = []
        citations: list[str] = []

        if kind == "EXPRESSION":
            provider_type = "RULE_BASED"
            result = self.sandbox.execute({"action": "evaluate", **dict(payload)}).data

        elif kind == "RETRIEVAL":
            provider_type = "RETRIEVAL"
            query = _text(payload.get("query"), "query", 4_096)
            top_k = payload.get("top_k", 5)
            if type(top_k) is not int or not 1 <= top_k <= 20:
                raise LocalPillarError("INVALID_INPUT", "top_k must be 1-20")
            evidence = self.rag.retrieve(query, top_k)
            if not evidence:
                raise LocalPillarError("EVIDENCE_UNAVAILABLE", "hybrid retrieval found no evidence")
            citations = [item["evidence_id"] for item in evidence if "evidence_id" in item]
            result = {"evidence": evidence, "citations": citations}

        elif kind == "GROUNDED_ANSWER":
            if self.rag.health_check():
                provider_type = "LOCAL_MODEL"
                ask_res = self.rag.ask({"action": "ask", **dict(payload)}).data
                result = ask_res
                citations = list(ask_res.get("citations", []))
            elif allow_fallback:
                # Graceful failover to retrieval only
                query = _text(payload.get("question"), "question", 4_096)
                top_k = int(payload.get("top_k", 5))
                evidence = self.rag.retrieve(query, top_k)
                if not evidence:
                    raise LocalPillarError("EVIDENCE_UNAVAILABLE", "degraded retrieval found no evidence")
                citations = [item["evidence_id"] for item in evidence if "evidence_id" in item]
                provider_type = "RETRIEVAL"
                failover_history.append(
                    {
                        "fallback_from": "LOCAL_MODEL",
                        "reason": "local model health check failed",
                        "fell_back_to": "RETRIEVAL",
                    }
                )
                result = {
                    "evidence": evidence,
                    "citations": citations,
                    "answer_status": "NOT_GENERATED",
                    "fallback_applied": True,
                }
            else:
                raise LocalPillarError("PROVIDER_UNAVAILABLE", "local model is unavailable")

        elif kind == "REMOTE_ANSWER":
            # Gating Rule 1: Sensitivity check (Restricted data cannot leave local perimeter)
            if sensitivity == "RESTRICTED":
                raise LocalPillarError("PRIVACY_DENIAL", "restricted sensitivity data cannot be routed to remote providers")

            # Gating Rule 2: Offline mode enforcement
            if request_offline:
                if allow_fallback:
                    failover_history.append(
                        {
                            "fallback_from": "REMOTE_MODEL",
                            "reason": "offline mode active",
                            "fell_back_to": "LOCAL_MODEL",
                        }
                    )
                    # Route to local model as fallback
                    if self.rag.health_check():
                        try:
                            provider_type = "LOCAL_MODEL"
                            result = self.rag.ask({"action": "ask", **dict(payload)}).data
                            citations = list(result.get("citations", []))
                        except LocalPillarError:
                            query = _text(payload.get("question", payload.get("prompt", "")), "question", 4_096)
                            evidence = self.rag.retrieve(query, int(payload.get("top_k", 5)))
                            provider_type = "RETRIEVAL"
                            citations = [item["evidence_id"] for item in evidence if "evidence_id" in item]
                            result = {"evidence": evidence, "citations": citations, "fallback_applied": True}
                    else:
                        query = _text(payload.get("question", payload.get("prompt", "")), "question", 4_096)
                        evidence = self.rag.retrieve(query, int(payload.get("top_k", 5)))
                        provider_type = "RETRIEVAL"
                        citations = [item["evidence_id"] for item in evidence if "evidence_id" in item]
                        result = {"evidence": evidence, "citations": citations, "fallback_applied": True}
                else:
                    raise LocalPillarError("OFFLINE_REQUIRED", "offline mode prohibits remote model egress")
            else:
                # Remote execution attempt
                if self.remote_provider is None or not getattr(self.remote_provider, "health_check", lambda: False)():
                    if allow_fallback:
                        failover_history.append(
                            {
                                "fallback_from": "REMOTE_MODEL",
                                "reason": "remote provider unconfigured or unhealthy",
                                "fell_back_to": "LOCAL_MODEL",
                            }
                        )
                        if self.rag.health_check():
                            try:
                                provider_type = "LOCAL_MODEL"
                                result = self.rag.ask({"action": "ask", **dict(payload)}).data
                                citations = list(result.get("citations", []))
                            except LocalPillarError:
                                query = _text(payload.get("question", payload.get("prompt", "")), "question", 4_096)
                                evidence = self.rag.retrieve(query, int(payload.get("top_k", 5)))
                                provider_type = "RETRIEVAL"
                                citations = [item["evidence_id"] for item in evidence if "evidence_id" in item]
                                result = {"evidence": evidence, "citations": citations, "fallback_applied": True}
                        else:
                            query = _text(payload.get("question", payload.get("prompt", "")), "question", 4_096)
                            evidence = self.rag.retrieve(query, int(payload.get("top_k", 5)))
                            provider_type = "RETRIEVAL"
                            citations = [item["evidence_id"] for item in evidence if "evidence_id" in item]
                            result = {"evidence": evidence, "citations": citations, "fallback_applied": True}
                    else:
                        raise LocalPillarError("REMOTE_UNAVAILABLE", "remote model provider is unconfigured or unhealthy")
                else:
                    try:
                        remote_out = self.remote_provider.ask(payload)
                        provider_type = "REMOTE_MODEL"
                        result = dict(remote_out)
                        citations = list(result.get("citations", []))
                    except Exception as exc:
                        if allow_fallback:
                            failover_history.append(
                                {
                                    "fallback_from": "REMOTE_MODEL",
                                    "reason": str(exc),
                                    "fell_back_to": "LOCAL_MODEL",
                                }
                            )
                            provider_type = "LOCAL_MODEL"
                            result = self.rag.ask({"action": "ask", **dict(payload)}).data
                            citations = list(result.get("citations", []))
                        else:
                            raise LocalPillarError("REMOTE_UNAVAILABLE", f"remote model execution failed: {exc}") from exc

        elif kind == "MEDIA":
            provider_type = "TOOL"
            result = self.media.execute({"action": "observe_file", **dict(payload)}).data

        else:
            raise LocalPillarError("REQUEST_KIND_UNSUPPORTED", "no hybrid adapter supports request")

        latency = time.perf_counter_ns() - started
        route_id = uuid.uuid4().hex
        result_digest = _digest(result)
        now = time.time()

        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO hybrid_routes VALUES(?,?,?,?,?,?,?,?)",
                    (
                        route_id,
                        kind,
                        provider_type,
                        sensitivity,
                        latency,
                        result_digest,
                        _canonical(failover_history),
                        now,
                    ),
                )
                self._save_receipt(connection, route_id, provider_type, result_digest)
                self._log_audit(
                    connection,
                    route_id,
                    "ROUTE_EXECUTED",
                    provider_type,
                    {
                        "request_kind": kind,
                        "sensitivity": sensitivity,
                        "latency_ns": latency,
                        "failover_history": failover_history,
                        "objective_id": objective_id,
                    },
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "hybrid route was not stored") from exc

        return LocalPillarResult(
            "P037",
            "HYBRID_PROVIDER_EXECUTED",
            {
                "route_id": route_id,
                "provider_type": provider_type,
                "sensitivity": sensitivity,
                "latency_ns": latency,
                "result_digest": result_digest,
                "result": result,
                "citations": citations,
                "failover_history": failover_history,
                "objective_id": objective_id,
            },
        )

    def register_provider(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "provider_name", "provider_type", "endpoint", "capabilities", "ttl_seconds"},
            {"action", "provider_name", "provider_type", "capabilities"},
        )
        name = _text(request["provider_name"], "provider_name", 128)
        ptype = _text(request["provider_type"], "provider_type", 64).upper()
        if ptype not in {"RULE_BASED", "RETRIEVAL", "LOCAL_MODEL", "REMOTE_MODEL", "TOOL"}:
            raise LocalPillarError("INVALID_INPUT", "provider_type is unsupported")
        endpoint = _text(request["endpoint"], "endpoint", 256) if "endpoint" in request else None
        caps = request["capabilities"]
        if not isinstance(caps, list):
            raise LocalPillarError("INVALID_INPUT", "capabilities must be a list")
        ttl = float(request.get("ttl_seconds", 60.0))
        now = time.time()
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO hybrid_providers VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(provider_name) DO UPDATE SET
                    provider_type=excluded.provider_type,
                    endpoint=excluded.endpoint,
                    health_status='HEALTHY',
                    last_health_check=excluded.last_health_check,
                    health_ttl_seconds=excluded.health_ttl_seconds,
                    capabilities_json=excluded.capabilities_json""",
                    (name, ptype, endpoint, "HEALTHY", now, ttl, _canonical(caps), now),
                )
                self._log_audit(
                    connection,
                    None,
                    "PROVIDER_REGISTERED",
                    ptype,
                    {"provider_name": name, "endpoint": endpoint, "capabilities": caps},
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "provider registration failed") from exc

        return LocalPillarResult(
            "P037",
            "PROVIDER_REGISTERED",
            {"provider_name": name, "provider_type": ptype, "status": "HEALTHY"},
        )

    def list_providers(self) -> list[dict[str, Any]]:
        now = time.time()
        try:
            with self._connect() as connection:
                rows = connection.execute("SELECT * FROM hybrid_providers ORDER BY registered_at ASC").fetchall()
                result = []
                for row in rows:
                    is_expired = (now - float(row["last_health_check"])) > float(row["health_ttl_seconds"])
                    status = "EXPIRED" if is_expired else row["health_status"]
                    result.append(
                        {
                            "provider_name": row["provider_name"],
                            "provider_type": row["provider_type"],
                            "endpoint": row["endpoint"],
                            "health_status": status,
                            "ttl_seconds": row["health_ttl_seconds"],
                            "capabilities": json.loads(row["capabilities_json"]),
                        }
                    )
                return result
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to list providers") from exc

    def history(self, limit: int = 50) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                routes = connection.execute(
                    "SELECT * FROM hybrid_routes ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                audits = connection.execute(
                    "SELECT * FROM hybrid_routing_audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                receipts = connection.execute(
                    "SELECT * FROM hybrid_route_receipts ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read routing history") from exc

        return {
            "routes": [
                {
                    "route_id": r["route_id"],
                    "request_kind": r["request_kind"],
                    "provider_type": r["provider_type"],
                    "sensitivity": r["sensitivity"],
                    "latency_ns": r["latency_ns"],
                    "result_digest": r["result_digest"],
                    "failover_history": json.loads(r["failover_history_json"]),
                    "created_at": r["created_at"],
                }
                for r in routes
            ],
            "audit_events": [
                {
                    "audit_id": a["audit_id"],
                    "route_id": a["route_id"],
                    "action": a["action"],
                    "provider_type": a["provider_type"],
                    "details": json.loads(a["details_json"]),
                    "created_at": a["created_at"],
                }
                for a in audits
            ],
            "receipts": [
                {
                    "receipt_id": rc["receipt_id"],
                    "route_id": rc["route_id"],
                    "provider_type": rc["provider_type"],
                    "result_digest": rc["result_digest"],
                    "created_at": rc["created_at"],
                }
                for rc in receipts
            ],
        }

    def verify_integrity(self) -> LocalPillarResult:
        try:
            with self._connect() as connection:
                check = connection.execute("PRAGMA quick_check").fetchone()
                if not check or check[0] != "ok":
                    raise LocalPillarError("STORAGE_CORRUPT", "sqlite pragma quick_check failed")

                receipts = connection.execute("SELECT * FROM hybrid_route_receipts").fetchall()
                for rc in receipts:
                    r_row = connection.execute(
                        "SELECT result_digest FROM hybrid_routes WHERE route_id=?", (rc["route_id"],)
                    ).fetchone()
                    if r_row is None or r_row["result_digest"] != rc["result_digest"]:
                        raise LocalPillarError(
                            "STORAGE_CORRUPT", f"route receipt digest mismatch for {rc['route_id']}"
                        )
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "storage verification error") from exc

        return LocalPillarResult(
            "P037",
            "INTEGRITY_VERIFIED",
            {"status": "HEALTHY", "receipts_checked": len(receipts)},
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "route":
            return self.route(request)
        if action == "register_provider":
            return self.register_provider(request)
        if action == "providers":
            return LocalPillarResult("P037", "PROVIDERS_LISTED", {"providers": self.list_providers()})
        if action == "history":
            limit = int(request.get("limit", 50))
            return LocalPillarResult("P037", "ROUTING_HISTORY_READ", self.history(limit))
        if action == "verify_integrity":
            return self.verify_integrity()
        raise LocalPillarError("UNSUPPORTED_ACTION", "hybrid routing action is unsupported")
