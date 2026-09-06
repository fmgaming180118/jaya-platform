"""Shared truthfulness contracts for academic text generation.

The helpers in this module deliberately treat language-model output as
untrusted.  Callers must supply evidence identifiers; generated prose may only
use those identifiers, and unsupported prose is labelled for human review.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


UNSUPPORTED_MARKER = "[UNSUPPORTED: no supplied evidence ID]"


class AcademicGenerationStatus(str, Enum):
    """Machine-readable state for an academic generation attempt."""

    COMPLETE_HUMAN_REVIEW_REQUIRED = "COMPLETE_HUMAN_REVIEW_REQUIRED"
    ABSTAINED_INSUFFICIENT_EVIDENCE = "ABSTAINED_INSUFFICIENT_EVIDENCE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_PROVIDER_OUTPUT = "INVALID_PROVIDER_OUTPUT"


@dataclass(frozen=True)
class AcademicGenerationResult:
    """Typed result that never implies autonomous publication approval."""

    status: AcademicGenerationStatus
    content: str
    evidence_ids: tuple[str, ...] = ()
    unsupported_claim_count: int = 0
    provider_error_code: str | None = None
    human_review_required: bool = True
    publication_ready: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "content": self.content,
            "evidence_ids": list(self.evidence_ids),
            "unsupported_claim_count": self.unsupported_claim_count,
            "provider_error_code": self.provider_error_code,
            "human_review_required": self.human_review_required,
            "publication_ready": self.publication_ready,
        }


class AcademicTextProvider(Protocol):
    """Small provider surface accepted by the academic agents."""

    def generate_completion(self, prompt: str) -> str: ...


ProviderFactory = Callable[[], AcademicTextProvider]


@dataclass(frozen=True)
class ReferenceRecord:
    """A supplied, traceable reference suitable for a bibliography."""

    evidence_id: str
    citation: str


_CITATION_RE = re.compile(r"(?<!\!)\[([^\[\]\r\n]{1,128})\](?!\s*\()")
_REFERENCE_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s+(?:references|bibliography|daftar pustaka)\s*$"
)
_VALID_EVIDENCE_ID_RE = re.compile(r"^[^\[\]\r\n]{1,128}$")
_UNSUPPORTED_PREFIXES = ("unsupported:", "provider_", "abstained:")


def normalize_evidence_ids(values: object) -> tuple[str, ...]:
    """Return unique, bounded identifiers while rejecting ambiguous values."""
    if values is None:
        return ()
    if isinstance(values, str):
        candidates: Iterable[object] = (values,)
    elif isinstance(values, Sequence):
        candidates = values
    else:
        return ()

    normalized: list[str] = []
    for candidate in candidates:
        value = str(candidate).strip()
        if not _VALID_EVIDENCE_ID_RE.fullmatch(value):
            continue
        if value.casefold().startswith(_UNSUPPORTED_PREFIXES):
            continue
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def extract_citation_ids(text: str) -> tuple[str, ...]:
    """Extract citation markers while ignoring Markdown links/status markers."""
    found: list[str] = []
    for match in _CITATION_RE.finditer(text or ""):
        identifier = match.group(1).strip()
        if identifier.casefold().startswith(_UNSUPPORTED_PREFIXES):
            continue
        if identifier not in found:
            found.append(identifier)
    return tuple(found)


def unknown_citation_ids(text: str, allowed_ids: Iterable[str]) -> tuple[str, ...]:
    allowed = set(normalize_evidence_ids(tuple(allowed_ids)))
    return tuple(
        identifier
        for identifier in extract_citation_ids(text)
        if identifier not in allowed
    )


def strip_generated_bibliography(text: str) -> str:
    """Remove a provider-authored bibliography; callers append canonical data."""
    match = _REFERENCE_HEADING_RE.search(text or "")
    return (text[: match.start()] if match else text).rstrip()


def reference_section(text: str) -> str:
    """Return the exact bibliography tail, including its heading, if supplied."""
    match = _REFERENCE_HEADING_RE.search(text or "")
    return text[match.start() :].strip() if match else ""


def headings(text: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in (text or "").splitlines()
        if re.match(r"^#{1,6}\s+\S", line.strip())
    )


def annotate_unsupported_claims(
    text: str,
    allowed_ids: Iterable[str],
) -> tuple[str, int]:
    """Label substantive uncited sentences instead of presenting them as fact."""
    allowed = set(normalize_evidence_ids(tuple(allowed_ids)))
    unsupported = 0
    rendered: list[str] = []
    in_code_fence = False

    for line in (text or "").splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        body = line[:-1] if ending else line
        stripped = body.strip()
        fence_count = stripped.count("```")
        is_reference_line = any(
            stripped.startswith(f"[{identifier}]") for identifier in allowed
        )
        if (
            not stripped
            or in_code_fence
            or stripped.startswith("```")
            or stripped.startswith("#")
            or stripped.startswith("<!--")
            or is_reference_line
        ):
            rendered.append(body + ending)
        else:
            parts = re.split(r"(?<=[.!])([ \t]+)", body)
            annotated_parts: list[str] = []
            for part in parts:
                candidate = part.strip()
                is_separator = bool(part) and not candidate
                has_allowed_citation = any(
                    identifier in allowed
                    for identifier in extract_citation_ids(candidate)
                )
                should_annotate = (
                    bool(candidate)
                    and not is_separator
                    and not candidate.endswith("?")
                    and UNSUPPORTED_MARKER not in candidate
                    and not has_allowed_citation
                    and len(re.findall(r"\b[\w-]+\b", candidate)) >= 4
                )
                if should_annotate:
                    annotated_parts.append(part.rstrip() + " " + UNSUPPORTED_MARKER)
                    unsupported += 1
                else:
                    annotated_parts.append(part)
            rendered.append("".join(annotated_parts) + ending)
        if fence_count % 2:
            in_code_fence = not in_code_fence

    return "".join(rendered), unsupported


def normalize_reference(reference: object) -> ReferenceRecord | None:
    """Normalize only references carrying an explicit supplied identifier."""
    if isinstance(reference, str):
        match = re.fullmatch(r"\s*\[([^\[\]\r\n]+)\]\s+(.+?)\s*", reference)
        if not match:
            return None
        evidence_ids = normalize_evidence_ids(match.group(1))
        if not evidence_ids:
            return None
        return ReferenceRecord(evidence_ids[0], match.group(2).strip())

    if not isinstance(reference, Mapping):
        return None
    raw_identifier = next(
        (
            reference.get(key)
            for key in (
                "evidence_id",
                "citation_id",
                "id",
                "doi",
                "uri",
                "url",
                "pdf_link",
                "sha256",
            )
            if reference.get(key)
        ),
        None,
    )
    evidence_ids = normalize_evidence_ids(raw_identifier)
    title = str(reference.get("title") or "").strip()
    if not evidence_ids or not title:
        return None

    details: list[str] = []
    authors = reference.get("authors")
    if isinstance(authors, Sequence) and not isinstance(authors, str):
        supplied_authors = [str(author).strip() for author in authors if str(author).strip()]
        if supplied_authors:
            details.append(", ".join(supplied_authors))
    year = str(reference.get("published") or reference.get("year") or "").strip()
    if year:
        details.append(year)
    details.append(title)
    source = str(reference.get("source") or "").strip()
    if source:
        details.append(source)
    locator = str(
        reference.get("uri")
        or reference.get("url")
        or reference.get("pdf_link")
        or reference.get("doi")
        or ""
    ).strip()
    if locator and locator != evidence_ids[0]:
        details.append(locator)
    source_hash = str(reference.get("sha256") or "").strip()
    if source_hash and source_hash != evidence_ids[0]:
        details.append(f"sha256: {source_hash}")
    return ReferenceRecord(evidence_ids[0], ". ".join(details))


def supplied_references(values: Iterable[object]) -> tuple[ReferenceRecord, ...]:
    """Return de-duplicated supplied references, dropping untraceable records."""
    records: list[ReferenceRecord] = []
    seen: set[str] = set()
    for value in values:
        record = normalize_reference(value)
        if record is None or record.evidence_id in seen:
            continue
        seen.add(record.evidence_id)
        records.append(record)
    return tuple(records)


def canonical_bibliography(records: Sequence[ReferenceRecord]) -> str:
    if not records:
        return ""
    return "\n".join(
        f"[{record.evidence_id}] {record.citation}" for record in records
    )


def default_provider_factory() -> AcademicTextProvider:
    """Create the optional Teacher only when generation is actually requested."""
    try:
        from jaya_research.teacher import Teacher
    except ImportError:
        from jaya_research.teacher import Teacher

    return Teacher(model_type="reasoning")


def call_provider(provider: Any, prompt: str) -> str:
    """Invoke a compatible provider and reject empty/non-text responses."""
    completion = getattr(provider, "generate_completion", None)
    if callable(completion):
        response = completion(prompt)
    else:
        ask = getattr(provider, "ask", None)
        if not callable(ask):
            raise TypeError("academic provider must define generate_completion or ask")
        response = ask(prompt)
    if not isinstance(response, str) or not response.strip():
        raise ValueError("academic provider returned empty or non-text content")
    return response.strip()


def safe_provider_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    return str(code) if code else type(error).__name__
