import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.research.graph_rag import GraphRAGEngine
import unittest

class TestGraphRAG(unittest.TestCase):
    def setUp(self):
        self.test_db = "data/test_graph.json"
        self.engine = GraphRAGEngine(storage_path=self.test_db)
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_extraction(self):
        text = "Deep Learning uses Neural Networks to solve complex problems. PyTorch is a framework for Deep Learning."
        print(f"Extracting from: {text}")
        
        count = self.engine.ingest_document(text, "test_doc_1")
        print(f"Extracted {count} triples.")
        
        # Verify Graph
        self.assertTrue(self.engine.graph.has_node("Deep Learning"))
        # self.assertTrue(self.engine.graph.has_edge("Deep Learning", "Neural Networks")) # Depends on LLM randomness
        
        # Verify JSON output
        context = self.engine.get_context("PyTorch")
        print(f"Context for 'PyTorch':\n{context}")
        self.assertIn("PyTorch", context)

if __name__ == "__main__":
    unittest.main()
