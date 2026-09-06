#!/usr/bin/env python3
"""Convert a registered student model into a verified GGUF artifact.

All registry, adapter, and output paths are contained within the workspace. The
external llama.cpp checkout must be supplied explicitly through CLI or env.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CORE_ROOT = Path(__file__).resolve().parents[3]
POLICY_ROOT = CORE_ROOT / "data" / "jaya-core" / "policies"
EDGE_ROOT = CORE_ROOT / "data" / "jaya-core" / "edge_deploy"
POLICY_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
QUANTIZATIONS = ("q4_k_m", "q4_k_s", "q5_k_m", "q8_0", "f16")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_contained(
    raw_path: str | os.PathLike[str],
    *,
    root: Path,
    base: Path = CORE_ROOT,
    must_exist: bool = False,
    directory: bool = False,
) -> Path:
    """Resolve a path and fail if it escapes an allowed root."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved_root = root.resolve(strict=False)
    resolved = candidate.resolve(strict=must_exist)
    if not _is_relative_to(resolved, resolved_root):
        raise ValueError(f"path must stay inside {resolved_root}: {resolved}")
    if must_exist and directory and not resolved.is_dir():
        raise ValueError(f"expected a directory: {resolved}")
    return resolved


def resolve_llama_cpp(raw_path: str | os.PathLike[str]) -> Path:
    """Validate an explicitly configured llama.cpp checkout."""
    path = Path(raw_path).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError(f"llama.cpp path is not a directory: {path}")
    converter = path / "convert_hf_to_gguf.py"
    if not converter.is_file():
        raise ValueError(f"missing llama.cpp converter: {converter}")
    return path


def resolve_adapter_path(raw_path: str) -> Path:
    """Resolve a registry adapter path under the canonical policy directory."""
    normalized = raw_path.replace("\\", "/")
    return resolve_contained(
        normalized,
        root=POLICY_ROOT,
        base=CORE_ROOT,
        must_exist=True,
        directory=True,
    )


