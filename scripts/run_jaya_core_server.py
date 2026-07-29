#!/usr/bin/env python3
"""Canonical JAYA Core HTTP launcher with no fabricated fallback responses."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
_CORE_ROOT = _ROOT / "JAYA_CORE"


class CoreServerConfigurationError(RuntimeError):
    """Raised when the canonical service cannot be launched truthfully."""


def _canonical_components() -> tuple[Any, Callable[..., Any]]:
    """Load only the public Core configuration and service factory."""
    if str(_CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(_CORE_ROOT))
    from src.core_config import core_config
    from src.core_service import create_app

    return core_config, create_app


def build_app(*, runtime: Any | None = None) -> Any:
    """Build the canonical service; absent runtime remains unavailable."""
    config, factory = _canonical_components()
    return factory(config, runtime=runtime)


def run_server(*, runtime: Any | None = None) -> None:
    """Run uvicorn using only validated host and port configuration."""
    try:
        import uvicorn
    except ImportError as exc:
        raise CoreServerConfigurationError("uvicorn is not installed") from exc
    config, factory = _canonical_components()
    app = factory(config, runtime=runtime)
    uvicorn.run(
        app,
        host=config.bind_host,
        port=config.bind_port,
        log_level="info",
    )


if __name__ == "__main__":
    try:
        run_server()
    except Exception as exc:
        print(f"JAYA Core server did not start: {exc}", file=sys.stderr)
        sys.exit(2)
