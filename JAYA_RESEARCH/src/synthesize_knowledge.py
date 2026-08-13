"""Synthesize video reports without persisting provider failures as knowledge."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

try:
    from config import config
    from provider_errors import (
        ProviderAuthError,
        ProviderError,
        ProviderInvalidResponseError,
        ProviderPolicy,
        ensure_http_success,
        execute_with_retry,
    )
except ImportError:
    from src.config import config
    from src.provider_errors import (
        ProviderAuthError,
        ProviderError,
        ProviderInvalidResponseError,
        ProviderPolicy,
        ensure_http_success,
        execute_with_retry,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _extract_content(payload: Any) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderInvalidResponseError(
            "nvidia_nim",
            "Provider response did not contain synthesized content",
            cause_type=type(exc).__name__,
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderInvalidResponseError(
            "nvidia_nim",
            "Provider returned empty synthesized content",
        )
    return content


def generate_knowledge_synthesis(all_reports_content: str) -> str:
    """Return a valid synthesis or raise a typed provider exception."""
    if not isinstance(all_reports_content, str) or not all_reports_content.strip():
        raise ValueError("all_reports_content must be a non-empty string")

    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ProviderAuthError(
            "nvidia_nim",
            "NVIDIA_API_KEY is not configured",
        )

    model = (
        os.getenv("NVIDIA_LLAMA31_MODEL")
        or os.getenv("NVIDIA_LLAMA3.1_MODEL")
        or config.NVIDIA_REASONING_MODEL
    )
    base_url = (
        os.getenv("NVIDIA_LLAMA31_BASE_URL")
        or os.getenv("NVIDIA_LLAMA3.1_BASE_URL")
        or config.NVIDIA_BASE_URL
    )
    invoke_url = f"{base_url.rstrip('/')}/chat/completions"
    max_tokens = int(os.getenv("NVIDIA_LLAMA31_MAX_TOKENS", "4096"))
    if max_tokens <= 0:
        raise ValueError("NVIDIA_LLAMA31_MAX_TOKENS must be greater than zero")

    prompt = f"""
You are JAYA_RESEARCH, an advanced AI researcher.

Analyze the raw observational reports below and create one Markdown knowledge
artifact. Separate direct observations, supported inferences, uncertainties,
and follow-up questions. Extract core topics, facts, procedures, technical
details, and actionable knowledge. Never present failed analyses as evidence.

RAW REPORTS:
{all_reports_content}
"""
    temperature = float(os.getenv("NVIDIA_LLAMA31_TEMPERATURE", "0.5"))
    top_p = float(os.getenv("NVIDIA_LLAMA31_TOP_P", "0.95"))
    if not 0 <= temperature <= 2:
        raise ValueError("NVIDIA_LLAMA31_TEMPERATURE must be between 0 and 2")
    if not 0 <= top_p <= 1:
        raise ValueError("NVIDIA_LLAMA31_TOP_P must be between 0 and 1")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    policy = ProviderPolicy.from_env("NVIDIA_PROVIDER")

    def request() -> str:
        response = requests.post(
            invoke_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=policy.requests_timeout,
        )
        ensure_http_success("nvidia_nim", response)
        try:
            response_payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderInvalidResponseError(
                "nvidia_nim",
                "Provider returned malformed JSON",
                cause_type=type(exc).__name__,
            ) from exc
        return _extract_content(response_payload)

    return execute_with_retry("nvidia_nim", request, policy)


def main() -> int:
    reports_dir = PROJECT_ROOT / "reports" / "video_analysis"
    report_files = list(reports_dir.glob("*_report.md"))
    print(f"Found {len(report_files)} report files.")

    report_sections: list[str] = []
    for report_file in report_files:
        print(f"Reading: {report_file.name}")
        content = report_fs.read_text(encoding="utf-8")
        if "Analysis failed" in content and len(content) < 2000:
            print(f"Skipping incomplete report: {report_file.name}")
            continue
        report_sections.append(
            f"\n\n=== SOURCE REPORT: {report_file.name} ===\n{content}"
        )

    if not report_sections:
        print("No valid content to synthesize.")
        return 0

    try:
        knowledge = generate_knowledge_synthesis("".join(report_sections))
    except ProviderError as error:
        print(f"[SYNTHESIS FAILED] {error.code} ({error.provider})")
        return 1

    knowledge_path = reports_dir / "CONSOLIDATED_KNOWLEDGE.md"
    knowledge_path.write_text(knowledge, encoding="utf-8")
    print(f"Knowledge synthesis complete: {knowledge_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
