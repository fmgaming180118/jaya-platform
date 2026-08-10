#!/usr/bin/env python3
"""Canonical JAYA Core HTTP launcher with no fabricated fallback responses."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
_CORE_ROOT = _ROOT / "JAYA_CORE"


class CoreServerConfigurationError(RuntimeError):
    """Raised when the canonical service cannot be launched truthfully."""


def _canonical_components() -> tuple[Any, Callable[..., Any]]:
    """Load only the public Core configuration and service factory."""
    # Legacy Core modules still use the canonical ``JAYA_CORE.src`` namespace,
    # while the service package uses ``src``. Both roots must resolve when this
    # launcher is executed from any working directory.
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    if str(_CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(_CORE_ROOT))
    from src.core_config import core_config
    from src.core_service import create_app

    return core_config, create_app


def _build_runtime(config: Any) -> Any:
    """Construct the production runtime from validated/discovered identity data."""
    from src.brain_v2.protection.dna_anchor import (
        DNAAnchor,
        EncryptedFileKeyStore,
    )
    from src.cognitive.runtime import JayaCoreRuntime

    if not config.data_dir.exists() or not config.data_dir.is_dir():
        raise CoreServerConfigurationError(
            "JAYA_CORE_DATA_DIR must exist before the runtime starts"
        )
    node_id = config.node_id or platform.node().strip()
    if not node_id:
        raise CoreServerConfigurationError(
            "JAYA_NODE_ID is required when host identity cannot be discovered"
        )
    puzzle_dirs = tuple(
        Path(item).expanduser()
        for item in os.environ.get("JAYA_CORE_PUZZLE_DIRS", "").split(os.pathsep)
        if item.strip()
    )
    identity_anchor = None
    if config.identity_required:
        key_store = EncryptedFileKeyStore(
            config.identity_dir / "keystore",
            config.identity_key_secret.get_secret_value(),
        )
        identity_anchor = DNAAnchor(config.identity_dir, key_store)
    return JayaCoreRuntime(
        db_path=config.data_dir / "jaya_core_runtime.db",
        node_id=node_id,
        puzzle_dirs=puzzle_dirs,
        identity_anchor=identity_anchor,
        identity_required=config.identity_required,
    )


def build_app(*, runtime: Any | None = None) -> Any:
    """Build the canonical service with a real runtime by default."""
    config, factory = _canonical_components()
    active_runtime = runtime or _build_runtime(config)
    app = factory(config, runtime=active_runtime)
    if runtime is None:
        app.add_event_handler("shutdown", active_runtime.close)
    return app


def run_server(*, runtime: Any | None = None) -> None:
    """Run uvicorn using only validated host and port configuration."""
    try:
        import uvicorn
    except ImportError as exc:
        raise CoreServerConfigurationError("uvicorn is not installed") from exc
    config, factory = _canonical_components()
    active_runtime = runtime or _build_runtime(config)
    app = factory(config, runtime=active_runtime)
    if runtime is None:
        app.add_event_handler("shutdown", active_runtime.close)
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
