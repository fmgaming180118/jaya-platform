"""NVIDIA NIM-backed language-model adapter for JAYA_RESEARCH."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from openai import OpenAI

try:
    from config import config
    from provider_errors import (
        ProviderAuthError,
        ProviderInvalidResponseError,
        ProviderPolicy,
        execute_with_retry,
    )
except ImportError:
    from src.config import config
    from src.provider_errors import (
        ProviderAuthError,
        ProviderInvalidResponseError,
        ProviderPolicy,
        execute_with_retry,
    )


load_dotenv()

_override_model: Optional[str] = None


def set_override_model(model_name: str) -> None:
    global _override_model
    _override_model = model_name.strip() or None


def get_override_model() -> Optional[str]:
    return _override_model


def _bounded_env_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


class Teacher:
    """Typed, bounded adapter around the NVIDIA OpenAI-compatible endpoint."""

    PROVIDER = "nvidia_nim"

    def __init__(
        self,
        config_path: str = "config.yaml",
        model_type: str = "reasoning",
        *,
        client: Any = None,
        policy: Optional[ProviderPolicy] = None,
    ) -> None:
        self.config = self._load_config(config_path)
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise ProviderAuthError(
                self.PROVIDER,
                "NVIDIA_API_KEY is not configured",
            )

        self.model = self._resolve_model(model_type)
        self.api_base = os.getenv("NVIDIA_LLAMA31_BASE_URL", config.NVIDIA_BASE_URL)
        self.provider_policy = policy or ProviderPolicy.from_env("NVIDIA_PROVIDER")
        self.temperature = _bounded_env_float(
            "NVIDIA_LLAMA31_TEMPERATURE",
            0.6,
            minimum=0.0,
            maximum=2.0,
        )
        self.top_p = _bounded_env_float(
            "NVIDIA_LLAMA31_TOP_P",
            0.95,
            minimum=0.0,
            maximum=1.0,
        )

        self.client = client or OpenAI(
            base_url=self.api_base,
            api_key=self.api_key,
            timeout=self.provider_policy.read_timeout_seconds,
            max_retries=0,
        )

    def _resolve_model(self, model_type: str) -> str:
        if _override_model:
            return _override_model

        reasoning_model = (
            os.getenv("RESEARCH_REASONING_MODEL")
            or os.getenv("NVIDIA_LLAMA3.1_MODEL")
            or os.getenv("NVIDIA_LLAMA31_MODEL")
            or config.NVIDIA_REASONING_MODEL
        )
        model_by_type = {
            "reasoning": reasoning_model,
            "chat": os.getenv("NVIDIA_CHAT_MODEL") or config.NVIDIA_CHAT_MODEL,
            "standard": os.getenv("NVIDIA_CHAT_MODEL") or config.NVIDIA_CHAT_MODEL,
            "coding": os.getenv("NVIDIA_CODING_MODEL") or config.NVIDIA_CODING_MODEL,
            "vision": os.getenv("VIDEO_VLM_MODEL") or config.NVIDIA_VISION_MODEL,
        }
        return model_by_type.get(model_type, model_by_type["chat"])

    def _load_config(self, path: str) -> dict[str, Any]:
        candidate = Path(path)
        if not candidate.is_absolute():
            project_candidate = Path(__file__).resolve().parents[1] / candidate
            if project_candidate.exists():
                candidate = project_candidate
            elif Path("config.yaml").exists():
                candidate = Path("config.yaml")
        if candidate.exists():
            with candidate.open("r", encoding="utf-8") as file_handle:
                loaded = yaml.safe_load(file_handle)
            return loaded if isinstance(loaded, dict) else {}
        return {"system": {"name": "JAYA_RESEARCH"}}

    def ask(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        system_instruction: str = "You are a helpful AI assistant.",
        stream: bool = False,
    ) -> str:
        """Send a prompt and either return valid model content or raise."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(system_instruction, str) or not system_instruction.strip():
            raise ValueError("system_instruction must be a non-empty string")

        tokens_to_use = (
            max_tokens
            if max_tokens is not None
            else int(os.getenv("NVIDIA_LLAMA31_MAX_TOKENS", "4096"))
        )
        if tokens_to_use <= 0:
            raise ValueError("max_tokens must be greater than zero")

        def request_completion() -> str:
            extra_body: dict[str, Any] = {}
            if os.getenv("NVIDIA_LLAMA3.1_THINKING_MODE", "false").lower() == "true":
                extra_body["thinking_mode"] = True

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=tokens_to_use,
                extra_body=extra_body,
                stream=stream,
            )
            return (
                self._consume_stream(completion)
                if stream
                else self._extract_completion(completion)
            )

        return execute_with_retry(
            self.PROVIDER,
            request_completion,
            self.provider_policy,
        )

    def _extract_completion(self, completion: Any) -> str:
        try:
            content = completion.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider response did not contain a completion",
                cause_type=type(exc).__name__,
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider returned empty completion content",
            )
        return content

    def _consume_stream(self, completion: Any) -> str:
        parts: list[str] = []
        try:
            for chunk in completion:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                content = getattr(choices[0].delta, "content", None)
                if isinstance(content, str):
                    parts.append(content)
        except ProviderInvalidResponseError:
            raise
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider returned a malformed completion stream",
                cause_type=type(exc).__name__,
            ) from exc

        response = "".join(parts)
        if not response.strip():
            raise ProviderInvalidResponseError(
                self.PROVIDER,
                "Provider returned an empty completion stream",
            )
        return response

    def generate_completion(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        system_instruction: str = "You are a helpful AI assistant.",
    ) -> str:
        return self.ask(
            prompt,
            max_tokens=max_tokens,
            system_instruction=system_instruction,
        )

    def suggest_optimization(
        self,
        code_snippet: str,
        focus: str = "performance",
    ) -> str:
        """Ask the model for a code-only optimization response."""
        prompt = f"""
        You are a Senior Python Optimization Engineer.
        Rewrite the Python code below for better speed, memory use, and clarity.
        Focus: {focus}.

        IMPORTANT:
        1. Return ONLY the raw Python code. No ```python``` blocks, no explanations.
        2. Keep every public function, class, and signature unchanged.
        3. Keep the logic identical. 1+1 must still equal 2.

        CODE:
        {code_snippet}
        """
        response = self.ask(
            prompt,
            max_tokens=2048,
            system_instruction="You are a code optimizer. Output only raw code.",
        )

        if response.startswith("```python"):
            response = response.replace("```python", "").replace("```", "")
        elif response.startswith("```"):
            response = response.replace("```", "")
        return response.strip()


if __name__ == "__main__":
    try:
        teacher = Teacher()
        print(f"[*] Connected to Teacher: {teacher.model}")
        print("[*] Sending test query...")
        teacher_response = teacher.ask(
            "What is 2 + 2? Answer with just the number."
        )
        print(f"[*] Teacher Response: {teacher_response}")
    except Exception as error:
        print(f"[!] Setup failed: {type(error).__name__}")
