"""API Phase A and workspace-boundary regression tests."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# The production application is fail-closed without API credentials. This
# process-local bypass is accepted only when both explicit test flags are set.
os.environ["JAYA_ENV"] = "test"
os.environ["JAYA_HTTP_SECURITY_TEST_MODE"] = "1"

from network import research_api  # noqa: E402
from network.research_api import app  # noqa: E402
from network.job_repository import DurableJobRepository  # noqa: E402
from research.workspace_manager import (  # noqa: E402
    WorkspaceManager,
    WorkspaceSecurityError,
)


class DummyRAG:
    def __init__(self):
        self.ingested = []

    def ingest_text(self, text, metadata=None):
        self.ingested.append((text, metadata))
        return {"status": "success", "chunks_added": 1, "workspace_id": "default"}

    def search(self, query, top_k=5, workspace_id="default"):
        return [
            {
                "document": {"file_name": "doc.md"},
                "snippet": f"match for {query}",
                "score": 0.9,
            }
        ]


class DummyGraph:
    def get_context(self, query):
        return f"graph context for {query}"


client = TestClient(app)


@patch("network.research_api.get_engines")
def test_ingest_endpoint(mock_get_engines):
    dummy_rag = DummyRAG()
    mock_get_engines.return_value = (dummy_rag, DummyGraph())

    response = client.post(
        "/ingest",
        json={
            "text": "hello rag",
            "metadata": {"source": "notes.md"},
            "workspace_id": "default",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["chunks_added"] == 1


@patch("network.research_api.get_engines")
def test_recursive_research_endpoint(mock_get_engines):
    dummy_rag = DummyRAG()
    mock_get_engines.return_value = (dummy_rag, DummyGraph())

    response = client.post(
        "/research/recursive",
        json={"query": "RAG", "depth": 2, "workspace_id": "default"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "RAG"
    assert payload["depth_reached"] >= 1
    assert payload["sources"]
    assert (
        "Vector Context" in payload["synthesis"]
        or "Graph Context" in payload["synthesis"]
    )


@pytest.fixture
def workspace_manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(base_dir=tmp_path / "workspaces")


def _create_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (NotImplementedError, OSError) as exc:
        symlink_error = exc

    if os.name == "nt":
        result = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(link),
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return

    pytest.skip(f"Directory links are unavailable in this environment: {symlink_error}")


def _remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
        return
    is_junction = getattr(link, "is_junction", None)
    if is_junction and is_junction():
        link.rmdir()


def test_workspace_paths_are_canonical_and_contained(
    workspace_manager: WorkspaceManager,
) -> None:
    result = workspace_manager.create_workspace(
        "My Secure Study",
        description="Path containment test",
    )

    assert result["status"] == "success"
    assert result["id"] == "my_secure_study"

    paths = workspace_manager.get_paths("MY_SECURE_STUDY")
    assert set(paths) == {"root", "vector_store", "knowledge_graph"}
    assert Path(paths["root"]).name == "my_secure_study"

    for raw_path in paths.values():
        canonical_path = Path(raw_path).resolve(strict=False)
        canonical_path.relative_to(workspace_manager.base_dir)


@pytest.mark.parametrize(
    "workspace_id",
    [
        "",
        " ",
        ".",
        "..",
        "../escape",
        "..\\escape",
        "safe/name",
        "safe\\name",
        "/tmp/escape",
        r"C:\temp\escape",
        r"C:relative-drive-path",
        r"\\server\share",
        "%2e%2e%2fescape",
        "%252e%252e%252fescape",
        "safe%2Fescape",
        "safe%5Cescape",
        "safe%252Fescape",
        "name with spaces",
        "nul",
    ],
)
@pytest.mark.parametrize(
    "operation_name",
    [
        "get_paths",
        "get_or_create_paths",
        "delete_workspace",
    ],
)
def test_workspace_id_operations_reject_unsafe_input(
    workspace_manager: WorkspaceManager,
    workspace_id: str,
    operation_name: str,
) -> None:
    operation: Callable[[str], object] = getattr(
        workspace_manager,
        operation_name,
    )

    with pytest.raises(WorkspaceSecurityError):
        operation(workspace_id)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "..\\escape",
        "/tmp/escape",
        r"C:\temp\escape",
        r"\\server\share",
        "%2e%2e%2fescape",
        "safe%252Fescape",
    ],
)
def test_create_workspace_rejects_path_like_names(
    workspace_manager: WorkspaceManager,
    name: str,
) -> None:
    with pytest.raises(WorkspaceSecurityError):
        workspace_manager.create_workspace(name)


def test_traversal_never_touches_outside_directory(
    workspace_manager: WorkspaceManager,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "escape"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("must survive", encoding="utf-8")

    for operation in (
        workspace_manager.get_paths,
        workspace_manager.get_or_create_paths,
        workspace_manager.delete_workspace,
    ):
        with pytest.raises(WorkspaceSecurityError):
            operation("../escape")

    assert marker.read_text(encoding="utf-8") == "must survive"


def test_workspace_root_symlink_escape_is_rejected(
    workspace_manager: WorkspaceManager,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-root"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("outside", encoding="utf-8")
    link = workspace_manager.base_dir / "escape"
    _create_directory_link(link, outside)

    try:
        for operation in (
            workspace_manager.get_paths,
            workspace_manager.get_or_create_paths,
            workspace_manager.delete_workspace,
        ):
            with pytest.raises(WorkspaceSecurityError):
                operation("escape")

        with pytest.raises(WorkspaceSecurityError):
            workspace_manager.create_workspace("escape")

        assert marker.read_text(encoding="utf-8") == "outside"
        assert workspace_manager._is_linklike(link)
    finally:
        _remove_directory_link(link)


def test_child_symlink_escape_blocks_get_and_delete(
    workspace_manager: WorkspaceManager,
    tmp_path: Path,
) -> None:
    paths = workspace_manager.get_or_create_paths("secured")
    vector_store = Path(paths["vector_store"])
    vector_store.rmdir()

    outside = tmp_path / "outside-vector-store"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("outside", encoding="utf-8")
    _create_directory_link(vector_store, outside)

    try:
        with pytest.raises(WorkspaceSecurityError):
            workspace_manager.get_paths("secured")
        with pytest.raises(WorkspaceSecurityError):
            workspace_manager.get_or_create_paths("secured")
        with pytest.raises(WorkspaceSecurityError):
            workspace_manager.delete_workspace("secured")

        assert marker.read_text(encoding="utf-8") == "outside"
        assert workspace_manager._is_linklike(vector_store)
    finally:
        _remove_directory_link(vector_store)


def test_delete_removes_only_validated_workspace(
    workspace_manager: WorkspaceManager,
    tmp_path: Path,
) -> None:
    workspace_paths = workspace_manager.get_or_create_paths("temporary")
    workspace_root = Path(workspace_paths["root"])
    (workspace_root / "result.txt").write_text("result", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("outside", encoding="utf-8")

    result = workspace_manager.delete_workspace("temporary")

    assert result["status"] == "success"
    assert not workspace_root.exists()
    assert workspace_manager.get_paths("default")["root"] == str(
        workspace_manager.base_dir / "default"
    )
    assert marker.read_text(encoding="utf-8") == "outside"


def test_cors_is_allowlisted_and_never_wildcard_with_credentials() -> None:
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert cors.kwargs["allow_origins"]
    assert cors.kwargs["allow_origins"] != ["*"]
    assert cors.kwargs["allow_methods"] != ["*"]
    assert cors.kwargs["allow_headers"] != ["*"]


def test_evolution_start_fails_closed_without_server_consent_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAYA_AUTONOMOUS_CONSENT_TOKEN", raising=False)

    response = client.post(
        "/evolution/start-autonomous-loop",
        json={
            "consent_token": "not-configured",
            "topics": ["Evidence quality"],
            "max_iterations": 1,
            "interval_seconds": 30,
        },
    )

    assert response.status_code == 503
    assert research_api._is_autonomous_loop_running is False


def test_evolution_start_rejects_wrong_consent_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAYA_AUTONOMOUS_CONSENT_TOKEN", "s" * 32)

    response = client.post(
        "/evolution/start-autonomous-loop",
        json={
            "consent_token": "x" * 32,
            "topics": ["Evidence quality"],
            "max_iterations": 1,
            "interval_seconds": 30,
        },
    )

    assert response.status_code == 403
    assert research_api._is_autonomous_loop_running is False


def test_evolution_start_is_bounded_and_process_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "s" * 32
    saved_states: list[bool] = []

    async def no_op_worker() -> None:
        research_api._is_autonomous_loop_running = False

    monkeypatch.setenv("JAYA_AUTONOMOUS_CONSENT_TOKEN", token)
    monkeypatch.setattr(
        research_api,
        "_continuous_autonomous_research_worker",
        no_op_worker,
    )
    monkeypatch.setattr(research_api, "_save_loop_state", saved_states.append)
    research_api._is_autonomous_loop_running = False

    response = client.post(
        "/evolution/start-autonomous-loop",
        json={
            "consent_token": token,
            "topics": ["Evidence quality"],
            "max_iterations": 2,
            "interval_seconds": 30,
        },
    )

    assert response.status_code == 200
    assert response.json()["max_iterations"] == 2
    assert response.json()["core_mutation_enabled"] is False
    assert saved_states == [False]


@pytest.mark.asyncio
async def test_lifespan_clears_persisted_loop_instead_of_restoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_states: list[bool] = []
    monkeypatch.setattr(research_api, "_read_loop_state", lambda: True)
    monkeypatch.setattr(research_api, "_save_loop_state", saved_states.append)
    monkeypatch.setattr(research_api, "digital_twin", None)
    research_api._is_autonomous_loop_running = True

    async with research_api.lifespan(app):
        assert research_api._is_autonomous_loop_running is False
        assert research_api._auto_loop_task is None

    assert saved_states == [False, False]


def test_one_shot_candidate_endpoint_never_claims_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "s" * 32
    monkeypatch.setenv("JAYA_AUTONOMOUS_CONSENT_TOKEN", token)
    monkeypatch.setattr(
        research_api,
        "_do_auto_upgrade_sync",
        lambda topic: {
            "topic": topic,
            "candidate_status": "REJECTED_SIMULATION",
            "evidence_kind": "SIMULATION",
            "auto_deployed": False,
            "core_mutated": False,
        },
    )

    response = client.post(
        "/evolution/auto-upgrade",
        json={"consent_token": token, "topic": "Evidence quality"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["core_mutated"] is False
    assert "injected" not in payload["message"].casefold()
    assert "deployed" not in payload["message"].casefold()


def test_research_job_is_durable_idempotent_and_reports_real_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = DurableJobRepository(tmp_path / "jobs.db")
    ingested_reports: list[tuple[str, str]] = []

    class FakeResearchAgent:
        def __init__(self, *, topic: str, focus_areas: str, workspace: str):
            assert topic == "Grounded systems"
            assert workspace == "default"
            self.config = SimpleNamespace(max_queries=5)

        def run(self, *, human_in_loop: bool) -> str:
            assert human_in_loop is False
            return "Evidence-labelled research report"

    class FakeGraph:
        def ingest_document(self, report: str, title: str) -> None:
            ingested_reports.append((report, title))

    monkeypatch.setattr(research_api, "_job_repository", repository)
    monkeypatch.setattr(research_api, "ResearchAgent", FakeResearchAgent)
    monkeypatch.setattr(
        research_api,
        "get_engines",
        lambda _workspace: (DummyRAG(), FakeGraph()),
    )
    request_payload = {
        "topic": "Grounded systems",
        "focus_areas": "provenance",
        "max_queries": 3,
        "workspace_id": "default",
    }

    first = client.post(
        "/research/autonomous",
        headers={"Idempotency-Key": "research-request-0001"},
        json=request_payload,
    )
    repeated = client.post(
        "/research/autonomous",
        headers={"Idempotency-Key": "research-request-0001"},
        json=request_payload,
    )

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert first.json()["created"] is True
    assert repeated.json()["created"] is False
    job_id = first.json()["job"]["job_id"]
    stored = repository.get(job_id)
    assert stored.state.value == "SUCCEEDED"
    assert stored.result["evidence_status"] == "UNVERIFIED_RESEARCH_REPORT"
    assert stored.result["core_mutated"] is False
    assert len(stored.result["report_sha256"]) == 64
    assert ingested_reports == [
        ("Evidence-labelled research report", "Research: Grounded systems")
    ]

    status_response = client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["job"]["state"] == "SUCCEEDED"


def test_research_job_cancel_is_persistent_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = DurableJobRepository(tmp_path / "jobs.db")
    job, _ = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="research-request-0002",
        payload={"topic": "Canceled", "focus_areas": "", "max_queries": 1},
    )
    monkeypatch.setattr(research_api, "_job_repository", repository)

    first = client.post(f"/jobs/{job.job_id}/cancel")
    repeated = client.post(f"/jobs/{job.job_id}/cancel")

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert first.json()["job"]["state"] == "CANCELED"
    assert repeated.json()["job"]["state"] == "CANCELED"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
