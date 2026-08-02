"""Validate the canonical JAYA documentation layout and local links."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]

CANONICAL_DOCS = (
    Path("docs/README.md"),
    Path("docs/PRODUCT.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/DECISIONS.md"),
    Path("docs/JAYA_CORE_DESIGN.md"),
    Path("docs/JAYA_MESH_DESIGN.md"),
    Path("docs/DISCOVERY_PIPELINE_DESIGN.md"),
    Path("docs/COMPLETED_PHASES_CHECKLIST.md"),
    Path("docs/WORKFLOWS.md"),
    Path("docs/STATUS.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/ACCEPTANCE_CRITERIA.md"),
    Path("docs/REMEDIATION_CHECKLIST.md"),
    Path("docs/GOVERNANCE.md"),
    Path("docs/DEVELOPMENT.md"),
    Path("docs/GLOSSARY.md"),
    Path("docs/CHANGELOG.md"),
    Path("docs/archive/README.md"),
)

ENTRYPOINTS = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("JAYA_RESEARCH/README.md"),
    Path("JAYA_CORE/README.md"),
    Path("JAYA_AGENT/README.md"),
    Path("JAYA_OS/README.md"),
    Path("JAYA_ANDROID/README.md"),
)

QUALITY_GATES = (
    Path("pyproject.toml"),
    Path("scripts/run_test_matrix.py"),
)

MODULES = (
    Path("JAYA_RESEARCH"),
    Path("JAYA_CORE"),
    Path("JAYA_AGENT"),
    Path("JAYA_OS"),
    Path("JAYA_ANDROID"),
)

TRACKABILITY_PROBES = (
    Path("JAYA_RESEARCH/tests/_trackability_probe.py"),
    Path("JAYA_CORE/tests/_trackability_probe.py"),
    Path("JAYA_CORE/src/brain_v2/evolution/_trackability_probe.py"),
    Path("JAYA_CORE/features/_trackability_probe.py"),
    Path("JAYA_RESEARCH/src/experiments/_trackability_probe.py"),
    Path("JAYA_OS/tests/_trackability_probe.py"),
    Path("JAYA_ANDROID/app/_trackability_probe.py"),
)

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HTTP_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def validate_doc_files() -> list[str]:
    errors: list[str] = []

    for rel_path in CANONICAL_DOCS:
        full_path = ROOT / rel_path
        if not full_path.exists():
            errors.append(f"Missing canonical documentation file: {rel_path}")

    for entry in ENTRYPOINTS:
        full_path = ROOT / entry
        if not full_path.exists():
            errors.append(f"Missing entrypoint pointer file: {entry}")

    for qg in QUALITY_GATES:
        full_path = ROOT / qg
        if not full_path.exists():
            errors.append(f"Missing quality gate asset: {qg}")

    for module_dir in MODULES:
        bad_docs_dir = ROOT / module_dir / "docs"
        if bad_docs_dir.exists():
            errors.append(
                f"Found non-canonical documentation directory: {module_dir}/docs"
            )

    return errors


def is_git_ignored(rel_path: Path) -> bool:
    try:
        cmd = ["git", "check-ignore", "-q", str(rel_path)]
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def validate_trackability() -> list[str]:
    errors: list[str] = []
    for probe in TRACKABILITY_PROBES:
        if is_git_ignored(probe):
            errors.append(f"Probe is ignored by Git: {probe}")
    return errors


def validate_local_links() -> list[str]:
    errors: list[str] = []
    scanned_files = list(CANONICAL_DOCS) + list(ENTRYPOINTS)

    for rel_path in scanned_files:
        source_file = ROOT / rel_path
        if not source_file.is_file():
            continue

        try:
            content = source_file.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Cannot read file {rel_path}: {exc}")
            continue

        for match in LINK_PATTERN.finditer(content):
            label, target = match.groups()
            target = target.strip()

            if not target or target.startswith("#") or HTTP_PATTERN.match(target):
                continue

            target_path_str = target.split("#", 1)[0]
            if not target_path_str:
                continue

            decoded_target = unquote(target_path_str)
            resolved_target = (source_file.parent / decoded_target).resolve()

            try:
                resolved_target.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"Link out of repository boundary in {rel_path}: '{target}' -> {resolved_target}"
                )
                continue

            if not resolved_target.exists():
                errors.append(
                    f"Broken local link in {rel_path}: '{label}' points to non-existent '{target}'"
                )

    return errors


def validate_single_git_root() -> list[str]:
    errors: list[str] = []
    try:
        cmd = ["git", "rev-parse", "--show-toplevel"]
        result = subprocess.run(
            cmd,
            cwd=ROOT / "JAYA_RESEARCH",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append("Failed to execute git rev-parse from JAYA_RESEARCH.")
        else:
            toplevel = Path(result.stdout.strip()).resolve()
            if toplevel != ROOT:
                errors.append(
                    f"Submodule Git root detected at {toplevel}; expected single root at {ROOT}"
                )
    except OSError as exc:
        errors.append(f"Git check failed: {exc}")

    return errors


def main() -> int:
    doc_errors = validate_doc_files()
    track_errors = validate_trackability()
    link_errors = validate_local_links()
    git_errors = validate_single_git_root()

    all_errors = doc_errors + track_errors + link_errors + git_errors
    if all_errors:
        print("GAGAL: Ditemukan kesalahan pada struktur dokumentasi/repository:\n")
        for err in all_errors:
            print(f" - {err}")
        return 1

    print(
        f"Validasi dokumentasi LULUS: {len(CANONICAL_DOCS)} file aktif, satu Git root, "
        "tanpa docs modul, seluruh tautan lokal valid, dan source/test dapat dilacak."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
