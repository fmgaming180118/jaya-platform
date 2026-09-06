"""
Citation Graph
Maps paper → references relationships so that previously extracted
journals can be reused without re-downloading.

Stored at: data/citation_graph.json
"""
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from jaya_research.config import config

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False
    print("[CitationGraph] networkx not available — graph features disabled.")


CITATION_GRAPH_PATH = Path(config.DATA_DIR) / "citation_graph.json"


class CitationGraph:
    """
    Directed graph: Paper → References it cites.

    Node attributes:
        title, source, year, rank_score, insight_excerpt,
        pdf_link, local_path, fetched_at, language

    Edge attributes:
        relation = "cites"
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = Path(storage_path) if storage_path else CITATION_GRAPH_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if NX_AVAILABLE:
            self.graph = nx.DiGraph()
            self._load()
        else:
            self.graph = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.graph = nx.node_link_graph(data)
                print(f"[CitationGraph] Loaded {self.graph.number_of_nodes()} papers, "
                      f"{self.graph.number_of_edges()} citation edges.")
            except Exception as e:
                print(f"[CitationGraph] Load error: {e} — starting fresh.")
                self.graph = nx.DiGraph()

    def save(self):
        if not NX_AVAILABLE or self.graph is None:
            return
        data = nx.node_link_data(self.graph)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[CitationGraph] Saved {self.graph.number_of_nodes()} nodes.")

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def _normalize_title(self, title: str) -> str:
        """Normalize title to use as graph node ID."""
        return title.strip().lower()[:120]

    def add_paper(
        self,
        paper_meta: Dict[str, Any],
        references: List[Dict[str, Any]],
    ):
        """
        Add a paper and its references to the graph.

        Args:
            paper_meta: dict with keys: title, source, year, rank_score,
                        insight_excerpt, pdf_link, local_path, language
            references: list of dicts with keys: title, year, authors
        """
        if not NX_AVAILABLE or self.graph is None:
            return

        title = paper_meta.get("title", "Unknown")
        node_id = self._normalize_title(title)

        self.graph.add_node(
            node_id,
            title=title,
            source=paper_meta.get("source", "Unknown"),
            year=str(paper_meta.get("year") or paper_meta.get("published", "")),
            rank_score=float(paper_meta.get("rank_score", 0.0)),
            insight_excerpt=paper_meta.get("insight_excerpt", "")[:500],
            pdf_link=paper_meta.get("pdf_link", ""),
            local_path=paper_meta.get("local_path", ""),
            language=paper_meta.get("language", "en"),
            fetched_at=paper_meta.get("fetched_at", time.time()),
            node_type="paper",
        )

        for ref in references:
            ref_title = ref.get("title", "").strip()
            if not ref_title:
                continue
            ref_id = self._normalize_title(ref_title)

            # Add reference node if not present
            if not self.graph.has_node(ref_id):
                self.graph.add_node(
                    ref_id,
                    title=ref_title,
                    source="reference",
                    year=str(ref.get("year", "")),
                    rank_score=0.0,
                    insight_excerpt="",
                    pdf_link="",
                    local_path="",
                    language="",
                    fetched_at=0,
                    node_type="reference",
                )

            self.graph.add_edge(node_id, ref_id, relation="cites")

        self.save()

    # ------------------------------------------------------------------
    # Query / Search
    # ------------------------------------------------------------------

    def search_by_query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search cached papers by keyword overlap.
        Returns only nodes that are fully processed papers (node_type='paper').
        """
        if not NX_AVAILABLE or self.graph is None:
            return []

        query_terms = [t for t in query.lower().split() if len(t) > 2]
        results = []

        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") != "paper":
                continue
            title = (attrs.get("title") or "").lower()
            excerpt = (attrs.get("insight_excerpt") or "").lower()
            overlap = sum(1 for t in query_terms if t in title or t in excerpt)
            if overlap > 0:
                results.append({**attrs, "node_id": node_id, "_score": overlap})

        results.sort(key=lambda x: (x["_score"], x.get("rank_score", 0)), reverse=True)
        return results[:top_k]

    def get_citation_tree(
        self, paper_title: str, max_hops: int = 2
    ) -> Dict[str, Any]:
        """
        Returns subgraph of a paper and its citation chain (up to max_hops).
        Output: { nodes: [...], edges: [...] }
        """
        if not NX_AVAILABLE or self.graph is None:
            return {"nodes": [], "edges": []}

        start = self._normalize_title(paper_title)
        if not self.graph.has_node(start):
            return {"nodes": [], "edges": []}

        # BFS
        visited = {start}
        frontier = {start}
        for _ in range(max_hops):
            next_frontier = set()
            for n in frontier:
                next_frontier.update(self.graph.successors(n))
            next_frontier -= visited
            visited.update(next_frontier)
            frontier = next_frontier

        subgraph = self.graph.subgraph(visited)
        return self._to_react_flow(subgraph)

    def list_all_papers(self) -> List[Dict[str, Any]]:
        """Returns all fully-processed paper nodes."""
        if not NX_AVAILABLE or self.graph is None:
            return []
        results = []
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") == "paper":
                results.append({**attrs, "node_id": node_id})
        results.sort(key=lambda x: x.get("fetched_at", 0), reverse=True)
        return results

    # ------------------------------------------------------------------
    # Visualisation Export
    # ------------------------------------------------------------------

    def _to_react_flow(self, g) -> Dict[str, Any]:
        """Convert networkx graph to React Flow compatible format."""
        nodes = []
        edges = []

        source_colors = {
            "arxiv": "#3b82f6",
            "semantic scholar": "#8b5cf6",
            "openalex": "#10b981",
            "crossref indonesia": "#f59e0b",
            "garuda": "#22d3ee",
            "reference": "#374151",
            "unknown": "#6b7280",
        }

        for node_id, attrs in g.nodes(data=True):
            node_type = attrs.get("node_type", "reference")
            source_key = (attrs.get("source") or "").lower()
            if node_type == "reference":
                bg = "#374151"
            else:
                bg = source_colors.get(source_key, "#6b7280")

            nodes.append({
                "id": node_id,
                "data": {
                    "label": (attrs.get("title") or node_id)[:60],
                    "full_title": attrs.get("title", ""),
                    "source": attrs.get("source", ""),
                    "year": attrs.get("year", ""),
                    "insight_excerpt": attrs.get("insight_excerpt", ""),
                    "pdf_link": attrs.get("pdf_link", ""),
                    "local_path": attrs.get("local_path", ""),
                    "language": attrs.get("language", ""),
                    "node_type": node_type,
                    "rank_score": attrs.get("rank_score", 0),
                },
                "style": {"background": bg},
            })

        for u, v, edata in g.edges(data=True):
            edges.append({
                "id": f"{u}to{v}",
                "source": u,
                "target": v,
                "label": edata.get("relation", "cites"),
            })

        return {"nodes": nodes, "edges": edges}

    def get_viz_data(self) -> Dict[str, Any]:
        """Export full graph for React Flow."""
        if not NX_AVAILABLE or self.graph is None:
            return {"nodes": [], "edges": []}
        return self._to_react_flow(self.graph)

    def get_stats(self) -> Dict[str, Any]:
        if not NX_AVAILABLE or self.graph is None:
            return {"papers": 0, "references": 0, "edges": 0}
        papers = sum(1 for _, d in self.graph.nodes(data=True) if d.get("node_type") == "paper")
        refs = self.graph.number_of_nodes() - papers
        return {
            "papers": papers,
            "references": refs,
            "edges": self.graph.number_of_edges(),
        }


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------
_instance: Optional[CitationGraph] = None


def get_citation_graph() -> CitationGraph:
    global _instance
    if _instance is None:
        _instance = CitationGraph()
    return _instance
