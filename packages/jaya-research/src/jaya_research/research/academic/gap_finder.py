"""Citation-graph gap candidates with traceable evidence.

A disconnected graph is a search observation, not proof of a scientific gap.
This module therefore emits review candidates tied to exact paper IDs and never
labels model-generated prose as a verified or novel finding.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import networkx as nx

from jaya_research.research.academic.literature import SemanticScholarClient


class GapFinder:
    """Build a bounded citation graph and identify review candidates."""

    def __init__(
        self,
        *,
        scholar: Any | None = None,
        max_seed_papers: int = 5,
        max_citations_per_seed: int = 5,
    ) -> None:
        if not 1 <= max_seed_papers <= 50:
            raise ValueError("max_seed_papers must be between 1 and 50")
        if not 1 <= max_citations_per_seed <= 100:
            raise ValueError("max_citations_per_seed must be between 1 and 100")
        self.scholar = scholar if scholar is not None else SemanticScholarClient()
        self.max_seed_papers = max_seed_papers
        self.max_citations_per_seed = max_citations_per_seed
        self.graph = nx.DiGraph()
        self.topic = ""
        self.search_completed = False

    def build_network(self, topic: str, depth: int = 1) -> nx.DiGraph:
        """Build a fresh graph from real provider records.

        ``depth`` is intentionally limited to zero or one.  Recursive provider
        crawling belongs to a budgeted job, not a request-scoped Phase A helper.
        """
        normalized_topic = " ".join(topic.split())
        if not normalized_topic:
            raise ValueError("topic must not be empty")
        if depth not in {0, 1}:
            raise ValueError("depth must be 0 or 1")

        self.graph.clear()
        self.topic = normalized_topic
        self.search_completed = False
        seeds = self.scholar.search_papers(
            normalized_topic,
            max_results=self.max_seed_papers,
        )
        if not isinstance(seeds, Sequence) or isinstance(seeds, str):
            raise TypeError("Semantic Scholar results must be a sequence")

        normalized_seeds: list[dict[str, str]] = []
        for paper in seeds:
            normalized = self._normalize_paper(paper, paper_type="seed")
            if normalized is None:
                continue
            normalized_seeds.append(normalized)
            self.graph.add_node(normalized["evidence_id"], **normalized)

        if depth == 1:
            for seed in normalized_seeds:
                citations = self.scholar.get_citations(
                    seed["provider_id"],
                    limit=self.max_citations_per_seed,
                )
                if not isinstance(citations, Sequence) or isinstance(citations, str):
                    raise TypeError("Citation results must be a sequence")
                for citation in citations:
                    normalized = self._normalize_paper(
                        citation,
                        paper_type="citation",
                    )
                    if normalized is None:
                        continue
                    self.graph.add_node(normalized["evidence_id"], **normalized)
                    self.graph.add_edge(
                        normalized["evidence_id"],
                        seed["evidence_id"],
                        relation="CITES",
                    )

        self.search_completed = True
        return self.graph

    def analyze_gaps_structured(self, *, max_candidates: int = 3) -> dict[str, Any]:
        """Return observed clusters and unverified structural-hole candidates."""
        if not 1 <= max_candidates <= 20:
            raise ValueError("max_candidates must be between 1 and 20")
        if not self.search_completed:
            return {
                "status": "SEARCH_NOT_RUN",
                "topic": self.topic,
                "graph": {"nodes": 0, "edges": 0},
                "clusters": [],
                "candidates": [],
                "verified_gap": False,
                "promotion_eligible": False,
            }
        if self.graph.number_of_nodes() == 0:
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "topic": self.topic,
                "graph": {"nodes": 0, "edges": 0},
                "clusters": [],
                "candidates": [],
                "verified_gap": False,
                "promotion_eligible": False,
            }

        components = sorted(
            nx.weakly_connected_components(self.graph),
            key=lambda component: (-len(component), sorted(component)[0]),
        )
        clusters = [
            self._cluster_payload(index, component)
            for index, component in enumerate(components, start=1)
        ]
        candidates: list[dict[str, Any]] = []
        for left_index, left in enumerate(clusters):
            for right in clusters[left_index + 1 :]:
                evidence_ids = list(
                    dict.fromkeys(left["evidence_ids"] + right["evidence_ids"])
                )
                candidates.append(
                    {
                        "candidate_id": f"GAP-CANDIDATE-{len(candidates) + 1}",
                        "status": "CANDIDATE_REQUIRES_REVIEW",
                        "cluster_ids": [left["cluster_id"], right["cluster_id"]],
                        "evidence_ids": evidence_ids,
                        "observation": (
                            "No citation path was observed between these clusters "
                            "within the bounded provider result set."
                        ),
                        "limitations": (
                            "Search coverage, indexing gaps, terminology differences, "
                            "and citation delay may explain the disconnection."
                        ),
                        "next_step": (
                            "Broaden the preregistered search and obtain domain-expert "
                            "review before treating this as a research gap."
                        ),
                    }
                )
                if len(candidates) >= max_candidates:
                    break
            if len(candidates) >= max_candidates:
                break

        return {
            "status": (
                "CANDIDATES_REQUIRE_REVIEW"
                if candidates
                else "NO_STRUCTURAL_HOLE_OBSERVED"
            ),
            "topic": self.topic,
            "graph": {
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
            },
            "clusters": clusters,
            "candidates": candidates,
            "verified_gap": False,
            "promotion_eligible": False,
        }

    def analyze_gaps(self) -> str:
        """Compatibility Markdown view of :meth:`analyze_gaps_structured`."""
        result = self.analyze_gaps_structured()
        lines = [
            "## Research Gap Screening",
            "",
            f"**Status:** {result['status']}",
            f"**Topic:** {result['topic'] or 'not supplied'}",
            (
                f"**Graph:** {result['graph']['nodes']} papers, "
                f"{result['graph']['edges']} citation edges"
            ),
            "",
        ]
        if not result["candidates"]:
            lines.append(
                "No structural-hole candidate can be supported by the current "
                "bounded evidence set."
            )
            return "\n".join(lines)

        lines.extend(
            [
                "The following items are search observations, not verified or novel gaps:",
                "",
            ]
        )
        for candidate in result["candidates"]:
            lines.extend(
                [
                    f"### {candidate['candidate_id']}",
                    candidate["observation"],
                    f"- Evidence IDs: {', '.join(candidate['evidence_ids'])}",
                    f"- Limitation: {candidate['limitations']}",
                    f"- Next step: {candidate['next_step']}",
                    "",
                ]
            )
        return "\n".join(lines).rstrip()

    def _cluster_payload(
        self,
        index: int,
        component: set[str],
    ) -> dict[str, Any]:
        evidence_ids = sorted(component)
        return {
            "cluster_id": f"CLUSTER-{index}",
            "evidence_ids": evidence_ids,
            "titles": [
                str(self.graph.nodes[evidence_id].get("title") or "Untitled")
                for evidence_id in evidence_ids
            ],
        }

    @staticmethod
    def _normalize_paper(
        paper: Any,
        *,
        paper_type: str,
    ) -> dict[str, str] | None:
        if not isinstance(paper, Mapping):
            return None
        provider_id = str(paper.get("id") or "").strip()
        title = " ".join(str(paper.get("title") or "").split())
        if not provider_id or not title:
            return None
        source_uri = str(
            paper.get("url")
            or paper.get("pdf_link")
            or paper.get("landing_page_url")
            or ""
        ).strip()
        return {
            "evidence_id": f"semantic_scholar:{provider_id}",
            "provider_id": provider_id,
            "title": title,
            "paper_type": paper_type,
            "year": str(paper.get("year") or paper.get("published") or ""),
            "source_uri": source_uri,
            "provider": "semantic_scholar",
        }
