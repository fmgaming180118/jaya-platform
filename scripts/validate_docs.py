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
    Path("docs/WORKFLOWS.md"),
    Path("docs/STATUS.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/ACCEPTANCE_CRITERIA.md"),
    Path("docs/REMEDIATION_CHECKLIST.md"),
    Path("docs/GOVERNANCE.md"),
    Path("docs/DEVELOPMENT.md"),
    Path("docs/GLOSSARY.md"),
    Path("docs/CHANGELOG.md"),
    Path("docs/arsitektur_40_pilar_jaya.md"),
    Path("docs/40_PILLARS_IMPLEMENTATION_MATRIX.md"),
    Path("docs/pillars/README.md"),
    Path("docs/LOGICAL_FOUNDATION_PROGRESS.md"),
    Path("docs/SOVEREIGN_FOUNDATION_PROGRESS.md"),
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
PILLAR_HEADER_STATUS_PATTERN = re.compile(
    r"\*\*Status saat audit:\*\*\s*([A-Z_]+)"
)
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

    pillar_dir = ROOT / "docs/pillars"
    pillar_docs = sorted(pillar_dir.glob("*.md")) if pillar_dir.is_dir() else []
    pillar_docs = [path for path in pillar_docs if path.name != "README.md"]
    if len(pillar_docs) != 40:
        errors.append(
            f"Expected exactly 40 pillar construction documents, found {len(pillar_docs)}"
        )

    construction_orders: set[int] = set()
    pillar_ids: set[int] = set()
    contract_path = ROOT / "JAYA_CORE/contracts/40_pillars.yaml"
    try:
        contract_text = contract_path.read_text(encoding="utf-8")
        contract_statuses = {
            int(pillar_id): status
            for pillar_id, status in PILLAR_CONTRACT_PATTERN.findall(contract_text)
        }
    except OSError as exc:
        errors.append(f"Cannot read pillar contract {contract_path.relative_to(ROOT)}: {exc}")
        contract_statuses = {}

    index_path = pillar_dir / "README.md"
    try:
        pillar_index = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Cannot read pillar index {index_path.relative_to(ROOT)}: {exc}")
        pillar_index = ""

    matrix_path = ROOT / "docs/40_PILLARS_IMPLEMENTATION_MATRIX.md"
    try:
        matrix_text = matrix_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Cannot read pillar matrix {matrix_path.relative_to(ROOT)}: {exc}")
        matrix_text = ""

    for path in pillar_docs:
        match = PILLAR_DOC_PATTERN.fullmatch(path.name)
        if match is None:
            errors.append(f"Invalid pillar document filename: {path.relative_to(ROOT)}")
            continue
        construction_orders.add(int(match.group(1)))
        filename_pillar_id = int(match.group(2))
        pillar_ids.add(filename_pillar_id)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Cannot read pillar document {path.relative_to(ROOT)}: {exc}")
            continue
        for marker in PILLAR_REQUIRED_MARKERS:
            if marker not in content:
                errors.append(
                    f"Missing marker '{marker}' in {path.relative_to(ROOT)}"
                )
        header_id_match = PILLAR_HEADER_ID_PATTERN.search(content)
        if header_id_match is None or int(header_id_match.group(1)) != filename_pillar_id:
            errors.append(
                f"Pillar ID header does not match filename in {path.relative_to(ROOT)}"
            )
        status_match = PILLAR_HEADER_STATUS_PATTERN.search(content)
        expected_status = contract_statuses.get(filename_pillar_id)
        if status_match is None or status_match.group(1) != expected_status:
            errors.append(
                f"Pillar status drift in {path.relative_to(ROOT)}: "
                f"expected {expected_status}, found "
                f"{status_match.group(1) if status_match else 'MISSING'}"
            )
        if path.name not in pillar_index:
            errors.append(f"Pillar document is missing from index: {path.relative_to(ROOT)}")

    expected_numbers = set(range(1, 41))
    if construction_orders != expected_numbers:
        errors.append("Pillar construction order must contain each number 01-40 exactly once")
    if pillar_ids != expected_numbers:
        errors.append("Pillar documents must cover each pillar ID 01-40 exactly once")

    matrix_statuses = {
        int(pillar_id): status
        for pillar_id, status in PILLAR_MATRIX_STATUS_PATTERN.findall(matrix_text)
    }
    if matrix_statuses != contract_statuses:
        errors.append("40-pillar implementation matrix status is out of sync with contract")

    index_statuses = {
        int(pillar_id): status
        for pillar_id, status in PILLAR_INDEX_STATUS_PATTERN.findall(pillar_index)
    }
    if index_statuses != contract_statuses:
        errors.append("40-pillar construction index status is out of sync with contract")

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
    pillar_docs = sorted((ROOT / "docs/pillars").glob("*.md"))
    scanned_files = list(CANONICAL_DOCS) + list(ENTRYPOINTS)
    scanned_files.extend(path.relative_to(ROOT) for path in pillar_docs)

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
        f"Validasi dokumentasi LULUS: {len(CANONICAL_DOCS)} dokumen kanonis + "
        "40 dokumen pilar, satu Git root, tanpa docs modul, seluruh tautan lokal "
        "valid, status pilar sinkron, dan source/test dapat dilacak."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
