"""Capability-gated web research through an injected public adapter."""

from __future__ import annotations

import json

from security.capability_sandbox import require_active_capability
from skills.adapters import SkillAdapterUnavailable, WebResearchAdapter
from skills.base_skill import Skill, skill_action


class WebResearchSkill(Skill):
    """Search only through a separately configured, reviewed adapter."""

    name = "web_skill"
    description = "Bounded web research"
    NETWORK_RESOURCES = (
        "https://api.duckduckgo.com",
        "https://html.duckduckgo.com/html",
    )

    def __init__(self, client: WebResearchAdapter | None = None) -> None:
        self._client = client

    @skill_action(
        "web_search",
        "Searches allowlisted HTTPS providers for information",
        params={"query": "str"},
        capability="network.search",
        fixed_resources=NETWORK_RESOURCES,
        timeout_seconds=15.0,
    )
    def web_search(self, query: str) -> str:
        require_active_capability(
            "network.search",
            self.NETWORK_RESOURCES,
        )
        clean_query = query.strip()
        if (
            not clean_query
            or len(clean_query) > 512
            or any(ord(character) < 32 for character in clean_query)
        ):
            raise ValueError("Search query is empty, oversized, or contains controls")
        if self._client is None:
            raise SkillAdapterUnavailable("web_research")
        results = self._client.search(clean_query, max_results=3)
        if not isinstance(results, list):
            raise ValueError("Web research adapter returned an invalid result")
        return json.dumps(results, ensure_ascii=False, indent=2)
