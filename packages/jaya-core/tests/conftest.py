"""Pytest configuration for JAYA_CORE tests."""

import os
import sys
from pathlib import Path

# Add all workspace package src directories to sys.path
ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent.parent
for pkg in ["jaya-core", "jaya-agent", "jaya-os", "jaya-research"]:
    pkg_src = WORKSPACE / "packages" / pkg / "src"
    if pkg_src.exists() and str(pkg_src) not in sys.path:
        sys.path.insert(0, str(pkg_src))
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Ensure background resource monitor does not interfere with unit/integration test suites
os.environ.setdefault("JAYA_RESOURCE_MONITOR_ENABLED", "false")