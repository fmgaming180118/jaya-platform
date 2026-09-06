"""Bounded, TLS-verified web search adapters for JAYA_RESEARCH."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import warnings
from typing import Any, Dict, Iterable, List, Optional

import requests

from jaya_research.provider_errors import (
    ProviderError,
    ProviderInvalidResponseError,
    ProviderPolicy,
    classify_provider_error,
    ensure_http_success,
    execute_with_retry,
    select_primary_error,
)


WEB_SEARCH_AVAILABLE = True
DDGS_CLASS = None

try:
    from ddgs import DDGS as DDGS_CLASS
except ImportError:
    try:
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            module="duckduckgo_search",
        )
        from duckduckgo_search import DDGS as DDGS_CLASS
    except ImportError:
        DDGS_CLASS = None


class WebSearchClient:
    """Search DuckDuckGo through independent adapters with explicit failure state."""

    API_URL = "https://api.duckduckgo.com/"
    HTML_URL = "https://html.duckduckgo.com/html/"
    USER_AGENT = "JAYA-Research/1.0"

    def __init__(
        self,
        *,
        ddgs_client: Any = None,
        policy: Optional[ProviderPolicy] = None,
    ) -> None:
        self.enabled = True
        self.policy = policy or ProviderPolicy.from_env("WEB_SEARCH_PROVIDER")
        self.ddgs = ddgs_client
        self._ddgs_initialized = ddgs_client is not None

    @staticmethod
    def _create_ddgs_client() -> Any:
        if DDGS_CLASS is None:
            return None
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=RuntimeWarning,
            )
            return DDGS_CLASS()

    def is_available(self) -> bool:
        return self.enabled

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Return real results, a genuine empty result, or a typed provider error."""
        if not self.enabled:
            return []
        if not isinstance(query, str) or not query.strip():
            return []
        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")

        provider_errors: list[ProviderError] = []
        successful_providers = 0

        if not self._ddgs_initialized:
            self.ddgs = self._create_ddgs_client()
            self._ddgs_initialized = True

        if self.ddgs is not None:
            try:
                results = self._search_ddgs(query.strip(), max_results)
                successful_providers += 1
                if results:
                    return results
            except Exception as raw_error:
                provider_errors.append(
                    classify_provider_error("duckduckgo_ddgs", raw_error)
                )

        for provider, operation in (
            (
                "duckduckgo_api",
                lambda: self._search_instant_answer(query.strip(), max_results),
            ),
            (
                "duckduckgo_html",
                lambda: self._search_html(query.strip(), max_results),
            ),
        ):
            try:
                results = operation()
                successful_providers += 1
                if results:
                    return results
            except Exception as raw_error:
                provider_errors.append(
                    classify_provider_error(provider, raw_error)
                )

        if successful_providers == 0 and provider_errors:
            raise select_primary_error(provider_errors)
        return []

    def _search_ddgs(
        self,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        def request() -> List[Dict[str, Any]]:
            raw_results = self.ddgs.text(query, max_results=max_results)
            try:
                items = list(raw_results or [])
            except TypeError as exc:
                raise ProviderInvalidResponseError(
                    "duckduckgo_ddgs",
                    "Search provider returned a non-iterable response",
                    cause_type=type(exc).__name__,
                ) from exc
            return self._normalize_ddgs_items(items, max_results)

        return execute_with_retry(
            "duckduckgo_ddgs",
            request,
            self.policy,
        )

    @staticmethod
    def _normalize_ddgs_items(
        items: Iterable[Any],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                raise ProviderInvalidResponseError(
                    "duckduckgo_ddgs",
                    "Search provider returned a malformed result",
                )
            result = WebSearchClient._build_result(
                title=str(item.get("title") or ""),
                snippet=str(item.get("body") or item.get("snippet") or ""),
                url=str(item.get("href") or item.get("link") or ""),
                source="duckduckgo_ddgs",
            )
            if result:
                results.append(result)
            if len(results) >= max_results:
                break
        return results

    def _search_instant_answer(
        self,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        def request() -> Dict[str, Any]:
            response = requests.get(
                self.API_URL,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
                headers={"User-Agent": self.USER_AGENT},
                timeout=self.policy.requests_timeout,
            )
            ensure_http_success("duckduckgo_api", response)
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise ProviderInvalidResponseError(
                    "duckduckgo_api",
                    "Search provider returned malformed JSON",
                    cause_type=type(exc).__name__,
                ) from exc
            if not isinstance(payload, dict):
                raise ProviderInvalidResponseError(
                    "duckduckgo_api",
                    "Search provider response must be a JSON object",
                )
            return payload

        data = execute_with_retry("duckduckgo_api", request, self.policy)
        results: List[Dict[str, Any]] = []

        abstract = data.get("Abstract")
        if isinstance(abstract, str) and abstract.strip():
            result = self._build_result(
                title=str(data.get("Heading") or query),
                snippet=abstract,
                url=str(data.get("AbstractURL") or ""),
                source="duckduckgo_api",
            )
            if result:
                results.append(result)

        related_topics = data.get("RelatedTopics", [])
        if not isinstance(related_topics, list):
            raise ProviderInvalidResponseError(
                "duckduckgo_api",
                "Search provider returned malformed related topics",
            )
        for topic in self._flatten_topics(related_topics):
            result = self._build_result(
                title=str(topic.get("Text") or "")[:120],
                snippet=str(topic.get("Text") or ""),
                url=str(topic.get("FirstURL") or ""),
                source="duckduckgo_api",
            )
            if result:
                results.append(result)
            if len(results) >= max_results:
                break
        return results[:max_results]

    @staticmethod
    def _flatten_topics(topics: Iterable[Any]) -> Iterable[Dict[str, Any]]:
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            nested = topic.get("Topics")
            if isinstance(nested, list):
                yield from WebSearchClient._flatten_topics(nested)
            elif topic.get("Text"):
                yield topic

    def _search_html(
        self,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        def request() -> str:
            response = requests.get(
                self.HTML_URL,
                params={"q": query},
                headers={"User-Agent": self.USER_AGENT},
                timeout=self.policy.requests_timeout,
            )
            ensure_http_success("duckduckgo_html", response)
            if not isinstance(response.text, str):
                raise ProviderInvalidResponseError(
                    "duckduckgo_html",
                    "Search provider returned a non-text response",
                )
            return response.text

        body = execute_with_retry("duckduckgo_html", request, self.policy)
        result_pattern = re.compile(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>'
            r"(.*?)</a>.*?"
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        results: List[Dict[str, Any]] = []
        for raw_url, raw_title, raw_snippet in result_pattern.findall(body):
            result = self._build_result(
                title=self._strip_html(raw_title),
                snippet=self._strip_html(raw_snippet),
                url=self._decode_result_url(html.unescape(raw_url)),
                source="duckduckgo_html",
            )
            if result:
                results.append(result)
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _strip_html(value: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()

    @staticmethod
    def _decode_result_url(value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        if parsed.netloc.endswith("duckduckgo.com"):
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [])
            if target:
                return target[0]
        return value

    @staticmethod
    def _build_result(
        *,
        title: str,
        snippet: str,
        url: str,
        source: str,
    ) -> Optional[Dict[str, Any]]:
        clean_title = title.strip()
        clean_snippet = snippet.strip()
        clean_url = url.strip()
        if not clean_title and not clean_snippet:
            return None
        document = {
            "title": clean_title,
            "url": clean_url,
            "source": source,
        }
        return {
            "title": clean_title,
            "snippet": clean_snippet,
            "url": clean_url,
            "source": source,
            "document": document,
        }


if __name__ == "__main__":
    client = WebSearchClient()
    print(json.dumps(client.search("Quantum Computing", max_results=3), indent=2))
