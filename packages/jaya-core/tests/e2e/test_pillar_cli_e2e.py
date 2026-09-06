import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PACKAGE_SRC = ROOT / "packages" / "jaya-core" / "src"
BASELINE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "src"
    / "jaya_core"
    / "contracts"
    / "40_pillars.yaml"
)
CANDIDATE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "examples"
    / "pillar-041-adaptive-evidence.yaml"
)


def _run(db: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(PACKAGE_SRC) + (os.pathsep + existing if existing else "")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "jaya_core.pillars.cli",
            "--db",
            str(db),
            "--manifest",
            str(BASELINE),
            *arguments,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_cli_registers_and_reads_a_new_pillar_after_process_restart(tmp_path: Path) -> None:
    db = tmp_path / "pillars.db"
    before = _run(db, "list")
    registered = _run(
        db,
        "register",
        "--candidate",
        str(CANDIDATE),
        "--idempotency-key",
        "e2e:adaptive-evidence:v1",
        "--actor",
        "e2e:operator",
    )
    after = _run(db, "list")

    assert before.returncode == 0, before.stderr
    assert registered.returncode == 0, registered.stderr
    assert after.returncode == 0, after.stderr
    assert json.loads(before.stdout)["total"] == 40
    assert json.loads(registered.stdout)["created"] is True
    after_payload = json.loads(after.stdout)
    assert after_payload["total"] == 41
    assert after_payload["dynamic_total"] == 1
    assert after_payload["canonical_40_present"] is True
