import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config import config

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import pypdf
from src.research.academic.literature import ArxivClient, SemanticScholarClient, OpenAlexClient
from src.teacher import Teacher
from src.research.config import get_config

class JournalProcessor:
    """
    Orchestrates the search, download, and processing of academic journals for Research Chat.
    """
    
    def __init__(self, download_dir: str = config.PAPERS_TEMP_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        self.arxiv = ArxivClient()
        self.scholar = SemanticScholarClient()
        self.openalex = OpenAlexClient()
        self.teacher = Teacher(model_type="reasoning")
        self.config = get_config()
        
    def process_query(self, query: str, max_papers: int = 1) -> Dict[str, Any]:
        """
        End-to-end processing: Search -> Download -> Extract -> Summarize
        
        Args:
            query: User's research topic
            max_papers: Number of papers to fully process (keep low for latency)
            
        Returns:
            Dict containing synthesis and source metadata
        """
        print(f"[JournalProcessor] Processing: {query}")
        
        # 1. Search across free sources
        papers = self._search_free_sources(query, max_papers=max_papers)
        if not papers:
            return {"status": "empty", "message": "No papers found."}

        papers = self._rank_papers(query, papers)
            
        processed_data = []
        
        # 2. Process each paper
        for paper in papers:
            pdf_link = paper.get("pdf_link")
            if not pdf_link:
                continue
                
            # Download
            pdf_path = self.arxiv.download_paper(pdf_link, self.download_dir)
            if not pdf_path:
                continue
                
            # Extract Text
            text_content = self._extract_text_from_pdf(pdf_path)
            if not text_content:
                continue
                
            # Save raw text for debugging/caching
            txt_path = pdf_path.with_suffix(".txt")
            with open(txt_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(text_content)
                
            # Summarize/Extract Insight
            insight = self._analyze_content(text_content, query)
            
            processed_data.append({
                "metadata": paper,
                "insight": insight,
                "summary": self._build_paper_summary(paper, insight),
                "compact_summary": self._build_compact_summary(paper, insight),
                "local_path": str(pdf_path),
                "source_meta": {
                    "title": paper.get("title", "Unknown Title"),
                    "source": paper.get("source", "Unknown Source"),
                    "rank_score": paper.get("rank_score", 0.0),
                    "pdf_link": paper.get("pdf_link") or paper.get("landing_page_url") or "",
                }
            })
            
        # 3. Synthesize Final Answer
        if not processed_data:
            return {"status": "error", "message": "Failed to process papers."}
            
        # If multiple papers, we could combine them. For now, just return the list.
        return {
            "status": "success",
            "papers": processed_data
        }

    def _rank_papers(self, query: str, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank papers by a simple free heuristic using title/summary overlap."""
        query_terms = [t for t in query.lower().split() if len(t) > 2]

        def score(paper: Dict[str, Any]) -> float:
            title = (paper.get("title") or "").lower()
            summary = (paper.get("summary") or "").lower()
            source_bonus = 0.0
            if paper.get("source") == "ArXiv":
                source_bonus += 0.1
            elif paper.get("source") == "OpenAlex":
                source_bonus += 0.08
            elif paper.get("source") == "Semantic Scholar":
                source_bonus += 0.06

            overlap = sum(1 for term in query_terms if term in title or term in summary)
            length_bonus = min(len(summary) / 5000.0, 0.15)
            return float(overlap) + source_bonus + length_bonus

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

    def _build_compact_summary(self, paper: Dict[str, Any], insight: str) -> Dict[str, Any]:
        return {
            "title": paper.get("title", "Unknown Title"),
            "source": paper.get("source", "Unknown Source"),
            "year": paper.get("published", ""),
            "rank_score": paper.get("rank_score", 0.0),
            "insight_excerpt": insight[:400],
            "link": paper.get("pdf_link") or paper.get("landing_page_url") or "",
        }

    def _search_free_sources(self, query: str, max_papers: int = 1) -> List[Dict[str, Any]]:
        """Search free academic metadata sources and deduplicate results."""
        combined: List[Dict[str, Any]] = []
        seen_titles = set()

        sources = [
            self.arxiv.search_papers(query, max_results=max_papers),
            self.scholar.search_papers(query, max_results=max_papers),
            self.openalex.search_papers(query, max_results=max_papers),
        ]

        for source_results in sources:
            for paper in source_results:
                title = (paper.get("title") or "").strip().lower()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                combined.append(paper)

        return combined[: max_papers * 3]

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extracts text using pypdf"""
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            full_text = []
            for page in reader.pages:
                full_text.append(page.extract_text())
            return "\n".join(full_text)
        except Exception as e:
            print(f"[JournalProcessor] Extraction error for {pdf_path}: {e}")
            return ""

    def _analyze_content(self, text: str, query: str) -> str:
        """Uses LLM to extract key insights relevant to the query"""
        # Truncate text if too long (approx 20k chars for Context Window safety)
        # Nvembed/Nemotron can handle long context but let's be safe for latency
        truncated_text = text[:30000] 
        
        prompt = f"""
        You are a Research Scientist Analysis Agent.
        
        User Query: {query}
        
        Paper Content (Excerpt):
        {truncated_text}
        ...
        
        Task:
        1. Summarize the paper's core contribution relative to the query.
        2. Extract key methodologies or results.
        3. Identify any novel findings.
        
        Keep it concise (maximum 3 paragraphs).
        """
        
        return self.teacher.ask(
            prompt,
            system_instruction="You are a Research Scientist. Analyze the paper content and extract key insights."
        )

if __name__ == "__main__":
    # Test
    processor = JournalProcessor()
    result = processor.process_query("Self-Evolving AI Architectures")
    print(result)
