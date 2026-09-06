import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber
from jaya_research.config import config
from jaya_research.research.academic.citation_graph import get_citation_graph
from jaya_research.research.academic.indonesia_sources import (
    CrossrefIndonesiaClient,
    GarudaClient,
)
from jaya_research.research.academic.literature import (
    ArxivClient,
    OpenAlexClient,
    SemanticScholarClient,
)
from jaya_research.research.config import get_config
from jaya_research.teacher import Teacher

from jaya_research.provider_errors import ProviderError, ProviderInvalidResponseError


class PaperCache:
    """
    Persistent index of already-processed papers.
    Stored as JSON at data/papers_cache/index.json.
    Key: normalised title  (lowercase, stripped)
    Value: full metadata + local paths
    """

    INDEX_PATH = Path(config.PAPERS_TEMP_DIR) / "index.json"

    def __init__(self):
        self.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.INDEX_PATH.exists():
            try:
                with open(self.INDEX_PATH, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                print(f"[PaperCache] Loaded {len(self._index)} cached papers.")
            except Exception as e:
                print(f"[PaperCache] Load error: {e}")
                self._index = {}

    def _save(self):
        with open(self.INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _key(title: str) -> str:
        # Use full title with hash to avoid collisions
        import hashlib

        normalized = title.strip().lower()
        # Use first 200 chars + hash for uniqueness
        title_part = normalized[:200]
        hash_part = hashlib.md5(normalized.encode()).hexdigest()[:8]
        return f"{title_part}_{hash_part}"

    def has(self, title: str) -> bool:
        return self._key(title) in self._index

    def get(self, title: str) -> Optional[Dict[str, Any]]:
        entry = self._index.get(self._key(title))
        if not entry:
            return None
        # Check local file still exists
        local_path = entry.get("local_path", "")
        if local_path and not Path(local_path).exists():
            print(f"[PaperCache] File missing for '{title}', removing from cache.")
            del self._index[self._key(title)]
            self._save()
            return None
        return entry

    def put(
        self,
        paper_meta: Dict[str, Any],
        insight: str,
        local_path: str,
        references: List[Dict[str, Any]],
    ):
        title = paper_meta.get("title", "")
        if not title:
            return
        self._index[self._key(title)] = {
            "title": title,
            "source": paper_meta.get("source", ""),
            "year": str(paper_meta.get("published", "")),
            "rank_score": paper_meta.get("rank_score", 0.0),
            "insight_excerpt": insight[:500],
            "pdf_link": paper_meta.get("pdf_link")
            or paper_meta.get("landing_page_url")
            or "",
            "local_path": local_path,
            "language": paper_meta.get("language", "en"),
            "references": references,
            "fetched_at": time.time(),
        }
        self._save()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Quick keyword search over cached index with improved scoring."""
        terms = [t for t in query.lower().split() if len(t) > 2]
        results = []
        for entry in self._index.values():
            title_lc = entry.get("title", "").lower()
            excerpt_lc = entry.get("insight_excerpt", "").lower()
            source_lc = entry.get("source", "").lower()

            # Score based on term frequency in title, excerpt, and source
            title_score = sum(3 for t in terms if t in title_lc)
            excerpt_score = sum(1 for t in terms if t in excerpt_lc)
            source_score = sum(2 for t in terms if t in source_lc)

            total_score = title_score + excerpt_score + source_score

            if total_score > 0:
                results.append({**entry, "_cache_score": total_score})

        # Sort by score, then by rank_score
        results.sort(
            key=lambda x: (x["_cache_score"], x.get("rank_score", 0)), reverse=True
        )
        return results[:top_k]

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._index.values())


class JournalProcessor:
    """
    Orchestrates academic search, download, and processing for Research Chat.
    Supports:
      - Paper cache: already-downloaded PDFs are reused, not re-downloaded
      - Indonesia sources: CrossrefIndonesia + GARUDA
      - Citation graph: automatically records paper → references relationships
    """

    def __init__(self, download_dir: str = config.PAPERS_TEMP_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self.arxiv = ArxivClient()
        self.scholar = SemanticScholarClient()
        self.openalex = OpenAlexClient()
        self.crossref_id = CrossrefIndonesiaClient()
        self.garuda = GarudaClient()
        self.teacher = Teacher(model_type="reasoning")
        self.config = get_config()
        self.cache = PaperCache()
        self.citation_graph = get_citation_graph()
        self.last_provider_errors: List[ProviderError] = []
        self.last_completed_providers = 0

    def process_query(self, query: str, max_papers: int = 1) -> Dict[str, Any]:
        """
        End-to-end processing: Cache Check -> Search -> Download -> Extract -> Summarize
        Papers already in cache are served immediately without re-downloading.

        Args:
            query: User's research topic
            max_papers: Number of papers to fully process (keep low for latency)

        Returns:
            Dict containing synthesis and source metadata
        """
        print(f"[JournalProcessor] Processing: {query}")

        # 0. Check cache first — return cached papers if relevant
        cached_hits = self.cache.search(query, top_k=max_papers)
        if cached_hits:
            hit_count = len(cached_hits)
            print(
                f"[JournalProcessor] Cache hit: {hit_count} paper(s); "
                "skipping download."
            )
            processed_data = []
            for entry in cached_hits:
                insight = entry.get("insight_excerpt", "")
                paper_meta = {
                    "title": entry["title"],
                    "source": entry.get("source", ""),
                    "published": entry.get("year", ""),
                    "rank_score": entry.get("rank_score", 0.0),
                    "pdf_link": entry.get("pdf_link", ""),
                    "language": entry.get("language", "en"),
                }
                processed_data.append(
                    {
                        "metadata": paper_meta,
                        "insight": insight,
                        "summary": self._build_paper_summary(paper_meta, insight),
                        "compact_summary": self._build_compact_summary(
                            paper_meta, insight
                        ),
                        "local_path": entry.get("local_path", ""),
                        "from_cache": True,
                        "source_meta": {
                            "title": entry["title"],
                            "source": entry.get("source", ""),
                            "rank_score": entry.get("rank_score", 0.0),
                            "pdf_link": entry.get("pdf_link", ""),
                            "language": entry.get("language", "en"),
                        },
                    }
                )
            return {"status": "success", "papers": processed_data, "from_cache": True}

        # 1. Search across all sources
        papers = self._search_free_sources(query, max_papers=max_papers)
        if not papers:
            if self.last_provider_errors:
                return {
                    "status": (
                        "partial" if self.last_completed_providers else "provider_error"
                    ),
                    "message": (
                        "No reliable papers were found while one or more "
                        "academic providers were unavailable."
                    ),
                    "provider_errors": [
                        error.to_dict() for error in self.last_provider_errors
                    ],
                }
            return {
                "status": "empty",
                "message": "No papers found.",
                "provider_errors": [],
            }

        papers = self._rank_papers(query, papers)

        processed_data = []

        # 2. Process each paper
        for paper in papers:
            title = paper.get("title", "")

            # 2a. Check if this specific paper is already cached by title
            cached = self.cache.get(title) if title else None
            if cached:
                print(
                    f"[JournalProcessor] Paper cached: '{title}' — skipping download."
                )
                insight = cached.get("insight_excerpt", "")
                processed_data.append(
                    {
                        "metadata": paper,
                        "insight": insight,
                        "summary": self._build_paper_summary(paper, insight),
                        "compact_summary": self._build_compact_summary(paper, insight),
                        "local_path": cached.get("local_path", ""),
                        "from_cache": True,
                        "source_meta": {
                            "title": title,
                            "source": paper.get("source", ""),
                            "rank_score": paper.get("rank_score", 0.0),
                            "pdf_link": paper.get("pdf_link") or "",
                            "language": paper.get("language", "en"),
                        },
                    }
                )
                continue

            pdf_link = paper.get("pdf_link")
            if not pdf_link:
                continue

            # 2b. Download
            pdf_path = self.arxiv.download_paper(pdf_link, self.download_dir)
            if not pdf_path:
                continue

            # 2c. Extract Text
            text_content = self._extract_text_from_pdf(pdf_path)
            if not text_content:
                continue

            # Save raw text
            txt_path = pdf_path.with_suffix(".txt")
            with open(txt_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(text_content)

            # 2d. Extract insight
            insight = self._analyze_content(text_content, query)

            # 2e. Extract references from the paper text
            references = self._extract_references(text_content, title)

            # 2f. Save to cache + citation graph
            self.cache.put(paper, insight, str(pdf_path), references)
            self.citation_graph.add_paper(
                paper_meta={
                    **paper,
                    "insight_excerpt": insight[:500],
                    "local_path": str(pdf_path),
                    "fetched_at": time.time(),
                },
                references=references,
            )

            processed_data.append(
                {
                    "metadata": paper,
                    "insight": insight,
                    "summary": self._build_paper_summary(paper, insight),
                    "compact_summary": self._build_compact_summary(paper, insight),
                    "local_path": str(pdf_path),
                    "from_cache": False,
                    "references": references,
                    "source_meta": {
                        "title": paper.get("title", "Unknown Title"),
                        "source": paper.get("source", "Unknown Source"),
                        "rank_score": paper.get("rank_score", 0.0),
                        "pdf_link": paper.get("pdf_link")
                        or paper.get("landing_page_url")
                        or "",
                        "language": paper.get("language", "en"),
                    },
                }
            )

        # 3. Synthesize
        if not processed_data:
            return {"status": "error", "message": "Failed to process papers."}

        return {
            "status": "success",
            "papers": processed_data,
            "from_cache": False,
            "provider_errors": [error.to_dict() for error in self.last_provider_errors],
        }

    def _rank_papers(
        self, query: str, papers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rank papers by relevance using improved scoring."""
        query_terms = [t for t in query.lower().split() if len(t) > 2]
        query_lower = query.lower()

        def score(paper: Dict[str, Any]) -> float:
            title = (paper.get("title") or "").lower()
            summary = (paper.get("summary") or "").lower()
            source = (paper.get("source") or "").lower()

            # Source quality bonus
            source_bonus = 0.0
            if paper.get("source") == "ArXiv":
                source_bonus += 0.15
            elif paper.get("source") == "OpenAlex":
                source_bonus += 0.12
            elif paper.get("source") == "Semantic Scholar":
                source_bonus += 0.10
            elif paper.get("source") == "Crossref Indonesia":
                source_bonus += 0.08
            elif paper.get("source") == "GARUDA":
                source_bonus += 0.05

            # Title overlap (highest weight)
            title_overlap = sum(3 for term in query_terms if term in title)

            # Summary overlap
            summary_overlap = sum(1 for term in query_terms if term in summary)

            # Source overlap
            source_overlap = sum(2 for term in query_terms if term in source)

            # Exact phrase bonus
            phrase_bonus = 0.0
            if query_lower in title:
                phrase_bonus += 0.5
            elif query_lower in summary:
                phrase_bonus += 0.3

            # Length bonus (prefer papers with more content)
            length_bonus = min(len(summary) / 10000.0, 0.2)

            # Recency bonus (prefer newer papers)
            year_str = str(paper.get("published", ""))
            recency_bonus = 0.0
            try:
                year = int(year_str[:4])
                if year >= 2023:
                    recency_bonus = 0.15
                elif year >= 2020:
                    recency_bonus = 0.10
                elif year >= 2015:
                    recency_bonus = 0.05
            except (TypeError, ValueError):
                pass

            return (
                float(title_overlap + summary_overlap + source_overlap)
                + source_bonus
                + phrase_bonus
                + length_bonus
                + recency_bonus
            )

        ranked = sorted(papers, key=score, reverse=True)
        for item in ranked:
            item["rank_score"] = score(item)
        return ranked

    def _build_paper_summary(self, paper: Dict[str, Any], insight: str) -> str:
        title = paper.get("title", "Unknown Title")
        source = paper.get("source", "Unknown Source")
        year = paper.get("published", "")
        pdf_link = paper.get("pdf_link") or paper.get("landing_page_url") or ""
        lines = [
            f"Title: {title}",
            f"Source: {source}",
        ]
        if year:
            lines.append(f"Year: {year}")
        if pdf_link:
            lines.append(f"Link: {pdf_link}")
        if insight:
            lines.append("Insight:")
            lines.append(insight[:1200])
        return "\n".join(lines)

    def _build_compact_summary(
        self, paper: Dict[str, Any], insight: str
    ) -> Dict[str, Any]:
        return {
            "title": paper.get("title", "Unknown Title"),
            "source": paper.get("source", "Unknown Source"),
            "year": paper.get("published", ""),
            "rank_score": paper.get("rank_score", 0.0),
            "insight_excerpt": insight[:400],
            "link": paper.get("pdf_link") or paper.get("landing_page_url") or "",
        }

    def _search_free_sources(
        self, query: str, max_papers: int = 1
    ) -> List[Dict[str, Any]]:
        """Search all academic sources and deduplicate their results."""
        combined: List[Dict[str, Any]] = []
        seen_titles = set()
        self.last_provider_errors = []
        self.last_completed_providers = 0

        sources = [
            ("arxiv", self.arxiv.search_papers),
            ("semantic_scholar", self.scholar.search_papers),
            ("openalex", self.openalex.search_papers),
            ("crossref", self.crossref_id.search_papers),
            ("garuda", self.garuda.search_papers),
        ]

        for provider_name, search in sources:
            try:
                source_results = search(query, max_results=max_papers)
                self.last_completed_providers += 1
            except ProviderError as error:
                self.last_provider_errors.append(error)
                print(f"[JournalProcessor] {provider_name} unavailable: {error.code}")
                continue
            for paper in source_results:
                title = (paper.get("title") or "").strip().lower()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                combined.append(paper)

        return combined[: max_papers * 5]  # wider pool due to 5 sources

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extracts text using pdfplumber for better quality"""
        try:
            full_text = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if text:
                        full_text.append(text)

                    # Also extract tables
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if row:
                                full_text.append(" | ".join(str(c or "") for c in row))

            return "\n".join(full_text)
        except Exception as e:
            print(f"[JournalProcessor] Extraction error for {pdf_path}: {e}")
            return ""

    def _analyze_content(self, text: str, query: str) -> str:
        """Uses LLM to extract key insights relevant to the query."""
        # Use more text for better analysis (up to 50k chars)
        truncated_text = text[:50000]

        prompt = f"""
You are a Research Scientist Analysis Agent.

User Query: {query}

Paper Content (Excerpt):
{truncated_text}
...

Task:
1. Summarize the paper's core contribution relative to the query.
2. Extract key methodologies, algorithms, or approaches used.
3. Identify any novel findings, results, or conclusions.
4. Note any limitations or future work mentioned.
5. If the paper is in Indonesian, provide the summary in Indonesian.

Keep it concise (maximum 4 paragraphs) and relevant to the query.
"""

        return self.teacher.ask(
            prompt,
            system_instruction=(
                "You are a Research Scientist. Extract precise, technical "
                "insights relevant to the user's query."
            ),
        )

    def _extract_references(self, text: str, paper_title: str) -> List[Dict[str, Any]]:
        """
        Uses LLM to extract reference list from paper text.
        Searches the entire document for references section.
        Returns list of {title, year, authors} dicts.
        """
        # Find references section - look for common reference section headers
        ref_section = self._find_references_section(text)

        if not ref_section:
            # Fallback: use last 15000 chars if no clear section found
            ref_section = text[-15000:]

        prompt = f"""
Extract the reference list from the text below.
Return a JSON array of objects with keys: "title", "year", "authors".
- "title": string
- "year": string (4-digit year or empty)
- "authors": array of strings
Extract as many references as you can find, up to 50.
Output ONLY valid JSON. No markdown, no explanation.

Paper: {paper_title}

Text (references section):
{ref_section}
"""

        try:
            raw = self.teacher.ask(
                prompt,
                system_instruction=(
                    "You are a reference extractor. Output raw JSON only."
                ),
            )
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            refs = json.loads(raw)
            if isinstance(refs, list):
                reference_count = len(refs)
                print(
                    f"[JournalProcessor] Extracted {reference_count} "
                    f"references from '{paper_title}'."
                )
                return refs
        except ProviderError:
            raise
        except (json.JSONDecodeError, TypeError) as error:
            raise ProviderInvalidResponseError(
                "nvidia_nim",
                "Reference extractor returned malformed JSON",
                cause_type=type(error).__name__,
            ) from error
        raise ProviderInvalidResponseError(
            "nvidia_nim",
            "Reference extractor response must be a JSON array",
        )

    def _find_references_section(self, text: str) -> str:
        """Find the references/bibliography section in the paper text"""
        # Common reference section headers (case insensitive)
        ref_patterns = [
            r"\n\s*references\s*\n",
            r"\n\s*bibliography\s*\n",
            r"\n\s*reference list\s*\n",
            r"\n\s*literature cited\s*\n",
            r"\n\s*works cited\s*\n",
            r"\n\s*daftar pustaka\s*\n",
            r"\n\s*referensi\s*\n",
        ]

        text_lower = text.lower()
        for pattern in ref_patterns:
            match = re.search(pattern, text_lower)
            if match:
                # Return text from the match to the end
                return text[match.start() :]

        return ""


if __name__ == "__main__":
    # Test
    processor = JournalProcessor()
    result = processor.process_query("Self-Evolving AI Architectures")
    print(result)
