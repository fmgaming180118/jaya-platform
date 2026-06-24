"""
Public API Client for Jaya AI
Provides safe access to public internet services (e.g., Wikipedia, DuckDuckGo) with filtering.
"""

import logging
import requests
from typing import Optional, Dict, Any
from protection.filters import is_domain_allowed, sanitize_outbound

logger = logging.getLogger(__name__)

class PublicAPIClient:
    def __init__(self, timeout: int = 10):
        """
        Initialize the public API client.
        :param timeout: Request timeout in seconds.
        """
        self.timeout = timeout
        self.session = requests.Session()
        # Set a user-agent to identify ourselves
        self.session.headers.update({
            'User-Agent': 'JayaAI/1.0 (+https://github.com/fmgaming180118/jaya-research)'
        })

    def query(self, user_intent: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Query a public API for the user intent.
        Currently supports Wikipedia summary and DuckDuckGo instant answer.
        :param user_intent: The sanitized user intent.
        :param context: Optional context.
        :return: Answer string or None if failed.
        """
        # Try Wikipedia first
        try:
            resp = self._query_wikipedia(user_intent)
            if resp:
                return resp
        except Exception as e:
            logger.warning(f"Wikipedia query failed: {e}")

        # Try DuckDuckGo Instant Answer
        try:
            resp = self._query_duckduckgo(user_intent)
            if resp:
                return resp
        except Exception as e:
            logger.warning(f"DuckDuckGo query failed: {e}")

        # If both fail, return None
        return None

    def _query_wikipedia(self, query: str) -> Optional[str]:
        """
        Use Wikipedia API to get a summary.
        """
        # Ensure the domain is allowed (should be, but double-check)
        if not is_domain_allowed("https://en.wikipedia.org/w/api.php"):
            logger.warning("Wikipedia domain not allowed.")
            return None
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'search',
            'srsearch': query,
            'srlimit': 1
        }
        try:
            r = self.session.get('https://en.wikipedia.org/w/api.php', params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            search_results = data.get('query', {}).get('search', [])
            if not search_results:
                return None
            page_title = search_results[0]['title']
            # Now get the summary
            params2 = {
                'action': 'query',
                'format': 'json',
                'prop': 'extracts',
                'exintro': True,
                'explaintext': True,
                'titles': page_title
            }
            r2 = self.session.get('https://en.wikipedia.org/w/api.php', params=params2, timeout=self.timeout)
            r2.raise_for_status()
            data2 = r2.json()
            pages = data2.get('query', {}).get('pages', {})
            for page in pages.values():
                return page.get('extract', '').strip()
        except Exception as e:
            logger.error(f"Error in Wikipedia query: {e}")
            return None

    def _query_duckduckgo(self, query: str) -> Optional[str]:
        """
        Use DuckDuckGo Instant Answer API.
        """
        if not is_domain_allowed("https://api.duckduckgo.com/"):
            logger.warning("DuckDuckGo domain not allowed.")
            return None
        params = {
            'q': query,
            'format': 'json',
            'no_html': 1,
            'skip_disambig': 1
        }
        try:
            r = self.session.get('https://api.duckduckgo.com/', params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            # Prefer the abstract, then the definition, then the answer
            answer = data.get('AbstractText') or data.get('Definition') or data.get('Answer')
            if answer:
                return answer.strip()
            # If not, maybe there is related topics
            # For simplicity, we just return the abstract if present
            return None
        except Exception as e:
            logger.error(f"Error in DuckDuckGo query: {e}")
            return None

    def close(self):
        """Close the session."""
        self.session.close()