"""
Built-in Web Research Skill for JAYA_AGENT.
Integrated DuckDuckGo API / HTTP fallback search.
"""

import sys
import os
import json
from typing import Dict, Any
from ..base_skill import Skill, skill_action

# Import WebSearchClient from JAYA_RESEARCH
try:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    research_src = os.path.join(root_dir, "JAYA_RESEARCH", "src")
    if research_src not in sys.path:
        sys.path.insert(0, research_src)
    from research.web_search import WebSearchClient
    web_client = WebSearchClient()
except Exception:
    web_client = None


class WebResearchSkill(Skill):
    name = "web_skill"
    description = "Web research and DuckDuckGo search"

    @skill_action("web_search", "Searches the web for information", params={"query": "str"})
    def web_search(self, query: str) -> str:
        if web_client is None:
            return f"Web search client unavailable. Query: '{query}'"
        results = web_client.search(query, max_results=3)
        if not results:
            return f"No web search results found for query: '{query}'"
        return json.dumps(results, indent=2)
