"""Offline trust-boundary tests for JAYA_RESEARCH provider adapters."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from provider_errors import (  # noqa: E402
    ProviderAuthError,
    ProviderInvalidResponseError,
    ProviderNetworkError,
    ProviderPolicy,
    ProviderQuotaError,
    ProviderTimeoutError,
    ensure_http_success,
    execute_with_retry,
)
from research.academic.indonesia_sources import (  # noqa: E402
    CrossrefIndonesiaClient,
    GarudaClient,
)
from research.academic.journal_processor import JournalProcessor  # noqa: E402
from research.academic.literature import (  # noqa: E402
    ArxivClient,
    SemanticScholarClient,
)
from research.academic.novelty_checker import NoveltyChecker  # noqa: E402
from research.enhanced_rag import (  # noqa: E402
    EnhancedRAGClient,
    NVIDIAEmbeddings,
)
from research.web_search import WebSearchClient  # noqa: E402
from synthesize_knowledge import generate_knowledge_synthesis  # noqa: E402
from teacher import Teacher  # noqa: E402

NO_DELAY_POLICY = ProviderPolicy(
    connect_timeout_seconds=1,
    read_timeout_seconds=2,
    max_attempts=3,
    retry_base_delay_seconds=0,
    retry_max_delay_seconds=0,
)


def _response(
    status_code: int = 200,
    *,
    payload: object = None,
    content: bytes = b"",
    text: str = "",
    url: str = "https://provider.example/result",
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    response.json.return_value = {} if payload is None else payload
    response.content = content
    response.text = text
    response.url = url
    return response


def test_retry_is_bounded_and_only_retries_transient_failures() -> None:
    attempts = 0

    def transient_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise requests.Timeout("secret provider detail")
        return "valid"

    assert (
        execute_with_retry(
            "offline_provider",
            transient_operation,
            NO_DELAY_POLICY,
        )
        == "valid"
    )
    assert attempts == 3

    auth_response = _response(status_code=401)
    with pytest.raises(ProviderAuthError):
        ensure_http_success("offline_provider", auth_response)


def test_teacher_raises_quota_error_instead_of_returning_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    client = MagicMock()
    quota_error = RuntimeError("response body must not become knowledge")
    quota_error.status_code = 429
    client.chat.completions.create.side_effect = quota_error

    teacher = Teacher(client=client, policy=NO_DELAY_POLICY)
    with pytest.raises(ProviderQuotaError) as raised:
        teacher.ask("Use only verified evidence.")

    assert raised.value.code == "provider_quota_error"
    assert client.chat.completions.create.call_count == 1
    assert "response body" not in str(raised.value)


def test_teacher_retries_timeout_then_returns_valid_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Evidence-backed answer")
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        requests.Timeout(),
        completion,
    ]

    teacher = Teacher(client=client, policy=NO_DELAY_POLICY)
    assert teacher.ask("Question") == "Evidence-backed answer"
    assert client.chat.completions.create.call_count == 2


def test_local_embedding_provenance_is_not_labeled_nvidia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    embedder = NVIDIAEmbeddings()

    provenance = embedder.get_provenance()
    assert embedder.mode == "local_offline"
    assert provenance == {
        "provider": "jaya_local",
        "model": "sha256-feature-hashing",
        "version": "1",
        "type": "deterministic_local_fallback",
    }


def test_embedding_provenance_is_persisted_with_retrieved_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as store_dir:
        client = EnhancedRAGClient(
            vector_store_path=store_dir,
            workspace_id="offline-test",
        )
        client.web_search = None
        client.ingest_text(
            "JAYA validates research evidence provenance.",
            metadata={"source": "offline.txt"},
        )
        results = client.search("research evidence", top_k=1)

    embedding = results[0]["metadata"]["embedding"]
    assert embedding["provider"] == "jaya_local"
    assert embedding["type"] == "deterministic_local_fallback"


def test_embedding_auth_failure_never_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "invalid-key")
    monkeypatch.setenv("NVIDIA_EMBEDDING_PROVIDER_MAX_ATTEMPTS", "1")
    embedder = NVIDIAEmbeddings()

    with patch(
        "research.enhanced_rag.requests.post",
        return_value=_response(status_code=401),
    ) as request:
        with pytest.raises(ProviderAuthError):
            embedder.embed_texts(["research evidence"])

    kwargs = request.call_args.kwargs
    assert "verify" not in kwargs
    assert isinstance(kwargs["timeout"], tuple)


def test_web_search_all_failures_raise_typed_error_not_empty_results() -> None:
    ddgs = MagicMock()
    ddgs.text.side_effect = requests.Timeout()
    client = WebSearchClient(ddgs_client=ddgs, policy=NO_DELAY_POLICY)

    with patch(
        "research.web_search.requests.get",
        side_effect=requests.Timeout(),
    ) as request:
        with pytest.raises(ProviderTimeoutError):
            client.search("bounded provider test", max_results=2)

    assert ddgs.text.call_count == NO_DELAY_POLICY.max_attempts
    assert request.call_count == NO_DELAY_POLICY.max_attempts * 2
    assert all("verify" not in call.kwargs for call in request.call_args_list)


def test_web_search_success_uses_tls_defaults_and_normalized_evidence() -> None:
    ddgs = MagicMock()
    ddgs.text.return_value = []
    client = WebSearchClient(ddgs_client=ddgs, policy=NO_DELAY_POLICY)
    api_response = _response(
        payload={
            "Abstract": "A supported fact.",
            "Heading": "Verified result",
            "AbstractURL": "https://example.org/evidence",
            "RelatedTopics": [],
        }
    )

    with patch(
        "research.web_search.requests.get",
        return_value=api_response,
    ) as request:
        results = client.search("verified result", max_results=2)

    assert results[0]["snippet"] == "A supported fact."
    assert results[0]["document"]["url"].startswith("https://")
    assert "verify" not in request.call_args.kwargs
    assert request.call_args.kwargs["timeout"] == (1, 2)


def test_academic_clients_use_https_timeout_and_typed_status_errors() -> None:
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/1</id>
        <title>Bounded Research</title>
        <summary>Verified abstract.</summary>
        <published>2026-01-01T00:00:00Z</published>
        <author><name>Jaya</name></author>
        <link title="pdf" href="https://arxiv.org/pdf/1"/>
      </entry>
    </feed>"""
    client = ArxivClient(policy=NO_DELAY_POLICY)

    with patch(
        "research.academic.literature.requests.get",
        return_value=_response(content=atom),
    ) as request:
        papers = client.search_papers("bounded research", max_results=1)

    assert papers[0]["source"] == "ArXiv"
    assert request.call_args.args[0].startswith("https://")
    assert "verify" not in request.call_args.kwargs
    assert request.call_args.kwargs["timeout"] == (1, 2)

    scholar = SemanticScholarClient(policy=NO_DELAY_POLICY)
    with patch(
        "research.academic.literature.requests.get",
        return_value=_response(status_code=429),
    ):
        with pytest.raises(ProviderQuotaError):
            scholar.search_papers("quota", max_results=1)


