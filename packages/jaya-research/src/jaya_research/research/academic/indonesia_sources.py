"""
Indonesia Academic Sources
Provides access to Indonesian journals via:
  1. CrossrefIndonesiaClient — Crossref REST API filtered to Indonesian publishers
  2. GarudaClient            — GARUDA (Garba Rujukan Digital) HTTP scraper

Both return the same Dict schema used by ArxivClient / SemanticScholarClient.
"""

import re
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

from jaya_research.provider_errors import (
    ProviderInvalidResponseError,
    ProviderPolicy,
    ensure_http_success,
    execute_with_retry,
)

# Known Indonesian Crossref member IDs / prefixes (top universities & publishers)
# We filter by checking publisher affiliation in metadata.
INDONESIAN_CROSSREF_MEMBERS = [
    # LPPM & journal prefix hints — Crossref doesn't have a simple country filter
    # so we search by query AND post-filter on publisher location.
]

# Common Indonesian publisher name keywords for post-filtering
INDONESIAN_PUBLISHER_KEYWORDS = [
    "universitas",
    "institut teknologi",
    "uin",
    "iain",
    "itb",
    "ugm",
    "ui ",
    "its",
    "undip",
    "unpad",
    "unair",
    "unhas",
    "uny",
    "unnes",
    "telkom",
    "binus",
    "indonesia",
    "indonesian",
    "jurnal",
    "journal of indonesian",
]


