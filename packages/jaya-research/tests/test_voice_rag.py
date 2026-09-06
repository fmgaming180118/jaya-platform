import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules before importing agent
sys.modules["pipecat"] = MagicMock()
sys.modules["pipecat.pipeline.pipeline"] = MagicMock()

# Patch EnhancedRAGClient before importing agent to avoid real initialization
with patch.dict('sys.modules', {'research.enhanced_rag': MagicMock()}):
    from jaya_research.voice_agent.agent import JayaVoiceAgent

class TestVoiceRAG(unittest.TestCase):
    
    def setUp(self):
        # Setup mock RAG client
        self.mock_rag = MagicMock()
        self.mock_rag.query.return_value = {"answer": "Omniverse is a platform..."}
        
    def test_rag_query_processing(self):
        """Test that process_query calls RAG client correctly"""
        # Inject mock directly
        agent = JayaVoiceAgent(api_key="test_key", rag_client=self.mock_rag)
        
        # Verify RAG init
        self.assertIs(agent.rag_client, self.mock_rag)
        
        # Test query
        response = agent.process_query("What is Omniverse?")
        print(f"DEBUG RESPONSE: {response}")
            
        # Assert interactions
        agent.rag_client.query.assert_called_with("What is Omniverse?")
        self.assertIn("Omniverse is a platform...", response)
        print("\n[TEST] Voice-RAG Integration Verified!")
        print(f"Response: {response}")

if __name__ == "__main__":
    unittest.main()
