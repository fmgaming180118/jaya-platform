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
