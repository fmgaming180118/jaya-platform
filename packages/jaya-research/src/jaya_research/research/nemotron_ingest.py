"""
Nemotron Ingest Module (Library Mode)
Uses nv-ingest to extract text, tables, and charts from documents without Docker.
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class NemotronIngestor:
    """
    Ingestor wrapper for NVIDIA nv-ingest library.
    Running in 'Library Mode' (Client-only or Local subprocess).
    """
    
    def __init__(self):
        self.client = None
        self.available = False
        
        try:
            # Try importing nv_ingest components
            # Note: The actual import paths depend on the specific version of nv-ingest
            # This is a best-effort implementation based on the tutorial architecture
            from nv_ingest.client import NvIngestClient
            from nv_ingest.util.flow.client import SimpleClient
            from nv_ingest.model.ingestor import Ingestor
            
            self.NvIngestClient = NvIngestClient
            self.SimpleClient = SimpleClient
            self.Ingestor = Ingestor
            self.available = True
            logger.info("[Nemotron] nv-ingest library found. Ready for library mode.")
            
        except ImportError as e:
            logger.warning(f"[Nemotron] nv-ingest library NOT found: {e}")
            logger.warning("[Nemotron] Run 'pip install nv-ingest' to enable advanced document processing.")
            self.available = False

    def ingest_file(self, file_path: str) -> Dict[str, Any]:
        """
        Ingest a single file using Nemotron pipeline.
        
        Args:
            file_path: Absolute path to the file (PDF)
            
        Returns:
            Dictionary containing extracted content (text, tables, charts)
        """
        if not self.available:
            return {"error": "nv-ingest not installed"}
            
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
            
        try:
            # Helper to run pipeline locally if not already running
            # In a real library mode usage, we might need to assume the pipeline 
            # is initialized or use a specific API to run it in-process.
            # detailed implementation would depend on the specific nv-ingest API version.
            
            # For this implementation, we follow the tutorial's client pattern
            # assuming a local worker is started or we are driving the flow directly.
            
            client = self.NvIngestClient(
                message_client_allocator=self.SimpleClient,
                message_client_hostname=os.getenv("NV_INGEST_HOST", "localhost"), # Local execution
                message_client_port=int(os.getenv("NV_INGEST_PORT", "7671")) # Default port
            )
            
            logger.info(f"[Nemotron] Extracting {file_path}...")
            
            ingestor = (self.Ingestor(client=client)
                .files([file_path])
                .extract(
                    extract_text=True,
                    extract_tables=True,
                    extract_charts=True,
                    extract_images=False, # Focus on charts/tables for now
                    extract_method="pdfium", # Robust for PDFs
                    table_output_format="markdown" # Critical for LLM understanding
                )
            )
            
            job_results = ingestor.ingest()
            
            if not job_results:
                return {"error": "No results returned from ingestion"}
                
            extracted_data = job_results[0]
            
            # Process and structure the data for our RAG system
            processed_content = self._process_results(extracted_data, file_path)
            return processed_content
            
        except Exception as e:
            logger.error(f"[Nemotron] Ingestion failed: {e}")
            return {"error": str(e)}

    def _process_results(self, raw_data: Any, file_path: str) -> Dict[str, Any]:
        """
        Convert raw nv-ingest output to Jaya's document format.
        """
        # This mapping depends on the exact JSON structure returned by nv-ingest
        # Using a generic structure for now
        
        chunks = []
        tables = []
        
        # Example traversal (pseudo-code as actual schema varies)
        # Assuming raw_data is a list of metadata/content dictionaries
        
        # If raw_data is just the raw result object, we might need to iterate it
        # For safety, we wrap in a list if it's not
        items = raw_data if isinstance(raw_data, list) else [raw_data]
        
        full_text = []
        
        for item in items:
            content_type = item.get("type", "text")
            content = item.get("content", "")
            metadata = item.get("metadata", {})
            
            if content_type == "table":
                tables.append({
                    "content": content, # Markdown table
                    "page": metadata.get("page_number"),
                    "caption": metadata.get("caption")
                })
                # Append table markdown to full text for context
                full_text.append(f"\n[TABLE on Page {metadata.get('page_number')}]\n{content}\n")
            
            elif content_type == "chart":
                # Handle charts (maybe referenced by ID or Image)
                full_text.append(f"\n[CHART on Page {metadata.get('page_number')}]\n")
            
            else:
                # Regular text
                full_text.append(content)
        
        return {
            "status": "success",
            "file_path": file_path,
            "full_text": "\n".join(full_text),
            "tables": tables,
            "raw_items": items # Keep raw items for advanced embedding later
        }
