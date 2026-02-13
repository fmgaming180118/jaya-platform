import networkx as nx
import json
from pathlib import Path

class KnowledgeGraphEngine:
    def __init__(self, memory_file="data/evolution_memory.json"):
        self.graph = nx.DiGraph()
        self.memory_file = Path(memory_file)
        
    def build_from_reports(self, reports):
        """
        Build graph nodes/edges from research reports.
        Nodes: Research Topics, Key Concepts
        Edges: 'related_to', 'part_of'
        """
        self.graph.clear()
        
        # Add Central Node
        self.graph.add_node("JAYA Research", type="root", label="JAYA Research")
        
        for report in reports:
            # Topic Node
            topic = report.get('topic', 'Unknown Topic')
            self.graph.add_node(topic, type="topic", label=topic)
            self.graph.add_edge("JAYA Research", topic, relation="researched")
            
            # Extract Concepts (Simple keyword extraction for MVP)
            # In Phase 8, this will use NER from LLM
            content = report.get('content', '')
            # Simple heuristic: capitalized words in headers or bullet points? 
            # For now, let's just use specific metadata if available, or dummy extraction
            
            # If report has 'findings' or 'tags'
            tags = report.get('tags', [])
            for tag in tags:
                self.graph.add_node(tag, type="concept", label=tag)
                self.graph.add_edge(topic, tag, relation="relates_to")

    def get_graph_data(self):
        """
        Convert NetworkX graph to React Flow format
        """
        nodes = []
        edges = []
        
        # Simple layout positioning (random or circular for now, React Flow can handle it too)
        # But React Flow needs x,y. Let's let frontend handle layout or provide basic ones.
        # We'll just provide data.
        
        for i, (node, data) in enumerate(self.graph.nodes(data=True)):
            nodes.append({
                "id": node,
                "data": { "label": data.get('label', node) },
                "position": { "x": 0, "y": 0 }, # Frontend should use dagre/elk to layout
                "type": "default" if data.get('type') != 'root' else 'input'
            })
            
        for i, (u, v, data) in enumerate(self.graph.edges(data=True)):
            edges.append({
                "id": f"e{i}",
                "source": u,
                "target": v,
                "label": data.get('relation', ''),
                "animated": True
            })
            
        return {
            "nodes": nodes,
            "edges": edges
        }
