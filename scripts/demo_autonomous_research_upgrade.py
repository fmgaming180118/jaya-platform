#!/usr/bin/env python3
"""Inspect one immutable Research candidate without evaluating or deploying it."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from JAYA_RESEARCH.src.research.research_artifact import (
    ArtifactValidationError,
    validate_artifact_dict,
)


class ArtifactInspectionError(RuntimeError):
    """Raised when a candidate cannot be inspected safely."""


def inspect_candidate(path: Path | str) -> dict[str, Any]:
    """Verify the public contract and report its still-inactive status."""
    artifact_path = Path(path).expanduser().resolve()
    if not artifact_path.is_file() or artifact_path.is_symlink():
        raise ArtifactInspectionError("artifact must be a regular file")
    if not 0 < artifact_path.stat().st_size <= 2 * 1024 * 1024:
        raise ArtifactInspectionError("artifact size is invalid")
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        validate_artifact_dict(artifact)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ArtifactValidationError,
    ) as exc:
        raise ArtifactInspectionError("artifact verification failed") from exc
    return {
        "artifact_id": artifact["artifact_id"],
        "artifact_type": artifact["artifact_type"],
        "evidence_kind": artifact["evidence_kind"],
        "status": artifact["status"],
        "content_sha256": artifact["content_sha256"],
        "executed": False,
        "deployed": False,
        "human_review_required": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify an inactive Research candidate artifact"
    )
    parser.add_argument("--artifact", required=True)
    arguments = parser.parse_args(argv)
    try:
        result = inspect_candidate(arguments.artifact)
    except ArtifactInspectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
