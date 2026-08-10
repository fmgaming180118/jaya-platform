"""Deterministic, bounded, and persistent inference for JAYA Pure Logic.

The solver implements propositional forward chaining with explicit negative
literals. It never asks a language model to decide truth and never converts an
unknown result into success.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_ATOM_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_RULE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SCHEMA_VERSION = 1


class LogicStatus(str, Enum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class LogicFailureCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    THEORY_LIMIT_EXCEEDED = "THEORY_LIMIT_EXCEEDED"
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    STORAGE_ERROR = "STORAGE_ERROR"
    CORRUPT_PROOF = "CORRUPT_PROOF"
    RUNTIME_NOT_READY = "RUNTIME_NOT_READY"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RESOURCE_PROBE_UNAVAILABLE = "RESOURCE_PROBE_UNAVAILABLE"


class PureLogicError(RuntimeError):
    """Structured failure raised by the Pure Logic boundary."""

    def __init__(self, code: LogicFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Literal:
    atom: str
    negated: bool = False

    def __post_init__(self) -> None:
        normalized = self.atom.strip().casefold()
        if not _ATOM_PATTERN.fullmatch(normalized):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                f"invalid atom: {self.atom!r}",
            )
        object.__setattr__(self, "atom", normalized)

    @classmethod
    def parse(cls, value: str) -> "Literal":
        if not isinstance(value, str):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "literal must be a string",
            )
        stripped = value.strip()
        if stripped.startswith("!"):
            return cls(stripped[1:], True)
        if stripped.casefold().startswith("not:"):
            return cls(stripped[4:], True)
        return cls(stripped, False)

    @property
    def key(self) -> str:
        return f"!{self.atom}" if self.negated else self.atom

    def inverse(self) -> "Literal":
        return Literal(self.atom, not self.negated)

    def to_dict(self) -> dict[str, object]:
        return {"atom": self.atom, "negated": self.negated, "key": self.key}


@dataclass(frozen=True, slots=True)
class LogicRule:
    rule_id: str
    premises: tuple[Literal, ...]
    conclusion: Literal

    def __post_init__(self) -> None:
        if not _RULE_ID_PATTERN.fullmatch(self.rule_id):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                f"invalid rule id: {self.rule_id!r}",
            )
        if not self.premises:
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                f"rule {self.rule_id!r} has no premises",
            )
        if len(set(self.premises)) != len(self.premises):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                f"rule {self.rule_id!r} contains duplicate premises",
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LogicRule":
        allowed = {"id", "if", "then"}
        unknown = set(value) - allowed
        if unknown:
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                f"unknown rule fields: {sorted(unknown)}",
            )
        premises = value.get("if")
        if not isinstance(premises, Sequence) or isinstance(premises, (str, bytes)):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "rule 'if' must be a list of literals",
            )
        rule_id = value.get("id")
        if not isinstance(rule_id, str):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "rule 'id' must be a string",
            )
        return cls(
            rule_id=rule_id,
            premises=tuple(Literal.parse(item) for item in premises),
            conclusion=Literal.parse(value.get("then")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.rule_id,
            "if": [item.key for item in self.premises],
            "then": self.conclusion.key,
        }


@dataclass(frozen=True, slots=True)
class LogicTheory:
    facts: tuple[Literal, ...]
    rules: tuple[LogicRule, ...]


@dataclass(frozen=True, slots=True)
class ProofStep:
    literal: Literal
    source: str
    premises: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "literal": self.literal.key,
            "source": self.source,
            "premises": list(self.premises),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProofStep":
        return cls(
            literal=Literal.parse(str(value["literal"])),
            source=str(value["source"]),
            premises=tuple(str(item) for item in value.get("premises", ())),
        )


@dataclass(frozen=True, slots=True)
class LogicResult:
    request_id: str
    status: LogicStatus
    query: Literal
    proof: tuple[ProofStep, ...]
    contradictions: tuple[str, ...]
    derived_literals: tuple[str, ...]
    iterations: int
    elapsed_ms: float
    input_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "request_id": self.request_id,
            "status": self.status.value,
            "query": self.query.key,
            "proof": [step.to_dict() for step in self.proof],
            "contradictions": list(self.contradictions),
            "derived_literals": list(self.derived_literals),
            "iterations": self.iterations,
            "elapsed_ms": self.elapsed_ms,
            "input_sha256": self.input_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LogicResult":
        if int(value.get("schema_version", 0)) != _SCHEMA_VERSION:
            raise PureLogicError(
                LogicFailureCode.CORRUPT_PROOF,
                "unsupported proof schema version",
            )
        return cls(
            request_id=str(value["request_id"]),
            status=LogicStatus(str(value["status"])),
            query=Literal.parse(str(value["query"])),
            proof=tuple(ProofStep.from_dict(item) for item in value.get("proof", ())),
            contradictions=tuple(str(item) for item in value.get("contradictions", ())),
            derived_literals=tuple(
                str(item) for item in value.get("derived_literals", ())
            ),
            iterations=int(value["iterations"]),
            elapsed_ms=float(value["elapsed_ms"]),
            input_sha256=str(value["input_sha256"]),
        )


@dataclass(frozen=True, slots=True)
class SolverLimits:
    max_facts: int = 2_000
    max_rules: int = 2_000
    max_premises_per_rule: int = 32
    max_iterations: int = 2_000
    timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_facts,
            self.max_rules,
            self.max_premises_per_rule,
            self.max_iterations,
        )
        if any(value <= 0 for value in integer_limits):
            raise ValueError("solver integer limits must be positive")
        if not 0.001 <= self.timeout_seconds <= 300:
            raise ValueError("solver timeout_seconds must be between 0.001 and 300")


class PureLogicSolver:
    """Bounded forward-chaining solver with explicit proof provenance."""

    def __init__(self, limits: SolverLimits | None = None) -> None:
        self.limits = limits or SolverLimits()

    def health_check(self) -> bool:
        theory = LogicTheory(
            facts=(Literal("health.input"),),
            rules=(
                LogicRule(
                    "health-rule",
                    (Literal("health.input"),),
                    Literal("health.output"),
                ),
            ),
        )
        result = self.solve("health-check", theory, Literal("health.output"))
        return result.status is LogicStatus.PROVED

    def solve(
        self,
        request_id: str,
        theory: LogicTheory,
        query: Literal,
        *,
        max_process_memory_mb: int | None = None,
    ) -> LogicResult:
        self._validate_request_id(request_id)
        self._validate_theory(theory)
        input_sha256 = self.input_sha256(theory, query)
        started = time.monotonic()
        self._check_process_memory(max_process_memory_mb)

        known: dict[str, ProofStep] = {}
        agenda: deque[Literal] = deque()
        for fact in theory.facts:
            if fact.key not in known:
                known[fact.key] = ProofStep(fact, "FACT")
                agenda.append(fact)

        rules_by_premise: dict[str, list[LogicRule]] = {}
        remaining: dict[str, set[str]] = {}
        for rule in theory.rules:
            premise_keys = {item.key for item in rule.premises}
            remaining[rule.rule_id] = set(premise_keys)
            for premise_key in premise_keys:
                rules_by_premise.setdefault(premise_key, []).append(rule)

        iterations = 0
        while agenda:
            self._check_timeout(started)
            self._check_process_memory(max_process_memory_mb)
            literal = agenda.popleft()
            for rule in rules_by_premise.get(literal.key, ()):  # only affected rules
                pending = remaining[rule.rule_id]
                pending.discard(literal.key)
                if pending or rule.conclusion.key in known:
                    continue
                iterations += 1
                if iterations > self.limits.max_iterations:
                    raise PureLogicError(
                        LogicFailureCode.THEORY_LIMIT_EXCEEDED,
                        "maximum solver iterations exceeded",
                    )
                step = ProofStep(
                    literal=rule.conclusion,
                    source=rule.rule_id,
                    premises=tuple(item.key for item in rule.premises),
                )
                known[rule.conclusion.key] = step
                agenda.append(rule.conclusion)

        positive = query.key in known
        negative = query.inverse().key in known
        if positive and negative:
            status = LogicStatus.CONFLICT
        elif positive:
            status = LogicStatus.PROVED
        elif negative:
            status = LogicStatus.DISPROVED
        else:
            status = LogicStatus.UNKNOWN

        contradiction_atoms = sorted(
            literal.atom
            for literal in (step.literal for step in known.values())
            if not literal.negated and literal.inverse().key in known
        )
        proof_targets: list[str] = []
        if positive:
            proof_targets.append(query.key)
        if negative:
            proof_targets.append(query.inverse().key)
        proof = self._proof_trace(known, proof_targets)

        return LogicResult(
            request_id=request_id,
            status=status,
            query=query,
            proof=proof,
            contradictions=tuple(contradiction_atoms),
            derived_literals=tuple(sorted(known)),
            iterations=iterations,
            elapsed_ms=round((time.monotonic() - started) * 1_000, 6),
            input_sha256=input_sha256,
        )

    @staticmethod
    def input_sha256(theory: LogicTheory, query: Literal) -> str:
        """Return a stable digest for idempotency across process restarts."""
        payload = {
            "facts": sorted(item.key for item in theory.facts),
            "rules": sorted(
                (rule.to_dict() for rule in theory.rules),
                key=lambda item: str(item["id"]),
            ),
            "query": query.key,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_request_id(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not _RULE_ID_PATTERN.fullmatch(
            request_id
        ):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "request_id must contain 1-128 safe characters",
            )

    def _validate_theory(self, theory: LogicTheory) -> None:
        if len(theory.facts) > self.limits.max_facts:
            raise PureLogicError(
                LogicFailureCode.THEORY_LIMIT_EXCEEDED,
                "maximum fact count exceeded",
            )
        if len(theory.rules) > self.limits.max_rules:
            raise PureLogicError(
                LogicFailureCode.THEORY_LIMIT_EXCEEDED,
                "maximum rule count exceeded",
            )
        rule_ids = [rule.rule_id for rule in theory.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "duplicate rule id",
            )
        if any(
            len(rule.premises) > self.limits.max_premises_per_rule
            for rule in theory.rules
        ):
            raise PureLogicError(
                LogicFailureCode.THEORY_LIMIT_EXCEEDED,
                "maximum premises per rule exceeded",
            )

    def _check_timeout(self, started: float) -> None:
        if time.monotonic() - started > self.limits.timeout_seconds:
            raise PureLogicError(
                LogicFailureCode.SOLVER_TIMEOUT,
                "solver timeout exceeded",
            )

    @staticmethod
    def _check_process_memory(max_process_memory_mb: int | None) -> None:
        if max_process_memory_mb is None:
            return
        if max_process_memory_mb <= 0:
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "max_process_memory_mb must be positive",
            )
        try:
            import psutil

            rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        except (ImportError, OSError, RuntimeError) as exc:
            raise PureLogicError(
                LogicFailureCode.RESOURCE_PROBE_UNAVAILABLE,
                "cannot enforce solver process-memory limit",
            ) from exc
        if rss_mb > max_process_memory_mb:
            raise PureLogicError(
                LogicFailureCode.MEMORY_LIMIT_EXCEEDED,
                "solver process-memory limit exceeded",
            )

    @staticmethod
    def _proof_trace(
        known: Mapping[str, ProofStep],
        targets: Iterable[str],
    ) -> tuple[ProofStep, ...]:
        ordered: list[ProofStep] = []
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visited or key not in known:
                return
            step = known[key]
            for premise in step.premises:
                visit(premise)
            visited.add(key)
            ordered.append(step)

        for target in targets:
            visit(target)
        return tuple(ordered)


class LogicProofStore:
    """SQLite proof store with idempotency and digest verification."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                self.db_path,
                timeout=5.0,
                check_same_thread=False,
            )
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS logic_proofs (
                    request_id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise PureLogicError(
                LogicFailureCode.STORAGE_ERROR,
                "failed to initialize logic proof store",
            ) from exc

    def save(self, result: LogicResult) -> bool:
        payload = json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                existing = self._connection.execute(
                    "SELECT result_sha256 FROM logic_proofs WHERE request_id = ?",
                    (result.request_id,),
                ).fetchone()
                if existing is not None:
                    if existing[0] == digest:
                        return False
                    raise PureLogicError(
                        LogicFailureCode.DUPLICATE_REQUEST,
                        "request_id already stores a different proof",
                    )
                with self._connection:
                    self._connection.execute(
                        """
                        INSERT INTO logic_proofs (
                            request_id, schema_version, result_json,
                            result_sha256, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            result.request_id,
                            _SCHEMA_VERSION,
                            payload,
                            digest,
                            created_at,
                        ),
                    )
            except PureLogicError:
                raise
            except sqlite3.Error as exc:
                raise PureLogicError(
                    LogicFailureCode.STORAGE_ERROR,
                    "failed to persist logic proof",
                ) from exc
        return True

    def count(self) -> int:
        with self._lock:
            try:
                row = self._connection.execute(
                    "SELECT COUNT(*) FROM logic_proofs"
                ).fetchone()
            except sqlite3.Error as exc:
                raise PureLogicError(
                    LogicFailureCode.STORAGE_ERROR,
                    "failed to count logic proofs",
                ) from exc
        return int(row[0])

    def get(self, request_id: str) -> LogicResult | None:
        with self._lock:
            try:
                row = self._connection.execute(
                    """
                    SELECT result_json, result_sha256
                    FROM logic_proofs WHERE request_id = ?
                    """,
                    (request_id,),
                ).fetchone()
            except sqlite3.Error as exc:
                raise PureLogicError(
                    LogicFailureCode.STORAGE_ERROR,
                    "failed to read logic proof",
                ) from exc
        if row is None:
            return None
        payload, expected_digest = row
        actual_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if actual_digest != expected_digest:
            raise PureLogicError(
                LogicFailureCode.CORRUPT_PROOF,
                "stored logic proof digest mismatch",
            )
        try:
            return LogicResult.from_dict(json.loads(payload))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PureLogicError(
                LogicFailureCode.CORRUPT_PROOF,
                "stored logic proof payload is invalid",
            ) from exc

    def health_check(self) -> bool:
        try:
            self._connection.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            return False
        return True

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class PureLogicService:
    """Validated service boundary used by the Core runtime and HTTP adapter."""

    def __init__(
        self,
        store: LogicProofStore,
        solver: PureLogicSolver | None = None,
    ) -> None:
        self.store = store
        self.solver = solver or PureLogicSolver()

    def is_ready(self) -> bool:
        return self.store.health_check() and self.solver.health_check()

    def evaluate(
        self,
        *,
        request_id: str,
        facts: Sequence[str],
        rules: Sequence[Mapping[str, Any]],
        query: str,
        max_process_memory_mb: int | None = None,
    ) -> LogicResult:
        if (
            not isinstance(facts, Sequence)
            or isinstance(facts, (str, bytes))
            or not isinstance(rules, Sequence)
            or isinstance(rules, (str, bytes))
        ):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "facts and rules must be arrays",
            )
        if any(not isinstance(item, str) for item in facts):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "every fact must be a string literal",
            )
        if any(not isinstance(item, Mapping) for item in rules):
            raise PureLogicError(
                LogicFailureCode.INVALID_INPUT,
                "every rule must be an object",
            )
        theory = LogicTheory(
            facts=tuple(Literal.parse(item) for item in facts),
            rules=tuple(LogicRule.from_mapping(item) for item in rules),
        )
        result = self.solver.solve(
            request_id,
            theory,
            Literal.parse(query),
            max_process_memory_mb=max_process_memory_mb,
        )
        existing = self.store.get(request_id)
        if existing is not None:
            if existing.input_sha256 == result.input_sha256:
                return existing
            raise PureLogicError(
                LogicFailureCode.DUPLICATE_REQUEST,
                "request_id already belongs to a different logic input",
            )
        self.store.save(result)
        return result

    def close(self) -> None:
        self.store.close()


__all__ = [
    "Literal",
    "LogicFailureCode",
    "LogicProofStore",
    "LogicResult",
    "LogicRule",
    "LogicStatus",
    "LogicTheory",
    "ProofStep",
    "PureLogicError",
    "PureLogicService",
    "PureLogicSolver",
    "SolverLimits",
]
