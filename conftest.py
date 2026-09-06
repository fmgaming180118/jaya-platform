"""
Pytest configuration with backwards compatibility support.
This ensures tests can run with both old and new import paths.
"""

import sys
from pathlib import Path

# Ensure compatibility layer is loaded first
_root = Path(__file__).parent
_compat_path = _root / "tools" / "migration" / "legacy_import_compat.py"
if _compat_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("compatibility", _compat_path)
    compat_module = importlib.util.module_from_spec(spec)
    sys.modules["compatibility"] = compat_module
    spec.loader.exec_module(compat_module)

# Add source paths for direct imports
for pkg in ["jaya-core", "jaya-agent", "jaya-os", "jaya-research"]:
    src_path = _root / "packages" / pkg / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

# Pytest fixtures
import pytest


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return _root


@pytest.fixture(scope="session")
def packages_dir():
    """Return the packages directory."""
    return _root / "packages"


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for tests."""
    return tmp_path


# Pytest markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: fast isolated tests")
    config.addinivalue_line("markers", "integration: crosses process/provider/model boundaries")
    config.addinivalue_line("markers", "network: requires live network access")
    config.addinivalue_line("markers", "hardware: requires physical hardware")
    config.addinivalue_line("markers", "manual: requires human observation")
    config.addinivalue_line("markers", "slow: long-running validation")
    config.addinivalue_line("markers", "e2e: end-to-end system tests")
    config.addinivalue_line("markers", "performance: performance benchmarks")
    config.addinivalue_line("markers", "chaos: chaos engineering tests")


# Collection ignore patterns
collect_ignore = [
    "packages/jaya-core/llama.cpp",
    "blueprint*",
    "blueprints*",
    "node_modules",
    "data",
    "build",
    "dist",
]

# Asyncio mode
pytest_asyncio_mode = "auto"
