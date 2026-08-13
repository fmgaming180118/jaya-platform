"""Architecture boundary guard for Phase 1.

Ensures `brain_v2` (resident layer) does not import `os_kernel` (home layer)
directly during Phase 1.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

BRAIN_DIR = ROOT / "src" / "brain_v2"


class TestPhase1ArchitectureBoundary(unittest.TestCase):
    def test_brain_v2_has_no_os_kernel_imports(self):
        py_files = list(BRAIN_DIR.rglob("*.py"))
        forbidden = re.compile(r"(^|\s)(from\s+src\.os_kernel|from\s+os_kernel|import\s+src\.os_kernel|import\s+os_kernel)")

        violations = []
        for path in py_files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if forbidden.search(line):
                    rel = path.relative_to(ROOT)
                    violations.append(f"{rel}:{line_no}: {line.strip()}")

        self.assertEqual(
            violations,
            [],
            "Phase 1 boundary violation detected (brain_v2 importing os_kernel):\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
