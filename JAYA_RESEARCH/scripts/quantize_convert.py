#!/usr/bin/env python3
"""Convert a Research-owned checkpoint into a review-only NumPy candidate."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

_RESEARCH_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INPUT_ROOT = _RESEARCH_ROOT / "data" / "checkpoints"
_DEFAULT_OUTBOX = _RESEARCH_ROOT / "data" / "artifact_outbox"


class CheckpointConversionError(RuntimeError):
    """Raised when a checkpoint cannot be converted without crossing a boundary."""


def _confined(path: Path | str, root: Path, label: str) -> Path:
    resolved_root = root.expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise CheckpointConversionError(
            f"{label} must remain inside {resolved_root}"
        ) from exc
    return resolved


def load_checkpoint(path: Path) -> Mapping[str, Any]:
    """Load tensor weights with PyTorch's non-executable weights-only mode."""
    try:
        import torch
    except ImportError as exc:
        raise CheckpointConversionError(
            "torch is required to read checkpoints"
        ) from exc
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise CheckpointConversionError(
            "installed torch lacks safe weights_only checkpoint loading"
        ) from exc
    except Exception as exc:
        raise CheckpointConversionError("checkpoint loading failed") from exc

    if not isinstance(checkpoint, Mapping):
        raise CheckpointConversionError("checkpoint must contain a state dictionary")
    candidate = checkpoint.get("model", checkpoint.get("state_dict", checkpoint))
    if not isinstance(candidate, Mapping):
        raise CheckpointConversionError("checkpoint state dictionary is invalid")
    return candidate


def state_dict_to_numpy(state_dict: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """Convert tensor-like values and reject empty or ambiguous candidates."""
    converted: dict[str, np.ndarray] = {}
    for raw_key, value in state_dict.items():
        key = str(raw_key).replace("/", "__")
        if not key or key in converted:
            raise CheckpointConversionError("checkpoint contains duplicate tensor keys")
        try:
            array = value.detach().cpu().numpy()
        except AttributeError:
            try:
                array = np.asarray(value)
            except Exception as exc:
                raise CheckpointConversionError(
                    f"tensor {key!r} cannot be converted"
                ) from exc
        if array.dtype == object:
            raise CheckpointConversionError(f"tensor {key!r} has unsafe object dtype")
        converted[key] = array
    if not converted:
        raise CheckpointConversionError("checkpoint contains no tensors")
    return converted


def convert_checkpoint(
    checkpoint_path: Path | str,
    output_path: Path | str,
    *,
    input_root: Path = _DEFAULT_INPUT_ROOT,
    outbox_root: Path = _DEFAULT_OUTBOX,
) -> Path:
    """Write a non-executable candidate without importing any Core internals."""
    source = _confined(checkpoint_path, input_root, "checkpoint")
    destination = _confined(output_path, outbox_root, "candidate output")
    if not source.is_file() or source.is_symlink():
        raise CheckpointConversionError("checkpoint must be a regular file")
    if destination.suffix.lower() != ".npz":
        raise CheckpointConversionError("candidate output must use the .npz suffix")
    destination.parent.mkdir(parents=True, exist_ok=True)
    arrays = state_dict_to_numpy(load_checkpoint(source))
    np.savez_compressed(destination, **arrays)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a review-only NumPy checkpoint candidate"
    )
    parser.add_argument(
        "--ckpt",
        required=True,
        help="checkpoint path relative to JAYA_RESEARCH/data/checkpoints",
    )
    parser.add_argument(
        "--out",
        required=True,
        help=".npz path relative to JAYA_RESEARCH/data/artifact_outbox",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        output = convert_checkpoint(arguments.ckpt, arguments.out)
    except CheckpointConversionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Candidate written for external review: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