def test_indonesia_sources_use_typed_tls_verified_adapters() -> None:
    crossref = CrossrefIndonesiaClient(policy=NO_DELAY_POLICY)
    crossref_response = _response(
        payload={
            "message": {
                "items": [
                    {
                        "DOI": "10.1/jaya",
                        "title": ["Riset Indonesia"],
                        "publisher": "Universitas Jaya Indonesia",
                        "container-title": ["Jurnal Jaya"],
                        "language": "id",
                        "published": {"date-parts": [[2026]]},
                        "author": [{"given": "Jaya", "family": "Research"}],
                        "URL": "https://example.id/paper",
                    }
                ]
            }
        }
    )
    with patch(
        "research.academic.indonesia_sources.requests.get",
        return_value=crossref_response,
    ) as request:
        papers = crossref.search_papers("riset", max_results=1)

    assert papers[0]["source"] == "Crossref Indonesia"
    assert "verify" not in request.call_args.kwargs
    assert request.call_args.kwargs["timeout"] == (1, 2)

    garuda = GarudaClient(policy=NO_DELAY_POLICY)
    garuda_response = _response(
        text="<html><body>Tidak ditemukan</body></html>",
        url="https://garuda.kemdikbud.go.id/documents?q=none",
    )
    with patch(
        "research.academic.indonesia_sources.requests.get",
        return_value=garuda_response,
    ):
        assert garuda.search_papers("none", max_results=1) == []


