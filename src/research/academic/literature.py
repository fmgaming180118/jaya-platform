import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
from typing import List, Dict

class ArxivClient:
    """
    Client for fetching papers from ArXiv.
    """
    BASE_URL = "http://export.arxiv.org/api/query"

    def search_papers(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Searches ArXiv for papers with category mapping.
        """
        # Map simple user topics to ArXiv categories
        category_map = {
            "ai": "cs.AI",
            "artificial intelligence": "cs.AI",
            "ml": "cs.LG",
            "machine learning": "cs.LG",
            "fullstack": "cs.SE",
            "software engineering": "cs.SE",
            "web": "cs.DC", # Distributed/Parallel/Cluster (close enough for web infra) or cs.SE
            "networking": "cs.NI",
            "cybersecurity": "cs.CR",
            "crypto": "cs.CR",
            "robotics": "cs.RO",
            "vision": "cs.CV"
        }

        # Check if query contains any known topics to refine search
        search_query = f"all:{query}"
        
        # If user queries a specific field, boost that category
        query_lower = query.lower()
        for key, cat in category_map.items():
            if key in query_lower:
                 # Construct advanced query: "all:fullstack AND cat:cs.SE"
                 # ArXiv API supports AND/OR
                 search_query = f"all:{query} AND cat:{cat}"
                 break

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        
        print(f"[ArXiv] Searching: {url}")
        
        try:
            with urllib.request.urlopen(url) as response:
                data = response.read()
                
            return self._parse_atom_response(data)
        except Exception as e:
            print(f"[ArXiv] Error: {e}")
            return []

    def _parse_atom_response(self, xml_data: bytes) -> List[Dict]:
        """
        Parses Atom XML response from ArXiv.
        """
        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
        
        papers = []
        for entry in root.findall('atom:entry', ns):
            paper = {
                "id": entry.find('atom:id', ns).text,
                "title": entry.find('atom:title', ns).text.strip(),
                "summary": entry.find('atom:summary', ns).text.strip(),
                "published": entry.find('atom:published', ns).text,
                "authors": [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)],
                "pdf_link": next((l.attrib['href'] for l in entry.findall('atom:link', ns) if l.attrib.get('title') == 'pdf'), None)
            }
            papers.append(paper)
            
        return papers


class SemanticScholarClient:
    """
    Client for Semantic Scholar API (Graph API).
    Good for broad computer science topics.
    """
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def search_papers(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Searches Semantic Scholar.
        """
        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,abstract,year,authors,url,openAccessPdf" 
        }
        
        # Add API Key if available
        headers = {}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        print(f"[SemanticScholar] Searching: {query}")
        
        try:
            req = urllib.request.Request(f"{self.BASE_URL}?{urllib.parse.urlencode(params)}", headers=headers)
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read())
            
            papers = []
            if "data" in data:
                for item in data["data"]:
                    # Safe extraction
                    pdf_url = item.get("openAccessPdf", {}).get("url") if item.get("openAccessPdf") else item.get("url")
                    
                    paper = {
                        "id": item.get("paperId"),
                        "title": item.get("title"),
                        "summary": item.get("abstract") or "No abstract available.",
                        "published": str(item.get("year")),
                        "authors": [a["name"] for a in item.get("authors", [])],
                        "pdf_link": pdf_url,
                        "source": "Semantic Scholar"
                    }
                    papers.append(paper)
            
            return papers

        except Exception as e:
            print(f"[SemanticScholar] Error: {e}")
            return []

    def get_citations(self, paper_id: str, limit: int = 10) -> List[Dict]:
        """
        Fetches papers that cite the given paper_id.
        """
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
        params = {"limit": limit, "fields": "title,abstract,year,authors,url"}
        
        headers = {}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key: headers["x-api-key"] = api_key
            
        try:
             req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=headers)
             with urllib.request.urlopen(req) as response:
                data = json.loads(response.read())
                
             citations = []
             if "data" in data:
                 for item in data["data"]:
                     citing_paper = item.get("citingPaper", {})
                     if not citing_paper: continue
                     
                     citations.append({
                         "id": citing_paper.get("paperId"),
                         "title": citing_paper.get("title"),
                         "year": citing_paper.get("year"),
                         "authors": [a["name"] for a in citing_paper.get("authors", [])],
                         "source": "Semantic Scholar"
                     })
             return citations
        except Exception as e:
            print(f"[SemanticScholar] Citation Error: {e}")
            return []

if __name__ == "__main__":
    import os
    # Test Combined
    print("--- ArXiv ---")
    arxiv = ArxivClient()
    print(len(arxiv.search_papers("ReactJS", 1)))
    
    print("\n--- Semantic Scholar ---")
    scholar = SemanticScholarClient()
    print(len(scholar.search_papers("ReactJS", 1)))
