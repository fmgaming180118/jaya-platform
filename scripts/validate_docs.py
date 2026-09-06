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

PILLAR_DOC_PATTERN = re.compile(r"^(\d{2})-p(\d{2})-[a-z0-9-]+\.md$")
PILLAR_REQUIRED_MARKERS = (
    "**ID pilar:**",
    "**Tahap:**",
    "**Status saat audit:**",
    "## Tujuan",
    "## Dependensi",
    "## Kontrak dan integrasi",
    "## Checklist implementasi",
    "## Exit criteria",
    "## Larangan",
)
PILLAR_CONTRACT_PATTERN = re.compile(
    r"^- id:\s*(\d+)\s*$.*?^\s+status:\s*([A-Z_]+)\s*$",
    re.MULTILINE | re.DOTALL,
)
PILLAR_HEADER_ID_PATTERN = re.compile(r"\*\*ID pilar:\*\*\s*(\d+)")
PILLAR_HEADER_STATUS_PATTERN = re.compile(r"\*\*Status saat audit:\*\*\s*([A-Z_]+)")
PILLAR_MATRIX_STATUS_PATTERN = re.compile(
    r"^##\s+(\d+)\s+—\s+.*?^\*\*Status:\*\*\s*^([A-Z_]+)\s*$",
    re.MULTILINE | re.DOTALL,
)
PILLAR_INDEX_STATUS_PATTERN = re.compile(
    r"^\|\s*\d{2}\s*\|\s*(\d+)\s*\|.*?\|\s*([A-Z_]+)\s*\|",
    re.MULTILINE,
)

ENTRYPOINTS = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("packages/jaya-research/README.md"),
    Path("packages/jaya-core/README.md"),
    Path("packages/jaya-agent/README.md"),
    Path("packages/jaya-os/README.md"),
    Path("packages/jaya-android/README.md"),
)

QUALITY_GATES = (
    Path("pyproject.toml"),
    Path("scripts/run_test_matrix.py"),
)

MODULES = (
    Path("packages/jaya-research"),
    Path("packages/jaya-core"),
    Path("packages/jaya-agent"),
    Path("packages/jaya-os"),
    Path("packages/jaya-android"),
)

TRACKABILITY_PROBES = (
    Path("packages/jaya-research/tests/_trackability_probe.py"),
    Path("packages/jaya-core/tests/_trackability_probe.py"),
    Path("packages/jaya-core/src/jaya_core/brain_v2/evolution/_trackability_probe.py"),
    Path("packages/jaya-core/src/jaya_core/features/_trackability_probe.py"),
    Path("packages/jaya-os/tests/_trackability_probe.py"),
    Path("packages/jaya-android/app/_trackability_probe.py"),
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
                    f"Link out of repository boundary in {rel_path}: "
                    f"'{target}' -> {resolved_target}"
                )
                continue

            if not resolved_target.exists():
                errors.append(
                    f"Broken local link in {rel_path}: '{label}' points to "
                    f"non-existent '{target}'"
                )

    return errors


def validate_single_git_root() -> list[str]:
    errors: list[str] = []
    try:
        cmd = ["git", "rev-parse", "--show-toplevel"]
        result = subprocess.run(
            cmd,
            cwd=ROOT / "packages/jaya-research",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append("Failed to execute git rev-parse from packages/jaya-research.")
        else:
            toplevel = Path(result.stdout.strip()).resolve()
            if toplevel != ROOT:
                errors.append(
                    f"Submodule Git root detected at {toplevel}; "
                    f"expected single root at {ROOT}"
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
        f"Validasi dokumentasi LULUS: {len(CANONICAL_DOCS)} dokumen kanonis + "
        "dokumen publik, satu Git root, tanpa docs modul, seluruh tautan lokal "
        "valid, dan source/test dapat dilacak."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
