"""TLS-verified academic metadata and paper-download providers."""

from __future__ import annotations

import os
import re
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from jaya_research.provider_errors import (
    ProviderInvalidResponseError,
    ProviderPolicy,
    ensure_http_success,
    execute_with_retry,
)


def _request_json(
    provider: str,
    url: str,
    policy: ProviderPolicy,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    def request() -> Dict[str, Any]:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=policy.requests_timeout,
        )
        ensure_http_success(provider, response)
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderInvalidResponseError(
                provider,
                "Provider returned malformed JSON",
                cause_type=type(exc).__name__,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderInvalidResponseError(
                provider,
                "Provider response must be a JSON object",
            )
        return payload

    return execute_with_retry(provider, request, policy)


def _validated_list(
    provider: str,
    payload: Dict[str, Any],
    key: str,
) -> List[Any]:
    value = payload.get(key)
    if value is None:
        raise ProviderInvalidResponseError(
            provider,
            f"Provider response omitted '{key}'",
        )
    if not isinstance(value, list):
        raise ProviderInvalidResponseError(
            provider,
            f"Provider field '{key}' must be a list",
        )
    return value


class ArxivClient:
    """Client for the ArXiv Atom API and TLS-verified PDF downloads."""

    PROVIDER = "arxiv"
    BASE_URL = "https://export.arxiv.org/api/query"
    CATEGORY_MAP = {
        "ai": "cs.AI",
        "artificial intelligence": "cs.AI",
        "ml": "cs.LG",
        "machine learning": "cs.LG",
        "fullstack": "cs.SE",
        "software engineering": "cs.SE",
        "web": "cs.DC",
        "networking": "cs.NI",
        "cybersecurity": "cs.CR",
        "crypto": "cs.CR",
        "robotics": "cs.RO",
        "vision": "cs.CV",
    }

    def __init__(self, *, policy: Optional[ProviderPolicy] = None) -> None:
        self.policy = policy or ProviderPolicy.from_env("ACADEMIC_PROVIDER")

    def search_papers(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            return []
        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")

        search_query = self._build_search_query(query.strip())
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        def request() -> bytes:
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers={"User-Agent": "JAYA-Research/1.0"},
                timeout=self.policy.requests_timeout,
            )
            ensure_http_success(self.PROVIDER, response)
            if not isinstance(response.content, bytes):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned a non-binary Atom response",
                )
            return response.content

        payload = execute_with_retry(self.PROVIDER, request, self.policy)
        return self._parse_atom_response(payload)

    def _build_search_query(self, query: str) -> str:
        if query.startswith("cat:") or any(
            operator in query for operator in (" AND ", " OR ")
        ):
            return query

        query_lower = query.lower()
        for keyword, category in self.CATEGORY_MAP.items():
            if keyword in query_lower:
                return f"all:{query} AND cat:{category}"
        return f"all:{query}"

    def _parse_atom_response(self, xml_data: bytes) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as exc:
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider returned malformed Atom XML",
                cause_type=type(exc).__name__,
            ) from exc

        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        papers: List[Dict[str, Any]] = []
        for entry in root.findall("atom:entry", namespace):
            identifier = entry.findtext("atom:id", default="", namespaces=namespace)
            title = entry.findtext("atom:title", default="", namespaces=namespace)
            if not identifier.strip() or not title.strip():
                continue
            summary = entry.findtext(
                "atom:summary",
                default="No abstract available.",
                namespaces=namespace,
            )
            published = entry.findtext(
                "atom:published",
                default="",
                namespaces=namespace,
            )
            authors = [
                name
                for author in entry.findall("atom:author", namespace)
                if (
                    name := author.findtext(
                        "atom:name",
                        default="",
                        namespaces=namespace,
                    ).strip()
                )
            ]
            pdf_link = next(
                (
                    link.attrib.get("href")
                    for link in entry.findall("atom:link", namespace)
                    if link.attrib.get("title") == "pdf"
                ),
                None,
            )
            papers.append(
                {
                    "id": identifier.strip(),
                    "title": " ".join(title.split()),
                    "summary": " ".join(summary.split()),
                    "published": published.strip(),
                    "authors": authors,
                    "pdf_link": pdf_link,
                    "source": "ArXiv",
                }
            )
        return papers

    def download_paper(
        self,
        pdf_url: str,
        save_dir: Path,
    ) -> Optional[Path]:
        if not pdf_url:
            return None

        secure_url = self._secure_download_url(pdf_url)
        save_dir = Path(save_dir)
        filename = self._safe_pdf_filename(secure_url)
        save_path = save_dir / filename
        if save_path.exists():
            return save_path

        max_bytes = int(os.getenv("ACADEMIC_PDF_MAX_BYTES", str(50 * 1024 * 1024)))
        if not 1024 <= max_bytes <= 500 * 1024 * 1024:
            raise ValueError(
                "ACADEMIC_PDF_MAX_BYTES must be between 1024 and 524288000"
            )

        headers = {
            "User-Agent": "JAYA-Research/1.0",
            "Accept": "application/pdf,application/octet-stream;q=0.9",
        }

        def download_once() -> Path:
            response = requests.get(
                secure_url,
                headers=headers,
                timeout=self.policy.requests_timeout,
                allow_redirects=True,
                stream=True,
            )
            temp_path: Optional[Path] = None
            try:
                ensure_http_success("academic_pdf", response)
                final_scheme = urllib.parse.urlsplit(response.url).scheme.lower()
                if final_scheme != "https":
                    raise ProviderInvalidResponseError(
                        "academic_pdf",
                        "Provider redirected the download to a non-TLS URL",
                    )
                content_disposition = response.headers.get(
                    "Content-Disposition",
                    "",
                )
                response_filename = self._filename_from_disposition(
                    content_disposition
                )
                target_path = (
                    save_dir / response_filename
                    if response_filename
                    else save_path
                )
                if target_path.exists():
                    return target_path

                save_dir.mkdir(parents=True, exist_ok=True)
                byte_count = 0
                signature = b""
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=".jaya-paper-",
                    suffix=".part",
                    dir=save_dir,
                    delete=False,
                ) as file_handle:
                    temp_path = Path(file_handle.name)
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        byte_count += len(chunk)
                        if byte_count > max_bytes:
                            raise ProviderInvalidResponseError(
                                "academic_pdf",
                                "Provider PDF exceeded the configured size limit",
                            )
                        if len(signature) < 5:
                            signature += chunk[: 5 - len(signature)]
                        file_handle.write(chunk)

                if signature != b"%PDF-":
                    raise ProviderInvalidResponseError(
                        "academic_pdf",
                        "Provider response was not a PDF document",
                    )
                temp_path.replace(target_path)
                return target_path
            finally:
                response.close()
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()

        return execute_with_retry(
            "academic_pdf",
            download_once,
            self.policy,
        )

    @staticmethod
    def _secure_download_url(pdf_url: str) -> str:
        parsed = urllib.parse.urlsplit(pdf_url.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ProviderInvalidResponseError(
                "academic_pdf",
                "Paper URL must be an absolute HTTP(S) URL",
            )
        if parsed.scheme.lower() == "http":
            parsed = parsed._replace(scheme="https")
        return urllib.parse.urlunsplit(parsed)

    @classmethod
    def _safe_pdf_filename(cls, pdf_url: str) -> str:
        raw_name = Path(urllib.parse.unquote(urllib.parse.urlsplit(pdf_url).path)).name
        if not raw_name.lower().endswith(".pdf"):
            raw_name = f"{raw_name}.pdf"
        return cls._sanitize_filename(raw_name)

    @classmethod
    def _filename_from_disposition(cls, value: str) -> Optional[str]:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', value, re.I)
        if not match:
            return None
        candidate = urllib.parse.unquote(match.group(1).strip())
        if not candidate.lower().endswith(".pdf"):
            return None
        return cls._sanitize_filename(candidate)

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        safe_name = "".join(
            character
            for character in Path(value).name
            if character.isalnum() or character in "._-"
        )[:180]
        if safe_name in {"", ".", "..", ".pdf"}:
            safe_name = "paper.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name = f"{safe_name}.pdf"
        return safe_name


class SemanticScholarClient:
    """Client for the Semantic Scholar Graph API."""

    PROVIDER = "semantic_scholar"
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, *, policy: Optional[ProviderPolicy] = None) -> None:
        self.policy = policy or ProviderPolicy.from_env("ACADEMIC_PROVIDER")

    def _headers(self) -> Dict[str, str]:
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        return {"x-api-key": api_key} if api_key else {}

    def search_papers(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            return []
        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")

        payload = _request_json(
            self.PROVIDER,
            self.BASE_URL,
            self.policy,
            params={
                "query": query.strip(),
                "limit": max_results,
                "fields": "title,abstract,year,authors,url,openAccessPdf",
            },
            headers=self._headers(),
        )
        papers: List[Dict[str, Any]] = []
        for item in _validated_list(self.PROVIDER, payload, "data"):
            if not isinstance(item, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned a malformed paper record",
                )
            open_access = item.get("openAccessPdf")
            if open_access is not None and not isinstance(open_access, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned malformed open-access metadata",
                )
            authors = item.get("authors") or []
            if not isinstance(authors, list):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned malformed author metadata",
                )
            papers.append(
                {
                    "id": item.get("paperId"),
                    "title": item.get("title"),
                    "summary": item.get("abstract") or "No abstract available.",
                    "published": str(item.get("year") or ""),
                    "authors": [
                        str(author.get("name"))
                        for author in authors
                        if isinstance(author, dict) and author.get("name")
                    ],
                    "pdf_link": (
                        open_access.get("url") if open_access else item.get("url")
                    ),
                    "source": "Semantic Scholar",
                }
            )
        return papers

    def get_citations(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if not paper_id:
            return []
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        payload = _request_json(
            self.PROVIDER,
            (
                "https://api.semanticscholar.org/graph/v1/paper/"
                f"{urllib.parse.quote(paper_id, safe='')}/citations"
            ),
            self.policy,
            params={
                "limit": limit,
                "fields": "title,abstract,year,authors,url",
            },
            headers=self._headers(),
        )
        citations: List[Dict[str, Any]] = []
        for item in _validated_list(self.PROVIDER, payload, "data"):
            if not isinstance(item, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned a malformed citation record",
                )
            citing_paper = item.get("citingPaper")
            if not isinstance(citing_paper, dict):
                continue
            authors = citing_paper.get("authors") or []
            citations.append(
                {
                    "id": citing_paper.get("paperId"),
                    "title": citing_paper.get("title"),
                    "year": citing_paper.get("year"),
                    "authors": [
                        str(author.get("name"))
                        for author in authors
                        if isinstance(author, dict) and author.get("name")
                    ],
                    "source": "Semantic Scholar",
                }
            )
        return citations


class OpenAlexClient:
    """Client for OpenAlex scholarly metadata."""

    PROVIDER = "openalex"
    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, *, policy: Optional[ProviderPolicy] = None) -> None:
        self.policy = policy or ProviderPolicy.from_env("ACADEMIC_PROVIDER")

    def search_papers(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            return []
        if max_results <= 0:
            raise ValueError("max_results must be greater than zero")

        payload = _request_json(
            self.PROVIDER,
            self.BASE_URL,
            self.policy,
            params={
                "search": query.strip(),
                "per-page": max_results,
                "sort": "cited_by_count:desc",
            },
        )
        papers: List[Dict[str, Any]] = []
        for item in _validated_list(self.PROVIDER, payload, "results"):
            if not isinstance(item, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned a malformed work record",
                )
            authors = [
                str(author.get("display_name"))
                for authorship in item.get("authorships") or []
                if isinstance(authorship, dict)
                and isinstance((author := authorship.get("author")), dict)
                and author.get("display_name")
            ]
            primary_location = item.get("primary_location") or {}
            if not isinstance(primary_location, dict):
                raise ProviderInvalidResponseError(
                    self.PROVIDER,
                    "Provider returned malformed location metadata",
                )
            landing_page = primary_location.get("landing_page_url")
            pdf_url = primary_location.get("pdf_url")
            summary = self._reconstruct_abstract(item.get("abstract_inverted_index"))
            papers.append(
                {
                    "id": item.get("id"),
                    "title": item.get("display_name"),
                    "summary": summary
                    or item.get("display_name")
                    or "No abstract available.",
                    "published": str(item.get("publication_year") or ""),
                    "authors": authors,
                    "pdf_link": pdf_url or landing_page,
                    "source": "OpenAlex",
                    "doi": item.get("doi"),
                    "landing_page_url": landing_page,
                }
            )
        return papers

    @staticmethod
    def _reconstruct_abstract(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        positions: list[tuple[int, str]] = []
        for word, raw_positions in value.items():
            if not isinstance(word, str) or not isinstance(raw_positions, list):
                continue
            for position in raw_positions:
                if isinstance(position, int) and position >= 0:
                    positions.append((position, word))
        return " ".join(word for _, word in sorted(positions))


if __name__ == "__main__":
    arxiv = ArxivClient()
    print(len(arxiv.search_papers("ReactJS", 1)))
