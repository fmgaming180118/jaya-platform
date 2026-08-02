"""
boundary_enforcer.py — JAYA_OS import boundary enforcement via AST analysis.

Verifies that no module outside the approved adapter path imports directly
from `jaya_os.*`.  The only approved import path is:
    JAYA_AGENT/src/security/capability_sandbox.py

Any other file in JAYA_CORE/ or JAYA_AGENT/ that imports directly from
jaya_os.* is a boundary violation and will be reported.

Usage:
    python JAYA_OS/src/jaya_os/boundary_enforcer.py
    python JAYA_OS/src/jaya_os/boundary_enforcer.py --repo-root /path/to/repo
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# The ONE approved adapter that is allowed to import jaya_os directly
# ---------------------------------------------------------------------------
_APPROVED_ADAPTER = Path("JAYA_AGENT") / "src" / "security" / "capability_sandbox.py"

# Directories scanned for violations (relative to repo root)
_SCAN_DIRS = ["JAYA_CORE", "JAYA_AGENT"]

# The protected package name
_PROTECTED_PACKAGE = "jaya_os"


@dataclass
class BoundaryViolation:
    relative_path: str
    lineno: int
    import_text: str
    reason: str


@dataclass
class BoundaryEnforcementResult:
    status: str  # "BOUNDARY_OK" or "BOUNDARY_VIOLATION"
    scanned_files: int = 0
    violations: List[BoundaryViolation] = field(default_factory=list)

    def is_ok(self) -> bool:
        return self.status == "BOUNDARY_OK"

    def summary(self) -> str:
        lines = [
            f"Status        : {self.status}",
            f"Scanned files : {self.scanned_files}",
            f"Violations    : {len(self.violations)}",
        ]
        for v in self.violations:
            lines.append(
                f"  [{v.relative_path}:{v.lineno}] {v.import_text!r} — {v.reason}"
            )
        return "\n".join(lines)


def _extract_imports(source: str) -> List[tuple[int, str]]:
    """Return (lineno, import_text) for every import/from-import in source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: List[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            results.append((node.lineno, f"from {module} import {names}"))
    return results


def _is_jaya_os_import(import_text: str) -> bool:
    """Return True if the import references jaya_os or a submodule."""
    parts = import_text.split()
    # "import jaya_os..." or "from jaya_os..."
    for part in parts:
        if part.startswith(_PROTECTED_PACKAGE):
            return True
    return False


class OsBoundaryEnforcer:
    """
    AST-based import boundary checker for JAYA_OS ownership rules.

    Only `JAYA_AGENT/src/security/capability_sandbox.py` is allowed to import
    directly from `jaya_os.*`.  All other Python files in JAYA_CORE/ and
    JAYA_AGENT/ must go through the adapter.
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
        self._approved_adapter = (self.repo_root / _APPROVED_ADAPTER).resolve()

    def enforce(self) -> BoundaryEnforcementResult:
        """Scan all Python files and return a BoundaryEnforcementResult."""
        violations: List[BoundaryViolation] = []
        scanned = 0

        for scan_dir_name in _SCAN_DIRS:
            scan_root = self.repo_root / scan_dir_name
            if not scan_root.is_dir():
                continue
            for py_file in scan_root.rglob("*.py"):
                resolved = py_file.resolve()

                # Skip __pycache__ files
                if "__pycache__" in resolved.parts:
                    continue

                # The approved adapter is allowed — skip it
                if resolved == self._approved_adapter:
                    scanned += 1
                    continue

                try:
                    source = resolved.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                scanned += 1
                rel = resolved.relative_to(self.repo_root)
                for lineno, import_text in _extract_imports(source):
                    if _is_jaya_os_import(import_text):
                        violations.append(
                            BoundaryViolation(
                                relative_path=str(rel),
                                lineno=lineno,
                                import_text=import_text,
                                reason=(
                                    f"Direct import of '{_PROTECTED_PACKAGE}' is only allowed "
                                    f"via the approved adapter "
                                    f"'{_APPROVED_ADAPTER}'"
                                ),
                            )
                        )

        status = "BOUNDARY_OK" if not violations else "BOUNDARY_VIOLATION"
        return BoundaryEnforcementResult(
            status=status,
            scanned_files=scanned,
            violations=violations,
        )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="JAYA_OS import boundary enforcer")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Path to repository root (default: auto-detect from this file's location)",
    )
    args = parser.parse_args()

    enforcer = OsBoundaryEnforcer(repo_root=args.repo_root)
    result = enforcer.enforce()
    print(result.summary())

    return 0 if result.is_ok() else 1


if __name__ == "__main__":
    sys.exit(main())