class CrossrefIndonesiaClient:
    """
    Searches Crossref (api.crossref.org) and post-filters results
    to Indonesian publishers/journals.
    """

    BASE_URL = "https://api.crossref.org/works"
    PROVIDER = "crossref"

    def __init__(self, *, policy: Optional[ProviderPolicy] = None) -> None:
        self.policy = policy or ProviderPolicy.from_env("ACADEMIC_PROVIDER")

    def search_papers(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search Crossref and return Indonesian-affiliated papers.
        """
        params = {
            "query": query,
            "rows": min(max_results * 4, 40),  # over-fetch for filtering
            "select": (
                "DOI,title,abstract,published,author,publisher,URL,link,"
                "language,container-title"
            ),
            "mailto": "jaya-research@app.local",  # Crossref polite pool
        }

        print(f"[CrossrefID] Searching: {query}")

        def request() -> Dict[str, Any]:
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers={
                    "User-Agent": "JAYA-Research/1.0 (mailto:jaya-research@app.local)"
                },
                timeout=self.policy.requests_timeout,
            )
            ensure_http_success(self.PROVIDER, response)
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned malformed JSON",
                    cause_type=type(exc).__name__,
                ) from exc
            if not isinstance(payload, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider response must be a JSON object",
                )
            return payload

        data = execute_with_retry(self.PROVIDER, request, self.policy)
        message = data.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("items"), list):
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider response omitted paper items",
            )

        items = message["items"]
        papers: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned a malformed paper record",
                )
            publisher = (item.get("publisher") or "").lower()
            container_titles = item.get("container-title") or []
            container = " ".join(container_titles).lower()

            # Post-filter: publisher must contain Indonesian keyword
            is_indonesian = any(
                keyword in publisher for keyword in INDONESIAN_PUBLISHER_KEYWORDS
            )
            is_indonesian = is_indonesian or any(
                keyword in container for keyword in INDONESIAN_PUBLISHER_KEYWORDS
            )
            lang = (item.get("language") or "").lower()
            is_indonesian = is_indonesian or lang in ("id", "in")
            if not is_indonesian:
                continue

            title_list = item.get("title") or []
            title = title_list[0] if title_list else "No Title"
            abstract = _strip_html(item.get("abstract") or "No abstract available.")
            publication = item.get("published") or item.get("published-print") or {}
            date_parts = publication.get("date-parts", [[]])
            year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""

            authors = []
            for author in item.get("author") or []:
                if not isinstance(author, dict):
                    continue
                name = (f"{author.get('given', '')} {author.get('family', '')}").strip()
                if name:
                    authors.append(name)

            pdf_link = None
            for link in item.get("link") or []:
                if (
                    isinstance(link, dict)
                    and link.get("content-type") == "application/pdf"
                ):
                    pdf_link = link.get("URL")
                    break
            if not pdf_link:
                pdf_link = item.get("URL")

            papers.append(
                {
                    "id": item.get("DOI", ""),
                    "title": title,
                    "summary": abstract[:1000],
                    "published": year,
                    "authors": authors,
                    "pdf_link": pdf_link,
                    "source": "Crossref Indonesia",
                    "language": "id",
                    "doi": item.get("DOI"),
                    "publisher": item.get("publisher", ""),
                    "container_title": (
                        container_titles[0] if container_titles else ""
                    ),
                }
            )

            if len(papers) >= max_results:
                break

        print(f"[CrossrefID] Found {len(papers)} Indonesian papers.")
        return papers


class GarudaClient:
    """
    Scraper for GARUDA — Garba Rujukan Digital (garuda.kemdikbud.go.id).
    Returns best-effort results; fails gracefully if site is unreachable.
    """

    BASE_URL = "https://garuda.kemdikbud.go.id/documents"
    PROVIDER = "garuda"

    def __init__(self, *, policy: Optional[ProviderPolicy] = None) -> None:
        self.policy = policy or ProviderPolicy.from_env("ACADEMIC_PROVIDER")

    def search_papers(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Scrape GARUDA search results page.
        """
        params = {"q": query, "page": 1}
        print(f"[GARUDA] Searching: {query}")

        def request() -> str:
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0"
                    ),
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,*/*;q=0.8"
                    ),
                    "Accept-Language": "id,en;q=0.9",
                },
                timeout=self.policy.requests_timeout,
            )
            ensure_http_success(self.PROVIDER, response)
            final_scheme = urllib.parse.urlsplit(response.url).scheme.lower()
            if final_scheme != "https":
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider redirected the search to a non-TLS URL",
                )
            if not isinstance(response.text, str) or not response.text.strip():
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned an empty HTML response",
                )
            return response.text

        html_body = execute_with_retry(self.PROVIDER, request, self.policy)
        papers = self._parse_html(html_body, max_results)
        if not papers and not re.search(
            r"(tidak ditemukan|no results?|hasil pencarian.*0)",
            html_body,
            re.IGNORECASE,
        ):
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider HTML did not match the expected result schema",
            )

        print(f"[GARUDA] Found {len(papers)} papers.")
        return papers

    def _parse_html(self, html: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Parse GARUDA HTML result cards.
        GARUDA renders article cards with various class patterns.
        """
        papers: List[Dict[str, Any]] = []

        # Try multiple patterns for article blocks
        patterns = [
            ('<div class="article">', "</article>"),
            ("<article", "</article>"),
            ('<div class="card', "</div>"),
            ('<div class="result-item', "</div>"),
            ('<li class="article', "</li>"),
        ]

        blocks = []
        for start_tag, end_tag in patterns:
            blocks = _extract_between(html, start_tag, end_tag)
            if blocks:
                break

        for block in blocks[:max_results]:
            # Title — try multiple patterns
            title = (
                _extract_first_text(block, "<h2", "</h2>")
                or _extract_first_text(block, "<h3", "</h3>")
                or _extract_first_text(block, "<h4", "</h4>")
                or _extract_attr(block, 'title="')
                or _extract_first_text(block, "<a ", "</a>")
                or _extract_attr(block, 'data-title="')
            )
            if not title:
                continue

            # Author - try multiple patterns
            author_raw = (
                _extract_first_text(block, '<span class="author"', "</span>")
                or _extract_first_text(block, '<div class="author"', "</div>")
                or _extract_first_text(block, '<p class="author"', "</p>")
                or _extract_first_text(block, '<span class="penulis"', "</span>")
                or _extract_first_text(block, '<div class="penulis"', "</div>")
                or ""
            )
            authors = [a.strip() for a in author_raw.split(";") if a.strip()]

            # Year - try multiple patterns
            year = (
                _extract_first_text(block, '<span class="year"', "</span>")
                or _extract_first_text(block, '<span class="date"', "</span>")
                or _extract_first_text(block, '<div class="year"', "</div>")
                or _extract_first_text(block, '<span class="tahun"', "</span>")
                or ""
            )
            year = year.strip()[:4]

            # Link
            href = (
                _extract_attr(block, 'href="')
                or _extract_attr(block, "href='")
                or _extract_attr(block, 'data-url="')
            )
            if href and not href.startswith("http"):
                href = f"https://garuda.kemdikbud.go.id{href}"

            papers.append(
                {
                    "id": href or title,
                    "title": _strip_html(title).strip(),
                    "summary": "No abstract available. See GARUDA for details.",
                    "published": year,
                    "authors": authors,
                    "pdf_link": href,
                    "source": "GARUDA",
                    "language": "id",
                }
            )

        return papers


# ---------------------------------------------------------------------------
# HTML utility helpers (no external deps)
# ---------------------------------------------------------------------------


def _strip_html(text: str) -> str:
    """Remove HTML tags from string."""
    import re

    return re.sub(r"<[^>]+>", "", text).strip()


def _extract_between(html: str, start_tag: str, end_tag: str) -> List[str]:
    """Extract all substrings between start_tag and end_tag."""
    results = []
    idx = 0
    while True:
        s = html.find(start_tag, idx)
        if s == -1:
            break
        e = html.find(end_tag, s + len(start_tag))
        if e == -1:
            break
        results.append(html[s : e + len(end_tag)])
        idx = e + len(end_tag)
    return results


def _extract_first_text(block: str, open_tag_prefix: str, close_tag: str) -> str:
    """Extract inner text of the first element matching open_tag_prefix."""
    s = block.find(open_tag_prefix)
    if s == -1:
        return ""
    # Find closing > of opening tag
    end_open = block.find(">", s)
    if end_open == -1:
        return ""
    e = block.find(close_tag, end_open)
    if e == -1:
        return ""
    inner = block[end_open + 1 : e]
    return _strip_html(inner)


def _extract_attr(block: str, attr_prefix: str) -> str:
    """Extract value of an HTML attribute (stops at quote)."""
    s = block.find(attr_prefix)
    if s == -1:
        return ""
    s += len(attr_prefix)
    # attr may start with a quote or not
    if s < len(block) and block[s] == '"':
        s += 1
    e = block.find('"', s)
    if e == -1:
        return ""
    return block[s:e]


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Crossref Indonesia ===")
    client = CrossrefIndonesiaClient()
    results = client.search_papers("machine learning", max_results=3)
    for r in results:
        print(f"  [{r['source']}] {r['title']} ({r['published']}) — {r['publisher']}")

    print("\n=== GARUDA ===")
    garuda = GarudaClient()
    results2 = garuda.search_papers("kecerdasan buatan", max_results=3)
    for r in results2:
        print(f"  [{r['source']}] {r['title']} ({r['published']})")
