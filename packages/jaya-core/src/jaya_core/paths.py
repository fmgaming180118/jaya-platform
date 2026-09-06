"""Portable filesystem defaults for the JAYA monorepo.

This module performs path discovery only. It never creates directories or loads
credentials, which keeps package imports side-effect free.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]


def _configured_path(
    key: str,
    default: Path,
    environment: Mapping[str, str] | None = None,
) -> Path:
    source = os.environ if environment is None else environment
    raw = source.get(key, "").strip()
    candidate = Path(raw).expanduser() if raw else default
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    return candidate.resolve(strict=False)


def core_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    return _configured_path(
        "JAYA_CORE_DATA_DIR",
        WORKSPACE_ROOT / "data" / "jaya-core",
        environment,
    )


def core_models_dir(environment: Mapping[str, str] | None = None) -> Path:
    return _configured_path(
        "JAYA_CORE_MODELS_DIR",
        WORKSPACE_ROOT / "data" / "models" / "jaya-core",
        environment,
    )


__all__ = ["WORKSPACE_ROOT", "core_data_dir", "core_models_dir"]
