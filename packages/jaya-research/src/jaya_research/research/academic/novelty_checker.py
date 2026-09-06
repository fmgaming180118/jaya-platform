"""Evidence-bound novelty assessment for academic workflows.

Novelty is never inferred from a provider outage or an empty search.  A
positive novelty decision requires coverage from multiple literature providers,
traceable evidence records, and an explicitly configured evaluator.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from jaya_research.provider_errors import ProviderError
from jaya_research.research.academic.literature import ArxivClient, SemanticScholarClient

try:
    from jaya_research.research.web_search import WebSearchClient
except ImportError:  # optional offline dependency
    WebSearchClient = None

_AUTO_WEB = object()


class NoveltyChecker:
    """Assess whether supplied literature already describes a hypothesis."""

    _STOPWORDS = {
        "about",
        "after",
        "akan",
        "antara",
        "atau",
        "dalam",
        "dengan",
        "from",
        "hasil",
        "into",
        "pada",
        "penelitian",
        "research",
        "that",
        "the",
        "this",
        "untuk",
        "using",
        "yang",
    }

    def __init__(
        self,
        *,
        evaluator: Any | None = None,
        arxiv: Any | None = None,
        scholar: Any | None = None,
        web: Any = _AUTO_WEB,
        min_completed_providers: int = 2,
    ) -> None:
        if not 1 <= min_completed_providers <= 3:
            raise ValueError("min_completed_providers must be between 1 and 3")
        self.evaluator = evaluator
        self.arxiv = arxiv if arxiv is not None else ArxivClient()
        self.scholar = scholar if scholar is not None else SemanticScholarClient()
        self.web = (
            WebSearchClient()
            if web is _AUTO_WEB and WebSearchClient is not None
            else (None if web is _AUTO_WEB else web)
        )
        self.min_completed_providers = min_completed_providers

    async def verify_novelty(
        self,
        hypothesis: str,
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a structured decision with provider and evidence coverage."""
        normalized_hypothesis = hypothesis.strip()
        if not normalized_hypothesis:
            raise ValueError("hypothesis must not be empty")

        search_terms = self._normalize_keywords(
            keywords or self._extract_keywords(normalized_hypothesis)
        )
        if len(search_terms) < 3:
            return self._indeterminate(
                "At least three technical search terms are required",
                keywords=search_terms,
            )
        search_query = " ".join(search_terms[:6])

        provider_specs: list[tuple[str, Any, str]] = [
            ("arxiv", self.arxiv, "search_papers"),
            ("semantic_scholar", self.scholar, "search_papers"),
        ]
        if self.web is not None and self._web_available(self.web):
            provider_specs.append(("web", self.web, "search"))

        tasks = [
            asyncio.to_thread(
                self._search_provider,
                provider_name,
                provider,
                method_name,
                search_query,
            )
            for provider_name, provider, method_name in provider_specs
        ]
        provider_results = await asyncio.gather(*tasks)

        completed = [result for result in provider_results if result["completed"]]
        provider_errors = [
            result["error"]
            for result in provider_results
            if result["error"] is not None
        ]
        evidence = [
            item
            for result in completed
            for item in result["evidence"]
        ]
        coverage = {
            "required": self.min_completed_providers,
            "attempted": len(provider_specs),
            "completed": len(completed),
            "providers": [result["provider"] for result in completed],
        }

        if len(completed) < self.min_completed_providers:
            return self._indeterminate(
                "Insufficient independent literature-provider coverage",
                keywords=search_terms,
                coverage=coverage,
                evidence=evidence,
                provider_errors=provider_errors,
            )
        if not evidence:
            return self._indeterminate(
                "The completed literature searches returned no evidence; absence "
                "of results is not proof of novelty",
                keywords=search_terms,
                coverage=coverage,
                provider_errors=provider_errors,
            )

        similarity, closest = self._closest_evidence(normalized_hypothesis, evidence)
        if closest is not None and similarity >= 0.75:
            return {
                "status": "complete",
                "is_novel": False,
                "confidence": round(similarity, 4),
                "reasoning": (
                    "The hypothesis has high lexical overlap with retrieved "
                    "literature and therefore fails the basic novelty screen."
                ),
                "keywords": search_terms,
                "coverage": coverage,
                "evidence": evidence,
                "decision_evidence_ids": [closest["evidence_id"]],
                "evaluation_method": "DETERMINISTIC_LEXICAL_REJECTION",
                "provider_errors": provider_errors,
                "promotion_eligible": False,
            }

        if self.evaluator is None:
            return self._indeterminate(
                "Literature was retrieved, but no novelty evaluator was configured",
                keywords=search_terms,
                coverage=coverage,
                evidence=evidence,
                provider_errors=provider_errors,
            )

        decision = self._evaluate_with_model(normalized_hypothesis, evidence)
        if decision is None:
            return self._indeterminate(
                "The novelty evaluator returned an invalid or untraceable decision",
                keywords=search_terms,
                coverage=coverage,
                evidence=evidence,
                provider_errors=provider_errors,
            )
        return {
            "status": "partial" if provider_errors else "complete",
            "is_novel": decision["is_novel"],
            "confidence": decision["confidence"],
            "reasoning": decision["reasoning"],
            "keywords": search_terms,
            "coverage": coverage,
            "evidence": evidence,
            "decision_evidence_ids": decision["evidence_ids"],
            "evaluation_method": "INJECTED_MODEL_WITH_EVIDENCE_IDS",
            "provider_errors": provider_errors,
            "promotion_eligible": False,
        }

    @classmethod
    def _extract_keywords(cls, text: str) -> list[str]:
        """Deterministically derive search terms from the hypothesis itself."""
        tokens = re.findall(r"[\w-]+", text.casefold(), flags=re.UNICODE)
        frequencies: dict[str, int] = {}
        for token in tokens:
            if len(token) < 4 or token in cls._STOPWORDS or token.isdigit():
                continue
            frequencies[token] = frequencies.get(token, 0) + 1
        return [
            token
            for token, _count in sorted(
                frequencies.items(),
                key=lambda item: (-item[1], -len(item[0]), item[0]),
            )[:8]
        ]

    @staticmethod
    def _normalize_keywords(keywords: Sequence[Any]) -> list[str]:
        normalized: list[str] = []
        for keyword in keywords:
            value = " ".join(str(keyword).strip().split())
            if value and value.casefold() not in {item.casefold() for item in normalized}:
                normalized.append(value)
        return normalized[:12]

    @staticmethod
    def _web_available(web: Any) -> bool:
        availability = getattr(web, "is_available", None)
        if not callable(availability):
            return True
        try:
            return availability() is True
        except Exception:
            return False

    @classmethod
    def _search_provider(
        cls,
        provider_name: str,
        provider: Any,
        method_name: str,
        query: str,
    ) -> dict[str, Any]:
        try:
            method = getattr(provider, method_name)
            raw_results = method(query, max_results=5)
            if not isinstance(raw_results, Sequence) or isinstance(raw_results, str):
                raise TypeError("provider result must be a sequence")
            evidence = [
                normalized
                for index, item in enumerate(raw_results, start=1)
                if (
                    normalized := cls._normalize_evidence(
                        provider_name,
                        index,
                        item,
                    )
                )
                is not None
            ]
            return {
                "provider": provider_name,
                "completed": True,
                "evidence": evidence,
                "error": None,
            }
        except ProviderError as exc:
            return {
                "provider": provider_name,
                "completed": False,
                "evidence": [],
                "error": exc.to_dict(),
            }
        except Exception as exc:
            return {
                "provider": provider_name,
                "completed": False,
                "evidence": [],
                "error": {
                    "provider": provider_name,
                    "code": "provider_invalid_result",
                    "retryable": False,
                    "cause_type": type(exc).__name__,
                },
            }

    @staticmethod
    def _normalize_evidence(
        provider_name: str,
        index: int,
        item: Any,
    ) -> dict[str, str] | None:
        if not isinstance(item, Mapping):
            return None
        title = " ".join(str(item.get("title") or "").split())
        abstract = " ".join(
            str(item.get("summary") or item.get("snippet") or "").split()
        )
        if not title and not abstract:
            return None
        raw_id = str(item.get("id") or item.get("url") or index).strip()
        source_uri = str(
            item.get("url")
            or item.get("pdf_link")
            or item.get("id")
            or ""
        ).strip()
        return {
            "evidence_id": f"{provider_name}:{raw_id}",
            "provider": provider_name,
            "title": title,
            "abstract": abstract,
            "source_uri": source_uri,
            "published": str(item.get("published") or item.get("year") or ""),
        }

    @classmethod
    def _closest_evidence(
        cls,
        hypothesis: str,
        evidence: Sequence[Mapping[str, str]],
    ) -> tuple[float, Mapping[str, str] | None]:
        hypothesis_tokens = set(cls._extract_keywords(hypothesis))
        best_score = 0.0
        closest: Mapping[str, str] | None = None
        for item in evidence:
            evidence_tokens = set(
                cls._extract_keywords(
                    f"{item.get('title', '')} {item.get('abstract', '')}"
                )
            )
            union = hypothesis_tokens | evidence_tokens
            score = (
                len(hypothesis_tokens & evidence_tokens) / len(union)
                if union
                else 0.0
            )
            if score > best_score:
                best_score = score
                closest = item
        return best_score, closest

    def _evaluate_with_model(
        self,
        hypothesis: str,
        evidence: Sequence[Mapping[str, str]],
    ) -> dict[str, Any] | None:
        compact_evidence = [
            {
                "evidence_id": item["evidence_id"],
                "title": item["title"],
                "abstract": item["abstract"][:2000],
            }
            for item in evidence
        ]
        prompt = (
            "Assess only whether the mechanism in the hypothesis appears in the "
            "supplied literature. Do not infer novelty from missing information. "
            "Return JSON only with is_novel (boolean), confidence (0..1), "
            "reasoning (string), and evidence_ids (non-empty list drawn exactly "
            "from the supplied evidence IDs).\n\n"
            f"HYPOTHESIS:\n{hypothesis}\n\nEVIDENCE:\n"
            + json.dumps(compact_evidence, ensure_ascii=False, sort_keys=True)
        )
        try:
            if hasattr(self.evaluator, "ask"):
                raw = self.evaluator.ask(
                    prompt,
                    max_tokens=1200,
                    system_instruction="Return valid JSON only.",
                )
            elif hasattr(self.evaluator, "generate_completion"):
                raw = self.evaluator.generate_completion(prompt, max_tokens=1200)
            else:
                return None
            payload = json.loads(
                str(raw).replace("```json", "").replace("```", "").strip()
            )
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("is_novel"), bool
        ):
            return None
        try:
            confidence = float(payload.get("confidence"))
        except (TypeError, ValueError):
            return None
        reasoning = str(payload.get("reasoning") or "").strip()
        evidence_ids = payload.get("evidence_ids")
        allowed_ids = {item["evidence_id"] for item in evidence}
        if (
            not 0.0 <= confidence <= 1.0
            or not reasoning
            or not isinstance(evidence_ids, list)
            or not evidence_ids
            or any(item not in allowed_ids for item in evidence_ids)
        ):
            return None
        return {
            "is_novel": payload["is_novel"],
            "confidence": round(confidence, 4),
            "reasoning": reasoning,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
        }

    @staticmethod
    def _indeterminate(
        reasoning: str,
        *,
        keywords: Sequence[str] = (),
        coverage: Mapping[str, Any] | None = None,
        evidence: Sequence[Mapping[str, Any]] = (),
        provider_errors: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        return {
            "status": "indeterminate",
            "is_novel": None,
            "confidence": 0.0,
            "reasoning": reasoning,
            "keywords": list(keywords),
            "coverage": dict(coverage or {}),
            "evidence": [dict(item) for item in evidence],
            "decision_evidence_ids": [],
            "evaluation_method": "NONE",
            "provider_errors": [dict(item) for item in provider_errors],
            "promotion_eligible": False,
        }
