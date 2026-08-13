"""Static verifier for legacy code datasets; execution is intentionally absent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DatasetVerificationError(ValueError):
    """Raised when a legacy code dataset is malformed."""


def verify_dataset_without_execution(path: Path | str) -> dict[str, Any]:
    """Validate and hash dataset samples without compiling or running them."""
    dataset_path = Path(path).expanduser().resolve()
    if not dataset_path.is_file() or dataset_path.is_symlink():
        raise DatasetVerificationError("dataset must be a regular file")
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetVerificationError("dataset is not valid UTF-8 JSON") from exc
    if not isinstance(payload, list):
        raise DatasetVerificationError("dataset must be a list")

    sample_digests: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise DatasetVerificationError(f"sample {index} must be an object")
        input_logic = item.get("input_logic")
        output_llvm = item.get("output_llvm")
        if not isinstance(input_logic, str) or not input_logic.strip():
            raise DatasetVerificationError(f"sample {index} has no input_logic")
        if not isinstance(output_llvm, str) or not output_llvm.strip():
            raise DatasetVerificationError(f"sample {index} has no output_llvm")
        canonical = json.dumps(
            {"input_logic": input_logic, "output_llvm": output_llvm},
            sort_keys=True,
            separators=(",", ":"),
        )
        sample_digests.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    return {
        "status": "verified_without_execution",
        "samples": len(sample_digests),
        "sample_sha256": sample_digests,
    }


if __name__ == "__main__":
    default_dataset = Path(__file__).resolve().parents[1] / "data" / "seed_dataset.json"
    print(json.dumps(verify_dataset_without_execution(default_dataset), indent=2))
