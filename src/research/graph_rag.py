"""
Graph RAG Engine
Implements Knowledge Graph construction and retrieval using LLM extraction.
"""
import networkx as nx
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Use existing Teacher for LLM calls
try:
    from teacher import Teacher
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from teacher import Teacher

class GraphRAGEngine:
    def __init__(self, storage_path=None):
        # Default to data/knowledge_graph.json if no path provided (Backward compatibility)
        self.storage_path = Path(storage_path) if storage_path else Path("data/knowledge_graph.json")
        self.graph = nx.DiGraph()
        # Use Reasoning model for extraction
        self.teacher = Teacher(model_type="reasoning")
        self._load_graph()
        
    def _load_graph(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
                print(f"[GraphRAG] Loaded {self.graph.number_of_nodes()} nodes.")
            except Exception as e:
                print(f"[GraphRAG] Error loading graph: {e}")
                self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()

    def save_graph(self):
        data = nx.node_link_data(self.graph)
        with open(self.storage_path, 'w') as f:
            json.dump(data, f)
        print(f"[GraphRAG] Saved {self.graph.number_of_nodes()} nodes.")

    def extract_triples(self, text: str) -> List[Tuple[str, str, str]]:
        """
        Uses LLM to extract (Subject, Predicate, Object) triples.
        """
        prompt = f"""
        Extract knowledge triples from the text below.
        Format as a JSON list of lists: [["Subject", "Predicate", "Object"], ...]
        
        Rules:
        - Entities should be concise concepts (e.g., "JIT Compiler", "Python").
        - Predicates should be verbs/relationships (e.g., "improves", "is_part_of").
        - Extract at least 3-5 key relationships.
        - Output ONLY JSON. No markdown.
        
        Text:
        {text[:2000]} 
        """
        # Truncate text to avoid token limits
        
        try:
            response = self.teacher.ask(prompt, system_instruction="You are a Knowledge Graph Extractor. Output raw JSON only.")
            # Clean up response
            response = response.replace("```json", "").replace("```", "").strip()
            triples = json.loads(response)
            return triples
        except Exception as e:
            print(f"[GraphRAG] Extraction error: {e}")
            return []

    def ingest_document(self, text: str, source_id: str):
        """
        Extracts knowledge from text and updates the graph.
        """
        triples = self.extract_triples(text)
        
        for subj, pred, obj in triples:
            self.graph.add_node(subj, type="concept")
            self.graph.add_node(obj, type="concept")
            self.graph.add_edge(subj, obj, relation=pred, source=source_id)
            
        self.save_graph()
        return len(triples)

    def get_context(self, query: str, max_hops=1) -> str:
        """
        Retrieves context by finding relevant nodes and traversing.
        Simple implementation: Find nodes matching query keywords.
        """
        relevant_nodes = []
        query_terms = query.lower().split()
        
        # 1. Find entry nodes (Naive keyword match)
        for node in self.graph.nodes():
            if any(term in str(node).lower() for term in query_terms):
                relevant_nodes.append(node)
        
        # 2. Traverse
        subgraph_nodes = set(relevant_nodes)
        for node in relevant_nodes:
            # Add neighbors
            neighbors = list(self.graph.neighbors(node))
            subgraph_nodes.update(neighbors)
            
        # 3. Format context
        context_lines = []
        subgraph = self.graph.subgraph(subgraph_nodes)
        for u, v, data in subgraph.edges(data=True):
            rel = data.get('relation', 'related_to')
            context_lines.append(f"{u} --[{rel}]--> {v}")
            
        return "\n".join(context_lines)

    def get_viz_data(self):
        """Returns data for React Flow"""
        return nx.node_link_data(self.graph)
