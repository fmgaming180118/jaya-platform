from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
SCRIPT = WORKSPACE / "scripts" / "ci" / "repository_health.py"
SHA256_HEX_LENGTH = 64


def _module():
    spec = importlib.util.spec_from_file_location("repository_health", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_counterparts_resolve_to_src_layout() -> None:
    module = _module()

    assert "packages/jaya-core/src/jaya_core/runtime/example.py" in module._counterpart_candidates(
        "JAYA_CORE/src/runtime/example.py"
    )
    assert (
        "packages/jaya-research/src/jaya_research/network/api.py"
        in module._counterpart_candidates("JAYA_RESEARCH/src/network/api.py")
    )
    assert (
        "tests/fixtures/legacy-features/login_dialog/scene.json"
        in module._counterpart_candidates("test_features/login_dialog/scene.json")
    )
    assert (
        "packages/jaya-research/src/jaya_research/optimizer/__init__.py"
        in module._counterpart_candidates("JAYA_RESEARCH/src/optimizer.py")
    )
    assert (
        "packages/jaya-core/src/jaya_core/resources/default_local_knowledge.json"
        in module._counterpart_candidates("JAYA_CORE/data/default_local_knowledge.json")
    )


def test_receipt_uses_real_git_state_without_secret_values(tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(WORKSPACE), "--json-out", str(output)],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["head"]
    assert receipt["branch"]
    assert len(receipt["path_digest_sha256"]) == SHA256_HEX_LENGTH
    assert isinstance(receipt["entries"], list)
    assert receipt["secret_scan"]["values_included"] is False
    assert all("content" not in entry for entry in receipt["entries"])


def test_local_identity_material_is_git_ignored() -> None:
    identity_path = WORKSPACE / "identity" / "keystore" / "dna_private_key.json"
    if not identity_path.exists():
        return

    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", identity_path.relative_to(WORKSPACE).as_posix()],
        cwd=WORKSPACE,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0
