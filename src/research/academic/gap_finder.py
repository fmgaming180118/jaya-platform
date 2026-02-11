import networkx as nx
from typing import List, Dict, Any
from src.research.academic.literature import SemanticScholarClient
from src.teacher import Teacher

class GapFinder:
    """
    Identifies Research Gaps using Citation Network Analysis.
    """
    def __init__(self):
        self.scholar = SemanticScholarClient()
        self.graph = nx.DiGraph()
        self.brain = Teacher(model_type="reasoning")

    def build_network(self, topic: str, depth: int = 1):
        """
        Builds a citation graph starting from a topic search.
        Depth 1: Search -> Citations
        """
        print(f"[GapFinder] Building network for topic: {topic}")
        
        # 1. Seed Papers
        seeds = self.scholar.search_papers(topic, max_results=5)
        for paper in seeds:
            self.graph.add_node(paper['id'], label=paper['title'], type='seed', year=paper.get('published'))
        
        # 2. Expand Citations
        if depth > 0:
            for paper in seeds:
                if not paper.get('id'): continue
                
                citations = self.scholar.get_citations(paper['id'], limit=5)
                for cite in citations:
                    if not cite.get('id'): continue
                    
                    self.graph.add_node(cite['id'], label=cite['title'], type='citation', year=cite.get('year'))
                    self.graph.add_edge(cite['id'], paper['id']) # Cited -> Original
        
        print(f"[GapFinder] Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
        return self.graph

    def analyze_gaps(self) -> str:
        """
        Analyzes the built graph to find gaps.
        """
        if self.graph.number_of_nodes() == 0:
            return "No data to analyze."

        # 1. Cluster Analysis (Community Detection)
        # Simple Connected Components for now
        components = list(nx.weakly_connected_components(self.graph))
        
        # 2. Extract Titles per Cluster
        clusters_text = ""
        for i, comp in enumerate(components[:3]): # Top 3 clusters
            titles = [self.graph.nodes[n].get('label', 'Unknown') for n in comp][:5]
            clusters_text += f"\nCluster {i+1}: " + ", ".join(titles)

        # 3. LLM Synthesis
        prompt = f"""
        You are a Research Scientist analyzing a citation network.
        
        OBSERVED CLUSTERS OF RESEARCH:
        {clusters_text}
        
        TASK:
        1. Identify the common themes in these clusters.
        2. Find "Structural Holes": What connects these clusters? Or what is MISSING between them?
        3. Propose 3 NOVEL Research Gaps (Ideas that combine these clusters or fill the void).
        
        OUTPUT FORMAT:
        ## Research Landscape
        [Summary]
        
        ## Identified Gaps
        1. [Gap 1]
        2. [Gap 2]
        3. [Gap 3]
        """
        
        return self.brain.generate_completion(prompt, max_tokens=1000)

if __name__ == "__main__":
    finder = GapFinder()
    finder.build_network("Generative AI for Healthcare")
    print(finder.analyze_gaps())
