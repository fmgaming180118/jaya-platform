"""Pillar 6 — authorized, reproducible Stochastic Spontaneity.

Exploration is never started merely because the process is idle. A caller must
provide explicit authorization and pass silence, privacy, resource, and opt-out
gates. Candidate text comes from a configured local model; missing or failed
providers produce structured failures instead of fabricated hypotheses.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol, Sequence

logger = logging.getLogger("SpontaneityEngine")

_DANGEROUS_ACTION_PATTERNS = re.compile(
    r"\b(rm\s+-rf|del\s+/[a-z]|format\s+[a-z]:|os\.system|subprocess\.|shutil\.rmtree|"
    r"powershell(\.exe)?\s+-|cmd(\.exe)?\s+/[ck]|eval\(|exec\(|"
    r"dump.*password|exfiltrat.*token|steal.*key|cat\s+/etc/shadow|"
    r"reverse_shell|meterpreter)\b",
    re.IGNORECASE,
)


def _evaluate_candidate_safety(hypothesis: str, rationale: str, next_step_type: str) -> tuple[bool, str]:
    combined = f"{hypothesis} {rationale}".strip()
    if _DANGEROUS_ACTION_PATTERNS.search(combined):
        return False, "UNSAFE_ACTION_PROHIBITED"
    if next_step_type not in {"research", "simulate", "review"}:
        return False, "UNALLOWLISTED_ACTION_TYPE"
    return True, ""


def _compute_diversity_score(texts: Sequence[str]) -> float:
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


class ExplorationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExplorationBudget:
    max_candidates: int = 3
    max_tokens: int = 512
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_candidates <= 8:
            raise ValueError("max_candidates must be between 1 and 8")
        if not 64 <= self.max_tokens <= 2_048:
            raise ValueError("max_tokens must be between 64 and 2048")
        if not 0.1 <= self.timeout_seconds <= 300.0:
            raise ValueError("timeout_seconds must be between 0.1 and 300")


@dataclass(frozen=True, slots=True)
class ExplorationRequest:
    topic: str
    authorized: bool
    owner_opt_out: bool = False
    silence_active: bool = False
    privacy_allows_local_model: bool = True
    resources_available: bool = True
    seed: int | None = None
    budget: ExplorationBudget = field(default_factory=ExplorationBudget)
    request_id: str = ""
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_topic = self.topic.strip()
        if not normalized_topic:
            raise ValueError("topic cannot be empty")
        if len(normalized_topic) > 500:
            raise ValueError("topic exceeds 500 characters")
        if self.seed is not None and not 0 <= self.seed <= (2**63 - 1):
            raise ValueError("seed must be an unsigned 63-bit integer")
        if not isinstance(self.evidence_ids, tuple):
            object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        for eid in self.evidence_ids:
            if not isinstance(eid, str) or not eid.strip() or len(eid) > 256:
                raise ValueError("evidence_id must be non-empty text <= 256 chars")


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    hypothesis: str
    rationale: str
    next_step_type: str


@dataclass(frozen=True, slots=True)
class ProviderResult:
    candidates: tuple[ProviderCandidate, ...]
    provider: str
    model: str
    provider_version: str
    prompt_sha256: str
    response_sha256: str
    latency_ms: float


class HypothesisProvider(Protocol):
    def healthcheck(self) -> Mapping[str, object]: ...

    def generate(
        self,
        *,
        topic: str,
        seed: int,
        budget: ExplorationBudget,
    ) -> ProviderResult: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class LocalLLMHypothesisProvider:
    """Production adapter for a real llama.cpp-backed local GGUF model."""

    ALLOWED_NEXT_STEPS = frozenset({"research", "simulate", "review"})

    def __init__(self, model_path: Path | str) -> None:
        self.model_path = Path(model_path).expanduser().resolve(strict=False)
        if not self.model_path.is_file():
            raise ExplorationError(
                "MODEL_NOT_CONFIGURED",
                "configured spontaneity model file does not exist",
            )
        from jaya_core.ai_connectors.local_llm_adapter import LocalLLMAdapter

        self._adapter = LocalLLMAdapter(model_path=str(self.model_path))
        if self._adapter.model is None:
            raise ExplorationError(
                "PROVIDER_UNAVAILABLE",
                "llama.cpp local model could not be loaded",
            )
        try:
            self._provider_version = importlib.metadata.version("llama-cpp-python")
        except importlib.metadata.PackageNotFoundError:
            self._provider_version = "unknown"

    def healthcheck(self) -> Mapping[str, object]:
        return {
            "ok": self._adapter.model is not None,
            "provider": "llama.cpp",
            "model": self.model_path.name,
            "provider_version": self._provider_version,
            "supports_seed": True,
            "network_required": False,
        }

    @staticmethod
    def _prompt(topic: str, seed: int, count: int) -> str:
        schema = {
            "candidates": [
                {
                    "hypothesis": "testable statement, explicitly a hypothesis",
                    "rationale": "why it is worth evaluating",
                    "next_step_type": "research|simulate|review",
                }
            ]
        }
        return (
            "Generate bounded research exploration candidates. "
            "Do not state discoveries, empirical proof, success percentages, or actions already executed. "
            f"Topic: {topic}\nSeed: {seed}\nCandidate count: {count}\n"
            "Return JSON only matching this schema: "
            f"{_canonical_json(schema)}"
        )

    @staticmethod
    def _parse_response(text: str, expected_max: int) -> tuple[ProviderCandidate, ...]:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ExplorationError(
                "PROVIDER_RESPONSE_INVALID", "model response is not valid JSON"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {"candidates"}:
            raise ExplorationError(
                "PROVIDER_RESPONSE_INVALID",
                "model response must contain only the candidates field",
            )
        raw_candidates = payload["candidates"]
        if not isinstance(raw_candidates, list) or not 1 <= len(raw_candidates) <= expected_max:
            raise ExplorationError(
                "PROVIDER_RESPONSE_INVALID",
                "candidate count is outside the requested budget",
            )
        candidates: list[ProviderCandidate] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict) or set(raw) != {
                "hypothesis",
                "rationale",
                "next_step_type",
            }:
                raise ExplorationError(
                    "PROVIDER_RESPONSE_INVALID",
                    "candidate has unknown or missing fields",
                )
            hypothesis = str(raw["hypothesis"]).strip()
            rationale = str(raw["rationale"]).strip()
            next_step = str(raw["next_step_type"]).strip().lower()
            if not hypothesis or len(hypothesis) > 2_000:
                raise ExplorationError(
                    "PROVIDER_RESPONSE_INVALID",
                    "candidate hypothesis is empty or too large",
                )
            if not rationale or len(rationale) > 2_000:
                raise ExplorationError(
                    "PROVIDER_RESPONSE_INVALID",
                    "candidate rationale is empty or too large",
                )
            if next_step not in LocalLLMHypothesisProvider.ALLOWED_NEXT_STEPS:
                raise ExplorationError(
                    "PROVIDER_RESPONSE_INVALID",
                    "candidate next_step_type is not allowlisted",
                )
            candidates.append(ProviderCandidate(hypothesis, rationale, next_step))
        return tuple(candidates)

    def generate(
        self,
        *,
        topic: str,
        seed: int,
        budget: ExplorationBudget,
    ) -> ProviderResult:
        model = self._adapter.model
        if model is None:
            raise ExplorationError("PROVIDER_UNAVAILABLE", "local model is not loaded")
        prompt = self._prompt(topic, seed, budget.max_candidates)
        started = time.monotonic()
        deadline = started + budget.timeout_seconds
        stopping_criteria = None
        try:
            from llama_cpp import StoppingCriteriaList

            stopping_criteria = StoppingCriteriaList(
                [lambda _input_ids, _logits: time.monotonic() >= deadline]
            )
        except (ImportError, TypeError):
            logger.warning(
                "llama.cpp stopping criteria unavailable; token budget remains active"
            )

        kwargs: dict[str, object] = {
            "max_tokens": budget.max_tokens,
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "seed": seed,
            "echo": False,
        }
        if stopping_criteria is not None:
            kwargs["stopping_criteria"] = stopping_criteria
        try:
            output = model(prompt, **kwargs)
        except Exception as exc:
            raise ExplorationError(
                "PROVIDER_FAILED", "local model generation failed"
            ) from exc
        latency_ms = (time.monotonic() - started) * 1_000.0
        if time.monotonic() >= deadline:
            raise ExplorationError(
                "PROVIDER_TIMEOUT", "local model exceeded exploration timeout"
            )
        if not isinstance(output, dict):
            raise ExplorationError(
                "PROVIDER_RESPONSE_INVALID", "model output is not an object"
            )
        choices = output.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ExplorationError(
                "PROVIDER_RESPONSE_INVALID", "model output has no completion"
            )
        text = str(choices[0].get("text") or "")
        candidates = self._parse_response(text, budget.max_candidates)
        return ProviderResult(
            candidates=candidates,
            provider="llama.cpp",
            model=self.model_path.name,
            provider_version=self._provider_version,
            prompt_sha256=_sha256_text(prompt),
            response_sha256=_sha256_text(text),
            latency_ms=latency_ms,
        )


@dataclass(frozen=True, slots=True)
class SpontaneousHypothesis:
    """Unverified candidate; never an empirical result or executable action."""

    hypothesis_id: str
    topic: str
    hypothesis_text: str
    confidence: float
    suggested_action: str
    metadata: Mapping[str, object]
    created_at: float

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "topic": self.topic,
            "hypothesis_text": self.hypothesis_text,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


class ExplorationReceiptStore:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser().resolve(strict=False)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                str(self.db_path), timeout=5.0, check_same_thread=False
            )
            with self._connection:
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spontaneity_schema (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        version INTEGER NOT NULL
                    )
                    """
                )
                row = self._connection.execute(
                    "SELECT version FROM spontaneity_schema WHERE singleton = 1"
                ).fetchone()
                if row is not None and int(row[0]) > self.SCHEMA_VERSION:
                    raise ExplorationError(
                        "STORAGE_SCHEMA_UNSUPPORTED", "newer schema detected"
                    )
                self._connection.execute(
                    "INSERT OR IGNORE INTO spontaneity_schema(singleton, version) VALUES (1, ?)",
                    (self.SCHEMA_VERSION,),
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS exploration_receipts (
                        run_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        seed INTEGER NOT NULL,
                        request_json TEXT NOT NULL,
                        provider_json TEXT NOT NULL,
                        candidates_json TEXT NOT NULL,
                        receipt_sha256 TEXT NOT NULL
                    )
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise ExplorationError(
                "STORAGE_UNAVAILABLE", "cannot initialize receipt store"
            ) from exc

    @staticmethod
    def _receipt_digest(values: Sequence[object]) -> str:
        return _sha256_text("\x1f".join(str(value) for value in values))

    def append(self, receipt: Mapping[str, object]) -> dict[str, object]:
        request_json = _canonical_json(receipt["request"])
        provider_json = _canonical_json(receipt["provider"])
        candidates_json = _canonical_json(receipt["candidates"])
        values: tuple[object, ...] = (
            receipt["run_id"],
            receipt["request_id"],
            receipt["created_at"],
            receipt["status"],
            receipt["seed"],
            request_json,
            provider_json,
            candidates_json,
        )
        digest = self._receipt_digest(values)
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO exploration_receipts (
                        run_id, request_id, created_at, status, seed, request_json,
                        provider_json, candidates_json, receipt_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*values, digest),
                )
        except sqlite3.IntegrityError:
            existing = self.by_request_id(str(receipt["request_id"]))
            if existing is None:
                raise ExplorationError(
                    "DUPLICATE_REQUEST", "receipt request_id conflicts"
                )
            return existing
        except sqlite3.Error as exc:
            raise ExplorationError(
                "STORAGE_FAILED", "cannot persist exploration receipt"
            ) from exc
        return {**dict(receipt), "receipt_sha256": digest}

    def by_request_id(self, request_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT run_id, request_id, created_at, status, seed, request_json,
                       provider_json, candidates_json, receipt_sha256
                FROM exploration_receipts WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        values = row[:8]
        if self._receipt_digest(values) != str(row[8]):
            raise ExplorationError(
                "STORAGE_CORRUPT", "receipt integrity check failed"
            )
        try:
            return {
                "run_id": str(row[0]),
                "request_id": str(row[1]),
                "created_at": str(row[2]),
                "status": str(row[3]),
                "seed": int(row[4]),
                "request": json.loads(str(row[5])),
                "provider": json.loads(str(row[6])),
                "candidates": json.loads(str(row[7])),
                "receipt_sha256": str(row[8]),
            }
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ExplorationError(
                "STORAGE_CORRUPT", "receipt payload is invalid"
            ) from exc

    def recent_candidate_hashes(self, limit: int = 1_000) -> set[str]:
        safe_limit = max(1, min(int(limit), 10_000))
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT candidates_json FROM exploration_receipts
                ORDER BY rowid DESC LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        hashes: set[str] = set()
        try:
            for row in rows:
                candidates = json.loads(str(row[0]))
                if not isinstance(candidates, list):
                    raise ValueError("candidate payload is not a list")
                for candidate in candidates:
                    if isinstance(candidate, dict) and candidate.get("content_sha256"):
                        hashes.add(str(candidate["content_sha256"]))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ExplorationError(
                "STORAGE_CORRUPT", "candidate history is invalid"
            ) from exc
        return hashes

    def healthcheck(self) -> dict[str, object]:
        try:
            with self._lock:
                self._connection.execute("SELECT 1").fetchone()
            return {
                "ok": True,
                "schema_version": self.SCHEMA_VERSION,
                "db_path": str(self.db_path),
            }
        except sqlite3.Error as exc:
            return {"ok": False, "error": str(exc)}

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class SpontaneityEngine:
    """Coordinates gates, a real model provider, evaluation, and receipts."""

    def __init__(
        self,
        receipt_store: ExplorationReceiptStore,
        provider: HypothesisProvider | None = None,
    ) -> None:
        self.receipt_store = receipt_store
        self.provider = provider
        self._last_result: dict[str, object] | None = None

    @staticmethod
    def is_idle_trigger(
        cpu_load: float,
        is_silence_mode: bool,
        *,
        authorized: bool = False,
        owner_opt_out: bool = False,
    ) -> bool:
        return (
            authorized
            and not owner_opt_out
            and not is_silence_mode
            and 0.0 <= float(cpu_load) < 0.30
        )

    def _blocked(self, code: str) -> dict[str, object]:
        result = {"ok": False, "status": code, "candidates": []}
        self._last_result = result
        return result

    def explore(self, request: ExplorationRequest) -> dict[str, object]:
        if not request.authorized:
            return self._blocked("PERMISSION_DENIED")
        if request.owner_opt_out:
            return self._blocked("OWNER_OPT_OUT")
        if request.silence_active:
            return self._blocked("COGNITIVE_SILENCE_ACTIVE")
        if not request.privacy_allows_local_model:
            return self._blocked("PRIVACY_BOUNDARY_ACTIVE")
        if not request.resources_available:
            return self._blocked("RESOURCE_UNAVAILABLE")
        if self.provider is None:
            return self._blocked("MODEL_NOT_CONFIGURED")
        health = dict(self.provider.healthcheck())
        if not bool(health.get("ok")):
            return self._blocked("PROVIDER_UNAVAILABLE")
        if not bool(health.get("supports_seed")):
            return self._blocked("PROVIDER_SEED_UNSUPPORTED")

        request_id = request.request_id.strip() or str(uuid.uuid4())
        existing = self.receipt_store.by_request_id(request_id)
        if existing is not None:
            result = {
                "ok": True,
                "status": "REPLAYED_RECEIPT",
                "receipt": existing,
                "candidates": existing.get("candidates", []),
            }
            self._last_result = result
            return result

        seed = request.seed if request.seed is not None else secrets.randbits(63)
        try:
            provider_result = self.provider.generate(
                topic=request.topic.strip(),
                seed=seed,
                budget=request.budget,
            )
        except ExplorationError as exc:
            return self._blocked(exc.code)

        previous_hashes = self.receipt_store.recent_candidate_hashes()
        seen_this_run: set[str] = set()
        candidates: list[SpontaneousHypothesis] = []
        receipt_candidates: list[dict[str, object]] = []
        now = time.time()
        for index, candidate in enumerate(provider_result.candidates):
            content_hash = _sha256_text(candidate.hypothesis.casefold().strip())
            is_safe, reject_reason = _evaluate_candidate_safety(
                candidate.hypothesis, candidate.rationale, candidate.next_step_type
            )
            is_duplicate = (content_hash in previous_hashes) or (content_hash in seen_this_run)
            seen_this_run.add(content_hash)

            if not is_safe:
                label = "REJECTED_HYPOTHESIS"
                evidence_status = "REJECTED"
                retained = False
                novel = False
                rejection_reason = reject_reason
            elif is_duplicate:
                label = "HYPOTHESIS"
                evidence_status = "UNVERIFIED"
                retained = False
                novel = False
                rejection_reason = "DUPLICATE_CANDIDATE"
            else:
                label = "HYPOTHESIS"
                evidence_status = "UNVERIFIED"
                retained = True
                novel = True
                rejection_reason = ""

            hypothesis = SpontaneousHypothesis(
                hypothesis_id=f"{request_id}:{index}",
                topic=request.topic.strip(),
                hypothesis_text=candidate.hypothesis,
                confidence=0.0,
                suggested_action=candidate.next_step_type,
                metadata={
                    "label": label,
                    "evidence_status": evidence_status,
                    "retained": retained,
                    "novel_against_receipts": novel,
                    "rejection_reason": rejection_reason,
                    "rationale": candidate.rationale,
                    "seed": seed,
                    "executable": False,
                    "confidence_kind": "NOT_ASSESSED",
                },
                created_at=now,
            )
            candidates.append(hypothesis)
            receipt_candidates.append(
                {**hypothesis.as_dict(), "content_sha256": content_hash}
            )

        total_count = len(provider_result.candidates)
        accepted_count = sum(1 for c in candidates if c.metadata.get("retained"))
        rejected_count = total_count - accepted_count
        acceptance_rate = (accepted_count / total_count) if total_count > 0 else 0.0
        novel_count = sum(1 for c in candidates if c.metadata.get("novel_against_receipts"))
        novelty_score = (novel_count / total_count) if total_count > 0 else 0.0
        diversity_score = _compute_diversity_score([c.hypothesis_text for c in candidates])

        metrics = {
            "total_candidates": total_count,
            "accepted_candidates": accepted_count,
            "rejected_candidates": rejected_count,
            "acceptance_rate": round(acceptance_rate, 4),
            "novelty_score": round(novelty_score, 4),
            "diversity_score": round(diversity_score, 4),
        }

        receipt = self.receipt_store.append(
            {
                "run_id": str(uuid.uuid4()),
                "request_id": request_id,
                "created_at": _utc_now(),
                "status": "UNVERIFIED",
                "seed": seed,
                "request": {
                    "topic": request.topic.strip(),
                    "budget": asdict(request.budget),
                    "authorized": True,
                    "privacy_allows_local_model": request.privacy_allows_local_model,
                    "resources_available": request.resources_available,
                    "evidence_ids": list(request.evidence_ids),
                },
                "provider": {
                    "provider": provider_result.provider,
                    "model": provider_result.model,
                    "provider_version": provider_result.provider_version,
                    "prompt_sha256": provider_result.prompt_sha256,
                    "response_sha256": provider_result.response_sha256,
                    "latency_ms": provider_result.latency_ms,
                    "health": health,
                },
                "candidates": receipt_candidates,
                "metrics": metrics,
            }
        )
        result = {
            "ok": True,
            "status": "UNVERIFIED",
            "label": "HYPOTHESIS",
            "candidates": [candidate.as_dict() for candidate in candidates],
            "metrics": metrics,
            "receipt": receipt,
        }
        self._last_result = result
        return result

    def generate_hypothesis(
        self,
        topic: str,
        *,
        authorized: bool = False,
        seed: int | None = None,
    ) -> SpontaneousHypothesis:
        """Compatibility helper that remains fail-closed without authorization."""
        result = self.explore(
            ExplorationRequest(topic=topic, authorized=authorized, seed=seed)
        )
        if not result.get("ok"):
            raise ExplorationError(
                str(result.get("status")), "exploration was blocked"
            )
        candidates = result.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ExplorationError("NO_CANDIDATES", "provider returned no candidates")
        first = candidates[0]
        if not isinstance(first, dict):
            raise ExplorationError(
                "PROVIDER_RESPONSE_INVALID", "candidate is invalid"
            )
        return SpontaneousHypothesis(
            hypothesis_id=str(first["hypothesis_id"]),
            topic=str(first["topic"]),
            hypothesis_text=str(first["hypothesis_text"]),
            confidence=float(first["confidence"]),
            suggested_action=str(first["suggested_action"]),
            metadata=dict(first["metadata"]),
            created_at=float(first["created_at"]),
        )

    def get_dream_history(self) -> list[SpontaneousHypothesis]:
        """Legacy API no longer exposes unbounded in-memory history."""
        return []

    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "requires_explicit_authorization": True,
            "automatic_background_generation": False,
            "provider": (
                dict(self.provider.healthcheck())
                if self.provider
                else {"ok": False, "status": "MODEL_NOT_CONFIGURED"}
            ),
            "storage": self.receipt_store.healthcheck(),
            "last_result": self._last_result,
        }

    def close(self) -> None:
        self.receipt_store.close()


__all__ = [
    "ExplorationBudget",
    "ExplorationError",
    "ExplorationReceiptStore",
    "ExplorationRequest",
    "HypothesisProvider",
    "LocalLLMHypothesisProvider",
    "ProviderCandidate",
    "ProviderResult",
    "SpontaneityEngine",
    "SpontaneousHypothesis",
]
