import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research.enhanced_rag import EnhancedRAGClient  # noqa: E402


class TestRAGWebSearch(unittest.TestCase):
    def setUp(self):
        # Mock env
        os.environ["NVIDIA_API_KEY"] = "test_key"
        os.environ["NVIDIA_EMBEDDING_MODEL"] = "test_model"

        # Mock components
        self.mock_embedder = MagicMock()
        self.mock_vector_store = MagicMock()
        self.mock_web_search = MagicMock()

        # Patch init to inject mocks
        with (
            patch(
                "src.research.enhanced_rag.NVIDIAEmbeddings",
                return_value=self.mock_embedder,
            ),
            patch(
                "src.research.enhanced_rag.VectorStore",
                return_value=self.mock_vector_store,
            ),
            patch(
                "src.research.enhanced_rag.WebSearchClient",
                return_value=self.mock_web_search,
            ),
        ):
            self.client = EnhancedRAGClient(use_embeddings=True)

    def test_local_results_only(self):
        """Test when local results are good, web search is NOT triggered"""
        # Setup local results with high score
        self.mock_vector_store.search.return_value = [
            {
                "document": {"file_name": "doc1.pdf"},
                "snippet": "Local answer",
                "score": 0.9,
            }
        ]

        result = self.client.query("test query")

        self.assertIn("Local Research Data", result["answer"])
        self.assertNotIn("Web Search Results", result["answer"])
        self.mock_web_search.search.assert_not_called()

    def test_fallback_web_search(self):
        """Test when local results are missing, web search IS triggered"""
        # Setup empty local results
        self.mock_vector_store.search.return_value = []
        self.mock_web_search.is_available.return_value = True
        self.mock_web_search.search.return_value = [
            {
                "document": {
                    "title": "Web Title",
                    "url": "http://example.com",
                },
                "snippet": "Web answer",
            }
        ]

        result = self.client.query("test query")

        self.assertIn("Web Search Results", result["answer"])
        self.mock_web_search.search.assert_called()

    def test_low_confidence_fallback(self):
        """Test when local results have low score, web search IS triggered"""
        # Setup local results with low score
        self.mock_vector_store.search.return_value = [
            {
                "document": {"file_name": "doc1.pdf"},
                "snippet": "Unsure answer",
                "score": 0.4,
            }
        ]
        self.mock_web_search.is_available.return_value = True
        self.mock_web_search.search.return_value = [
            {
                "document": {
                    "title": "Web Title",
                    "url": "http://example.com",
                },
                "snippet": "Better web answer",
            }
        ]

        result = self.client.query("test query")

        # Low-confidence local text must not be promoted into the answer.
        self.assertNotIn("Local Research Data", result["answer"])
        self.assertNotIn("Unsure answer", result["answer"])
        self.assertIn("Web Search Results", result["answer"])
        self.assertEqual(result["status"], "ANSWERED")
        self.assertFalse(result["uses_internal_knowledge"])
        self.mock_web_search.search.assert_called()


if __name__ == "__main__":
    unittest.main()
