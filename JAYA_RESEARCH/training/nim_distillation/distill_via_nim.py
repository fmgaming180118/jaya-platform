#!/usr/bin/env python3
"""Distil pengetahuan dari NVIDIA NIM ke artefak riset JAYA Research.

Script ini menjaga boundary domain: hasil distilasi disimpan ke artefak lokal
JSON/Markdown di JAYA_RESEARCH dan tidak mengimpor logika internal JAYA_CORE.

Fitur utama:
- orkestrasi workflow yang dibatasi jumlah prompt dan timeout jaringan
- pemanggilan API NIM yang terpisah dari parsing dan penyimpanan artefak
- logging jelas, error handling aman, dan metadata reproducibility

Usage:
    python distill_via_nim.py --prompts prompts.txt --output-json distilled_knowledge.json

Environment variables:
    NIM_API_URL: URL endpoint NIM, mis. https://ai.api.nvidia.com/v1/nim/<model>
    NIM_API_KEY: API key untuk autentikasi.
    NIM_MODEL: Nama model opsional.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load .env from JAYA_RESEARCH root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass(frozen=True)
class DistillationConfig:
    """Konfigurasi runtime untuk satu sesi distilasi."""

    api_url: str
    api_key: str
    model: Optional[str]
    max_tokens: int
    temperature: float
    timeout_seconds: int
    max_prompts: int
    seed: int


@dataclass(frozen=True)
class DistillationItem:
    """Satu hasil distilasi beserta metadata reproducibility."""

    prompt: str
    response: str
    model: str
    elapsed_seconds: float
    seed: int
    timestamp_unix: float

    def to_dict(self) -> Dict[str, Any]:
        """Ubah item menjadi dictionary serializable."""
        return asdict(self)


@dataclass(frozen=True)
class DistillationResult:
    """Kumpulan hasil distilasi dan ringkasan kegagalan."""

    metadata: Dict[str, Any]
    items: List[Dict[str, Any]]
    failures: List[Dict[str, Any]]


def parse_args() -> argparse.Namespace:
    """Parse argumen CLI secara terpisah dari eksekusi utama."""
    parser = argparse.ArgumentParser(description="Distill knowledge from NIM API into JAYA Research artifacts")
    parser.add_argument("--prompts", type=Path, required=True, help="File berisi prompt, satu per baris")
    parser.add_argument("--output-json", type=Path, help="Opsional: simpan output terstruktur ke JSON")
    parser.add_argument("--output-md", type=Path, help="Opsional: simpan ringkasan Markdown")
    parser.add_argument("--max-tokens", type=int, default=150, help="Maksimum token generasi")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="Timeout request ke NIM")
    parser.add_argument("--max-prompts", type=int, default=50, help="Batas prompt per eksekusi")
    parser.add_argument("--seed", type=int, default=42, help="Seed untuk reproducibility")
    return parser.parse_args()


def load_prompts(file_path: Path) -> List[str]:
    """Muat prompt dari file teks, satu prompt per baris."""
    with file_path.open("r", encoding="utf-8") as handle:
        prompts = [line.strip() for line in handle if line.strip()]
    return prompts


def build_request_payload(prompt: str, config: DistillationConfig) -> Dict[str, Any]:
    """Bangun payload request NIM secara deterministik."""
    payload: Dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "stream": False,
        "seed": config.seed,
    }
    if config.model:
        payload["model"] = config.model
    return payload


def query_nim(prompt: str, config: DistillationConfig) -> str:
    """Kirim prompt ke NIM dan kembalikan teks hasil generasi."""
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = build_request_payload(prompt, config)

    response = requests.post(
        config.api_url,
        headers=headers,
        json=payload,
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    result = response.json()

    try:
        return result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Format respons NIM tidak dikenali: {result}") from exc


def collect_distilled_item(
    prompt: str,
    response_text: str,
    model: str,
    elapsed_seconds: float,
    seed: int,
) -> DistillationItem:
    """Bentuk satu item hasil distilasi beserta metadata reproducibility."""
    return DistillationItem(
        prompt=prompt,
        response=response_text,
        model=model,
        elapsed_seconds=round(elapsed_seconds, 4),
        seed=seed,
        timestamp_unix=time.time(),
    )


def save_distilled_json(output_json: Path, result: DistillationResult) -> None:
    """Simpan hasil distilasi ke file JSON yang bisa dipakai ulang."""
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(asdict(result), handle, indent=2, ensure_ascii=False)


def render_markdown_summary(result: DistillationResult, source_prompts: Path) -> str:
    """Render ringkasan Markdown agar mudah dibaca manusia atau model lain."""
    lines = [
        "# Distilled Knowledge Summary",
        "",
        f"- Sumber prompt: `{source_prompts.name}`",
        f"- Jumlah item sukses: {len(result.items)}",
        f"- Jumlah kegagalan: {len(result.failures)}",
        f"- Seed: `{result.metadata.get('seed', 'unknown')}`",
        f"- Model: `{result.metadata.get('model') or 'unknown'}`",
        "",
        "## Metadata",
        "",
        "```json",
        json.dumps(result.metadata, indent=2, ensure_ascii=False),
        "```",
        "",
    ]

    if result.failures:
        lines.extend([
            "## Kegagalan",
            "",
            "```json",
            json.dumps(result.failures, indent=2, ensure_ascii=False),
            "```",
            "",
        ])

    lines.append("## Item Hasil")
    lines.append("")

    for index, item in enumerate(result.items, start=1):
        lines.extend([
            f"### Item {index}",
            f"- Prompt: {item['prompt']}",
            f"- Elapsed: {item['elapsed_seconds']}s",
            f"- Seed: {item['seed']}",
            "- Respons:",
            "",
            "```text",
            item["response"],
            "```",
            "",
        ])
    return "\n".join(lines)


def write_markdown(output_path: Path, markdown_text: str) -> None:
    """Tulis artefak Markdown ke disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_text, encoding="utf-8")