def load_policy(registry_path: Path, policy_name: str) -> dict[str, Any]:
    """Load and validate the selected policy entry."""
    if not POLICY_NAME_PATTERN.fullmatch(policy_name):
        raise ValueError(f"invalid policy name: {policy_name!r}")
    try:
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid registry JSON: {registry_path}: {exc}") from exc
    if not isinstance(registry_data, dict):
        raise ValueError("policy registry must contain a JSON object")

    policy = registry_data.get(policy_name)
    if not isinstance(policy, dict):
        raise ValueError(f"policy not found in registry: {policy_name}")
    for key in ("path", "base_model"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            raise ValueError(f"policy field {key!r} must be a non-empty string")
    return policy


def find_quantizer(llama_cpp_dir: Path) -> Path:
    """Find a built llama-quantize binary in standard build layouts."""
    candidates = (
        llama_cpp_dir / "build" / "bin" / "Release" / "llama-quantize.exe",
        llama_cpp_dir / "build" / "bin" / "llama-quantize.exe",
        llama_cpp_dir / "build" / "bin" / "llama-quantize",
        llama_cpp_dir / "llama-quantize.exe",
        llama_cpp_dir / "llama-quantize",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(strict=True)
    raise ValueError("llama-quantize is required for quantized GGUF output")


def run_checked(command: list[str], *, cwd: Path, timeout_seconds: int) -> None:
    """Run a fixed argv command and surface bounded diagnostic output."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {timeout_seconds}s: {Path(command[0]).name}"
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "no diagnostic output").strip()
        raise RuntimeError(
            f"command failed ({result.returncode}): {Path(command[0]).name}: "
            f"{stderr[-4000:]}"
        )


def merge_adapter(
    *,
    base_model: str,
    adapter_path: Path,
    merged_dir: Path,
    trust_remote_code: bool,
) -> None:
    """Merge a PEFT adapter without constructing executable source strings."""
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("conversion requires torch, transformers, and peft") from exc

    try:
        base = AutoModelForCausalLM.from_pretrained(
            base_model,
            torch_dtype=torch.float16,
            device_map="cpu",
            trust_remote_code=trust_remote_code,
        )
        model = PeftModel.from_pretrained(base, str(adapter_path))
        merged = model.merge_and_unload()
        merged.save_pretrained(merged_dir)
        tokenizer = AutoTokenizer.from_pretrained(
            base_model,
            trust_remote_code=trust_remote_code,
        )
        tokenizer.save_pretrained(merged_dir)
    except Exception as exc:
        raise RuntimeError(
            f"model merge failed for {base_model}: {type(exc).__name__}"
        ) from exc


def verify_gguf(path: Path) -> None:
    """Require a non-empty file with the GGUF magic header."""
    if not path.is_file() or path.stat().st_size <= 4:
        raise RuntimeError(f"GGUF output is missing or empty: {path}")
    with path.open("rb") as handle:
        if handle.read(4) != b"GGUF":
            raise RuntimeError(f"invalid GGUF magic header: {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a registered JAYA student model into GGUF."
    )
    parser.add_argument(
        "--policy",
        default="distilled-student-qwen-0.5b-v1",
        help="policy name in the registry",
    )
    parser.add_argument(
        "--registry",
        default=os.getenv("JAYA_POLICY_REGISTRY", str(POLICY_ROOT / "registry.json")),
        help="registry JSON inside data/jaya-core/policies",
    )
    parser.add_argument(
        "--out-dir",
        default=os.getenv("JAYA_GGUF_OUTPUT_DIR", str(EDGE_ROOT)),
        help="output directory inside data/jaya-core/edge_deploy",
    )
    parser.add_argument(
        "--quantization",
        default="q4_k_m",
        choices=QUANTIZATIONS,
        help="final GGUF quantization",
    )
    parser.add_argument(
        "--llama-cpp-dir",
        default=os.getenv("LLAMA_CPP_DIR"),
        help="explicit llama.cpp checkout (env: LLAMA_CPP_DIR)",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="explicitly allow model repository Python code",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing final GGUF artifact",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        help="timeout for each llama.cpp subprocess",
    )
    return parser


def convert(args: argparse.Namespace) -> tuple[Path, Path]:
    if not args.llama_cpp_dir:
        raise ValueError("--llama-cpp-dir or LLAMA_CPP_DIR is required")
    if args.timeout_seconds < 1:
        raise ValueError("--timeout-seconds must be positive")

    registry_path = resolve_contained(
        args.registry,
        root=POLICY_ROOT,
        must_exist=True,
    )
    if not registry_path.is_file():
        raise ValueError(f"registry is not a file: {registry_path}")
    output_dir = resolve_contained(args.out_dir, root=EDGE_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    llama_cpp_dir = resolve_llama_cpp(args.llama_cpp_dir)

    policy = load_policy(registry_path, args.policy)
    adapter_path = resolve_adapter_path(policy["path"])
    base_model = policy["base_model"]
    final_path = output_dir / f"{args.policy}-{args.quantization}.gguf"
    manifest_path = output_dir / f"{args.policy}-{args.quantization}.manifest.json"
    if final_path.exists() and not args.overwrite:
        raise FileExistsError(f"GGUF already exists; pass --overwrite: {final_path}")

    converter = llama_cpp_dir / "convert_hf_to_gguf.py"
    with tempfile.TemporaryDirectory(
        prefix=".gguf-build-", dir=output_dir
    ) as temp_name:
        temp_dir = Path(temp_name).resolve(strict=True)
        merged_dir = temp_dir / "merged_hf"
        merged_dir.mkdir()
        merge_adapter(
            base_model=base_model,
            adapter_path=adapter_path,
            merged_dir=merged_dir,
            trust_remote_code=args.trust_remote_code,
        )

        f16_path = temp_dir / "model-f16.gguf"
        run_checked(
            [
                sys.executable,
                str(converter),
                str(merged_dir),
                "--outfile",
                str(f16_path),
                "--outtype",
                "f16",
            ],
            cwd=llama_cpp_dir,
            timeout_seconds=args.timeout_seconds,
        )
        verify_gguf(f16_path)

        staged_final = temp_dir / final_path.name
        if args.quantization == "f16":
            shutil.copy2(f16_path, staged_final)
        else:
            quantizer = find_quantizer(llama_cpp_dir)
            run_checked(
                [
                    str(quantizer),
                    str(f16_path),
                    str(staged_final),
                    args.quantization.upper(),
                ],
                cwd=llama_cpp_dir,
                timeout_seconds=args.timeout_seconds,
            )
        verify_gguf(staged_final)

        if final_path.exists():
            final_path.unlink()
        shutil.move(staged_final, final_path)

    manifest = {
        "schema_version": 1,
        "policy": args.policy,
        "base_model": base_model,
        "adapter_path": adapter_path.relative_to(CORE_ROOT).as_posix(),
        "gguf_file": final_path.name,
        "quantization": args.quantization,
        "size_bytes": final_path.stat().st_size,
        "sha256": sha256_file(final_path),
        "target_vram_mb": policy.get("metadata", {}).get("target_vram_mb"),
        "converter": "convert_hf_to_gguf.py",
        "created_at": datetime.now(UTC).isoformat(),
    }
    staged_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with staged_manifest.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    staged_manifest.replace(manifest_path)
    return final_path, manifest_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        final_path, manifest_path = convert(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"GGUF conversion failed: {exc}", file=sys.stderr)
        return 1

    print(f"verified GGUF: {final_path}")
    print(f"deployment manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
