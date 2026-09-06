#!/usr/bin/env python3
"""Repository layout auditor for JAYA workspace.

Checks:
1. Root hygiene (unexpected root files/directories).
2. Canonical root documentation placement rules.
3. Cross-package test placement.
4. Direct cross-domain imports between jaya_core and jaya_research.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class Violation:
    severity: str
    rule: str
    path: str
    detail: str
    suggestion: str


ROOT_FILE_ALLOWLIST = {
    ".env",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "conftest.py",
    "LICENSE",
    "readme.md",
    "README.md",
    "jaya.jay",
    "JAYA_CORE_MODE.bat",
    "JAYA_RESEARCH_MODE.bat",
    "START_JAYA_RESEARCH.bat",
    "nvidia_nim_config.yaml",
    "pyproject.toml",
}

ROOT_DIR_ALLOWLIST = {
    ".agent",
    ".agents",
    ".devcontainer",
    ".github",
    ".git",
    ".pytest_cache",
    ".vscode",
    "benchmarks",
    "blueprint",
    "blueprint-nvidia",
    "configs",
    "data",
    "docs",
    "docker",
    "examples",
    "mcp-servers",
    "native",
    "outputs",
    "packages",
    "scripts",
    "tests",
    "tools",
}

ROOT_DIR_IGNORE = {
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
}

TREE_DIR_IGNORE = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".agent",
    ".agents",
    ".gradle",
    ".idea",
    ".kotlin",
    ".venv",
    "archive",
    "backups",
    "blueprints",
    "build",
    "data",
    "dist",
    "experiments",
    "llama.cpp",
    "logs",
    "reports",
    "scratch",
    "skills_docs",
    "temp",
    "workspaces",
    "venv",
    "env",
    "node_modules",
}

PORTABILITY_SCAN_ROOTS = (
    ".github/tools",
    "scripts",
    "packages/jaya-core",
    "packages/jaya-research",
    "packages/jaya-agent",
    "packages/jaya-os",
    "packages/jaya-android",
)
PORTABILITY_SOURCE_SUFFIXES = {
    ".bat",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".ps1",
    ".py",
    ".sh",
    ".ts",
    ".tsx",
}
PORTABILITY_IGNORE_PARTS = {
    ".git",
    ".gradle",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "blueprint-nvidia",
    "build",
    "data",
    "dist",
    "llama.cpp",
    "node_modules",
    "venv",
}
WORKSTATION_PATH_PATTERN = re.compile(
    r"(?:[a-z]:[\\/](?:users|kampus|project)[\\/]|/mnt/[a-z]/)",
    re.IGNORECASE,
)


def _to_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_ignored_dir_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in ROOT_DIR_IGNORE or lowered in TREE_DIR_IGNORE:
        return True
    if lowered.startswith(".pytest_tmp_"):
        return True
    # Ignore suffixed virtual environments, e.g. .venv312, venv311.
    if lowered.startswith(".venv") or lowered.startswith("venv"):
        return True
    return False


def _is_ignored_path(path: Path) -> bool:
    return any(_is_ignored_dir_name(part) for part in path.parts)


def _is_git_ignored(root: Path, path: Path) -> bool:
    """Return whether Git classifies a workspace path as ignored."""

    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "--", relative.as_posix()],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _scan_root_hygiene(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        name = item.name

        if _is_git_ignored(root, item):
            continue

        if item.is_dir():
            if _is_ignored_dir_name(name):
                continue
            if name not in ROOT_DIR_ALLOWLIST:
                violations.append(
                    Violation(
                        severity="error",
                        rule="root-directory-policy",
                        path=name,
                        detail="Unexpected root directory.",
                        suggestion=(
                            "Move it under packages/, data/, outputs/, docs/, "
                            "scripts/, tests/, tools/, or .github/."
                        ),
                    )
                )

            continue

        if name not in ROOT_FILE_ALLOWLIST:
            violations.append(
                Violation(
                    severity="error",
                    rule="root-file-policy",
                    path=name,
                    detail="Unexpected root file.",
                    suggestion=(
                        "Move it under the owning package, docs/, scripts/, "
                        "tests/, tools/, or outputs/."
                    ),
                )
            )

        if item.suffix.lower() == ".md" and name not in {
            "readme.md",
            "README.md",
            "AGENTS.md",
            "CONTRIBUTING.md",
        }:
            violations.append(
                Violation(
                    severity="error",
                    rule="root-markdown-policy",
                    path=name,
                    detail="Root markdown is restricted to workspace-level docs only.",
                    suggestion="Move cross-cutting docs to docs/.",
                )
            )

    return violations


def _scan_doc_placement(root: Path, domain: str) -> list[Violation]:
    violations: list[Violation] = []
    domain_root = root / domain
    if not domain_root.exists():
        return violations

    for md_path in domain_root.rglob("*.md"):
        if _is_ignored_path(md_path):
            continue

        rel = _to_posix(md_path, root)
        rel_lower = rel.lower()

        # README is the only active Markdown entrypoint inside a module.
        if rel_lower == f"{domain.lower()}/readme.md":
            continue
        if rel_lower.startswith(f"{domain.lower()}/.github/"):
            continue

        violations.append(
            Violation(
                severity="error",
                rule="domain-doc-placement",
                path=rel,
                detail=f"Active module Markdown is limited to {domain}/README.md.",
                suggestion="Move active documentation to root docs/.",
            )
        )

    return violations


def _iter_python_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    return (p for p in base.rglob("*.py") if p.is_file() and not _is_ignored_path(p))


def _scan_cross_imports(root: Path) -> list[Violation]:
    violations: list[Violation] = []

    def scan_side(side_dir: str, forbidden_prefix: str) -> None:
        base = root / side_dir
        for py_path in _iter_python_files(base):
            rel = _to_posix(py_path, root)
            try:
                text = py_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(text)
            except SyntaxError as exc:
                violations.append(
                    Violation(
                        severity="warning",
                        rule="python-parse-warning",
                        path=rel,
                        detail=f"Failed to parse Python file: {exc}",
                        suggestion="Fix syntax first, then rerun layout audit.",
                    )
                )
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden_prefix):
                            line = getattr(node, "lineno", 1)
                            violations.append(
                                Violation(
                                    severity="error",
                                    rule="cross-domain-import",
                                    path=f"{rel}:{line}",
                                    detail=(
                                        f"{side_dir} directly imports "
                                        f"{forbidden_prefix}."
                                    ),
                                    suggestion=(
                                        "Remove direct cross-domain dependency and "
                                        "use approved contract boundary."
                                    ),
                                )
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith(forbidden_prefix):
                        line = getattr(node, "lineno", 1)
                        violations.append(
                            Violation(
                                severity="error",
                                rule="cross-domain-import",
                                path=f"{rel}:{line}",
                                detail=(
                                    f"{side_dir} directly imports from "
                                    f"{forbidden_prefix}."
                                ),
                                suggestion=(
                                    "Remove direct cross-domain dependency and "
                                    "use approved contract boundary."
                                ),
                            )
                        )

    scan_side("packages/jaya-core", "jaya_research")
    scan_side("packages/jaya-research", "jaya_core")

    return violations


def _scan_workstation_paths(root: Path) -> list[Violation]:
    """Reject source tied to a developer workstation directory."""

    violations: list[Violation] = []
    for relative_root in PORTABILITY_SCAN_ROOTS:
        scan_root = root / relative_root
        if not scan_root.exists():
            continue
        for current_root, directories, filenames in os.walk(scan_root):
            directories[:] = [
                directory
                for directory in directories
                if directory.lower() not in PORTABILITY_IGNORE_PARTS
                and not directory.lower().startswith((".venv", "venv"))
            ]
            for filename in filenames:
                path = Path(current_root) / filename
                if path.suffix.lower() not in PORTABILITY_SOURCE_SUFFIXES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if (
                        WORKSTATION_PATH_PATTERN.search(line)
                        and "portability-audit: allow" not in line
                    ):
                        violations.append(
                            Violation(
                                severity="error",
                                rule="absolute-workstation-path",
                                path=f"{_to_posix(path, root)}:{line_number}",
                                detail=(
                                    "Source depends on an absolute workstation path."
                                ),
                                suggestion=(
                                    "Use runtime discovery, configuration, or an "
                                    "environment variable instead."
                                ),
                            )
                        )
    return violations


def run_audit(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    violations.extend(_scan_root_hygiene(root))
    for domain in (
        "packages/jaya-core",
        "packages/jaya-research",
        "packages/jaya-agent",
        "packages/jaya-os",
        "packages/jaya-android",
    ):
        violations.extend(_scan_doc_placement(root, domain))
    violations.extend(_scan_cross_imports(root))
    violations.extend(_scan_workstation_paths(root))
    return violations


def _print_report(violations: list[Violation], root: Path) -> None:
    print("Repository Layout Audit")
    print(f"Workspace: {root}")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print("")

    if not violations:
        print("Status: PASS")
        print("No misplaced files or cross-domain import violations found.")
        return

    by_rule: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for item in violations:
        by_rule[item.rule] = by_rule.get(item.rule, 0) + 1
        by_severity[item.severity] = by_severity.get(item.severity, 0) + 1

    has_errors = any(item.severity == "error" for item in violations)
    print("Status: FAIL" if has_errors else "Status: WARN")
    print(f"Total violations: {len(violations)}")
    print("Severity:")
    for key in sorted(by_severity.keys()):
        print(f"- {key}: {by_severity[key]}")
    print("Rules:")
    for key in sorted(by_rule.keys()):
        print(f"- {key}: {by_rule[key]}")
    print("")
    print("Violation details:")
    for idx, item in enumerate(violations, start=1):
        print(f"{idx}. [{item.severity}] {item.rule}")
        print(f"   path: {item.path}")
        print(f"   detail: {item.detail}")
        print(f"   suggestion: {item.suggestion}")


def _write_json(path: Path, root: Path, violations: list[Violation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(root),
        "status": (
            "fail"
            if any(item.severity == "error" for item in violations)
            else "warn"
            if violations
            else "pass"
        ),
        "summary": {
            "total": len(violations),
            "errors": sum(1 for v in violations if v.severity == "error"),
            "warnings": sum(1 for v in violations if v.severity == "warning"),
        },
        "violations": [asdict(v) for v in violations],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit repository layout policy for JAYA workspace."
    )
    parser.add_argument(
        "--root", default=".", help="Workspace root path (default: current directory)"
    )
    parser.add_argument("--json-out", help="Optional JSON report output path")
    parser.add_argument(
        "--fail-on-violations",
        action="store_true",
        help="Return exit code 2 when error-level violations are found",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    violations = run_audit(root)
    _print_report(violations, root)

    if args.json_out:
        out_path = Path(args.json_out)
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        _write_json(out_path, root, violations)
        print("")
        print(f"JSON report written: {out_path}")

    if args.fail_on_violations and any(
        violation.severity == "error" for violation in violations
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
