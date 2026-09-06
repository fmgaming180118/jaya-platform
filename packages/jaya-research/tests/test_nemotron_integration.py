import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path to find src module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock nv_ingest modules before importing nemotron_ingest
sys.modules["nv_ingest"] = MagicMock()
sys.modules["nv_ingest.client"] = MagicMock()
sys.modules["nv_ingest.util.flow.client"] = MagicMock()
sys.modules["nv_ingest.model.ingestor"] = MagicMock()

# Now we can safely import our module
from jaya_research.research.nemotron_ingest import NemotronIngestor

class TestNemotronIntegration(unittest.TestCase):
    
    def setUp(self):
        # Setup mocks for the external library components
        self.mock_client_cls = MagicMock()
        self.mock_simple_client = MagicMock()
        self.mock_ingestor_cls = MagicMock()
        
        # Patch the specific classes used in NemotronIngestor
        # We need to patch where they are imported/used in the module
        # Since the module imports them inside __init__, we patch sys.modules or use patcher
        pass

    def test_ingestion_flow(self):
        """Test the ingestion flow with mocked NvIngest components"""
        
        # 1. Setup specific mock behaviors
        mock_client_cls = sys.modules["nv_ingest.client"].NvIngestClient
        mock_ingestor_cls = sys.modules["nv_ingest.model.ingestor"].Ingestor
        
        # 2. Initialize Ingestor
        ingestor = NemotronIngestor()
        
        # 3. Setup Mock Return Values for the chained calls
        mock_job_result = [{
            "type": "table",
            "content": "| Col1 | Col2 |\n|---|---|\n| Val1 | Val2 |",
            "metadata": {"page_number": 1, "caption": "Table 1"}
        }, {
            "type": "text",
            "content": "Some analysis text.",
            "metadata": {"page_number": 1}
        }]
        
        # Chain: Ingestor(client).files().extract().ingest()
        # mock_ingestor_instance is what Ingestor(...) returns
        mock_ingestor_instance = mock_ingestor_cls.return_value
        mock_ingestor_instance.files.return_value.extract.return_value.ingest.return_value = [mock_job_result]
        
        # 4. Create a dummy PDF file for testing check
        test_file = "test_doc.pdf"
        with open(test_file, "w") as f:
            f.write("dummy content")
            
        try:
            # 5. Run Ingest
            result = ingestor.ingest_file(test_file)
            
            # 6. Assertions
            self.assertEqual(result["status"], "success")
            self.assertIn("| Col1 | Col2 |", result["full_text"])
            self.assertEqual(len(result["tables"]), 1)
            self.assertEqual(result["tables"][0]["page"], 1)
            
            print("\n[TEST] Integration Logic Verified Successfully!")
            print(f"Extracted Text Preview: {result['full_text'][:50]}...")
            
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

if __name__ == "__main__":
    unittest.main()