def build_config(args: argparse.Namespace) -> DistillationConfig:
    """Bangun konfigurasi runtime dari CLI dan environment."""
    api_url = os.getenv("NIM_API_URL")
    api_key = os.getenv("NIM_API_KEY")
    model = os.getenv("NIM_MODEL")

    if not api_url or not api_key:
        raise RuntimeError("NIM_API_URL dan NIM_API_KEY harus diset di environment.")

    return DistillationConfig(
        api_url=api_url,
        api_key=api_key,
        model=model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        timeout_seconds=args.timeout_seconds,
        max_prompts=args.max_prompts,
        seed=args.seed,
    )


def run_distillation(prompts: List[str], config: DistillationConfig) -> DistillationResult:
    """Jalankan distilasi dengan batas prompt dan handling error yang aman."""
    bounded_prompts = prompts[: config.max_prompts]
    distilled_items: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    print(f"Runtime config: {json.dumps(asdict(config), ensure_ascii=False)}")

    for index, prompt in enumerate(bounded_prompts, start=1):
        preview = prompt[:80] + ("..." if len(prompt) > 80 else "")
        print(f"[{index}/{len(bounded_prompts)}] Querying NIM for: {preview}")

        try:
            start_time = time.time()
            response_text = query_nim(prompt, config)
            elapsed_seconds = time.time() - start_time
            print(
                f"  -> Response received in {elapsed_seconds:.2f}s: "
                f"{response_text[:100]}{'...' if len(response_text) > 100 else ''}"
            )
            item = collect_distilled_item(
                prompt=prompt,
                response_text=response_text,
                model=config.model or "unknown",
                elapsed_seconds=elapsed_seconds,
                seed=config.seed,
            )
            distilled_items.append(item.to_dict())
        except requests.Timeout as exc:
            error_message = f"Timeout saat query NIM: {exc}"
            print(f"  !! {error_message}", file=sys.stderr)
            failures.append({"prompt": prompt, "error": error_message})
        except requests.RequestException as exc:
            error_message = f"HTTP error saat query NIM: {exc}"
            print(f"  !! {error_message}", file=sys.stderr)
            failures.append({"prompt": prompt, "error": error_message})
        except ValueError as exc:
            error_message = f"Error parsing respons NIM: {exc}"
            print(f"  !! {error_message}", file=sys.stderr)
            failures.append({"prompt": prompt, "error": error_message})
        except Exception as exc:
            error_message = f"Error tak terduga saat memproses prompt: {exc}"
            print(f"  !! {error_message}", file=sys.stderr)
            failures.append({"prompt": prompt, "error": error_message})

    metadata = {
        "api_url": config.api_url,
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "timeout_seconds": config.timeout_seconds,
        "max_prompts": config.max_prompts,
        "seed": config.seed,
        "source_prompt_count": len(prompts),
        "executed_prompt_count": len(bounded_prompts),
        "success_count": len(distilled_items),
        "failure_count": len(failures),
    }
    return DistillationResult(metadata=metadata, items=distilled_items, failures=failures)


def main() -> int:
    """Entry point CLI utama dengan exit code eksplisit."""
    args = parse_args()

    try:
        config = build_config(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        prompts = load_prompts(args.prompts)
    except FileNotFoundError:
        print(f"Error: file prompt tidak ditemukan: {args.prompts}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error saat membaca file prompt {args.prompts}: {exc}", file=sys.stderr)
        return 1

    if not prompts:
        print("Error: tidak ada prompt valid yang ditemukan.", file=sys.stderr)
        return 1

    print(f"Loaded {len(prompts)} prompts from {args.prompts}")
    result = run_distillation(prompts, config)

    if args.output_json:
        save_distilled_json(args.output_json, result)
        print(f"Saved distilled knowledge to {args.output_json}")

    if args.output_md:
        markdown_text = render_markdown_summary(result, args.prompts)
        write_markdown(args.output_md, markdown_text)
        print(f"Saved markdown summary to {args.output_md}")

    print(
        f"Distillation complete. Success={len(result.items)} Failure={len(result.failures)} "
        f"PromptLimit={config.max_prompts}"
    )

    if result.failures:
        print("Some prompts failed, but the process ended safely with preserved state.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
