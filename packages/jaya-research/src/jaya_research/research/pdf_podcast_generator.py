"""
PDF to Podcast Generator Module for JAYA_RESEARCH (Adopting PDF-to-Podcast Blueprint).
Transforms research papers and thesis PDFs into engaging 2-speaker conversational AI audio podcast scripts.
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Absolute resolution of src/config.py to avoid collision with src/research/config.py
src_dir = str(Path(__file__).resolve().parents[1])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    import jaya_research.config as jaya_global_config
    config = getattr(jaya_global_config, "config", None)
except Exception:
    config = None

logger = logging.getLogger(__name__)


class PDFPodcastGenerator:
    """
    Transforms scientific documents into 2-speaker podcast audio dialogue scripts.
    """

    def __init__(self, teacher: Optional[Any] = None):
        self.teacher = teacher
        self.tts_model = getattr(config, "NVIDIA_TTS_MODEL", "nvidia/riva-tts-fastpitch") if config else "nvidia/riva-tts-fastpitch"

    def generate_podcast_script(
        self, document_title: str, text_content: str
    ) -> Dict[str, Any]:
        """
        Generates a 2-speaker podcast dialogue script from text content.
        """
        clean_text = re.sub(r"\s+", " ", text_content[:3000]).strip()

        # Check if LLM Teacher is available for dynamic script generation
        if self.teacher and hasattr(self.teacher, "ask"):
            prompt = f"""
            Transform the research paper below into an engaging 2-speaker podcast dialogue.
            Title: {document_title}
            Content: {clean_text[:1500]}
            Format output ONLY as JSON list of objects: [{"speaker": "Host Alex" | "Dr. Jaya", "text": "..."}]
            """
            try:
                raw_res = self.teacher.ask(prompt, system_instruction="Output raw JSON array only.")
                raw_res = raw_res.replace("```json", "").replace("```", "").strip()
                dialogue = json.loads(raw_res)
            except Exception as e:
                logger.warning(f"LLM script generation failed, using structured template: {e}")
                dialogue = self._build_template_dialogue(document_title, clean_text)
        else:
            dialogue = self._build_template_dialogue(document_title, clean_text)

        total_words = sum(len(line.get("text", "").split()) for line in dialogue)
        est_duration = round(total_words / 2.5, 1)  # ~150 words per minute -> 2.5 words/sec

        podcast_data = {
            "podcast_id": f"PODCAST-{datetime.now().strftime('%Y%m%d')}-{hash(document_title) % 1000:03d}",
            "title": f"Deep Dive Podcast: {document_title}",
            "dialogue": dialogue,
            "tts_config": {
                "tts_model": self.tts_model,
                "voices": {
                    "Host Alex": "en-US-Riva-Male-Narrative",
                    "Dr. Jaya": "en-US-Riva-Male-Expert",
                },
            },
            "metrics": {
                "total_turns": len(dialogue),
                "total_words": total_words,
                "estimated_duration_seconds": est_duration,
            },
            "timestamp": datetime.now().isoformat(),
        }

        return podcast_data

    def _build_template_dialogue(self, title: str, text: str) -> List[Dict[str, str]]:
        snippet = text[:200] if text else "important research findings"
        return [
            {
                "speaker": "Host Alex",
                "text": f"Welcome back to JAYA Science Breakdown! Today we are diving into '{title}'. Dr. Jaya, what is the core breakthrough here?",
            },
            {
                "speaker": "Dr. Jaya",
                "text": f"Thanks Alex! This work focuses on {snippet}... It presents a significant advancement in autonomous system efficiency.",
            },
            {
                "speaker": "Host Alex",
                "text": "Fascinating! How does this impact edge-bound deployment and real-time execution?",
            },
            {
                "speaker": "Dr. Jaya",
                "text": "By eliminating redundant computation and leveraging quantized micro-adapters, execution latency is reduced dramatically.",
            },
            {
                "speaker": "Host Alex",
                "text": "Incredible insight as always, Dr. Jaya! Thanks for tuning in to today's episode.",
            },
        ]
