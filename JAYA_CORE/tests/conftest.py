"""Pytest configuration for JAYA_CORE tests."""

import sys
from pathlib import Path

# Add JAYA_CORE root to sys.path so 'src' imports work
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))