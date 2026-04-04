import argparse
from collections import Counter
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, cast

# Make src/ importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.brain_v2.extensions.nvidia_llm import NvidiaNIMClient
from src.brain_v2.soul.language_policy import LANGUAGE_CORE


REQUIRED_PLACEHOLDERS: Dict[str, tuple[str, ...]] = {
    "intent_action": ("{intent}",),
    "intent_query": ("{intent}",),
    "segment_no_memory": ("{index}",),
    "segment_clarify": ("{index}",),
    "segment_with_memory": ("{index}", "{summary}"),
    "procedure_step": ("{index}", "{step}"),
    "procedure_meta": ("{source}", "{confidence}"),
}

PLACEHOLDER_PATTERN = re.compile(r"\{[a-z_]+\}")


class _NimChatClient(Protocol):
    def chat(
        self,
        messages: list[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.5,
    ) -> Optional[str]: ...


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


def _default_output_path() -> Path:
    core_root = Path(__file__).resolve().parents[1]
    return core_root / "docs" / "language_policy_overrides.json"


def _schema_keys() -> list[str]:
    return list(LANGUAGE_CORE["id"].keys())


def _seed_value_to_line(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()

    if isinstance(value, list):
        raw_items = cast(list[Any], value)
        parts = [_seed_value_to_line(item) for item in raw_items]
        clean_parts = [part for part in parts if part]
        return " | ".join(clean_parts[:12])

    if isinstance(value, dict):
        raw_map = cast(Dict[str, Any], value)
        pairs: list[str] = []
        for key, nested in raw_map.items():
            nested_text = _seed_value_to_line(nested)
            if nested_text:
                pairs.append(f"{key}={nested_text}")
        return "; ".join(pairs[:10])

    return ""


def _load_seed_examples(seed_file: Optional[str]) -> str:
    if not seed_file:
        return ""

    seed_path = Path(seed_file).expanduser().resolve()
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    text = seed_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return ""

    if seed_path.suffix.lower() != ".json":
        return text

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text

    lines: list[str] = []
    if isinstance(payload, dict):
        raw_map = cast(Dict[str, Any], payload)
        for key, value in raw_map.items():
            normalized = _seed_value_to_line(value)
            if normalized:
                lines.append(f"{key}: {normalized}")
    elif isinstance(payload, list):
        raw_items = cast(list[Any], payload)
        for item in raw_items:
            normalized = _seed_value_to_line(item)
            if normalized:
                lines.append(normalized)
    else:
        normalized = _seed_value_to_line(payload)
        if normalized:
            lines.append(normalized)

    return "\n".join(lines).strip()


def _build_prompt(seed_examples: str = "") -> str:
    keys = _schema_keys()
    key_list = ", ".join(keys)
    placeholder_rules = "; ".join(
        f"{key} must include {' and '.join(tokens)}"
        for key, tokens in REQUIRED_PLACEHOLDERS.items()
    )

    base_prompt = (
        "You are a compact language policy distiller for an ultra-lightweight local assistant. "
        "Return ONLY valid JSON object with top-level keys: id and en. "
        "Each top-level value is an object that may contain these keys only: "
        f"{key_list}. "
        "Rules: (1) Keep each value short, clear, <= 220 chars. "
        "(2) No markdown, no explanation, JSON only. "
        "(3) Indonesian text for id and English text for en. "
        "(4) Keep safety and clarity tone for low-resource offline assistant. "
        f"(5) Preserve placeholders for templated fields: {placeholder_rules}."
    )

    if not seed_examples:
        return base_prompt

    compact_seed = re.sub(r"\n{3,}", "\n\n", seed_examples.strip())
    if len(compact_seed) > 2600:
        compact_seed = compact_seed[:2600].rstrip() + "..."

    return (
        base_prompt
        + " (6) Use the style hints below as guidance, but do not copy personal data or secrets."
        + "\n\nStyle hints:\n"
        + compact_seed
    )


def _call_nim(model: Optional[str], prompt: str, max_tokens: int, temperature: float) -> str:
    client = cast(_NimChatClient, NvidiaNIMClient(is_reasoning=False))
    if model:
        cast(Any, client).model = model

    messages: list[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are a JSON-only generator. Output must be valid JSON object only, no markdown, no explanation."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    response_text = client.chat(messages, max_tokens=max_tokens, temperature=temperature)
    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("NVIDIA NIM returned empty response or request failed")
    return response_text


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    clean = text.strip()
    if not clean:
        return None

    try:
        payload = json.loads(clean)
        if isinstance(payload, dict):
            return cast(Dict[str, Any], payload)
    except Exception:
        pass

    start = clean.find("{")
    if start < 0:
        return None

    depth = 0
    for idx in range(start, len(clean)):
        ch = clean[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = clean[start: idx + 1]
                try:
                    payload = json.loads(candidate)
                    if isinstance(payload, dict):
                        return cast(Dict[str, Any], payload)
                except Exception:
                    return None
    return None


def _sanitize_policy_payload(payload: Dict[str, Any], max_chars: int = 220) -> Dict[str, Any]:
    keys = _schema_keys()
    result: Dict[str, Any] = {"id": {}, "en": {}}

    for lang in ("id", "en"):
        raw_lang = payload.get(lang)
        if not isinstance(raw_lang, dict):
            continue
        raw_map = cast(Dict[str, Any], raw_lang)

        for key in keys:
            value = raw_map.get(key)
            if not isinstance(value, str):
                continue

            clean = re.sub(r"\s+", " ", value.strip())
            if not clean:
                continue

            if len(clean) > max_chars:
                clean = clean[:max_chars].rstrip() + "..."

            required_tokens = REQUIRED_PLACEHOLDERS.get(key)
            if required_tokens and not all(token in clean for token in required_tokens):
                continue

            found_tokens = set(PLACEHOLDER_PATTERN.findall(clean))
            allowed_tokens = set(required_tokens or ())
            if found_tokens - allowed_tokens:
                continue

            result[lang][key] = clean

    return result


def _count_fields(payload: Dict[str, Any]) -> int:
    total = 0
    for lang in ("id", "en"):
        section = payload.get(lang)
        if isinstance(section, dict):
            total += len(cast(Dict[str, Any], section))
    return total


def _merge_candidates(candidates: list[Dict[str, Any]]) -> Dict[str, Any]:
    keys = _schema_keys()
    merged: Dict[str, Any] = {"id": {}, "en": {}}

    for lang in ("id", "en"):
        for key in keys:
            bucket: list[str] = []
            for candidate in candidates:
                lang_map = candidate.get(lang)
                if not isinstance(lang_map, dict):
                    continue
                value = cast(Dict[str, Any], lang_map).get(key)
                if isinstance(value, str) and value.strip():
                    bucket.append(value)

            if not bucket:
                continue

            counter = Counter(bucket)
            winner = sorted(counter.items(), key=lambda item: (-item[1], -len(item[0])))[0][0]
            merged[lang][key] = winner

    return merged


def _build_round_prompt(seed_examples: str, round_index: int, rounds: int) -> str:
    base = _build_prompt(seed_examples=seed_examples)
    if rounds <= 1:
        return base

    return (
        base
        + "\n\n"
        + "Round metadata (for internal diversity only): "
        + f"round={round_index + 1}/{rounds}. "
        + "Generate concise but not identical wording across rounds while preserving all constraints."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Distill compact language policy from NVIDIA NIM")
    parser.add_argument("--model", default=os.getenv("NVIDIA_MODEL", "meta/llama3-70b-instruct"), help="NVIDIA NIM model name")
    parser.add_argument("--out", default=str(_default_output_path()), help="Output JSON path")
    parser.add_argument("--seed-file", default=None, help="Optional txt/json seed examples file for style guidance")
    parser.add_argument("--rounds", type=int, default=1, help="Number of distillation rounds for ensemble merge")
    parser.add_argument("--round-delay", type=float, default=0.0, help="Optional delay between rounds (seconds)")
    parser.add_argument("--max-chars", type=int, default=220, help="Max chars per language field")
    parser.add_argument("--max-tokens", type=int, default=1200, help="Max output tokens from NIM")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    parser.add_argument("--dry-run", action="store_true", help="Print distilled payload without writing file")
    args = parser.parse_args()

    _load_env()

    try:
        rounds = max(1, min(int(args.rounds), 24))
        round_delay = max(0.0, min(float(args.round_delay), 15.0))
        bounded_max_chars = max(80, min(args.max_chars, 420))
        bounded_max_tokens = max(256, min(args.max_tokens, 4096))
        bounded_temperature = max(0.0, min(args.temperature, 1.0))

        seed_examples = _load_seed_examples(args.seed_file)

        candidates: list[Dict[str, Any]] = []
        candidate_field_counts: list[int] = []
        round_errors: list[str] = []

        for round_index in range(rounds):
            prompt = _build_round_prompt(seed_examples=seed_examples, round_index=round_index, rounds=rounds)
            try:
                raw_text = _call_nim(
                    model=args.model,
                    prompt=prompt,
                    max_tokens=bounded_max_tokens,
                    temperature=bounded_temperature,
                )

                payload = _extract_json_object(raw_text)
                if payload is None:
                    raise RuntimeError("Could not parse JSON object from NVIDIA NIM output")

                distilled_round = _sanitize_policy_payload(payload, max_chars=bounded_max_chars)
                round_fields = _count_fields(distilled_round)
                if round_fields > 0:
                    candidates.append(distilled_round)
                    candidate_field_counts.append(round_fields)
                else:
                    round_errors.append(f"round {round_index + 1}: zero usable fields")
            except Exception as round_exc:
                round_errors.append(f"round {round_index + 1}: {round_exc}")

            if round_delay > 0 and round_index < (rounds - 1):
                time.sleep(round_delay)

        if not candidates:
            detail = "; ".join(round_errors[:6])
            raise RuntimeError(f"All rounds failed. Detail: {detail}")

        if len(candidates) == 1:
            distilled = candidates[0]
        else:
            distilled = _merge_candidates(candidates)

        total_fields = _count_fields(distilled)
        if total_fields == 0:
            raise RuntimeError("Distilled payload has zero usable fields")

        distilled["_meta"] = {
            "source": "nim_distillation",
            "model": args.model,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_fields": total_fields,
            "rounds_requested": rounds,
            "rounds_succeeded": len(candidates),
            "candidate_field_counts": candidate_field_counts,
        }
        if round_errors:
            distilled["_meta"]["round_errors"] = round_errors[:6]
        if args.seed_file:
            distilled["_meta"]["seed_file"] = str(Path(args.seed_file).name)

        if args.dry_run:
            print(json.dumps(distilled, ensure_ascii=False, indent=2))
            print("\n[dry-run] no file written")
            return 0

        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(distilled, ensure_ascii=False, indent=2), encoding="utf-8")

        print("Distillation complete.")
        print(f"- Provider: NVIDIA NIM")
        print(f"- Model: {args.model}")
        print(f"- Rounds: {len(candidates)}/{rounds} succeeded")
        if args.seed_file:
            print(f"- Seed file: {Path(args.seed_file).resolve()}")
        print(f"- Fields: {total_fields}")
        print(f"- Output: {out_path}")
        print("- Runtime impact: tiny (only lightweight template strings are loaded)")
        return 0

    except Exception as exc:
        print(f"[ERROR] Distillation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
