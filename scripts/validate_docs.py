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
    Path(
        "JAYA_ANDROID/app/src/main/java/com/example/jaya/data/_trackability_probe.kt"
    ),
)

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "data:")


def normalize_link(raw_target: str) -> str:
    """Return a Markdown link target without title or anchor."""
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split(maxsplit=1)[0]
    target = target.split("#", maxsplit=1)[0]
    return unquote(target)


def validate_required_files(errors: list[str]) -> None:
    """Ensure all canonical documents and entrypoints exist."""
    for relative_path in (*CANONICAL_DOCS, *ENTRYPOINTS, *QUALITY_GATES):
        if not (ROOT / relative_path).is_file():
            errors.append(f"File wajib tidak ditemukan: {relative_path.as_posix()}")


def validate_repository_layout(errors: list[str]) -> None:
    """Ensure root owns Git and modules do not own docs or nested repositories."""
    if not (ROOT / ".git").is_dir():
        errors.append("Repository Git root tidak ditemukan.")

    for module in MODULES:
        if (ROOT / module / ".git").exists():
            errors.append(f"Nested Git dilarang: {(module / '.git').as_posix()}")
        if (ROOT / module / "docs").exists():
            errors.append(
                f"Dokumentasi modul dilarang: {(module / 'docs').as_posix()}"
            )

    research_dir = ROOT / "JAYA_RESEARCH"
    try:
        result = subprocess.run(
            ["git", "-C", str(research_dir), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        discovered_root = Path(result.stdout.strip()).resolve()
        if discovered_root != ROOT.resolve():
            errors.append(
                "JAYA_RESEARCH masih diarahkan ke Git root lain: "
                f"{discovered_root}"
            )
    except FileNotFoundError:
        errors.append("Executable Git tidak ditemukan; kepemilikan repository gagal dicek.")
    except subprocess.TimeoutExpired:
        errors.append("Pemeriksaan Git timeout setelah 10 detik.")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or f"exit {exc.returncode}"
        errors.append(f"Pemeriksaan Git gagal: {detail}")


def validate_local_links(errors: list[str]) -> None:
    """Check local Markdown links from active docs and entrypoint READMEs."""
    for relative_path in (*CANONICAL_DOCS, *ENTRYPOINTS):
        file_path = ROOT / relative_path
        if not file_path.is_file():
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"Gagal membaca {relative_path.as_posix()}: {exc}")
            continue

        for match in MARKDOWN_LINK.finditer(content):
            target = normalize_link(match.group(1))
            if not target or target.startswith("#"):
                continue
            if target.lower().startswith(EXTERNAL_PREFIXES):
                continue

            linked_path = (file_path.parent / target).resolve()
            try:
                linked_path.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(
                    f"Tautan keluar repository di {relative_path.as_posix()}: {target}"
                )
                continue

            if not linked_path.exists():
                line = content.count("\n", 0, match.start()) + 1
                errors.append(
                    f"Tautan rusak {relative_path.as_posix()}:{line} -> {target}"
                )


def validate_source_trackability(errors: list[str]) -> None:
    """Ensure future test and source files are not hidden by broad ignore rules."""
    for relative_path in TRACKABILITY_PROBES:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "check-ignore",
                    "--no-index",
                    "--quiet",
                    relative_path.as_posix(),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            errors.append(f"Pemeriksaan trackability gagal: {exc}")
            return

        if result.returncode == 0:
            errors.append(
                f"Source/test baru masih di-ignore: {relative_path.as_posix()}"
            )
        elif result.returncode not in (1,):
            detail = result.stderr.strip() or f"exit {result.returncode}"
            errors.append(f"git check-ignore gagal: {detail}")


def main() -> int:
    """Run every documentation validation and return a process exit code."""
    errors: list[str] = []

    validate_required_files(errors)
    validate_repository_layout(errors)
    validate_local_links(errors)
    validate_source_trackability(errors)

    if errors:
        print("Validasi dokumentasi GAGAL:")
        for error in errors:
            print(f"- {error}")
        return 1

    checked_count = len(CANONICAL_DOCS) + len(ENTRYPOINTS)
    print(
        "Validasi dokumentasi LULUS: "
        f"{checked_count} file aktif, satu Git root, tanpa docs modul, "
        "seluruh tautan lokal valid, dan source/test dapat dilacak."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
