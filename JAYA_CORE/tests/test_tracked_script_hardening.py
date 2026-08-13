from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import backup_source, benchmark_phase1_ir, convert_to_gguf

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = WORKSPACE_ROOT / "JAYA_CORE"

AUDITED_FILES = (
    WORKSPACE_ROOT / "JAYA_RESEARCH" / "scripts" / "process_ta_fachri.py",
    CORE_ROOT / "scripts" / "benchmark_phase1_ir.py",
    CORE_ROOT / "scripts" / "convert_to_gguf.py",
    CORE_ROOT / "scripts" / "backup_source.py",
    CORE_ROOT / "scripts" / "setup_ui_backend.py",
    CORE_ROOT / "scripts" / "_patch_genesis.py",
    CORE_ROOT / "scripts" / "_patch_homeostasis.py",
    CORE_ROOT / "scripts" / "_patch_intent.py",
    CORE_ROOT / "scripts" / "_patch_legacy.py",
    CORE_ROOT / "scripts" / "_patch_lingua.py",
    CORE_ROOT / "scripts" / "_patch_runtime.py",
    CORE_ROOT / "src" / "brain_v2" / "education" / "train_logic.py",
)

RETIRED_PATCH_TARGETS = {
    "_patch_genesis.py": CORE_ROOT / "src" / "brain_v2" / "genesis.py",
    "_patch_homeostasis.py": (
        CORE_ROOT / "src" / "brain_v2" / "organism" / "homeostasis.py"
    ),
    "_patch_intent.py": (
        CORE_ROOT / "src" / "brain_v2" / "engine" / "intent_engine.py"
    ),
    "_patch_legacy.py": (
        CORE_ROOT / "src" / "brain_v2" / "engine" / "legacy_protocol.py"
    ),
    "_patch_lingua.py": (CORE_ROOT / "src" / "brain_v2" / "soul" / "lingua_logica.py"),
    "_patch_runtime.py": (CORE_ROOT / "src" / "brain_v2" / "engine" / "runtime.py"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_audited_scripts_have_no_workstation_absolute_paths() -> None:
    drive_path = re.compile(r"(?i)(?:[a-z]:[\\/]|users[\\/])")
    violations = []
    for path in AUDITED_FILES:
        match = drive_path.search(path.read_text(encoding="utf-8"))
        if match:
            violations.append(f"{path.relative_to(WORKSPACE_ROOT)}:{match.group(0)}")
    assert violations == []


@pytest.mark.parametrize("script_name", sorted(RETIRED_PATCH_TARGETS))
def test_legacy_patch_scripts_refuse_source_mutation(script_name: str) -> None:
    script = CORE_ROOT / "scripts" / script_name
    target = RETIRED_PATCH_TARGETS[script_name]
    before = _sha256(target)

    result = subprocess.run(
        [sys.executable, str(script), "--explain"],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "retired" in result.stderr
    assert _sha256(target) == before


def test_cross_module_scaffold_is_retired() -> None:
    result = subprocess.run(
        [sys.executable, str(CORE_ROOT / "scripts" / "setup_ui_backend.py")],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "will not modify" in result.stderr


def test_backup_paths_are_contained_and_external_mirror_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="inside"):
        backup_source.resolve_contained(WORKSPACE_ROOT, root=CORE_ROOT)

    monkeypatch.delenv("JAYA_BACKUP_MIRROR_DIR", raising=False)
    args = backup_source.build_parser().parse_args([])
    assert args.mirror_dir is None


def test_converter_paths_are_contained_and_llama_cpp_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="inside"):
        convert_to_gguf.resolve_contained(
            WORKSPACE_ROOT,
            root=convert_to_gguf.POLICY_ROOT,
            must_exist=True,
        )

    monkeypatch.delenv("LLAMA_CPP_DIR", raising=False)
    args = convert_to_gguf.build_parser().parse_args([])
    assert args.llama_cpp_dir is None
    assert args.trust_remote_code is False


def test_research_pdf_processor_requires_explicit_input_and_contained_output() -> None:
    source = (
        WORKSPACE_ROOT / "JAYA_RESEARCH" / "scripts" / "process_ta_fachri.py"
    ).read_text(encoding="utf-8")
    assert "JAYA_RESEARCH_TA_PDF" in source
    assert "resolve_pdf_path(args.pdf_path)" in source
    assert "resolve_output_dir(args.output_dir)" in source
    assert "_is_relative_to(output_dir, DATA_ROOT)" in source


def test_benchmark_json_output_is_contained_to_canonical_reports() -> None:
    with pytest.raises(ValueError, match="reports"):
        benchmark_phase1_ir._resolve_json_output(str(WORKSPACE_ROOT / "outside.json"))

    expected = (WORKSPACE_ROOT / "reports" / "benchmarks" / "phase1.json").resolve(
        strict=False
    )
    assert benchmark_phase1_ir._resolve_json_output(str(expected)) == expected


def test_gguf_verification_rejects_fabricated_artifacts(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.gguf"
    invalid.write_bytes(b"not-a-model")
    with pytest.raises(RuntimeError, match="magic"):
        convert_to_gguf.verify_gguf(invalid)

    valid = tmp_path / "valid.gguf"
    valid.write_bytes(b"GGUF\x00")
    convert_to_gguf.verify_gguf(valid)
