"""
domain_validator.py — Cognitive Kernel Domain Neutrality Boundary Validator.

Verifies that the 11 Cognitive Kernel components in JAYA_CORE/src/cognitive/
remain 100% domain-neutral without hardcoded domain logic or assumptions.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# List of prohibited domain-specific hardcoded keywords inside the generic Cognitive Kernel
PROHIBITED_DOMAIN_KEYWORDS = [
    "thesis_analysis",
    "academic_paper_generator",
    "pdf_chatbot_mode",
]


@dataclass
class DomainViolation:
    file_path: str
    line_number: int
    prohibited_keyword: str
    code_snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DomainValidationReport:
    is_domain_neutral: bool
    scanned_files_count: int
    violations_count: int
    violations: List[DomainViolation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["violations"] = [v.to_dict() for v in self.violations]
        return d


class DomainBoundaryValidator:
    """Validator enforcing domain neutrality of the JAYA Core Cognitive Kernel."""

    def __init__(self, cognitive_dir: Optional[Path | str] = None) -> None:
        if cognitive_dir:
            self.cognitive_dir = Path(cognitive_dir).resolve()
        else:
            self.cognitive_dir = (Path(__file__).resolve().parent).resolve()

    def validate_cognitive_kernel(self) -> DomainValidationReport:
        if not self.cognitive_dir.is_dir():
            raise FileNotFoundError(f"Cognitive directory '{self.cognitive_dir}' not found")

        violations: List[DomainViolation] = []
        scanned_count = 0

        for py_file in sorted(self.cognitive_dir.glob("*.py")):
            if py_file.name.startswith("__") or py_file.name == "domain_validator.py":
                continue

            scanned_count += 1
            content = py_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            for i, line in enumerate(lines, start=1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue

                for kw in PROHIBITED_DOMAIN_KEYWORDS:
                    if kw in line:
                        violations.append(
                            DomainViolation(
                                file_path=py_file.name,
                                line_number=i,
                                prohibited_keyword=kw,
                                code_snippet=stripped[:80],
                            )
                        )

        return DomainValidationReport(
            is_domain_neutral=len(violations) == 0,
            scanned_files_count=scanned_count,
            violations_count=len(violations),
            violations=violations,
        )
