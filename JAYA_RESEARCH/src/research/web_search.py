"""
Web Search Integration for Research Assistant
Provides fallback search when RAG returns insufficient results
"""
import os
from typing import List, Dict, Any

try:
    # Try new package name first
    from ddgs import DDGS
    WEB_SEARCH_AVAILABLE = True
except ImportError:
    try:
        # Fallback to old package name
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")
        from duckduckgo_search import DDGS
        WEB_SEARCH_AVAILABLE = True
    except ImportError:
        WEB_SEARCH_AVAILABLE = False
        print("[WEB SEARCH] ddgs/duckduckgo-search not installed. Web search disabled.")


class WebSearchClient:
    """
    Web search client using DuckDuckGo (no API key needed).
    Falls back gracefully if library not available.
    """
    
    def __init__(self):
        """Initialize web search client"""
        self.enabled = WEB_SEARCH_AVAILABLE
        if self.enabled:
            self.ddgs = DDGS()
    
    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search the web for a query.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of search results with title, snippet, and link
        """
        if not self.enabled:
            return []
        
        try:
            # DuckDuckGo text search
            results = []
            
            for r in self.ddgs.text(query, max_results=max_results):
                # DDGS v4 vs v7 compatibility
                url = r.get('link') or r.get('href') or ''
                snippet = r.get('body') or r.get('snippet') or ''
                title = r.get('title', '')
                
                if not url: continue # Skip if no URL

                results.append({
                    "document": {
                        "type": "web_search_result",
                        "title": title,
                        "content": snippet,
                        "url": url
                    },
                    "score": 0.9,  # Web results get high score
                    "snippet": snippet[:200]
                })
            
            return results
        
        except Exception as e:
            print(f"[WEB SEARCH] Error: {e}")
            return []
    
    def is_available(self) -> bool:
        """Check if web search is available"""
        return self.enabled


# Simple test
if __name__ == "__main__":
    client = WebSearchClient()
    
    if client.is_available():
        print("Testing web search...")
        results = client.search("neural compiler optimization", max_results=3)
        
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['document']['title']}")
            print(f"   {result['snippet']}")
            print(f"   {result['document']['url']}")
    else:
        print("Web search not available")
