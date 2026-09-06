"""
Protocol Database Manager for JAYA_RESEARCH.
Manages caches and templates for scientific experimental protocols.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProtocolDatabase:
    """
    Manages cached protocol templates and experimental designs
    derived from scientific literature and standard computer science benchmarks.
    """

    DEFAULT_TEMPLATES = {
        "controlled_comparison": {
            "name": "Controlled Comparative Analysis Protocol",
            "type": "Controlled Comparison",
            "steps": [
                "1. Establish baseline control group environment.",
                "2. Apply single independent variable intervention to test group.",
                "3. Execute N benchmark trials under identical environment parameters.",
                "4. Measure dependent metric response and variance.",
                "5. Perform t-test / ANOVA statistical confidence evaluation."
            ],
            "recommended_controls": ["System Environment", "Memory Limit", "Timeout Interval"]
        },
        "sensitivity_analysis": {
            "name": "Parameter Sensitivity & Scalability Protocol",
            "type": "Sensitivity Analysis",
            "steps": [
                "1. Define continuous spectrum for target independent parameter.",
                "2. Sweep parameter values across logarithmic / linear scale.",
                "3. Record output latency, memory footprint, and metric accuracy.",
                "4. Plot pareto frontier curve to identify optimal operating point."
            ],
            "recommended_controls": ["Hardware Allocation", "Concurrently Running Tasks"]
        },
        "ab_testing": {
            "name": "A/B Hypothesis Verification Protocol",
            "type": "A/B Testing",
            "steps": [
                "1. Split incoming workload evenly between Variant A (Original) and Variant B (Hypothesis).",
                "2. Collect metric stream across equal sample sizes.",
                "3. Evaluate effect size and p-value cutoff."
            ],
            "recommended_controls": ["Sample Distribution", "Random Seed"]
        }
    }

    def __init__(self):
        self.cached_protocols: Dict[str, Dict[str, Any]] = dict(self.DEFAULT_TEMPLATES)

    def get_protocol(self, protocol_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve protocol template by key or type."""
        key_lower = protocol_key.lower().replace(" ", "_")
        return self.cached_protocols.get(key_lower) or self.cached_protocols.get("controlled_comparison")

    def register_protocol(self, key: str, template: Dict[str, Any]):
        """Register custom experimental protocol template."""
        self.cached_protocols[key.lower().replace(" ", "_")] = template

    def search_protocols(self, query: str) -> List[Dict[str, Any]]:
        """Search protocol database by query keyword."""
        query_lower = query.lower()
        results = []
        for proto in self.cached_protocols.values():
            if query_lower in proto.get("name", "").lower() or query_lower in proto.get("type", "").lower():
                results.append(proto)
        return results if results else [self.DEFAULT_TEMPLATES["controlled_comparison"]]
