"""Persistent knowledge graph with an explicitly injected extraction provider."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import networkx as nx

from config import config
from provider_errors import ProviderError, ProviderInvalidResponseError


class GraphRAGExtractionError(RuntimeError):
    """Raised when graph extraction cannot produce validated triples."""


class GraphRAGEngine:
    """Store graph triples without initializing a provider during startup."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
        *,
        teacher: Any | None = None,
    ) -> None:
        self.storage_path = Path(
            storage_path or config.KNOWLEDGE_GRAPH_PATH
        ).resolve()
        self.graph = nx.DiGraph()
        self.teacher = teacher
        self._load_graph()

    def _load_graph(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            loaded = nx.node_link_graph(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise GraphRAGExtractionError(
                f"Knowledge graph could not be loaded: {type(exc).__name__}"
            ) from exc
        if not isinstance(loaded, nx.DiGraph):
            loaded = nx.DiGraph(loaded)
        self.graph = loaded

    def save_graph(self) -> None:
        """Persist atomically so interrupted writes cannot corrupt the graph."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = nx.node_link_data(self.graph)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.storage_path.name}.",
            suffix=".tmp",
            dir=self.storage_path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.storage_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def extract_triples(self, text: str) -> list[tuple[str, str, str]]:
        """Extract and validate triples, or raise a typed failure."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Graph extraction text must not be empty")
        if self.teacher is None:
            raise GraphRAGExtractionError(
                "Graph extraction provider is not configured"
            )
        prompt = (
            "Extract knowledge triples as a JSON list of three-string lists. "
            "Output JSON only and do not add facts absent from the text.\n\n"
            f"Text:\n{text[:2000]}"
        )
        try:
            response = self.teacher.ask(
                prompt,
                system_instruction=(
                    "You are an extractive knowledge graph parser. "
                    "Output raw JSON only."
                ),
            )
            raw_triples = json.loads(
                response.replace("```json", "").replace("```", "").strip()
            )
        except ProviderError:
            raise
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderInvalidResponseError(
                "graph_extraction",
                "Provider returned malformed graph triples",
                cause_type=type(exc).__name__,
            ) from exc
        if not isinstance(raw_triples, list):
            raise ProviderInvalidResponseError(
                "graph_extraction",
                "Graph triples must be a JSON list",
            )

        triples: list[tuple[str, str, str]] = []
        for item in raw_triples:
            if (
                not isinstance(item, list)
                or len(item) != 3
                or any(not isinstance(value, str) or not value.strip() for value in item)
            ):
                raise ProviderInvalidResponseError(
                    "graph_extraction",
                    "Each graph triple must contain three non-empty strings",
                )
            triples.append(tuple(value.strip() for value in item))
        return triples

    def ingest_document(self, text: str, source_id: str) -> int:
        """Extract triples and persist them with explicit source provenance."""
        normalized_source = str(source_id or "").strip()
        if not normalized_source:
            raise ValueError("source_id is required")
        triples = self.extract_triples(text)
        for subject, predicate, object_value in triples:
            self.graph.add_node(subject, type="concept")
            self.graph.add_node(object_value, type="concept")
            self.graph.add_edge(
                subject,
                object_value,
                relation=predicate,
                source_id=normalized_source,
            )
        self.save_graph()
        return len(triples)

    def get_context(self, query: str, max_hops: int = 1) -> str:
        if max_hops < 0 or max_hops > 5:
            raise ValueError("max_hops must be between 0 and 5")
        query_terms = str(query or "").casefold().split()
        if not query_terms:
            return ""
        relevant_nodes = [
            node
            for node in self.graph.nodes()
            if any(term in str(node).casefold() for term in query_terms)
        ]
        subgraph_nodes = set(relevant_nodes)
        frontier = set(relevant_nodes)
        for _ in range(max_hops):
            next_frontier: set[Any] = set()
            for node in frontier:
                next_frontier.update(self.graph.successors(node))
                next_frontier.update(self.graph.predecessors(node))
            next_frontier.difference_update(subgraph_nodes)
            subgraph_nodes.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        subgraph = self.graph.subgraph(subgraph_nodes)
        return "\n".join(
            f"{source} --[{data.get('relation', 'related_to')}]--> {target}"
            for source, target, data in subgraph.edges(data=True)
        )

    def get_viz_data(self) -> dict[str, Any]:
        return nx.node_link_data(self.graph)

