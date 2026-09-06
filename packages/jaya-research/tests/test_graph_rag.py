import json
from pathlib import Path

import pytest

from jaya_research.research.graph_rag import GraphRAGEngine, GraphRAGExtractionError
import unittest

class TestGraphRAG(unittest.TestCase):
    def setUp(self):
        self.test_directory = pytest.TempPathFactory

    class FakeTeacher:
        @staticmethod
        def ask(_prompt, *, system_instruction):
            assert "JSON" in system_instruction
            return json.dumps(
                [
                    ["Deep Learning", "uses", "Neural Networks"],
                    ["PyTorch", "supports", "Deep Learning"],
                ]
            )

    def test_extraction(self):
        import tempfile

        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        test_db = Path(temporary_directory.name) / "test_graph.json"
        self.engine = GraphRAGEngine(
            storage_path=test_db,
            teacher=self.FakeTeacher(),
        )
        text = "Deep Learning uses Neural Networks to solve complex problems. PyTorch is a framework for Deep Learning."
        count = self.engine.ingest_document(text, "test_doc_1")

        self.assertEqual(count, 2)
        self.assertTrue(self.engine.graph.has_node("Deep Learning"))
        self.assertTrue(
            self.engine.graph.has_edge("Deep Learning", "Neural Networks")
        )
        context = self.engine.get_context("PyTorch")
        self.assertIn("PyTorch", context)
        self.assertTrue(test_db.is_file())

    def test_missing_provider_fails_without_modifying_graph(self):
        import tempfile

        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        test_db = Path(temporary_directory.name) / "test_graph.json"
        engine = GraphRAGEngine(storage_path=test_db)

        with self.assertRaises(GraphRAGExtractionError):
            engine.ingest_document("Evidence text", "source-001")

        self.assertEqual(engine.graph.number_of_nodes(), 0)
        self.assertFalse(test_db.exists())

if __name__ == "__main__":
    unittest.main()
