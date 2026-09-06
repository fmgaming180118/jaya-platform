"""Persistent local reasoning capabilities for Pillars 3, 36, and 38."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import requests

from .agentic_rag_capability import AgenticRAGCapability
from .foundation_capabilities import SandboxedImaginationCapability
from .local_capabilities import LocalPillarError, LocalPillarResult

DREAM_CAPABILITY_ID = "core.reasoning.dream"
SPECULATIVE_CAPABILITY_ID = "core.reasoning.speculative"
META_PLANNING_CAPABILITY_ID = "core.planning.meta"


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


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class HypothesisProvider(Protocol):
    provider_type: str
    provider_name: str

    def health_check(self) -> bool:
        ...

    def generate(
        self,
        topic: str,
        evidence: Sequence[Mapping[str, Any]],
        candidate_limit: int,
        seed: int,
    ) -> Sequence[Mapping[str, Any]]:
        ...


_DANGEROUS_GOAL_PATTERNS = re.compile(
    r"(?:\b(rm\s+-rf|del\s+/[a-z]|format\s+[a-z]:|os\.system|subprocess\.|shutil\.rmtree|"
    r"powershell(?:\.exe)?\s+-|cmd(?:\.exe)?\s+/[ck]|eval\(|exec\(|"
    r"dump.*password|exfiltrat.*token|steal.*key|cat\s+/etc/shadow|"
    r"reverse_shell|meterpreter))",
    re.IGNORECASE,
)


def _evaluate_dream_goal_safety(topic: str, query: str) -> tuple[bool, str]:
    combined = f"{topic} {query}".strip()
    if _DANGEROUS_GOAL_PATTERNS.search(combined):
        return False, "UNSAFE_GOAL_PROHIBITED"
    return True, ""


def _compute_lexical_diversity(texts: Sequence[str]) -> float:
    if not texts:
        return 0.0
    all_tokens: list[str] = []
    unique_tokens: set[str] = set()
    for text in texts:
        tokens = [t.lower() for t in re.findall(r"\b\w+\b", text)]
        all_tokens.extend(tokens)
        unique_tokens.update(tokens)
    if not all_tokens:
        return 0.0
    return len(unique_tokens) / len(all_tokens)


class DeterministicCounterfactualProvider:
    """Deterministic, grounded counterfactual hypothesis generator for tests/offline."""

    provider_type = "TEST_IMPLEMENTATION"
    provider_name = "deterministic_counterfactual_engine"

    def __init__(
        self,
        *,
        simulate_timeout: bool = False,
        simulate_unhealthy: bool = False,
        unsafe_candidate: bool = False,
    ) -> None:
        self.simulate_timeout = simulate_timeout
        self.simulate_unhealthy = simulate_unhealthy
        self.unsafe_candidate = unsafe_candidate

    def health_check(self) -> bool:
        return not self.simulate_unhealthy

    def generate(
        self,
        topic: str,
        evidence: Sequence[Mapping[str, Any]],
        candidate_limit: int,
        seed: int,
    ) -> Sequence[Mapping[str, Any]]:
        if self.simulate_timeout:
            raise LocalPillarError("TIMEOUT", "hypothesis model timed out")
        if not evidence:
            raise LocalPillarError("EVIDENCE_UNAVAILABLE", "no evidence provided for hypothesis generation")

        candidates = []
        limit = min(candidate_limit, len(evidence))
        for idx in range(limit):
            ev = evidence[idx % len(evidence)]
            ev_id = str(ev["evidence_id"])
            chunk_content = str(ev.get("content", ""))
            words = chunk_content.split()
            concept = " ".join(words[:6]) if words else f"concept_{idx}"

            if self.unsafe_candidate and idx == 0:
                stmt = f"Counterfactual exploit: execute rm -rf / to invalidate {concept}"
                falsify = "Observe system failure"
            else:
                stmt = f"Counterfactual: If {concept} is inverted under seed {seed + idx}, system stability increases"
                falsify = f"Measure stability delta under inverted {concept}"

            candidates.append(
                {
                    "statement": stmt,
                    "evidence_id": ev_id,
                    "falsification_test": falsify,
                }
            )
        return candidates


class OllamaHypothesisProvider:
    """Generate bounded counterfactual candidates using a configured local model."""

    provider_type = "LOCAL_MODEL"

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.provider_name = _text(model, "model", 256)
        if not 1.0 <= timeout_seconds <= 300.0:
            raise LocalPillarError("INVALID_CONFIG", "model timeout must be 1-300 seconds")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def health_check(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            return any(
                item.get("name") == self.provider_name
                for item in response.json().get("models", [])
            )
        except (requests.RequestException, ValueError, TypeError):
            return False

    def generate(
        self,
        topic: str,
        evidence: Sequence[Mapping[str, Any]],
        candidate_limit: int,
        seed: int,
    ) -> Sequence[Mapping[str, Any]]:
        evidence_ids = [str(item["evidence_id"]) for item in evidence]
        context = "\n".join(
            f"[{item['evidence_id']}] {item['content']}" for item in evidence
        )
        schema = {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": candidate_limit,
                    "items": {
                        "type": "object",
                        "properties": {
                            "statement": {"type": "string"},
                            "evidence_id": {"type": "string", "enum": evidence_ids},
                            "falsification_test": {"type": "string"},
                        },
                        "required": ["statement", "evidence_id", "falsification_test"],
                    },
                }
            },
            "required": ["candidates"],
        }
        prompt = (
            "Create counterfactual hypotheses, not facts. Each must be falsifiable and cite one "
            "evidence ID. Do not claim empirical validation. Return only schema JSON.\n"
            f"TOPIC: {topic}\nEVIDENCE:\n{context}"
        )
        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.provider_name,
                    "prompt": prompt,
                    "format": schema,
                    "stream": False,
                    "think": False,
                    "options": {
                        "temperature": 0.3,
                        "seed": seed,
                        "num_predict": min(768, candidate_limit * 192),
                    },
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            raw = response.json().get("response")
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > 262_144:
                raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "hypothesis output is invalid")
            payload = json.loads(raw)
        except requests.Timeout as exc:
            raise LocalPillarError("TIMEOUT", "hypothesis model timed out") from exc
        except requests.RequestException as exc:
            raise LocalPillarError("PROVIDER_UNAVAILABLE", "hypothesis model failed") from exc
        except (ValueError, TypeError) as exc:
            raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "hypothesis JSON is invalid") from exc
        candidates = payload.get("candidates") if isinstance(payload, Mapping) else None
        if not isinstance(candidates, list):
            raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "candidate list is missing")
        return candidates

    def close(self) -> None:
        self.session.close()


class ActiveDreamingCapability:
    """Generate evidence-bound hypotheses and isolate numeric constraint checks."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        database_path: Path,
        rag: AgenticRAGCapability,
        sandbox: SandboxedImaginationCapability,
        provider: HypothesisProvider | None,
        ethical_heart: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.rag = rag
        self.sandbox = sandbox
        self.provider = provider
        self.ethical_heart = ethical_heart
        self.memory = memory
        self._lock = threading.RLock()
        try:
            with _connection(self.database_path) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS dream_schema (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        version INTEGER NOT NULL
                    )"""
                )
                row = connection.execute(
                    "SELECT version FROM dream_schema WHERE singleton = 1"
                ).fetchone()
                if row is not None and int(row[0]) > self.SCHEMA_VERSION:
                    raise LocalPillarError("STORAGE_SCHEMA_UNSUPPORTED", "newer schema detected")
                connection.execute(
                    "INSERT OR IGNORE INTO dream_schema(singleton, version) VALUES (1, ?)",
                    (self.SCHEMA_VERSION,),
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS dream_artifacts(
                        dream_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL,
                        status TEXT NOT NULL DEFAULT 'UNVERIFIED',
                        seed INTEGER NOT NULL DEFAULT 0,
                        topic TEXT NOT NULL DEFAULT '',
                        provider_type TEXT NOT NULL,
                        provider_name TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        result_json TEXT NOT NULL,
                        receipt_sha256 TEXT NOT NULL DEFAULT ''
                    )"""
                )
                table_info = [r[1] for r in connection.execute("PRAGMA table_info(dream_artifacts)").fetchall()]
                if "request_id" not in table_info:
                    connection.execute("ALTER TABLE dream_artifacts ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
                if "status" not in table_info:
                    connection.execute("ALTER TABLE dream_artifacts ADD COLUMN status TEXT NOT NULL DEFAULT 'UNVERIFIED'")
                if "seed" not in table_info:
                    connection.execute("ALTER TABLE dream_artifacts ADD COLUMN seed INTEGER NOT NULL DEFAULT 0")
                if "topic" not in table_info:
                    connection.execute("ALTER TABLE dream_artifacts ADD COLUMN topic TEXT NOT NULL DEFAULT ''")
                if "receipt_sha256" not in table_info:
                    connection.execute("ALTER TABLE dream_artifacts ADD COLUMN receipt_sha256 TEXT NOT NULL DEFAULT ''")
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "dream store unavailable") from exc

    @staticmethod
    def _receipt_digest(values: Sequence[object]) -> str:
        return hashlib.sha256("\x1f".join(str(v) for v in values).encode("utf-8")).hexdigest()

    def health_check(self) -> bool:
        return bool(
            self.provider
            and self.provider.health_check()
            and self.rag.health_check()
            and self.sandbox.health_check()
        )

    def by_request_id(self, request_id: str) -> dict[str, Any] | None:
        with self._lock, _connection(self.database_path) as connection:
            row = connection.execute(
                """SELECT dream_id, request_id, created_at, status, seed, topic,
                          provider_type, provider_name, request_json, result_json, receipt_sha256
                   FROM dream_artifacts WHERE request_id = ?""",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        values = row[:10]
        stored_digest = str(row[10])
        if stored_digest and self._receipt_digest(values) != stored_digest:
            raise LocalPillarError("STORAGE_CORRUPT", "dream receipt integrity check failed")
        data = json.loads(str(row[9]))
        if isinstance(data, dict):
            data["receipt_sha256"] = stored_digest
        return data

    def by_dream_id(self, dream_id: str) -> dict[str, Any] | None:
        with self._lock, _connection(self.database_path) as connection:
            row = connection.execute(
                """SELECT dream_id, request_id, created_at, status, seed, topic,
                          provider_type, provider_name, request_json, result_json, receipt_sha256
                   FROM dream_artifacts WHERE dream_id = ?""",
                (dream_id,),
            ).fetchone()
        if row is None:
            return None
        values = row[:10]
        stored_digest = str(row[10])
        if stored_digest and self._receipt_digest(values) != stored_digest:
            raise LocalPillarError("STORAGE_CORRUPT", "dream receipt integrity check failed")
        data = json.loads(str(row[9]))
        if isinstance(data, dict):
            data["receipt_sha256"] = stored_digest
        return data

    def recent_candidate_hashes(self, limit: int = 1_000) -> set[str]:
        hashes: set[str] = set()
        with self._lock, _connection(self.database_path) as connection:
            rows = connection.execute(
                "SELECT result_json FROM dream_artifacts ORDER BY rowid DESC LIMIT ?",
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        for row in rows:
            try:
                data = json.loads(str(row[0]))
                for cand in data.get("candidates", []):
                    if isinstance(cand, dict) and "candidate_id" in cand:
                        hashes.add(str(cand["candidate_id"]))
            except Exception:
                continue
        return hashes

    def dream(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "topic", "query", "constraints", "candidate_limit", "seed", "top_k", "request_id"},
            {"action", "topic", "constraints"},
        )
        topic = _text(request["topic"], "topic", 1_000, 3)
        query = _text(request.get("query", topic), "query", 1_000)
        request_id = _text(request.get("request_id", uuid.uuid4().hex), "request_id", 128)
        limit = request.get("candidate_limit", 3)
        top_k = request.get("top_k", 5)
        seed = request.get("seed", 0)

        if type(limit) is not int or not 1 <= limit <= 8:
            raise LocalPillarError("RESOURCE_LIMIT", "candidate_limit must be 1-8")
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise LocalPillarError("RESOURCE_LIMIT", "top_k must be 1-20")
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise LocalPillarError("INVALID_INPUT", "seed is invalid")

        # 1. Safety Check against Destructive Actions/Goals
        is_safe, reject_reason = _evaluate_dream_goal_safety(topic, query)
        if not is_safe:
            raise LocalPillarError(reject_reason, f"dream goal violates safety policy: {reject_reason}")

        # 2. Check deterministic replay if request_id already exists
        existing = self.by_request_id(request_id)
        if existing is not None:
            return LocalPillarResult("P003", "REPLAYED_DREAM", existing)

        # 3. Check Sandboxed Constraints
        constraints = request["constraints"]
        if not isinstance(constraints, list) or not 1 <= len(constraints) <= 16:
            raise LocalPillarError("RESOURCE_LIMIT", "constraints must contain 1-16 expressions")
        checks = []
        for expression in constraints:
            result = self.sandbox.evaluate(expression)
            if type(result.data["result"]) is not bool:
                raise LocalPillarError("INVALID_CONSTRAINT", "constraint must return boolean")
            checks.append({"expression": expression, "passed": result.data["result"]})
        if not all(item["passed"] for item in checks):
            raise LocalPillarError("CONSTRAINT_REJECTED", "one or more dream constraints failed")

        # 4. Evidence Retrieval via RAG
        evidence = self.rag.retrieve(query, top_k)
        if not evidence:
            raise LocalPillarError("EVIDENCE_UNAVAILABLE", "dreaming requires retrieved evidence")

        # 5. Model Availability Gating
        if self.provider is None or not self.provider.health_check():
            raise LocalPillarError("MODEL_NOT_CONFIGURED", "hypothesis model is unavailable")

        # 6. Generate Candidates
        raw_candidates = self.provider.generate(topic, evidence, limit, seed)
        allowed_evidence = {item["evidence_id"]: item for item in evidence}
        previous_hashes = self.recent_candidate_hashes()
        seen_this_run: set[str] = set()
        candidates = []
        for index, raw in enumerate(raw_candidates[:limit]):
            if not isinstance(raw, Mapping):
                raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "candidate must be an object")
            statement = _text(raw.get("statement"), "statement", 4_096, 8)
            evidence_id = _text(raw.get("evidence_id"), "evidence_id", 128)
            if evidence_id not in allowed_evidence:
                raise LocalPillarError("INVALID_CITATION", "hypothesis cited unknown evidence")
            falsification = _text(
                raw.get("falsification_test"), "falsification_test", 4_096, 8
            )
            cand_id = _digest(
                {"topic": topic, "statement": statement, "evidence_id": evidence_id}
            )
            is_cand_safe, cand_reject_reason = _evaluate_dream_goal_safety(statement, "")
            is_duplicate = (cand_id in previous_hashes) or (cand_id in seen_this_run)
            seen_this_run.add(cand_id)

            is_retained = (not is_duplicate) and is_cand_safe
            rejection_reason = ""
            if not is_cand_safe:
                rejection_reason = cand_reject_reason
            elif is_duplicate:
                rejection_reason = "DUPLICATE_CANDIDATE"

            candidates.append(
                {
                    "candidate_id": cand_id,
                    "statement": statement,
                    "evidence_id": evidence_id,
                    "retrieval_score": allowed_evidence[evidence_id]["retrieval_score"],
                    "falsification_test": falsification,
                    "verification_expression": constraints[index % len(constraints)],
                    "label": "REJECTED_HYPOTHESIS" if not is_cand_safe else "HYPOTHESIS",
                    "verification": "REJECTED" if not is_cand_safe else "UNVERIFIED",
                    "executable": False,
                    "retained": is_retained,
                    "novel_against_artifacts": not is_duplicate,
                    "rejection_reason": rejection_reason,
                }
            )
        if not candidates:
            raise LocalPillarError("NO_CANDIDATE", "model produced no hypothesis candidates")

        total_count = len(candidates)
        accepted_count = sum(1 for c in candidates if c["retained"])
        rejected_count = total_count - accepted_count
        acceptance_rate = (accepted_count / total_count) if total_count > 0 else 0.0
        novel_count = sum(1 for c in candidates if c["novel_against_artifacts"])
        novelty_score = (novel_count / total_count) if total_count > 0 else 0.0
        diversity_score = _compute_lexical_diversity([c["statement"] for c in candidates])

        metrics = {
            "total_candidates": total_count,
            "accepted_candidates": accepted_count,
            "rejected_candidates": rejected_count,
            "acceptance_rate": round(acceptance_rate, 4),
            "novelty_score": round(novelty_score, 4),
            "diversity_score": round(diversity_score, 4),
        }

        # Check for conflicting evidence
        evidence_texts = [str(ev.get("content", "")).lower() for ev in evidence]
        has_evidence_conflict = any("conflict" in t or "contradict" in t for t in evidence_texts)
        uncertainty = "EVIDENCE_CONFLICT" if has_evidence_conflict else "UNVERIFIED"
        warnings = ["MODEL_OUTPUT_IS_NOT_EMPIRICAL_EVIDENCE"]
        if has_evidence_conflict:
            warnings.append("EVIDENCE_CONFLICT_DETECTED")

        dream_id = uuid.uuid4().hex
        now = time.time()
        output = {
            "dream_id": dream_id,
            "request_id": request_id,
            "topic": topic,
            "seed": seed,
            "model": self.provider.provider_name,
            "provider_type": self.provider.provider_type,
            "constraints": checks,
            "evidence": evidence,
            "candidates": candidates,
            "metrics": metrics,
            "warning": "MODEL_OUTPUT_IS_NOT_EMPIRICAL_EVIDENCE",
            "warnings": warnings,
            "uncertainty": uncertainty,
        }
        req_json = json.dumps(dict(request), sort_keys=True)
        res_json = json.dumps(output, sort_keys=True)
        values = (
            dream_id,
            request_id,
            now,
            "UNVERIFIED",
            seed,
            topic,
            self.provider.provider_type,
            self.provider.provider_name,
            req_json,
            res_json,
        )
        digest = self._receipt_digest(values)
        try:
            with self._lock, _connection(self.database_path) as connection:
                connection.execute(
                    """INSERT INTO dream_artifacts (
                        dream_id, request_id, created_at, status, seed, topic,
                        provider_type, provider_name, request_json, result_json, receipt_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*values, digest),
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "dream artifact was not stored") from exc
        output["receipt_sha256"] = digest
        return LocalPillarResult("P003", "HYPOTHESIS_ARTIFACT_CREATED", output)

    def get(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "dream_id"}, {"action", "dream_id"})
        dream_id = _text(request["dream_id"], "dream_id", 128)
        data = self.by_dream_id(dream_id)
        if data is None:
            raise LocalPillarError("DREAM_NOT_FOUND", "dream artifact was not found")
        return LocalPillarResult("P003", "HYPOTHESIS_ARTIFACT_READ", data)

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "dream":
            return self.dream(request)
        if action == "get":
            return self.get(request)
        if action == "replay":
            _strict(request, {"action", "request_id"}, {"action", "request_id"})
            req_id = _text(request["request_id"], "request_id", 128)
            data = self.by_request_id(req_id)
            if data is None:
                raise LocalPillarError("DREAM_NOT_FOUND", "dream artifact was not found for replay")
            return LocalPillarResult("P003", "REPLAYED_DREAM", data)
        if action == "status":
            return LocalPillarResult(
                "P003",
                "HEALTHY" if self.health_check() else "DEGRADED",
                {
                    "health": self.health_check(),
                    "provider": (
                        {
                            "name": self.provider.provider_name,
                            "type": self.provider.provider_type,
                            "health": self.provider.health_check(),
                        }
                        if self.provider
                        else None
                    ),
                    "database": str(self.database_path),
                },
            )
        raise LocalPillarError("UNSUPPORTED_ACTION", f"unsupported action: {action}")

    def close(self) -> None:
        if self.provider and hasattr(self.provider, "close"):
            try:
                self.provider.close()
            except Exception:
                pass


class SpeculativeReasoningCapability:
    """Verify reasoning candidates with independent citation, sandbox, and safety checks."""

    def __init__(
        self,
        database_path: Path,
        rag: AgenticRAGCapability,
        sandbox: SandboxedImaginationCapability,
    ) -> None:
        self.database_path = database_path.resolve()
        self.rag = rag
        self.sandbox = sandbox
        self._lock = threading.Lock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock, _connection(self.database_path) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=5000")
                connection.execute("PRAGMA synchronous=NORMAL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS speculative_schema(
                    version INTEGER PRIMARY KEY, singleton INTEGER UNIQUE CHECK(singleton = 1))"""
                )
                connection.execute(
                    "INSERT OR IGNORE INTO speculative_schema(version, singleton) VALUES(1, 1)"
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS speculative_runs(
                    run_id TEXT PRIMARY KEY,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    selected_candidate_id TEXT,
                    result_json TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS speculative_rejections(
                    rejection_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    failure_code TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    checks_json TEXT NOT NULL,
                    created_at REAL NOT NULL)"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_spec_request_id ON speculative_runs(request_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_spec_rejections_run_id ON speculative_rejections(run_id)"
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "speculative store unavailable") from exc

    def health_check(self) -> bool:
        return self.sandbox.health_check()

    @staticmethod
    def _receipt_digest(values: tuple[Any, ...]) -> str:
        serialized = "|".join(str(v) for v in values)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def by_run_id(self, run_id: str) -> dict[str, Any] | None:
        try:
            with self._lock, _connection(self.database_path) as connection:
                row = connection.execute(
                    """SELECT run_id, request_id, created_at, status, selected_candidate_id,
                              result_json, receipt_sha256
                       FROM speculative_runs WHERE run_id = ?""",
                    (run_id,),
                ).fetchone()
                if row is None:
                    return None
                r_id, req_id, created_at, status, sel_id, res_json, receipt = row
                expected = self._receipt_digest((r_id, req_id, created_at, status, sel_id, res_json))
                if receipt != expected:
                    raise LocalPillarError(
                        "STORAGE_CORRUPT", "speculative run receipt digest mismatch"
                    )
                data = json.loads(res_json)
                data["receipt_sha256"] = receipt
                return data
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read speculative run") from exc

    def by_request_id(self, request_id: str) -> dict[str, Any] | None:
        try:
            with self._lock, _connection(self.database_path) as connection:
                row = connection.execute(
                    """SELECT run_id, request_id, created_at, status, selected_candidate_id,
                              result_json, receipt_sha256
                       FROM speculative_runs WHERE request_id = ?""",
                    (request_id,),
                ).fetchone()
                if row is None:
                    return None
                r_id, req_id, created_at, status, sel_id, res_json, receipt = row
                expected = self._receipt_digest((r_id, req_id, created_at, status, sel_id, res_json))
                if receipt != expected:
                    raise LocalPillarError(
                        "STORAGE_CORRUPT", "speculative run receipt digest mismatch"
                    )
                data = json.loads(res_json)
                data["receipt_sha256"] = receipt
                return data
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read speculative run") from exc

    def rejections_by_run_id(self, run_id: str) -> list[dict[str, Any]]:
        try:
            with self._lock, _connection(self.database_path) as connection:
                rows = connection.execute(
                    """SELECT rejection_id, candidate_id, failure_code, reason, checks_json, created_at
                       FROM speculative_rejections WHERE run_id = ? ORDER BY created_at ASC""",
                    (run_id,),
                ).fetchall()
                rejections = []
                for rej_id, cand_id, code, reason, checks_json, created_at in rows:
                    rejections.append({
                        "rejection_id": rej_id,
                        "candidate_id": cand_id,
                        "failure_code": code,
                        "reason": reason,
                        "checks": json.loads(checks_json),
                        "created_at": created_at,
                    })
                return rejections
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read speculative rejections") from exc

    def evaluate(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "candidates", "maximum_candidates", "request_id", "timeout"},
            {"action", "candidates"},
        )
        candidates = request["candidates"]
        maximum = request.get("maximum_candidates", 32)
        if type(maximum) is not int or not 1 <= maximum <= 32:
            raise LocalPillarError("RESOURCE_LIMIT", "maximum_candidates must be 1-32")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= maximum:
            raise LocalPillarError("RESOURCE_LIMIT", "candidate count exceeds the budget")

        request_id = request.get("request_id")
        if request_id is not None:
            request_id = _text(request_id, "request_id", 128)
            existing = self.by_request_id(request_id)
            if existing is not None:
                return LocalPillarResult("P036", "REPLAYED_SPECULATION", existing)

        accepted = []
        rejected = []
        seen: set[str] = set()
        run_id = uuid.uuid4().hex
        now = time.time()
        rejection_records: list[tuple[str, str, str, str, str, str, float]] = []

        for raw in candidates:
            if not isinstance(raw, Mapping):
                raise LocalPillarError("INVALID_INPUT", "candidate must be an object")
            candidate_id = _text(raw.get("candidate_id"), "candidate_id", 128)
            if candidate_id in seen:
                raise LocalPillarError("INVALID_INPUT", "candidate_id must be unique")
            seen.add(candidate_id)

            evidence_id = _text(raw.get("evidence_id"), "evidence_id", 128)
            expression = _text(raw.get("verification_expression"), "verification_expression", 4_096)
            statement = str(raw.get("statement", ""))

            # 1. Safety Policy Verifier
            is_safe, reject_reason = _evaluate_dream_goal_safety(statement, candidate_id)

            # 2. Independent Citation Verifier
            citation_check = bool(self.rag.evidence_exists(evidence_id))

            # 3. Independent Sandboxed Constraint Verifier
            sandbox_result = self.sandbox.evaluate(expression).data["result"]
            expression_check = bool(type(sandbox_result) is bool and sandbox_result)

            checks = {
                "citation_exists": citation_check,
                "sandbox_constraint": expression_check,
                "safety_policy": is_safe,
            }

            has_disagreement = len(set(checks.values())) > 1
            retrieval_score = float(raw.get("retrieval_score", 0.0))
            consensus_passed = all(checks.values())

            passed_checks_count = sum(1 for v in checks.values() if v)
            confidence_score = round(retrieval_score * (passed_checks_count / len(checks)), 4)

            record = {
                "candidate_id": candidate_id,
                "statement": statement,
                "evidence_id": evidence_id,
                "checks": checks,
                "retrieval_score": retrieval_score,
                "confidence_score": confidence_score,
                "evaluator_disagreement": has_disagreement,
                "consensus_passed": consensus_passed,
            }

            if consensus_passed:
                accepted.append(record)
            else:
                failure_codes = []
                reasons = []
                if not is_safe:
                    failure_codes.append("UNSAFE_GOAL_PROHIBITED")
                    reasons.append("candidate violates safety policy")
                if not citation_check:
                    failure_codes.append("CITATION_UNAVAILABLE")
                    reasons.append(f"cited evidence '{evidence_id}' does not exist")
                if not expression_check:
                    failure_codes.append("CONSTRAINT_REJECTED")
                    reasons.append(f"sandbox constraint evaluated to {sandbox_result}")

                primary_code = failure_codes[0] if failure_codes else "INDEPENDENT_CHECK_FAILED"
                combined_reason = "; ".join(reasons) if reasons else "INDEPENDENT_CHECK_FAILED"
                rejected_record = {
                    **record,
                    "failure_code": primary_code,
                    "reason": combined_reason,
                }
                rejected.append(rejected_record)

                rej_id = uuid.uuid4().hex
                rejection_records.append((
                    rej_id,
                    run_id,
                    candidate_id,
                    primary_code,
                    combined_reason,
                    json.dumps(checks, sort_keys=True),
                    now,
                ))

        accepted.sort(key=lambda item: (-item["confidence_score"], -item["retrieval_score"], item["candidate_id"]))
        selected = accepted[0] if accepted else None
        status = "VERIFIED_CANDIDATE_SELECTED" if selected else "NO_CANDIDATE_VERIFIED"

        output = {
            "run_id": run_id,
            "request_id": request_id,
            "status": status,
            "selected": selected,
            "accepted": accepted,
            "rejected": rejected,
            "metrics": {
                "total_candidates": len(candidates),
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "evaluator_disagreements": sum(1 for c in rejected if c.get("evaluator_disagreement")),
                "acceptance_rate": round(len(accepted) / len(candidates), 4) if candidates else 0.0,
            },
        }

        res_json = json.dumps(output, sort_keys=True)
        selected_id = selected["candidate_id"] if selected else None
        values = (run_id, request_id, now, status, selected_id, res_json)
        digest = self._receipt_digest(values)
        output["receipt_sha256"] = digest

        try:
            with self._lock, _connection(self.database_path) as connection:
                connection.execute(
                    """INSERT INTO speculative_runs (
                        run_id, request_id, created_at, status, selected_candidate_id,
                        result_json, receipt_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (*values, digest),
                )
                if rejection_records:
                    connection.executemany(
                        """INSERT INTO speculative_rejections (
                            rejection_id, run_id, candidate_id, failure_code, reason,
                            checks_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        rejection_records,
                    )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "speculative run was not stored") from exc

        return LocalPillarResult("P036", status, output)

    def get(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "run_id"}, {"action", "run_id"})
        run_id = _text(request["run_id"], "run_id", 128)
        data = self.by_run_id(run_id)
        if data is None:
            raise LocalPillarError("RUN_NOT_FOUND", "speculative run was not found")
        return LocalPillarResult("P036", "SPECULATION_RETRIEVED", data)

    def replay(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "request_id"}, {"action", "request_id"})
        req_id = _text(request["request_id"], "request_id", 128)
        data = self.by_request_id(req_id)
        if data is None:
            raise LocalPillarError("RUN_NOT_FOUND", "speculative run was not found for replay")
        return LocalPillarResult("P036", "REPLAYED_SPECULATION", data)

    def rejections(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "run_id"}, {"action", "run_id"})
        run_id = _text(request["run_id"], "run_id", 128)
        rejs = self.rejections_by_run_id(run_id)
        return LocalPillarResult("P036", "REJECTIONS_RETRIEVED", {"run_id": run_id, "rejections": rejs})

    def status(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        try:
            with self._lock, _connection(self.database_path) as connection:
                run_count = connection.execute("SELECT COUNT(*) FROM speculative_runs").fetchone()[0]
                rej_count = connection.execute("SELECT COUNT(*) FROM speculative_rejections").fetchone()[0]
                version = connection.execute("SELECT version FROM speculative_schema WHERE singleton = 1").fetchone()[0]
        except Exception:
            run_count = 0
            rej_count = 0
            version = 1
        return LocalPillarResult(
            "P036",
            "HEALTHY" if self.health_check() else "DEGRADED",
            {
                "health": self.health_check(),
                "database": str(self.database_path),
                "schema_version": version,
                "total_runs": run_count,
                "total_rejections": rej_count,
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action in ("evaluate", "speculate"):
            return self.evaluate(request)
        if action == "get":
            return self.get(request)
        if action == "replay":
            return self.replay(request)
        if action == "rejections":
            return self.rejections(request)
        if action == "status":
            return self.status(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", f"speculative action is unsupported: {action}")

    def close(self) -> None:
        pass


class PlanExecutionAuthority:
    """Decoupled execution authority enforcing capability allowlists and parameter verification."""

    ALLOWLISTED_TOOLS = {"sandbox", "retrieve", "speculate", "logic", "socratic"}

    def __init__(
        self,
        rag: AgenticRAGCapability,
        sandbox: SandboxedImaginationCapability,
        speculative: SpeculativeReasoningCapability,
    ) -> None:
        self.rag = rag
        self.sandbox = sandbox
        self.speculative = speculative

    def execute_step(self, step: Mapping[str, Any], caller_role: str = "PLANNER") -> dict[str, Any]:
        if not isinstance(step, Mapping):
            raise LocalPillarError("INVALID_INPUT", "plan step must be an object")
        step_type = step.get("type")
        if not isinstance(step_type, str) or step_type not in self.ALLOWLISTED_TOOLS:
            raise LocalPillarError("TOOL_UNAVAILABLE", f"plan step type is not allowlisted: {step_type}")

        if step_type == "sandbox":
            expr = step.get("expression")
            if not isinstance(expr, str) or not expr.strip():
                raise LocalPillarError("INVALID_INPUT", "sandbox step requires non-empty expression")
            result = self.sandbox.evaluate(expr)
            return {"type": step_type, "result": result.data["result"]}

        if step_type == "retrieve":
            query = _text(step.get("query"), "query", 4_096)
            minimum = step.get("minimum_results", 1)
            if type(minimum) is not int or not 1 <= minimum <= 20:
                raise LocalPillarError("INVALID_INPUT", "minimum_results must be 1-20")
            evidence = self.rag.retrieve(query, max(5, minimum))
            if len(evidence) < minimum:
                raise LocalPillarError("EVIDENCE_UNAVAILABLE", "plan retrieval threshold was not met")
            return {"type": step_type, "evidence": evidence}

        if step_type == "speculate":
            candidates = step.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise LocalPillarError("INVALID_INPUT", "speculate step requires non-empty candidates list")
            result = self.speculative.evaluate(
                {"action": "evaluate", "candidates": candidates}
            )
            if result.data.get("selected") is None:
                raise LocalPillarError("NO_CANDIDATE_VERIFIED", "plan has no valid candidate")
            return {"type": step_type, "selection": result.data["selected"]}

        if step_type == "logic":
            expr = step.get("expression")
            if not isinstance(expr, str) or not expr.strip():
                raise LocalPillarError("INVALID_INPUT", "logic step requires non-empty expression")
            result = self.sandbox.evaluate(expr)
            return {"type": step_type, "result": result.data["result"]}

        if step_type == "socratic":
            reflection = step.get("reflection")
            if not isinstance(reflection, str) or not reflection.strip():
                raise LocalPillarError("INVALID_INPUT", "socratic step requires reflection prompt")
            return {"type": step_type, "reflection": reflection.strip(), "status": "REFLECTED"}

        raise LocalPillarError("TOOL_UNAVAILABLE", f"unsupported tool: {step_type}")


class PlanProgressEvaluator:
    """Decoupled evaluator assessing invariants, budget, loop detection, and progress metrics."""

    def __init__(self, sandbox: SandboxedImaginationCapability) -> None:
        self.sandbox = sandbox

    def check_invariants(self, invariants: Sequence[str]) -> bool:
        for invariant in invariants:
            try:
                res = self.sandbox.evaluate(invariant)
                if res.data.get("result") is not True:
                    return False
            except Exception:
                return False
        return True

    def detect_loop(self, step_history: Sequence[Mapping[str, Any]]) -> bool:
        """Detect repeated cycles or failure loops."""
        if len(step_history) < 2:
            return False
        sigs = [
            f"{s.get('type')}:{hashlib.sha256(json.dumps(s.get('params', {}), sort_keys=True).encode()).hexdigest()[:8]}"
            for s in step_history
        ]
        # Consecutive duplicate failure
        if (
            len(sigs) >= 2
            and sigs[-1] == sigs[-2]
            and step_history[-1].get("status") == "FAILED"
            and step_history[-2].get("status") == "FAILED"
        ):
            return True
        # 2-step repeating cycle: A B A B
        if len(sigs) >= 4 and sigs[-4:-2] == sigs[-2:]:
            return True
        # 3-step repeating cycle: A B C A B C
        if len(sigs) >= 6 and sigs[-6:-3] == sigs[-3:]:
            return True
        return False

    def detect_no_progress(self, observations: Sequence[Mapping[str, Any]]) -> bool:
        """Detect when plan has multiple steps but produces zero delta in knowledge or output."""
        if len(observations) < 3:
            return False
        last_3 = observations[-3:]
        outs = [json.dumps(o.get("output"), sort_keys=True) for o in last_3]
        if outs[0] == outs[1] == outs[2] and outs[0] is not None:
            return True
        return False


class MetaPlanningCapability:
    """Execute persisted bounded plans over real sandbox, retrieval, and verifier tools."""

    def __init__(
        self,
        database_path: Path,
        rag: AgenticRAGCapability,
        sandbox: SandboxedImaginationCapability,
        speculative: SpeculativeReasoningCapability,
    ) -> None:
        self.database_path = database_path.resolve()
        self.rag = rag
        self.sandbox = sandbox
        self.speculative = speculative
        self.objective_resolver: Any | None = None
        self.authority = PlanExecutionAuthority(self.rag, self.sandbox, self.speculative)
        self.evaluator = PlanProgressEvaluator(self.sandbox)
        try:
            with _connection(self.database_path) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS meta_planning_schema (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        version INTEGER NOT NULL
                    )"""
                )
                connection.execute(
                    "INSERT OR IGNORE INTO meta_planning_schema (singleton, version) VALUES (1, 1)"
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS meta_plans(
                        plan_id TEXT PRIMARY KEY,
                        goal TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        result_json TEXT,
                        cancelled INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        request_id TEXT,
                        receipt_sha256 TEXT
                    )"""
                )
                columns = {col[1] for col in connection.execute("PRAGMA table_info(meta_plans)").fetchall()}
                if "request_id" not in columns:
                    connection.execute("ALTER TABLE meta_plans ADD COLUMN request_id TEXT")
                if "receipt_sha256" not in columns:
                    connection.execute("ALTER TABLE meta_plans ADD COLUMN receipt_sha256 TEXT")

                connection.execute(
                    """CREATE TABLE IF NOT EXISTS meta_plan_steps (
                        step_id TEXT PRIMARY KEY,
                        plan_id TEXT NOT NULL,
                        step_index INTEGER NOT NULL,
                        step_type TEXT NOT NULL,
                        step_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        output_json TEXT,
                        checkpoint_receipt TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY(plan_id) REFERENCES meta_plans(plan_id)
                    )"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_meta_plan_steps_plan ON meta_plan_steps(plan_id, step_index)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_meta_plans_req ON meta_plans(request_id)"
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "meta plan store unavailable") from exc

    def health_check(self) -> bool:
        try:
            with _connection(self.database_path) as conn:
                db_ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except Exception:
            db_ok = False
        return db_ok and self.sandbox.health_check()

    def _compute_receipt(
        self, plan_id: str, goal: str, status: str, steps_count: int, timestamp: float
    ) -> str:
        payload = f"{plan_id}|{goal}|{status}|{steps_count}|{int(timestamp)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _verify_receipt(
        self,
        plan_id: str,
        goal: str,
        status: str,
        steps_count: int,
        timestamp: float,
        receipt: str | None,
    ) -> bool:
        if not receipt:
            return False
        expected = self._compute_receipt(plan_id, goal, status, steps_count, timestamp)
        return hmac.compare_digest(expected, receipt)

    def _record_step(
        self,
        plan_id: str,
        step_index: int,
        step_type: str,
        step: Mapping[str, Any],
        status: str,
        output: Any,
    ) -> None:
        step_id = f"{plan_id}-s{step_index}"
        now = time.time()
        receipt = hashlib.sha256(
            f"{step_id}|{plan_id}|{step_index}|{status}|{now}".encode("utf-8")
        ).hexdigest()
        try:
            with _connection(self.database_path) as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO meta_plan_steps VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        step_id,
                        plan_id,
                        step_index,
                        step_type,
                        json.dumps(step, sort_keys=True),
                        status,
                        json.dumps(output, sort_keys=True) if output is not None else None,
                        receipt,
                        now,
                    ),
                )
        except sqlite3.Error:
            pass

    def _run_step(self, step: Mapping[str, Any]) -> dict[str, Any]:
        return self.authority.execute_step(step)

    def run(self, request: Mapping[str, Any]) -> LocalPillarResult:
        allowed = {
            "action",
            "goal",
            "invariants",
            "steps",
            "maximum_steps",
            "objective_id",
            "request_id",
            "max_replans",
            "allow_dynamic_replan",
            "dynamic_replan_steps",
            "detect_loops",
        }
        _strict(request, allowed, {"action", "goal", "invariants", "steps"})
        goal = _text(request["goal"], "goal", 2_000, 8)
        invariants = request["invariants"]
        objective_version = None
        objective_id = request.get("objective_id")
        if objective_id is not None:
            if self.objective_resolver is None:
                raise LocalPillarError("OBJECTIVE_UNAVAILABLE", "objective resolver is unavailable")
            active = self.objective_resolver(_text(objective_id, "objective_id", 128))
            if active["owner_goal"] != goal:
                raise LocalPillarError("OBJECTIVE_HIJACK", "plan goal differs from immutable owner goal")
            if not isinstance(invariants, list):
                raise LocalPillarError("INVALID_INPUT", "invariants must be a list")
            invariants = list(dict.fromkeys([*active["invariants"], *invariants]))
            objective_version = active["version"]

        request_id = request.get("request_id")
        if request_id is not None:
            request_id = _text(request_id, "request_id", 128)
            with _connection(self.database_path) as connection:
                row = connection.execute(
                    "SELECT plan_id, goal, status, result_json, receipt_sha256, updated_at FROM meta_plans WHERE request_id=?",
                    (request_id,),
                ).fetchone()
                if row is not None:
                    p_id, r_goal, r_status, r_result, r_receipt, r_updated = row
                    res_data = json.loads(r_result) if r_result else {}
                    steps_count = res_data.get("steps_used", 0)
                    if not self._verify_receipt(p_id, r_goal, r_status, steps_count, r_updated, r_receipt):
                        raise LocalPillarError("STORAGE_CORRUPT", "meta plan integrity verification failed")
                    return LocalPillarResult("P038", "REPLAYED_META_PLAN", res_data)

        steps = request["steps"]
        maximum = request.get("maximum_steps", 16)
        max_replans = request.get("max_replans", 3)
        allow_dynamic_replan = bool(request.get("allow_dynamic_replan", False))
        dynamic_replan_steps = request.get("dynamic_replan_steps") or []
        detect_loops = bool(request.get("detect_loops", False))

        if not isinstance(invariants, list) or not 1 <= len(invariants) <= 16:
            raise LocalPillarError("RESOURCE_LIMIT", "invariants must contain 1-16 expressions")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 64:
            raise LocalPillarError("RESOURCE_LIMIT", "steps must contain 1-64 items")
        if type(maximum) is not int or not 1 <= maximum <= 64 or len(steps) > maximum:
            raise LocalPillarError("RESOURCE_LIMIT", "plan exceeds maximum_steps")
        if type(max_replans) is not int or not 0 <= max_replans <= 16:
            raise LocalPillarError("INVALID_INPUT", "max_replans must be an integer between 0 and 16")

        for invariant in invariants:
            if not self.evaluator.check_invariants([invariant]):
                raise LocalPillarError("INVARIANT_VIOLATION", "plan invariant rejected execution")

        plan_id = uuid.uuid4().hex
        now = time.time()
        try:
            with _connection(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO meta_plans VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (plan_id, goal, json.dumps(steps), "RUNNING", None, 0, now, now, request_id, None),
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "meta plan was not stored") from exc

        observations: list[dict[str, Any]] = []
        step_history: list[dict[str, Any]] = []
        recovered = 0
        replan_count = 0
        status = "COMPLETED"

        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, Mapping):
                raise LocalPillarError("INVALID_INPUT", "plan step must be an object")

            with _connection(self.database_path) as connection:
                cancelled = connection.execute(
                    "SELECT cancelled FROM meta_plans WHERE plan_id=?", (plan_id,)
                ).fetchone()[0]
            if cancelled:
                status = "CANCELLED"
                break

            params = {k: v for k, v in raw_step.items() if k not in ("type", "fallback")}
            step_history.append({"type": raw_step.get("type"), "params": params, "status": "ATTEMPTED"})

            if detect_loops and self.evaluator.detect_loop(step_history):
                status = "LOOP_DETECTED"
                observations.append({"step": index, "status": "LOOP_DETECTED", "code": "LOOP_DETECTED"})
                break

            try:
                result = self.authority.execute_step(raw_step)
                observations.append({"step": index, "status": "SUCCESS", "output": result})
                step_history[-1]["status"] = "SUCCESS"
                self._record_step(plan_id, index, str(raw_step.get("type")), raw_step, "SUCCESS", result)
            except LocalPillarError as exc:
                step_history[-1]["status"] = "FAILED"
                fallback = raw_step.get("fallback")
                handled = False
                if isinstance(fallback, Mapping):
                    try:
                        result = self.authority.execute_step(fallback)
                        recovered += 1
                        handled = True
                        observations.append(
                            {"step": index, "status": "RECOVERED", "failure_code": exc.code, "output": result}
                        )
                        self._record_step(plan_id, index, str(fallback.get("type")), fallback, "RECOVERED", result)
                    except LocalPillarError:
                        handled = False

                if not handled:
                    if allow_dynamic_replan and replan_count < max_replans and replan_count < len(dynamic_replan_steps):
                        replan_step = dynamic_replan_steps[replan_count]
                        replan_count += 1
                        if not self.evaluator.check_invariants(invariants):
                            status = "INVARIANT_VIOLATION"
                            break
                        try:
                            replan_res = self.authority.execute_step(replan_step)
                            recovered += 1
                            handled = True
                            observations.append(
                                {
                                    "step": index,
                                    "status": "RECOVERED",
                                    "failure_code": exc.code,
                                    "replan": True,
                                    "replan_count": replan_count,
                                    "output": replan_res,
                                }
                            )
                            self._record_step(plan_id, index, str(replan_step.get("type")), replan_step, "RECOVERED", replan_res)
                        except LocalPillarError as r_exc:
                            observations.append({"step": index, "status": "FAILED", "code": r_exc.code})
                            status = "FAILED"
                            self._record_step(plan_id, index, str(raw_step.get("type")), raw_step, "FAILED", {"code": r_exc.code})
                            break
                    else:
                        observations.append({"step": index, "status": "FAILED", "code": exc.code})
                        status = "FAILED"
                        self._record_step(plan_id, index, str(raw_step.get("type")), raw_step, "FAILED", {"code": exc.code})
                        break

            if self.evaluator.detect_no_progress(observations):
                status = "NO_PROGRESS_DETECTED"
                break

            for invariant in invariants:
                if not self.evaluator.check_invariants([invariant]):
                    status = "INVARIANT_VIOLATION"
                    break

            if status != "COMPLETED":
                break

        decision = "STOP_SUCCESS" if status == "COMPLETED" else "STOP_FAILURE"
        output = {
            "plan_id": plan_id,
            "request_id": request_id,
            "goal": goal,
            "status": status,
            "steps_used": len(observations),
            "recoveries": recovered,
            "replans": replan_count,
            "observations": observations,
            "decision": decision,
            "objective_id": objective_id,
            "objective_version": objective_version,
        }
        finish_now = time.time()
        receipt = self._compute_receipt(plan_id, goal, status, len(observations), finish_now)
        output["receipt_sha256"] = receipt
        try:
            with _connection(self.database_path) as connection:
                connection.execute(
                    "UPDATE meta_plans SET status=?, result_json=?, receipt_sha256=?, updated_at=? WHERE plan_id=?",
                    (status, json.dumps(output, sort_keys=True), receipt, finish_now, plan_id),
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "meta plan result was not stored") from exc
        return LocalPillarResult("P038", "META_PLAN_EXECUTED", output)

    def resume(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "plan_id"}, {"action", "plan_id"})
        plan_id = _text(request["plan_id"], "plan_id", 128)
        with _connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT plan_id, request_id, goal, plan_json, status, result_json, receipt_sha256, updated_at FROM meta_plans WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
            if row is None:
                raise LocalPillarError("NOT_FOUND", f"meta plan not found: {plan_id}")
            p_id, req_id, goal, p_json, status, res_json, receipt, updated = row
            res_data = json.loads(res_json) if res_json else {}
            steps_count = res_data.get("steps_used", 0)
            if receipt and not self._verify_receipt(p_id, goal, status, steps_count, updated, receipt):
                raise LocalPillarError("STORAGE_CORRUPT", "meta plan integrity verification failed")

            all_steps = json.loads(p_json)
            completed_count = connection.execute(
                "SELECT COUNT(*) FROM meta_plan_steps WHERE plan_id=? AND status IN ('SUCCESS', 'RECOVERED')",
                (plan_id,),
            ).fetchone()[0]
            remaining_steps = all_steps[completed_count:]
            if not remaining_steps:
                return LocalPillarResult("P038", "META_PLAN_ALREADY_COMPLETED", res_data)

            connection.execute("UPDATE meta_plans SET cancelled=0, status='RUNNING' WHERE plan_id=?", (plan_id,))

        observations = res_data.get("observations", [])
        recovered = res_data.get("recoveries", 0)
        status = "COMPLETED"
        for idx_offset, raw_step in enumerate(remaining_steps):
            index = completed_count + idx_offset
            try:
                result = self.authority.execute_step(raw_step)
                observations.append({"step": index, "status": "SUCCESS", "output": result})
                self._record_step(plan_id, index, str(raw_step.get("type")), raw_step, "SUCCESS", result)
            except LocalPillarError as exc:
                fallback = raw_step.get("fallback")
                if not isinstance(fallback, Mapping):
                    observations.append({"step": index, "status": "FAILED", "code": exc.code})
                    status = "FAILED"
                    self._record_step(plan_id, index, str(raw_step.get("type")), raw_step, "FAILED", {"code": exc.code})
                    break
                result = self.authority.execute_step(fallback)
                recovered += 1
                observations.append(
                    {"step": index, "status": "RECOVERED", "failure_code": exc.code, "output": result}
                )
                self._record_step(plan_id, index, str(fallback.get("type")), fallback, "RECOVERED", result)

        decision = "STOP_SUCCESS" if status == "COMPLETED" else "STOP_FAILURE"
        output = {
            "plan_id": plan_id,
            "request_id": req_id,
            "goal": goal,
            "status": status,
            "steps_used": len(observations),
            "recoveries": recovered,
            "observations": observations,
            "decision": decision,
        }
        finish_now = time.time()
        receipt = self._compute_receipt(plan_id, goal, status, len(observations), finish_now)
        output["receipt_sha256"] = receipt
        with _connection(self.database_path) as connection:
            connection.execute(
                "UPDATE meta_plans SET status=?, result_json=?, receipt_sha256=?, updated_at=? WHERE plan_id=?",
                (status, json.dumps(output, sort_keys=True), receipt, finish_now, plan_id),
            )
        return LocalPillarResult("P038", "META_PLAN_RESUMED", output)

    def cancel(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "plan_id"}, {"action", "plan_id"})
        plan_id = _text(request["plan_id"], "plan_id", 128)
        with _connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT goal, result_json FROM meta_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
            if row is None:
                raise LocalPillarError("NOT_FOUND", f"meta plan not found: {plan_id}")
            goal, res_json = row
            res_data = json.loads(res_json) if res_json else {}
            steps_count = res_data.get("steps_used", 0)
            now = time.time()
            receipt = self._compute_receipt(plan_id, goal, "CANCELLED", steps_count, now)
            connection.execute(
                "UPDATE meta_plans SET cancelled=1, status='CANCELLED', receipt_sha256=?, updated_at=? WHERE plan_id=?",
                (receipt, now, plan_id),
            )
        return LocalPillarResult("P038", "META_PLAN_CANCELLED", {"plan_id": plan_id, "cancelled": True})


    def get(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "plan_id"}, {"action", "plan_id"})
        plan_id = _text(request["plan_id"], "plan_id", 128)
        with _connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT plan_id, request_id, goal, plan_json, status, result_json, receipt_sha256, created_at, updated_at FROM meta_plans WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
            if row is None:
                raise LocalPillarError("NOT_FOUND", f"meta plan not found: {plan_id}")
            p_id, req_id, goal, p_json, status, res_json, receipt, created, updated = row
            res_data = json.loads(res_json) if res_json else {}
            steps_count = res_data.get("steps_used", 0)
            if not self._verify_receipt(p_id, goal, status, steps_count, updated, receipt):
                raise LocalPillarError("STORAGE_CORRUPT", "meta plan integrity verification failed")

            step_rows = connection.execute(
                "SELECT step_id, step_index, step_type, status, output_json FROM meta_plan_steps WHERE plan_id=? ORDER BY step_index ASC",
                (plan_id,),
            ).fetchall()
            steps = [
                {
                    "step_id": s[0],
                    "step_index": s[1],
                    "step_type": s[2],
                    "status": s[3],
                    "output": json.loads(s[4]) if s[4] else None,
                }
                for s in step_rows
            ]
            return LocalPillarResult(
                "P038",
                "META_PLAN_RETRIEVED",
                {
                    "plan_id": p_id,
                    "request_id": req_id,
                    "goal": goal,
                    "status": status,
                    "result": res_data,
                    "receipt_sha256": receipt,
                    "steps": steps,
                    "created_at": created,
                    "updated_at": updated,
                },
            )

    def replay(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "plan_id", "request_id"}, {"action"})
        plan_id = request.get("plan_id")
        request_id = request.get("request_id")
        if not plan_id and not request_id:
            raise LocalPillarError("MISSING_FIELD", "replay requires plan_id or request_id")

        with _connection(self.database_path) as connection:
            if plan_id:
                row = connection.execute(
                    "SELECT plan_id, goal, status, result_json, receipt_sha256, updated_at FROM meta_plans WHERE plan_id=?",
                    (plan_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT plan_id, goal, status, result_json, receipt_sha256, updated_at FROM meta_plans WHERE request_id=?",
                    (request_id,),
                ).fetchone()

            if row is None:
                raise LocalPillarError("NOT_FOUND", "meta plan not found for replay")

            p_id, goal, status, res_json, receipt, updated = row
            res_data = json.loads(res_json) if res_json else {}
            steps_count = res_data.get("steps_used", 0)
            if not self._verify_receipt(p_id, goal, status, steps_count, updated, receipt):
                raise LocalPillarError("STORAGE_CORRUPT", "meta plan integrity verification failed")
            return LocalPillarResult("P038", "REPLAYED_META_PLAN", res_data)

    def history(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        limit = 50
        if request and "limit" in request:
            limit = int(request["limit"])
        with _connection(self.database_path) as connection:
            rows = connection.execute(
                "SELECT plan_id, request_id, goal, status, created_at, updated_at FROM meta_plans ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            items = [
                {
                    "plan_id": r[0],
                    "request_id": r[1],
                    "goal": r[2],
                    "status": r[3],
                    "created_at": r[4],
                    "updated_at": r[5],
                }
                for r in rows
            ]
        return LocalPillarResult("P038", "META_PLAN_HISTORY", {"plans": items, "count": len(items)})

    def status(self, request: Mapping[str, Any] | None = None) -> LocalPillarResult:
        with _connection(self.database_path) as connection:
            total = connection.execute("SELECT COUNT(*) FROM meta_plans").fetchone()[0]
            completed = connection.execute("SELECT COUNT(*) FROM meta_plans WHERE status='COMPLETED'").fetchone()[0]
            cancelled = connection.execute("SELECT COUNT(*) FROM meta_plans WHERE status='CANCELLED'").fetchone()[0]
            schema_ver = connection.execute("SELECT version FROM meta_planning_schema WHERE singleton=1").fetchone()[0]
        return LocalPillarResult(
            "P038",
            "HEALTHY" if self.health_check() else "DEGRADED",
            {
                "health": self.health_check(),
                "database": str(self.database_path),
                "schema_version": schema_ver,
                "total_plans": total,
                "completed_plans": completed,
                "cancelled_plans": cancelled,
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "run":
            return self.run(request)
        if action == "resume":
            return self.resume(request)
        if action == "cancel":
            return self.cancel(request)
        if action == "get":
            return self.get(request)
        if action in ("replay", "history"):
            if action == "replay":
                return self.replay(request)
            return self.history(request)
        if action == "status":
            return self.status(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", f"meta planning action is unsupported: {action}")

    def close(self) -> None:
        pass