def test_journal_aggregator_keeps_provider_failures_out_of_evidence() -> None:
    processor = JournalProcessor.__new__(JournalProcessor)
    processor.arxiv = MagicMock()
    processor.scholar = MagicMock()
    processor.openalex = MagicMock()
    processor.crossref_id = MagicMock()
    processor.garuda = MagicMock()
    processor.arxiv.search_papers.side_effect = ProviderTimeoutError(
        "arxiv",
        "Provider request timed out",
    )
    processor.scholar.search_papers.return_value = [
        {
            "title": "Verified Paper",
            "summary": "Actual evidence",
            "source": "Semantic Scholar",
        }
    ]
    processor.openalex.search_papers.side_effect = ProviderNetworkError(
        "openalex",
        "Could not connect to provider",
    )
    processor.crossref_id.search_papers.return_value = []
    processor.garuda.search_papers.return_value = []

    papers = processor._search_free_sources("verified", max_papers=1)

    assert [paper["title"] for paper in papers] == ["Verified Paper"]
    assert len(processor.last_provider_errors) == 2
    assert all(
        "provider_" not in paper.get("summary", "")
        for paper in papers
    )


def test_pdf_download_retries_stream_timeout_and_enforces_tls() -> None:
    first_response = _response(url="https://papers.example/paper.pdf")
    first_response.iter_content.side_effect = requests.Timeout()
    second_response = _response(url="https://papers.example/paper.pdf")
    second_response.iter_content.return_value = [b"%PDF-1.7\nverified"]
    client = ArxivClient(policy=NO_DELAY_POLICY)

    with tempfile.TemporaryDirectory() as download_dir:
        with patch(
            "research.academic.literature.requests.get",
            side_effect=[first_response, second_response],
        ) as request:
            saved_path = client.download_paper(
                "http://papers.example/paper.pdf",
                Path(download_dir),
            )
        assert saved_path is not None
        assert saved_path.read_bytes().startswith(b"%PDF-")

    assert request.call_count == 2
    assert all(call.args[0].startswith("https://") for call in request.call_args_list)
    assert all("verify" not in call.kwargs for call in request.call_args_list)


def test_synthesis_never_returns_provider_failure_as_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NVIDIA_PROVIDER_MAX_ATTEMPTS", "1")

    with patch(
        "synthesize_knowledge.requests.post",
        return_value=_response(status_code=503),
    ) as request:
        with pytest.raises(ProviderNetworkError):
            generate_knowledge_synthesis("A valid source report.")

    assert "verify" not in request.call_args.kwargs
    assert "timeout" in request.call_args.kwargs


def test_novelty_is_indeterminate_when_evidence_providers_fail() -> None:
    checker = NoveltyChecker.__new__(NoveltyChecker)
    checker.brain = MagicMock()
    checker.arxiv = MagicMock()
    checker.scholar = MagicMock()
    checker.web = MagicMock()
    checker.web.is_available.return_value = True
    checker.arxiv.search_papers.side_effect = ProviderTimeoutError(
        "arxiv",
        "Provider request timed out",
    )
    checker.scholar.search_papers.side_effect = ProviderNetworkError(
        "semantic_scholar",
        "Could not connect to provider",
    )
    checker.web.search.side_effect = ProviderInvalidResponseError(
        "duckduckgo",
        "Provider returned malformed data",
    )

    result = asyncio.run(
        checker.verify_novelty(
            "A hypothesis requiring external evidence.",
            keywords=["external", "evidence"],
        )
    )

    assert result["status"] == "indeterminate"
    assert result["is_novel"] is None
    assert result["confidence"] == 0.0
    checker.brain.ask.assert_not_called()


def test_provider_sources_do_not_disable_tls_verification() -> None:
    source_files = [
        SRC_DIR / "research" / "web_search.py",
        SRC_DIR / "research" / "academic" / "literature.py",
        SRC_DIR / "research" / "academic" / "indonesia_sources.py",
        SRC_DIR / "research" / "enhanced_rag.py",
        SRC_DIR / "research" / "video_processor.py",
        SRC_DIR / "synthesize_knowledge.py",
    ]
    forbidden = ("verify=False", "CERT_NONE", "check_hostname = False")

    for source_file in source_files:
        source = source_fs.read_text(encoding="utf-8")
        assert not any(marker in source for marker in forbidden), source_file
