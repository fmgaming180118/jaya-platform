"""Grounded persistent retrieval and local-model answering for Pillar 33."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import requests

from .local_capabilities import LocalPillarError, LocalPillarResult

RAG_CAPABILITY_ID = "core.retrieval.agentic"
_WORD = re.compile(r"[A-Za-z0-9_]{2,64}")


def _strict(request: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    candidate = " ".join(value.strip().split())
    if not 1 <= len(candidate) <= maximum:
        raise LocalPillarError("INVALID_INPUT", f"{field} must contain 1-{maximum} characters")
    return candidate


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GroundedAnswerProvider(Protocol):
    provider_type: str

    def health_check(self) -> bool:
        ...

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        ...


class OllamaGroundedAnswerProvider:
    """Call one explicitly configured Ollama model with a strict JSON contract."""

    provider_type = "LOCAL_MODEL"

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = _text(model, "model", 256)
        if not 1.0 <= timeout_seconds <= 300.0:
            raise LocalPillarError("INVALID_CONFIG", "model timeout must be 1-300 seconds")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def health_check(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            payload = response.json()
            return any(item.get("name") == self.model for item in payload.get("models", []))
        except (requests.RequestException, ValueError, TypeError):
            return False

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        evidence_ids = [str(item["evidence_id"]) for item in evidence]
        evidence_text = "\n\n".join(
            f"[{item['evidence_id']}] {item['content']}" for item in evidence
        )
        prompt = (
            "Answer only from the evidence. If evidence conflicts, explicitly state the conflict. "
            "Return JSON matching the schema. citations must contain only evidence IDs shown below.\n"
            f"QUESTION: {question}\nEVIDENCE:\n{evidence_text}"
        )
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "enum": evidence_ids},
                },
            },
            "required": ["answer", "citations"],
        }
        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "format": schema,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0, "num_predict": 384},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            outer = response.json()
            raw = outer.get("response")
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > 131_072:
                raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "model response is invalid")
            payload = json.loads(raw)
        except requests.Timeout as exc:
            raise LocalPillarError("TIMEOUT", "local model timed out") from exc
        except requests.RequestException as exc:
            raise LocalPillarError("PROVIDER_UNAVAILABLE", "local model request failed") from exc
        except (ValueError, TypeError) as exc:
            raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "local model returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "model result must be an object")
        return payload

    def close(self) -> None:
        self.session.close()


class ExtractiveGroundedAnswerProvider:
    """Deterministic CPU fallback extracting exact supporting sentences with verified citation spans."""

    provider_type = "EXTRACTIVE_LOCAL"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        if not evidence:
            raise LocalPillarError("EVIDENCE_UNAVAILABLE", "no evidence provided for extractive answer")
        q_words = [w.casefold() for w in _WORD.findall(question) if len(w) >= 3 and w.casefold() not in {"the", "and", "for", "what", "how", "why"}]
        if not q_words:
            q_words = [w.casefold() for w in _WORD.findall(question)]
        best_score = -1.0
        best_sentence = ""
        best_evidence_id = ""
        best_span = (0, 0)
        for item in evidence:
            ev_id = str(item["evidence_id"])
            content = str(item["content"])
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]
            offset = 0
            for sent in sentences:
                sent_start = content.find(sent, offset)
                if sent_start == -1:
                    sent_start = offset
                sent_end = sent_start + len(sent)
                offset = sent_end
                sent_words = [w.casefold() for w in _WORD.findall(sent)]
                overlap = sum(1 for w in q_words if w in sent_words)
                if overlap > best_score:
                    best_score = overlap
                    best_sentence = sent
                    best_evidence_id = ev_id
                    best_span = (sent_start, sent_end)
        if not best_sentence or best_score <= 0:
            first_chunk = evidence[0]
            best_evidence_id = str(first_chunk["evidence_id"])
            content = str(first_chunk["content"])
            parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]
            best_sentence = parts[0] if parts else content[:256]
            best_span = (0, len(best_sentence))
        return {
            "answer": best_sentence,
            "citations": [best_evidence_id],
            "spans": [{"evidence_id": best_evidence_id, "start": best_span[0], "end": best_span[1], "text": best_sentence}],
        }


class AgenticRAGCapability:
    """Persist sources, retrieve bounded evidence, and validate model citations."""

    MAX_SOURCE_BYTES = 1_048_576

    def __init__(self, database_path: Path, provider: GroundedAnswerProvider | None) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS rag_sources(
                        source_ref TEXT PRIMARY KEY,
                        source_digest TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks USING fts5(
                        evidence_id UNINDEXED,
                        source_ref UNINDEXED,
                        start_offset UNINDEXED,
                        end_offset UNINDEXED,
                        content,
                        tokenize='unicode61'
                    );
                    CREATE TABLE IF NOT EXISTS rag_answers(
                        answer_id TEXT PRIMARY KEY,
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        citations_json TEXT NOT NULL,
                        provider_type TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "RAG store unavailable") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def health_check(self) -> bool:
        if self.provider is None or not self.provider.health_check():
            return False
        return self.storage_health_check()

    def storage_health_check(self) -> bool:
        """Check the persistent evidence catalog independently of model health."""
        try:
            with self._connect() as connection:
                return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            return False

    @staticmethod
    def _chunks(content: str, maximum: int = 1_200, overlap: int = 120):
        start = 0
        length = len(content)
        while start < length:
            end = min(length, start + maximum)
            if end < length:
                boundary = content.rfind(" ", start + maximum // 2, end)
                if boundary > start:
                    end = boundary
            chunk = content[start:end].strip()
            if chunk:
                actual_start = content.find(chunk, start, end + 1)
                yield actual_start, actual_start + len(chunk), chunk
            if end >= length:
                break
            start = max(start + 1, end - overlap)

    def ingest(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "source_ref", "title", "content"}, {"action", "source_ref", "title", "content"})
        source_ref = _text(request["source_ref"], "source_ref", 512)
        title = _text(request["title"], "title", 512)
        content = _text(request["content"], "content", self.MAX_SOURCE_BYTES)
        if len(content.encode("utf-8")) > self.MAX_SOURCE_BYTES:
            raise LocalPillarError("RESOURCE_LIMIT", "RAG source exceeds 1 MiB")
        source_digest = _digest(content)
        chunks = [
            {
                "evidence_id": _digest(f"{source_ref}\x1f{start}\x1f{end}\x1f{text}"),
                "source_ref": source_ref,
                "start_offset": start,
                "end_offset": end,
                "content": text,
            }
            for start, end, text in self._chunks(content)
        ]
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT source_digest FROM rag_sources WHERE source_ref=?", (source_ref,)
                ).fetchone()
                if existing is not None:
                    if existing[0] != source_digest:
                        raise LocalPillarError("SOURCE_CONFLICT", "source_ref content changed")
                    count = connection.execute(
                        "SELECT count(*) FROM rag_chunks WHERE source_ref=?", (source_ref,)
                    ).fetchone()[0]
                    return LocalPillarResult(
                        "P033",
                        "RAG_SOURCE_DUPLICATE",
                        {"source_ref": source_ref, "source_digest": f"sha256:{source_digest}", "chunks": count},
                    )
                connection.execute(
                    "INSERT INTO rag_sources VALUES(?,?,?,?,?)",
                    (source_ref, source_digest, title, content, time.time()),
                )
                connection.executemany(
                    "INSERT INTO rag_chunks VALUES(?,?,?,?,?)",
                    (
                        (
                            item["evidence_id"],
                            item["source_ref"],
                            item["start_offset"],
                            item["end_offset"],
                            item["content"],
                        )
                        for item in chunks
                    ),
                )
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "RAG source was not stored") from exc
        return LocalPillarResult(
            "P033",
            "RAG_SOURCE_INGESTED",
            {
                "source_ref": source_ref,
                "source_digest": f"sha256:{source_digest}",
                "chunks": len(chunks),
            },
        )

    def retrieve(self, question: str, top_k: int) -> list[dict[str, Any]]:
        terms = list(dict.fromkeys(word.casefold() for word in _WORD.findall(question) if word.casefold() not in {"and", "or", "not"}))
        if not terms:
            raise LocalPillarError("INVALID_INPUT", "question has no searchable terms")
        expression = " OR ".join(f'"{term}"' for term in terms[:32])
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """SELECT evidence_id, source_ref, start_offset, end_offset,
                    content, bm25(rag_chunks) AS rank FROM rag_chunks
                    WHERE rag_chunks MATCH ? ORDER BY rank LIMIT ?""",
                    (expression, top_k),
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "RAG retrieval failed") from exc
        return [
            {
                "evidence_id": row["evidence_id"],
                "source_ref": row["source_ref"],
                "start_offset": int(row["start_offset"]),
                "end_offset": int(row["end_offset"]),
                "content": row["content"],
                "retrieval_score": 1.0 / (1.0 + abs(float(row["rank"]))),
            }
            for row in rows
            if math.isfinite(float(row["rank"]))
        ]

    def evidence_exists(self, evidence_id: str) -> bool:
        try:
            with self._connect() as connection:
                return (
                    connection.execute(
                        "SELECT 1 FROM rag_chunks WHERE evidence_id=? OR source_ref=? LIMIT 1",
                        (evidence_id, evidence_id),
                    ).fetchone()
                    is not None
                    or connection.execute(
                        "SELECT 1 FROM rag_sources WHERE source_ref=? LIMIT 1",
                        (evidence_id,),
                    ).fetchone()
                    is not None
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "RAG evidence lookup failed") from exc

    def evidence_by_ids(self, evidence_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Resolve exact persisted evidence IDs without performing fuzzy retrieval."""
        normalized = tuple(dict.fromkeys(str(item).strip() for item in evidence_ids))
        if not normalized:
            return []
        if len(normalized) > 256 or any(not item or len(item) > 128 for item in normalized):
            raise LocalPillarError("RESOURCE_LIMIT", "evidence_ids must contain 1-256 bounded IDs")
        placeholders = ",".join("?" for _ in normalized)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""SELECT evidence_id, source_ref, start_offset, end_offset, content
                    FROM rag_chunks WHERE evidence_id IN ({placeholders})""",
                    normalized,
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "RAG evidence lookup failed") from exc
        indexed = {
            str(row["evidence_id"]): {
                "evidence_id": str(row["evidence_id"]),
                "source_ref": str(row["source_ref"]),
                "start_offset": int(row["start_offset"]),
                "end_offset": int(row["end_offset"]),
                "content": str(row["content"]),
            }
            for row in rows
        }
        return [indexed[item] for item in normalized if item in indexed]

    @staticmethod
    def detect_need(question: str) -> dict[str, Any]:
        cleaned = _text(question, "question", 4_096)
        words = [w.casefold() for w in _WORD.findall(cleaned)]
        conversational = {"hi", "hello", "hey", "greetings", "ping", "morning", "afternoon"}
        is_purely_conversational = len(words) <= 2 and any(w in conversational for w in words)
        spec_indicators = {
            "what", "how", "why", "when", "where", "who", "which", "define", "explain",
            "describe", "status", "version", "config", "port", "digest", "hash",
            "specification", "bridge", "pillar", "spec"
        }
        has_inquiry = any(w in spec_indicators for w in words) or "?" in question
        requires_retrieval = not is_purely_conversational and (has_inquiry or len(words) >= 3)
        intent = "FACTUAL_LOOKUP" if has_inquiry else ("CONVERSATIONAL" if is_purely_conversational else "EXPLORATORY")
        keywords = list(dict.fromkeys(w for w in words if len(w) >= 3 and w not in {"the", "and", "for", "with", "this", "that", "from"}))
        expanded: list[str] = []
        if len(keywords) >= 2:
            expanded.append(" ".join(keywords[:3]))
            expanded.append(" ".join(keywords[1:4]))
        for k in keywords[:4]:
            expanded.append(k)
        return {
            "requires_retrieval": requires_retrieval,
            "intent": intent,
            "keywords": keywords,
            "expanded_queries": expanded,
        }

    @staticmethod
    def detect_conflicts(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Detect contradictory claims or numerical values in retrieved chunks."""
        conflicts: list[dict[str, Any]] = []
        prop_pattern = re.compile(r"([a-z_0-9]{3,32})\s*(?::|is|=)\s*([a-z0-9_.-]{1,64})", re.IGNORECASE)
        claims: dict[str, list[tuple[str, str]]] = {}
        for item in evidence:
            ev_id = str(item.get("evidence_id", ""))
            text = str(item.get("content", ""))
            for match in prop_pattern.finditer(text):
                prop = match.group(1).casefold()
                val = match.group(2).strip().casefold()
                if prop in {"the", "and", "this", "that", "there", "here", "with", "from"}:
                    continue
                claims.setdefault(prop, []).append((val, ev_id))
        for prop, occurrences in claims.items():
            distinct_vals = {v for v, _ in occurrences}
            if len(distinct_vals) > 1:
                conflicts.append({
                    "property": prop,
                    "contradictory_values": sorted(distinct_vals),
                    "evidence_ids": list(dict.fromkeys(ev for _, ev in occurrences)),
                })
        return conflicts

    @classmethod
    def evaluate_sufficiency(
        cls, question: str, evidence: Sequence[Mapping[str, Any]], strict_conflict: bool = True
    ) -> dict[str, Any]:
        if not evidence:
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "coverage": 0.0,
                "sufficiency_score": 0.0,
                "conflicts": [],
                "reason": "no evidence retrieved",
            }
        q_words = [w.casefold() for w in _WORD.findall(question) if len(w) >= 3 and w not in {"the", "and", "for", "what", "how", "why"}]
        if not q_words:
            q_words = [w.casefold() for w in _WORD.findall(question)]
        combined_text = " ".join(str(item.get("content", "")).casefold() for item in evidence)
        matches = sum(1 for w in q_words if w in combined_text)
        coverage = matches / max(1, len(q_words))
        conflicts = cls.detect_conflicts(evidence)
        if conflicts and strict_conflict:
            return {
                "status": "CONFLICTING_EVIDENCE",
                "coverage": round(coverage, 4),
                "sufficiency_score": round(coverage * 0.5, 4),
                "conflicts": conflicts,
                "reason": f"unresolved contradiction detected in {len(conflicts)} properties",
            }
        if coverage < 0.25 and matches == 0:
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "coverage": round(coverage, 4),
                "sufficiency_score": round(coverage, 4),
                "conflicts": conflicts,
                "reason": "insufficient query term coverage in retrieved evidence",
            }
        score = min(1.0, coverage * 1.1)
        return {
            "status": "SUFFICIENT",
            "coverage": round(coverage, 4),
            "sufficiency_score": round(score, 4),
            "conflicts": conflicts,
            "reason": "sufficient grounded evidence available",
        }

    @staticmethod
    def validate_citations(
        citations: Sequence[Any],
        evidence: Sequence[Mapping[str, Any]],
        answer: str = "",
    ) -> dict[str, Any]:
        if not isinstance(citations, (list, tuple)) or not citations:
            raise LocalPillarError("CITATION_REQUIRED", "grounded answer has no citations")
        allowed_map = {str(item["evidence_id"]): item for item in evidence}
        validated_citations: list[str] = []
        verified_spans: list[dict[str, Any]] = []
        injection_patterns = ["<|im_start|>", "<|im_end|>", "system:", "[admin]", "ignore previous instructions", "eval(", "exec("]
        for cite in citations:
            if isinstance(cite, str):
                cite_clean = cite.strip()
                if any(p in cite_clean.casefold() for p in injection_patterns):
                    raise LocalPillarError("CITATION_INJECTION_REJECTED", "citation contains malicious injection pattern")
                if cite_clean not in allowed_map:
                    raise LocalPillarError("INVALID_CITATION", f"model cited evidence outside retrieval: {cite_clean}")
                validated_citations.append(cite_clean)
            elif isinstance(cite, Mapping):
                ev_id = str(cite.get("evidence_id", "")).strip()
                if any(p in ev_id.casefold() for p in injection_patterns):
                    raise LocalPillarError("CITATION_INJECTION_REJECTED", "citation contains malicious injection pattern")
                if ev_id not in allowed_map:
                    raise LocalPillarError("INVALID_CITATION", f"model cited evidence outside retrieval: {ev_id}")
                item = allowed_map[ev_id]
                content = str(item["content"])
                text = cite.get("text")
                if text is not None:
                    if not isinstance(text, str) or text not in content:
                        raise LocalPillarError("INVALID_CITATION_SPAN", "citation text does not match evidence content")
                span = cite.get("span")
                if span is not None:
                    if not (isinstance(span, (list, tuple)) and len(span) == 2 and isinstance(span[0], int) and isinstance(span[1], int)):
                        raise LocalPillarError("INVALID_CITATION_SPAN", "citation span must be [start, end] integers")
                    start, end = span
                    if not (0 <= start < end <= len(content)):
                        raise LocalPillarError("INVALID_CITATION_SPAN", "citation span boundaries out of range")
                    if text is not None and content[start:end] != text:
                        raise LocalPillarError("INVALID_CITATION_SPAN", "citation span substring does not match citation text")
                    verified_spans.append({"evidence_id": ev_id, "start": start, "end": end, "text": content[start:end]})
                validated_citations.append(ev_id)
            else:
                raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "citations must be evidence IDs or citation objects")
        deduped = list(dict.fromkeys(validated_citations))
        cited_content = " ".join(str(allowed_map[eid]["content"]).casefold() for eid in deduped)
        ans_words = [w.casefold() for w in _WORD.findall(answer) if len(w) >= 3 and w not in {"the", "and", "for", "with", "this", "that"}]
        grounded_terms = sum(1 for w in ans_words if w in cited_content)
        groundedness = round(grounded_terms / max(1, len(ans_words)), 4) if ans_words else 1.0
        return {
            "valid": True,
            "citations": deduped,
            "verified_spans": verified_spans,
            "precision": 1.0,
            "groundedness": groundedness,
        }

    def status(self) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                sources_count = connection.execute("SELECT count(*) FROM rag_sources").fetchone()[0]
                chunks_count = connection.execute("SELECT count(*) FROM rag_chunks").fetchone()[0]
                answers_count = connection.execute("SELECT count(*) FROM rag_answers").fetchone()[0]
                file_size = self.database_path.stat().st_size if self.database_path.exists() else 0
                return {
                    "sources_count": int(sources_count),
                    "chunks_count": int(chunks_count),
                    "answers_count": int(answers_count),
                    "database_bytes": int(file_size),
                    "database_path": str(self.database_path),
                    "storage_healthy": self.storage_health_check(),
                    "model_configured": bool(self.provider is not None),
                    "model_healthy": bool(self.provider is not None and self.provider.health_check()),
                    "provider_type": self.provider.provider_type if self.provider else "NONE",
                }
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "RAG status check failed") from exc

    def ask(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "question", "top_k", "maximum_rounds", "allow_extractive_fallback", "mode", "strict_conflict"},
            {"action", "question"},
        )
        question = _text(request["question"], "question", 4_096)
        top_k = request.get("top_k", 5)
        rounds = request.get("maximum_rounds", 2)
        allow_extractive = bool(request.get("allow_extractive_fallback", False))
        mode = request.get("mode", "standard")
        strict_conflict = bool(request.get("strict_conflict", True))

        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise LocalPillarError("RESOURCE_LIMIT", "top_k must be 1-20")
        if type(rounds) is not int or not 1 <= rounds <= 3:
            raise LocalPillarError("RESOURCE_LIMIT", "maximum_rounds must be 1-3")

        # Provider determination
        active_provider: GroundedAnswerProvider
        if mode == "extractive":
            active_provider = ExtractiveGroundedAnswerProvider()
        elif self.provider is not None and self.provider.health_check():
            active_provider = self.provider
        elif allow_extractive:
            active_provider = ExtractiveGroundedAnswerProvider()
        else:
            raise LocalPillarError("MODEL_NOT_CONFIGURED", "grounded answer model is unavailable")

        # Information need detection
        need = self.detect_need(question)

        # Multi-round bounded retrieval loop
        evidence: list[dict[str, Any]] = []
        current_round = 1
        for current_round in range(1, rounds + 1):
            evidence = self.retrieve(question, min(20, top_k * current_round))
            if evidence:
                break
            # Query reformulation on subsequent rounds
            if current_round < rounds and need["expanded_queries"]:
                for exp_query in need["expanded_queries"]:
                    try:
                        expanded_evidence = self.retrieve(exp_query, min(20, top_k * current_round))
                        if expanded_evidence:
                            evidence = expanded_evidence
                            break
                    except LocalPillarError:
                        continue
                if evidence:
                    break

        if not evidence:
            raise LocalPillarError("EVIDENCE_UNAVAILABLE", "no evidence supports the question")

        # Sufficiency and conflict gate
        sufficiency = self.evaluate_sufficiency(question, evidence, strict_conflict=strict_conflict)
        if sufficiency["status"] == "CONFLICTING_EVIDENCE":
            raise LocalPillarError("CONFLICTING_EVIDENCE", f"retrieved evidence contains unresolved contradiction: {sufficiency['conflicts']}")
        if sufficiency["status"] == "INSUFFICIENT_EVIDENCE" and (mode == "strict" or sufficiency["coverage"] == 0.0):
            raise LocalPillarError("EVIDENCE_UNAVAILABLE" if sufficiency["coverage"] == 0.0 else "INSUFFICIENT_EVIDENCE", "no evidence supports the question")

        raw = active_provider.answer(question, evidence)
        answer = _text(raw.get("answer"), "answer", 16_384)
        citations_raw = raw.get("citations")
        if not isinstance(citations_raw, list) or not citations_raw:
            raise LocalPillarError("CITATION_REQUIRED", "grounded answer has no citations")

        # Validate citations strictly
        validation = self.validate_citations(citations_raw, evidence, answer)
        normalized_citations = validation["citations"]

        answer_id = _digest(
            json.dumps(
                {"question": question, "answer": answer, "citations": normalized_citations},
                sort_keys=True,
            )
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR IGNORE INTO rag_answers VALUES(?,?,?,?,?,?)",
                    (
                        answer_id,
                        question,
                        answer,
                        json.dumps(normalized_citations),
                        active_provider.provider_type,
                        time.time(),
                    ),
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "grounded answer was not stored") from exc

        return LocalPillarResult(
            "P033",
            "GROUNDED_ANSWER_CREATED",
            {
                "answer_id": answer_id,
                "answer": answer,
                "citations": normalized_citations,
                "evidence": evidence,
                "provider_type": active_provider.provider_type,
                "rounds_used": current_round,
                "sufficiency": sufficiency,
                "groundedness": validation["groundedness"],
                "precision": validation["precision"],
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action")
        if action == "ingest":
            return self.ingest(request)
        if action == "ask":
            return self.ask(request)
        if action == "retrieve":
            _strict(request, {"action", "question", "top_k"}, {"action", "question"})
            question = _text(request["question"], "question", 4_096)
            top_k = request.get("top_k", 5)
            if type(top_k) is not int or not 1 <= top_k <= 50:
                raise LocalPillarError("RESOURCE_LIMIT", "top_k must be 1-50")
            evidence = self.retrieve(question, top_k)
            return LocalPillarResult("P033", "RAG_EVIDENCE_RETRIEVED", {"question": question, "evidence": evidence, "count": len(evidence)})
        if action == "detect_need":
            _strict(request, {"action", "question"}, {"action", "question"})
            need = self.detect_need(request["question"])
            return LocalPillarResult("P033", "INFORMATION_NEED_DETECTED", need)
        if action == "evaluate_sufficiency":
            _strict(request, {"action", "question", "evidence", "strict_conflict"}, {"action", "question", "evidence"})
            question = _text(request["question"], "question", 4_096)
            evidence = request["evidence"]
            if not isinstance(evidence, (list, tuple)):
                raise LocalPillarError("INVALID_INPUT", "evidence must be a list")
            eval_res = self.evaluate_sufficiency(question, evidence, strict_conflict=request.get("strict_conflict", True))
            return LocalPillarResult("P033", "EVIDENCE_SUFFICIENCY_EVALUATED", eval_res)
        if action == "validate_citations":
            _strict(request, {"action", "citations", "evidence", "answer"}, {"action", "citations", "evidence"})
            val_res = self.validate_citations(request["citations"], request["evidence"], request.get("answer", ""))
            return LocalPillarResult("P033", "CITATIONS_VALIDATED", val_res)
        if action == "status":
            _strict(request, {"action"}, {"action"})
            return LocalPillarResult("P033", "RAG_STATUS_COMPUTED", self.status())
        raise LocalPillarError("UNSUPPORTED_ACTION", f"Agentic RAG action '{action}' is unsupported")

    def close(self) -> None:
        close_provider = getattr(self.provider, "close", None)
        if callable(close_provider):
            close_provider()

