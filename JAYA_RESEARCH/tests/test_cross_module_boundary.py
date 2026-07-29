from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from src.brain.system_control import SystemController
from src.capability_boundary import (
    ArbitraryExecutionRejected,
    CapabilityUnavailableError,
)
from src.memory_manager import EcosystemBoundaryError, MemoryManager
from src.sandbox import Sandbox
from src.tools.system.cmd_runner import CmdRunnerTool
from src.voice_agent.agent import JayaVoiceAgent

_RESEARCH_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _RESEARCH_ROOT.parent


class _RecordingGateway:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def request(self, request: Any) -> dict[str, str]:
        self.requests.append(request)
        return {"status": "accepted"}


class _Publisher:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def publish(self, artifact_path: Path, metadata: Any) -> dict[str, Any]:
        self.paths.append(artifact_path)
        return {"artifact": artifact_path.name, "metadata": dict(metadata)}


def test_research_python_has_no_core_internal_imports() -> None:
    offenders: list[str] = []
    for root in (_RESEARCH_ROOT / "src", _RESEARCH_ROOT / "scripts"):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any(
                    name == "JAYA_CORE"
                    or name.startswith("JAYA_CORE.")
                    or name == "src.brain_v2"
                    or name.startswith("src.brain_v2.")
                    for name in names
                ):
                    offenders.append(f"{path}:{node.lineno}")
    assert offenders == []


def test_legacy_source_execution_does_not_run_marker(tmp_path: Path) -> None:
    marker = tmp_path / "source-executed.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"
    sandbox = Sandbox(work_dir=tmp_path / "sandbox")

    with pytest.raises(ArbitraryExecutionRejected):
        sandbox.run_isolated_python(code)
    with pytest.raises(ArbitraryExecutionRejected):
        sandbox.run_c_code("int main(void) { return 0; }")
    assert not marker.exists()
    assert not (tmp_path / "sandbox").exists()


def test_raw_system_command_does_not_run_marker(tmp_path: Path) -> None:
    marker = tmp_path / "shell-executed.txt"
    controller = SystemController()
    command = f"python -c \"open(r'{marker}', 'w').write('bad')\""

    with pytest.raises(ArbitraryExecutionRejected):
        controller.run_command(command)
    assert not marker.exists()


def test_profile_tool_fails_closed_without_gateway() -> None:
    tool = CmdRunnerTool()
    with pytest.raises(CapabilityUnavailableError):
        tool.execute(profile="safe-readonly-profile")


def test_memory_sync_never_copies_database(tmp_path: Path) -> None:
    database = tmp_path / "research.db"
    database.write_bytes(b"research-owned")
    manager = MemoryManager(db_path=database, packages_dir=tmp_path / "packages")

    with pytest.raises(EcosystemBoundaryError):
        manager.sync_to_ecosystem()
    assert database.read_bytes() == b"research-owned"
    assert list(tmp_path.rglob("agentic_jarvis.db")) == []

    package = manager.packages_dir / "JAYA_MILESTONE_v1_m1.jay"
    package.write_text("candidate", encoding="utf-8")
    publisher = _Publisher()
    result = manager.sync_to_ecosystem(publisher)
    assert result["database_copied"] is False
    assert publisher.paths == [package.resolve()]


def test_voice_rejects_shell_before_capability_gateway(tmp_path: Path) -> None:
    gateway = _RecordingGateway()
    marker = tmp_path / "voice-shell-marker.txt"
    agent = JayaVoiceAgent(capability_gateway=gateway)

    response = agent.handle_command(
        f"eksekusi shell python -c open({str(marker)!r}, 'w')"
    )
    assert "ditolak" in response.casefold()
    assert gateway.requests == []
    assert not marker.exists()


def test_scoped_legacy_files_contain_no_process_or_cross_copy_primitive() -> None:
    relative_paths = (
        "src/brain/system_control.py",
        "src/tools/system/cmd_runner.py",
        "src/sandbox.py",
        "src/test_execution.py",
        "src/memory_manager.py",
        "src/discovery.py",
        "src/refactor.py",
        "src/launcher.py",
        "src/voice_agent/agent.py",
        "scripts/quantize_convert.py",
    )
    forbidden = (
        "subprocess.run",
        "subprocess.Popen",
        "shell=True",
        "os.system",
        "shutil.copy",
        "copytree(",
        "src.brain_v2",
        "Genesis123",
    )
    for relative in relative_paths:
        source = (_RESEARCH_ROOT / relative).read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden), relative


def test_root_legacy_scripts_are_verifier_or_canonical_wrapper_only() -> None:
    demo = (_WORKSPACE_ROOT / "scripts/demo_autonomous_research_upgrade.py").read_text(
        encoding="utf-8"
    )
    execution = (_WORKSPACE_ROOT / "scripts/verify_real_code_execution.py").read_text(
        encoding="utf-8"
    )
    server = (_WORKSPACE_ROOT / "scripts/run_jaya_core_server.py").read_text(
        encoding="utf-8"
    )

    assert "ResearchFinding(" not in demo
    assert "EvolutionGate" not in demo
    assert "exec_module" not in execution
    assert "spec_from_file_location" not in execution
    assert "HTTPServer" not in server
    assert "BaseHTTPRequestHandler" not in server
    assert "_pillar21_fallback" not in server
    assert "from src.core_service import create_app" in server


def test_discovery_exports_candidate_without_mutating_source(tmp_path: Path) -> None:
    from src.discovery import ScientificDiscovery

    class _Teacher:
        @staticmethod
        def suggest_optimization(_prompt: str, *, focus: str) -> str:
            assert focus == "review-only source optimization"
            return "VALUE = 2\n"

    source_root = tmp_path / "source"
    source_root.mkdir()
    target = source_root / "engine.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    discovery = ScientificDiscovery(
        target_file=target.name,
        teacher=_Teacher(),
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
    )

    receipts = discovery.run_discovery_loop(max_epochs=1)

    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert receipts[0]["status"] == "SIMULATION_CANDIDATE_EXPORTED"
    assert receipts[0]["source_mutated"] is False
    assert receipts[0]["candidate_executed"] is False


def test_discovery_refactor_and_launcher_have_no_legacy_mutation_loop() -> None:
    scoped_forbidden = {
        "src/discovery.py": (
            "while True",
            "random.",
            "ImmuneSystem",
            "open(target_path",
            '"SUCCESS"',
            "--forever",
        ),
        "src/refactor.py": ("write_text(", "D:\\", "os.walk("),
        "src/launcher.py": ("subprocess", "os.system", "shell=True"),
    }

    for relative, forbidden in scoped_forbidden.items():
        source = (_RESEARCH_ROOT / relative).read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden), relative
