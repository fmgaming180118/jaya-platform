"""Deterministic Phase A API workflow and failure-boundary tests."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ["JAYA_ENV"] = "test"
os.environ["JAYA_HTTP_SECURITY_TEST_MODE"] = "1"

from jaya_research.network import research_api  # noqa: E402
from jaya_research.network.research_api import app  # noqa: E402
from jaya_research.network.route_audit import validate_route_contract  # noqa: E402
from jaya_research.research.academic.thesis_session_repository import (  # noqa: E402
    PersistentThesisSessions,
    ThesisSessionRepository,
)
from jaya_research.research.multimodal_pdf import (  # noqa: E402
    PDFExtractionCode,
    PDFExtractionError,
)
from jaya_research.research.workspace_manager import WorkspaceManager  # noqa: E402


class InMemoryRAG:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.available = True

    def ingest_text(self, text: str, metadata: dict | None = None) -> dict:
        if not self.available:
            raise RuntimeError("offline provider unavailable")
        self.records.append({"content": text, "metadata": dict(metadata or {})})
        return {"status": "success", "chunks_added": 1}

    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace_id: str = "default",
    ) -> list[dict]:
        del workspace_id
        if not self.available:
            raise RuntimeError("offline provider unavailable")
        query_tokens = set(query.casefold().split())
        matches = []
        for record in self.records:
            text_tokens = set(record["content"].casefold().split())
            if query_tokens & text_tokens:
                matches.append(
                    {
                        "content": record["content"],
                        "snippet": record["content"],
                        "metadata": record["metadata"],
                        "score": 0.91,
                        "score_kind": "DETERMINISTIC_TEST_OVERLAP",
                    }
                )
        return matches[:top_k]


class NoopGraph:
    def ingest_document(self, *_args, **_kwargs) -> None:
        return None


def _fake_pdf_document(source_uri: str, license_id: str):
    text = "Metode penelitian menggunakan evaluasi retrieval yang dapat direproduksi."
    source_sha256 = hashlib.sha256(b"fake-pdf").hexdigest()
    page = SimpleNamespace(page_number=1, text=text)
    payload = {
        "document_name": "thesis.pdf",
        "total_pages": 1,
        "full_text": text,
        "status": "COMPLETE",
        "warnings": [],
        "pages": [
            {
                "page_number": 1,
                "text": text,
                "extraction_method": "PDF_TEXT",
            }
        ],
        "metadata": {
            "source_uri": source_uri,
            "source_sha256": source_sha256,
            "license_id": license_id,
            "promotable": license_id != "UNKNOWN",
        },
    }
    return SimpleNamespace(
        status="COMPLETE",
        full_text=text,
        total_pages=1,
        pages=[page],
        warnings=[],
        metadata=payload["metadata"],
        to_dict=lambda: payload,
    )


class FakePDFExtractor:
    def __init__(self, **_kwargs) -> None:
        pass

    def extract(self, _path, *, source_uri: str, license_id: str):
        return _fake_pdf_document(source_uri, license_id)


@pytest.fixture
def phase_a_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    manager = WorkspaceManager(base_dir=tmp_path / "workspaces")
    rag = InMemoryRAG()
    graph = NoopGraph()
    sessions = PersistentThesisSessions(
        ThesisSessionRepository(tmp_path / "thesis_sessions.db")
    )
    monkeypatch.setattr(research_api, "workspace_manager", manager)
    monkeypatch.setattr(research_api, "active_sessions", {})
    monkeypatch.setattr(research_api, "get_engines", lambda _workspace: (rag, graph))
    monkeypatch.setattr(research_api, "_thesis_sessions", sessions)
    monkeypatch.setattr(research_api, "PDFExtractorFactory", FakePDFExtractor)
    monkeypatch.setattr(research_api, "ThesisAnalysisProvider", None)
    return manager, rag


client = TestClient(app)


def test_workspace_ingest_chat_citation_and_deep_artifact_e2e(
    phase_a_runtime,
) -> None:
    manager, _ = phase_a_runtime
    created = client.post(
        "/workspaces/create",
        params={"name": "Phase A", "description": "offline evidence"},
    )
    assert created.status_code == 200
    workspace_id = created.json()["id"]

    source_text = "Retrieval evaluation requires traceable citations and fixed inputs."
    ingested = client.post(
        "/ingest",
        json={
            "workspace_id": workspace_id,
            "text": source_text,
            "license_id": "CC0-1.0",
            "metadata": {"title": "Phase A evidence"},
        },
    )
    assert ingested.status_code == 200
    receipt = ingested.json()
    assert receipt["status"] == "INDEXED"
    assert receipt["promotable"] is False
    assert receipt["source_uri"].startswith("sources/")

    chat = client.post(
        "/chat",
        json={"workspace_id": workspace_id, "message": "traceable citations"},
    )
    assert chat.status_code == 200
    answer = chat.json()
    assert answer["status"] == "ANSWERED"
    assert answer["uses_internal_knowledge"] is False
    assert answer["synthesis_provider"] == "NOT_USED_EXTRACTIVE_ONLY"
    assert answer["citations"][0]["source_uri"] == receipt["source_uri"]
    assert "Retrieval evaluation" in answer["answer"]

    opened = client.get(
        "/citations/open",
        params={"workspace_id": workspace_id, "source_uri": receipt["source_uri"]},
    )
    assert opened.status_code == 200
    assert opened.content.decode("utf-8") == source_text

    deep = client.post(
        "/research/recursive",
        json={"workspace_id": workspace_id, "query": "retrieval evaluation", "depth": 3},
    )
    assert deep.status_code == 200
    artifact = deep.json()
    assert artifact["status"] == "ANSWERED"
    assert artifact["depth_reached"] == 1
    artifact_path = Path(manager.get_paths(workspace_id)["root"]) / artifact["artifact_uri"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["artifact_sha256"]
    stored = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert stored["uses_internal_knowledge"] is False
    assert stored["citations"][0]["source_uri"] == receipt["source_uri"]


@pytest.mark.parametrize("route", ["/ingest", "/chat", "/research/recursive"])
def test_unknown_workspace_is_not_created(phase_a_runtime, route: str) -> None:
    manager, _ = phase_a_runtime
    payload = {
        "/ingest": {"workspace_id": "missing", "text": "valid source"},
        "/chat": {"workspace_id": "missing", "message": "question"},
        "/research/recursive": {"workspace_id": "missing", "query": "question"},
    }[route]

    response = client.post(route, json=payload)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "WORKSPACE_NOT_FOUND"
    assert not (manager.base_dir / "missing").exists()


@pytest.mark.parametrize(
    "route,payload",
    [
        ("/ingest", {"text": "   ", "workspace_id": "default"}),
        ("/chat", {"message": "   ", "workspace_id": "default"}),
        ("/research/recursive", {"query": "x", "depth": 6, "workspace_id": "default"}),
        ("/research/recursive", {"query": "", "workspace_id": "default"}),
    ],
)
def test_bounded_request_validation(phase_a_runtime, route: str, payload: dict) -> None:
    del phase_a_runtime
    response = client.post(route, json=payload)
    assert response.status_code == 422


def test_empty_retrieval_abstains_without_calling_a_generator(phase_a_runtime) -> None:
    del phase_a_runtime
    response = client.post(
        "/chat",
        json={"workspace_id": "default", "message": "unknown evidence"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ABSTAINED_NO_EVIDENCE"
    assert payload["citations"] == []
    assert payload["promotable"] is False
    assert payload["uses_internal_knowledge"] is False


def test_provider_unavailable_is_a_typed_error(phase_a_runtime, monkeypatch) -> None:
    del phase_a_runtime

    def unavailable(_workspace):
        raise RuntimeError("secret provider detail must not leak")

    monkeypatch.setattr(research_api, "get_engines", unavailable)
    response = client.post(
        "/chat",
        json={"workspace_id": "default", "message": "question"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PROVIDER_UNAVAILABLE",
        "capability": "grounded_retrieval",
        "message": "grounded_retrieval is not available for this request",
    }
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "source_uri",
    ["../metadata.json", "sources/../../metadata.json", "file:///etc/passwd", "%252e%252e/secret"],
)
def test_citation_open_rejects_noncanonical_paths(phase_a_runtime, source_uri: str) -> None:
    del phase_a_runtime
    response = client.get(
        "/citations/open",
        params={"workspace_id": "default", "source_uri": source_uri},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] in {
        "INVALID_SOURCE_URI",
        "SOURCE_PATH_ESCAPE",
    }


def test_pdf_requested_optional_capability_fails_closed(phase_a_runtime) -> None:
    del phase_a_runtime
    response = client.post(
        "/documents/ingest-pdf",
        params={"workspace_id": "default", "analyze_with_llm": "true"},
        files={"file": ("paper.pdf", b"%PDF-1.7\nbody", "application/pdf")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PROVIDER_UNAVAILABLE"


def test_corrupt_pdf_maps_canonical_typed_error(phase_a_runtime, monkeypatch) -> None:
    del phase_a_runtime

    class CorruptExtractor(FakePDFExtractor):
        def extract(self, _path, **_kwargs):
            raise PDFExtractionError(
                PDFExtractionCode.INVALID_PDF,
                "PDF structure is malformed or unsupported",
            )

    monkeypatch.setattr(research_api, "PDFExtractorFactory", CorruptExtractor)
    response = client.post(
        "/documents/ingest-pdf",
        params={"workspace_id": "default"},
        files={"file": ("corrupt.pdf", b"%PDF-1.7\ncorrupt", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PDF"


def test_ocr_required_is_not_reported_as_success(phase_a_runtime, monkeypatch) -> None:
    del phase_a_runtime

    class OCRRequiredExtractor(FakePDFExtractor):
        def extract(self, _path, **_kwargs):
            return SimpleNamespace(
                status="PARTIAL_OCR_REQUIRED",
                full_text="",
                total_pages=1,
                pages=[],
                warnings=["Embedded text unavailable on page 1"],
                metadata={"promotable": False},
                to_dict=lambda: {
                    "status": "PARTIAL_OCR_REQUIRED",
                    "full_text": "",
                    "warnings": ["Embedded text unavailable on page 1"],
                },
            )

    monkeypatch.setattr(research_api, "PDFExtractorFactory", OCRRequiredExtractor)
    response = client.post(
        "/documents/ingest-pdf",
        params={"workspace_id": "default"},
        files={"file": ("scan.pdf", b"%PDF-1.7\nscan", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "OCR_REQUIRED"
    assert response.json()["detail"]["artifact_uri"].startswith(
        "artifacts/pdf_extractions/"
    )


def test_oversize_pdf_is_rejected_before_parser(
    phase_a_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del phase_a_runtime
    monkeypatch.setenv("JAYA_UPLOAD_MAX_FILE_BYTES", "10")
    response = client.post(
        "/documents/ingest-pdf",
        params={"workspace_id": "default"},
        files={"file": ("large.pdf", b"%PDF-" + (b"x" * 100), "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_thesis_extraction_status_and_injected_analysis_artifact(
    phase_a_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _ = phase_a_runtime
    uploaded = client.post(
        "/thesis/upload",
        params={"workspace_id": "default", "license_id": "CC0-1.0"},
        files={"file": ("thesis.pdf", b"%PDF-1.7\nthesis", "application/pdf")},
    )
    assert uploaded.status_code == 200
    upload_payload = uploaded.json()
    assert upload_payload["status"] == "EXTRACTED"
    assert upload_payload["artifact_uri"].startswith("artifacts/thesis_extractions/")
    session_id = upload_payload["session_id"]

    unavailable = client.post(f"/thesis/analyze/{session_id}")
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "PROVIDER_UNAVAILABLE"
    unavailable_status = client.get(f"/thesis/status/{session_id}").json()
    assert unavailable_status["status"] == "PROVIDER_UNAVAILABLE"
    assert unavailable_status["extraction_artifact_sha256"]

    class InjectedProvider:
        @staticmethod
        def analyze(**kwargs) -> dict:
            assert kwargs["source_uri"].startswith("thesis_uploads/")
            return {"summary": "Provider output requiring human verification"}

    monkeypatch.setattr(research_api, "ThesisAnalysisProvider", InjectedProvider())
    started = client.post(f"/thesis/analyze/{session_id}")
    assert started.status_code == 200
    status = client.get(f"/thesis/status/{session_id}").json()
    assert status["status"] == "done"
    assert status["evidence_status"] == "UNVERIFIED_PROVIDER_ANALYSIS"
    assert status["promotable"] is False
    artifact_path = Path(manager.get_paths("default")["root"]) / status["analysis_artifact_uri"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == status[
        "analysis_artifact_sha256"
    ]


def test_route_inventory_has_no_duplicate_method_and_path() -> None:
    records = validate_route_contract(app)
    keys = [(record.method, record.normalized_path) for record in records]
    assert len(keys) == len(set(keys))


def test_api_import_keeps_optional_generation_and_pdf_providers_lazy() -> None:
    assert "Teacher" not in research_api.__dict__
    assert research_api.ResearchAgent is None
