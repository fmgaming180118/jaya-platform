from src.research.academic.literature import ArxivClient
import json

def test_arxiv():
    client = ArxivClient()
    
    topics = ["Fullstack Development", "Artificial Intelligence", "ReactJS"]
    
    for topic in topics:
        print(f"\n--- Testing Topic: {topic} ---")
        papers = client.search_papers(topic, max_results=2)
        if papers:
            for p in papers:
                print(f"[FOUND] {p['title']} ({p['published']})")
        else:
            print("[NO RESULTS] - Might need better mapping or ArXiv doesn't cover this.")

if __name__ == "__main__":
    test_arxiv()
