import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config import config

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import pypdf
from src.research.academic.literature import ArxivClient
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
        
        # 1. Search ArXiv
        papers = self.arxiv.search_papers(query, max_results=max_papers)
        if not papers:
            return {"status": "empty", "message": "No papers found."}
            
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
                "local_path": str(pdf_path)
            })
            
        # 3. Synthesize Final Answer
        if not processed_data:
            return {"status": "error", "message": "Failed to process papers."}
            
        # If multiple papers, we could combine them. For now, just return the list.
        return {
            "status": "success",
            "papers": processed_data
        }

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
