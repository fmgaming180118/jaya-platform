"""
Smart Query Router Module for JAYA_RESEARCH (Adopting LLM Router Blueprint).
Estimates query complexity score and routes simple queries to Edge Local models
and complex queries to NVIDIA Cloud NIM Nemotron Super 120B.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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


class SmartQueryRouter:
    """
    Intelligent LLM Query Router.
    Optimizes latency, cost, and accuracy by dynamically matching prompt complexity
    with the ideal execution tier (Edge Local vs Cloud NIM 120B).
    """

    TECHNICAL_KEYWORDS = [
        "quantum", "bayesian", "optimization", "matrix", "eigenvalue", "graphrag",
        "vector", "embedding", "hypothesis", "synthesis", "micro-patch", "falsifiability",
        "architecture", "distributed", "concurrency", "neural", "transformer", "qlora"
    ]

    def __init__(
        self,
        edge_model: Optional[str] = None,
        cloud_model: Optional[str] = None,
    ):
        self.edge_model = edge_model or getattr(config, "NVIDIA_CHAT_MODEL", "smollm2-135m") if config else "smollm2-135m"
        self.cloud_model = cloud_model or getattr(config, "NVIDIA_REASONING_MODEL", "nvidia/nemotron-super-120b") if config else "nvidia/nemotron-super-120b"

    def estimate_complexity(self, query: str) -> float:
        """
        Estimates complexity score between 0.0 (Simple) and 1.0 (Highly Complex).
        """
        if not query or not query.strip():
            return 0.0

        query_lower = query.lower()
        words = re.findall(r"\w+", query_lower)
        word_count = len(words)

        # 1. Base length score (0.0 to 0.4)
        length_score = min(0.4, word_count / 100.0)

        # 2. Technical keyword density score (0.0 to 0.4)
        matches = sum(1 for kw in self.TECHNICAL_KEYWORDS if kw in query_lower)
        tech_score = min(0.4, matches * 0.15)

        # 3. Question structure complexity (0.0 to 0.2)
        structure_score = 0.0
        if any(clause in query_lower for clause in ["mengapa", "bagaimana", "jelaskan alur", "analisis", "bandingkan", "sintesis"]):
            structure_score = 0.2

        total_score = round(min(1.0, length_score + tech_score + structure_score), 2)
        return total_score

    def route_query(self, query: str) -> Dict[str, Any]:
        """
        Routes the input query to the appropriate LLM tier based on complexity.
        """
        complexity = self.estimate_complexity(query)

        if complexity <= 0.40:
            target_tier = "EDGE_LOCAL"
            selected_model = self.edge_model
            reason = f"Low complexity ({complexity:.2f} <= 0.40). Routed to Edge Local for instant response."
        else:
            target_tier = "CLOUD_NIM_120B"
            selected_model = self.cloud_model
            reason = f"High complexity ({complexity:.2f} > 0.40). Routed to Cloud NIM 120B for deep reasoning."

        return {
            "query": query,
            "complexity_score": complexity,
            "target_tier": target_tier,
            "recommended_model": selected_model,
            "routing_reason": reason,
        }
