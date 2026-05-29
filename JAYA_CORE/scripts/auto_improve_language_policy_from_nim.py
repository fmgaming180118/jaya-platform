import argparse
import os
import subprocess
import sys
from pathlib import Path


def _load_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automatic CLI for improving JAYA language policy from NVIDIA NIM"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("NVIDIA_MODEL", "meta/llama3-70b-instruct"),
        help="NVIDIA NIM model name",
    )
    parser.add_argument(
        "--seed-file",
        default=None,
        help="Optional path to seed examples file for style guidance",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "docs" / "language_policy_overrides.json"),
        help="Output path for distilled language policy",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Number of distillation rounds to ask NVIDIA NIM",
    )
    parser.add_argument(
        "--round-delay",
        type=float,
        default=1.0,
        help="Seconds to wait between NIM rounds",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1200,
        help="Maximum output tokens from NIM",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="NIM sampling temperature",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the distilled payload without writing the output file",
    )
    args = parser.parse_args()

    _load_env()

    if not os.getenv("NVIDIA_API_KEY"):
        print("[ERROR] NVIDIA_API_KEY is not set. Set it in the environment or .env file.")
        return 1

    if args.seed_file is None:
        seed_path = Path(__file__).resolve().parents[1] / "docs" / "language_distillation_seed.example.json"
        if seed_path.exists():
            args.seed_file = str(seed_path)

    script_path = Path(__file__).with_name("distill_language_policy_from_nim.py")
    if not script_path.exists():
        print(f"[ERROR] Distillation script not found: {script_path}")
        return 1

    cmd = [
        sys.executable,
        str(script_path),
        "--model",
        args.model,
        "--out",
        args.out,
        "--rounds",
        str(max(1, min(args.rounds, 24))),
        "--round-delay",
        str(max(0.0, min(args.round_delay, 15.0))),
        "--max-tokens",
        str(max(256, min(args.max_tokens, 4096))),
        "--temperature",
        str(max(0.0, min(args.temperature, 1.0))),
    ]

    if args.seed_file:
        cmd.extend(["--seed-file", args.seed_file])
    if args.dry_run:
        cmd.append("--dry-run")

    print("Running NVIDIA NIM language distillation...")
    print("Command:", " ".join(cmd))

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[ERROR] Automatic distillation failed.")
        return result.returncode

    if args.dry_run:
        print("[INFO] Dry-run complete. No file was written.")
        return 0

    print("[OK] JAYA language policy updated from NVIDIA NIM.")
    print(f"- Output file: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
