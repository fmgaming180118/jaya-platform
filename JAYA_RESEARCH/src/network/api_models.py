"""
Research API Models (Pydantic)
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ResearchRequest(BaseModel):
    topic: str
    focus_areas: Optional[str] = ""
    max_queries: int = 5
    workspace_id: str = "default"

class ChatRequest(BaseModel):
    message: str
    context_files: List[str] = [] # Filenames or IDs
    workspace_id: str = "default"

class DebateRequest(BaseModel):
    topic: str
    rounds: int = 3
    persona_1: str = "Optimist"
    persona_2: str = "Skeptic"
    analyze_frames: bool = True

class VideoIngestRequest(BaseModel):
    url: str
    workspace_id: str = "default"
    title: Optional[str] = None
    source: Optional[str] = None

# --- New models for Phase A endpoints ---

class IngestRequest(BaseModel):
    """Request model for POST /ingest"""
    text: str
    metadata: Optional[Dict[str, Any]] = None
    workspace_id: str = "default"

class IngestResponse(BaseModel):
    """Response model for POST /ingest"""
    status: str
    chunks_added: int
    workspace_id: str
    message: Optional[str] = None

class RecursiveResearchRequest(BaseModel):
    """Request model for POST /research/recursive"""
    query: str
    depth: int = 3
    workspace_id: str = "default"
    max_sources_per_level: int = 5

class RecursiveResearchResponse(BaseModel):
    """Response model for POST /research/recursive"""
    query: str
    synthesis: str
    sources: List[Dict[str, Any]]
    depth_reached: int
    workspace_id: str
