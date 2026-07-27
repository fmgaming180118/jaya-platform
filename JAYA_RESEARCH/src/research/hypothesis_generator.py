"""Evidence-aware hypothesis generation for JAYA_RESEARCH.

This module creates *research proposals*, not findings. A generated hypothesis
is always marked as unverified until an empirical experiment supplies the
required provenance and reproducibility evidence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HypothesisGenerator:
    """Generate falsifiable, explicitly unverified research proposals."""

    def __init__(
        self, graph_engine: Optional[Any] = None, teacher: Optional[Any] = None
    ):
        self.graph_engine = graph_engine
        # External model clients must be injected explicitly. Importing and
        # initializing one here would hide network/configuration side effects.
        self.teacher = teacher
        self.corpus_memory: List[str] = []
        self.corpus_sources: List[str] = []

    def add_to_corpus(self, text: str, source_id: Optional[str] = None) -> str:
        """Add literature text and return its stable local evidence identifier."""
        normalized = text.strip()
        if not normalized:
            raise ValueError("Corpus text must not be empty.")

        evidence_id = source_id or (
            "inline:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        )
        if normalized not in self.corpus_memory:
            self.corpus_memory.append(normalized)
            self.corpus_sources.append(evidence_id)
        return evidence_id

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.casefold()))

    def detect_knowledge_gaps(
        self, topic: str, corpus_texts: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Identify candidate gaps without inventing missing evidence.

        Graph gaps are grounded in the supplied graph. Corpus gaps describe
        topic terms absent from the supplied corpus. If neither source exists,
        the result explicitly states that evidence is insufficient.
        """
        gaps: List[Dict[str, Any]] = []
        texts = self.corpus_memory if corpus_texts is None else corpus_texts

        if self.graph_engine and hasattr(self.graph_engine, "graph"):
            graph = self.graph_engine.graph
            nodes = list(graph.nodes())
            for index, concept_a in enumerate(nodes[:10]):
                for concept_b in nodes[index + 1 : 10]:
                    if not graph.has_edge(concept_a, concept_b) and not graph.has_edge(
                        concept_b, concept_a
                    ):
                        gaps.append(
                            {
                                "type": "missing_graph_link",
                                "concept_a": str(concept_a),
                                "concept_b": str(concept_b),
                                "description": (
                                    "No edge is present between "
                                    f"{concept_a} and {concept_b} in the supplied graph."
                                ),
                                "grounded": True,
                                "evidence_ids": [
                                    f"graph-node:{concept_a}",
                                    f"graph-node:{concept_b}",
                                ],
                            }
                        )

        if not gaps and texts:
            corpus_tokens = set().union(*(self._tokenize(text) for text in texts))
            topic_tokens = [
                token
                for token in sorted(self._tokenize(topic))
                if len(token) > 3 and token not in corpus_tokens
            ]
            if topic_tokens:
                missing_term = topic_tokens[0]
                gaps.append(
                    {
                        "type": "missing_corpus_coverage",
                        "concept_a": missing_term,
                        "concept_b": "preregistered primary outcome",
                        "description": (
                            f"The term '{missing_term}' is absent from the supplied "
                            "corpus; additional literature review is required."
                        ),
                        "grounded": True,
                        "evidence_ids": list(self.corpus_sources),
                    }
                )

        if not gaps:
            gaps.append(
                {
                    "type": "insufficient_evidence",
                    "concept_a": topic.strip() or "the proposed intervention",
                    "concept_b": "preregistered primary outcome",
                    "description": (
                        "No graph or literature evidence was supplied; this is only "
                        "a question seed and cannot be treated as a knowledge gap."
                    ),
                    "grounded": False,
                    "evidence_ids": [],
                }
            )

        return gaps

    def compute_novelty_score(
        self, statement: str, corpus_texts: Optional[List[str]] = None
    ) -> float:
        """Return Jaccard dissimilarity, or ``0.0`` when it cannot be assessed."""
        texts = self.corpus_memory if corpus_texts is None else corpus_texts
        if not texts:
            return 0.0

        statement_tokens = self._tokenize(statement)
        if not statement_tokens:
            return 0.0

        similarities: List[float] = []
        for text in texts:
            corpus_tokens = self._tokenize(text)
            if not corpus_tokens:
                continue
            union = statement_tokens | corpus_tokens
            similarities.append(
                len(statement_tokens & corpus_tokens) / len(union) if union else 0.0
            )

        if not similarities:
            return 0.0
        return round(max(0.0, min(1.0, 1.0 - max(similarities))), 4)

    @staticmethod
    def _as_string_list(value: Any, fallback: List[str]) -> List[str]:
        if not isinstance(value, list):
            return fallback
        cleaned = [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]
        return cleaned or fallback

    def generate_hypothesis(
        self,
        topic: str,
        context: Optional[str] = None,
        gap_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a structured proposal with explicit evidence limitations."""
        topic = topic.strip()
        if not topic:
            raise ValueError("A research topic is required.")
        if context:
            self.add_to_corpus(context)

        selected_gap = gap_info or self.detect_knowledge_gaps(topic)[0]
        concept_a = str(selected_gap.get("concept_a") or topic)
        concept_b = str(
            selected_gap.get("concept_b") or "preregistered primary outcome"
        )

        statement = ""
        independent_variables = [concept_a]
        dependent_variables = [concept_b]
        control_variables = ["preregistered baseline condition"]
        predicted_relationship = (
            f"A measurable difference in {concept_b} after changing {concept_a}."
        )
        falsifiability = (
            "Reject the hypothesis when the preregistered primary outcome does not "
            "meet its preregistered effect threshold or quality checks."
        )
        model_generated = False

        if self.teacher and hasattr(self.teacher, "ask"):
            prompt = (
                "Create one falsifiable research proposal. Do not invent citations, "
                "measurements, percentages, p-values, or prior results. Respond as "
                "JSON with statement, independent_variables, dependent_variables, "
                "control_variables, predicted_relationship, and "
                f"falsifiability_criteria. Topic: {topic}. Candidate gap: "
                f"{selected_gap.get('description', '')}"
            )
            try:
                raw_response = self.teacher.ask(
                    prompt,
                    max_tokens=1024,
                    system_instruction="Output valid JSON only.",
                )
                parsed = json.loads(
                    raw_response.replace("```json", "").replace("```", "").strip()
                )
                candidate_statement = parsed.get("statement")
                if isinstance(candidate_statement, str) and candidate_statement.strip():
                    statement = candidate_statement.strip()
                    independent_variables = self._as_string_list(
                        parsed.get("independent_variables"), independent_variables
                    )
                    dependent_variables = self._as_string_list(
                        parsed.get("dependent_variables"), dependent_variables
                    )
                    control_variables = self._as_string_list(
                        parsed.get("control_variables"), control_variables
                    )
                    predicted_relationship = str(
                        parsed.get("predicted_relationship") or predicted_relationship
                    )
                    falsifiability = str(
                        parsed.get("falsifiability_criteria") or falsifiability
                    )
                    model_generated = True
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Injected hypothesis model returned unusable output: %s", exc
                )

        if not statement:
            statement = (
                f"Under a preregistered comparison for {topic}, changing {concept_a} "
                f"will produce a measurable difference in {concept_b} relative to "
                "an unchanged baseline."
            )

        novelty_score = self.compute_novelty_score(statement)
        grounded = bool(selected_gap.get("grounded", False))
        now = datetime.now(timezone.utc)
        return {
            "hypothesis_id": f"HYP-{now:%Y%m%d}-{uuid.uuid4().hex[:12]}",
            "topic": topic,
            "statement": statement,
            "variables": {
                "independent": independent_variables,
                "dependent": dependent_variables,
                "control": control_variables,
            },
            "predicted_relationship": predicted_relationship,
            "domain": topic,
            "knowledge_gap": selected_gap.get("description", ""),
            "novelty_score": novelty_score,
            "novelty_status": "CALCULATED" if self.corpus_memory else "NOT_EVALUATED",
            "falsifiability_criteria": falsifiability,
            "timestamp": now.isoformat(),
            "llm_generated": model_generated,
            "evidence_kind": "UNVERIFIED",
            "grounding_status": "GROUNDED_PROPOSAL" if grounded else "UNGROUNDED_SEED",
            "evidence_ids": list(selected_gap.get("evidence_ids", [])),
            "promotion_eligible": False,
        }
