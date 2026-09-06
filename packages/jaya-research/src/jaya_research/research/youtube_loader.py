"""
Multimodal YouTube & Video Loader
Uses the VideoProcessor to extract audio, sample visual frames, and synthesize a markdown report.
"""
import os
import re
from pathlib import Path
from typing import Dict, Any

from jaya_research.research.video_processor import VideoProcessor

class YouTubeLoader:
    """
    Loader for YouTube and general video URLs.
    Downloads, processes visual/audio streams, and returns a synthesized document.
    """
    def __init__(self):
        try:
            self.processor = VideoProcessor()
            self.available = True
        except ValueError as e:
            print(f"[YouTubeLoader] Warning: {e}")
            self.available = False
            
    def is_valid_url(self, url: str) -> bool:
        """Simple check if string is a URL."""
        # Simple regex for youtube or http URLs
        return url.startswith("http://") or url.startswith("https://")

    def load_and_process(self, url: str) -> Dict[str, Any]:
        """
        Process the video URL.
        Returns a dictionary containing the extracted text/report.
        """
        if not self.available:
            return {"error": "VideoProcessor is not available (check NVIDIA_API_KEY and VIDEO_VLM_MODEL)."}
            
        if not self.is_valid_url(url):
            return {"error": f"Invalid URL: {url}"}
            
        try:
            print(f"[YouTubeLoader] Starting ingestion for: {url}")
            # Use process_video_chunked for robust handling (smart splitting + adaptive visual)
            result = self.processor.process_video_chunked(url)
            
            if result.get("status") == "success":
                # The processor returns a markdown 'report'
                return {
                    "status": "success",
                    "title": result.get("title", "Video Document"),
                    "full_text": result.get("report", ""),
                    "video_path": result.get("video_path", "")
                }
            else:
                return {"error": f"Failed to process video: {result.get('error', 'Unknown error')}"}
                
        except Exception as e:
            print(f"[YouTubeLoader] Error during ingestion: {e}")
            return {"error": str(e)}
