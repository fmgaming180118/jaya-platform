import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, cast

SCHEMA_KEYS = [
    "greeting",
    "no_memory",
    "portable",
    "header",
    "closing",
    "intent_action",
    "intent_query",
    "mixed_notice",
    "clarify",
    "segment_no_memory",
    "segment_clarify",
    "segment_with_memory",
    "procedure_step",
    "procedure_meta",
]

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


def _load_env() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _default_output_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "qlora" / "language_policy_qlora_dataset.jsonl"


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
                candidate = clean[start : idx + 1]
                try:
                    payload = json.loads(candidate)
                    if isinstance(payload, dict):
                        return cast(Dict[str, Any], payload)
                except Exception:
                    return None
    return None


def _seed_to_text(seed_file: Optional[str]) -> str:
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

    if isinstance(payload, dict):
        lines: list[str] = []
        for key, value in cast(Dict[str, Any], payload).items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    return text


def _build_prompt(language: str, key: str, seed_text: str, max_chars: int) -> str:
    language_name = "Indonesian" if language == "id" else "English"
    placeholder_rules = REQUIRED_PLACEHOLDERS.get(key)
    placeholder_text = ""
    if placeholder_rules:
        placeholder_text = " Must include placeholders: " + ", ".join(placeholder_rules) + "."

    prompt = (
        "Disable chain-of-thought output and return final answer directly. "
        "Generate one compact assistant template for language policy. "
        f"Language: {language_name}. Field: {key}. "
        f"Output limit: <= {max_chars} characters. "
        "Return only JSON object: {\"text\":\"...\"}. "
        "No markdown, no explanation."
        + placeholder_text
    )

    if seed_text:
        compact_seed = re.sub(r"\n{3,}", "\n\n", seed_text.strip())
        if len(compact_seed) > 2200:
            compact_seed = compact_seed[:2200].rstrip() + "..."
        prompt += "\n\nStyle hints:\n" + compact_seed

    return prompt


def _call_ollama(
    host: str,
    model: str,
    prompt: str,
    temperature: float,
    num_predict: int,
    timeout: int,
    num_ctx: int,
    disable_thinking: bool,
) -> str:
    url = host.rstrip("/") + "/api/generate"
    options: Dict[str, Any] = {
        "temperature": temperature,
        "num_predict": num_predict,
        "num_ctx": num_ctx,
    }
    if disable_thinking:
        options["think"] = False

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": options,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="ignore").strip()
        except Exception:
            detail = ""
        if detail:
            raise RuntimeError(f"Failed calling Ollama: HTTP {exc.code} {detail}") from exc
        raise RuntimeError(f"Failed calling Ollama: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed calling Ollama: {exc}") from exc

    body = json.loads(raw)
    response_text = body.get("response")
    if not isinstance(response_text, str) or not response_text.strip():
        # Some reasoning-capable models (for example qwen3) can place structured
        # output in `thinking` while leaving `response` empty.
        thinking_text = body.get("thinking")
        if isinstance(thinking_text, str) and thinking_text.strip():
            response_text = thinking_text

    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("Ollama returned empty response/thinking payload")

    nested = _extract_json_object(response_text)
    if nested and isinstance(nested.get("text"), str):
        return str(nested["text"]).strip()

    return response_text.strip()


def _sanitize_template(key: str, value: str, max_chars: int) -> Optional[str]:
    clean = re.sub(r"\s+", " ", value.strip())
    if not clean:
        return None

    if len(clean) > max_chars:
        clean = clean[:max_chars].rstrip() + "..."

    required_tokens = REQUIRED_PLACEHOLDERS.get(key)
    if required_tokens and not all(token in clean for token in required_tokens):
        return None

    found_tokens = set(PLACEHOLDER_PATTERN.findall(clean))
    allowed_tokens = set(required_tokens or ())
    if found_tokens - allowed_tokens:
        return None

    return clean


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QLoRA language dataset from Ollama model")
    parser.add_argument("--model", default=os.getenv("QLORA_OLLAMA_MODEL", "qwen3:4b"), help="Ollama model for synthetic data")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"), help="Ollama host URL")
    parser.add_argument("--out", default=str(_default_output_path()), help="Output JSONL dataset path")
    parser.add_argument("--seed-file", default=None, help="Optional seed text/json for style hints")
    parser.add_argument("--variants-per-key", type=int, default=6, help="Synthetic examples per key per language")
    parser.add_argument("--max-chars", type=int, default=220, help="Max characters per generated template")
    parser.add_argument("--temperature", type=float, default=0.2, help="Ollama temperature")
    parser.add_argument("--num-predict", type=int, default=120, help="Max generated tokens")
    parser.add_argument("--request-timeout", type=int, default=60, help="HTTP timeout in seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retries per sample on request errors")
    parser.add_argument("--num-ctx", type=int, default=int(os.getenv("OLLAMA_NUM_CTX", "2048")), help="Ollama context window")
    parser.add_argument(
        "--disable-thinking",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Request no-thinking mode for models that support it",
    )
    parser.add_argument("--sleep-ms", type=int, default=0, help="Delay between requests in milliseconds")
    parser.add_argument("--verbose", action="store_true", help="Print per-request logs")
    args = parser.parse_args()

    _load_env()

    seed_text = _seed_to_text(args.seed_file)
    variants = max(1, min(int(args.variants_per_key), 40))
    max_chars = max(80, min(int(args.max_chars), 420))
    temperature = max(0.0, min(float(args.temperature), 1.2))
    num_predict = max(32, min(int(args.num_predict), 512))
    timeout = max(10, min(int(args.request_timeout), 600))
    retries = max(0, min(int(args.retries), 8))
    num_ctx = max(512, min(int(args.num_ctx), 32768))
    disable_thinking = bool(args.disable_thinking)
    sleep_seconds = max(0.0, min(float(args.sleep_ms) / 1000.0, 2.0))

    dataset_rows: list[Dict[str, Any]] = []
    failed = 0
    failure_reasons: Dict[str, int] = {}
    total_requests = len(SCHEMA_KEYS) * 2 * variants
    completed = 0

    print("QLoRA dataset build started.", flush=True)
    print(f"- Teacher model: {args.model}", flush=True)
    print(f"- Target requests: {total_requests}", flush=True)

    for language in ("id", "en"):
        for key in SCHEMA_KEYS:
            for variant_idx in range(variants):
                completed += 1
                if args.verbose:
                    print(
                        f"[request] {completed}/{total_requests} "
                        f"lang={language} key={key} var={variant_idx + 1}",
                        flush=True,
                    )

                prompt = _build_prompt(language, key, seed_text, max_chars=max_chars)
                clean: Optional[str] = None
                last_exc: Optional[Exception] = None

                for attempt in range(retries + 1):
                    try:
                        text = _call_ollama(
                            host=args.host,
                            model=args.model,
                            prompt=prompt,
                            temperature=temperature,
                            num_predict=num_predict,
                            timeout=timeout,
                            num_ctx=num_ctx,
                            disable_thinking=disable_thinking,
                        )
                        clean = _sanitize_template(key, text, max_chars=max_chars)
                        if clean is not None:
                            break

                        # Soft failure: response received but not usable by sanitizer.
                        failure_reasons["sanitize_rejected"] = failure_reasons.get("sanitize_rejected", 0) + 1
                        if attempt < retries:
                            time.sleep(0.4 * (attempt + 1))
                    except Exception as exc:
                        last_exc = exc
                        if attempt < retries:
                            time.sleep(0.6 * (attempt + 1))

                if clean is None:
                    failed += 1
                    if last_exc is not None:
                        reason = str(last_exc).strip().splitlines()[0] if str(last_exc).strip() else "unknown_error"
                        if len(reason) > 160:
                            reason = reason[:160] + "..."
                        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                else:
                    user_prompt = (
                        "Write one assistant template for language policy "
                        f"field='{key}' language='{language}'."
                    )
                    dataset_rows.append(
                        {
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You write short, safe, structured language policy templates for JAYA.",
                                },
                                {
                                    "role": "user",
                                    "content": user_prompt,
                                },
                                {
                                    "role": "assistant",
                                    "content": clean,
                                },
                            ],
                            "meta": {
                                "language": language,
                                "key": key,
                                "variant": variant_idx + 1,
                                "teacher_model": args.model,
                            },
                        }
                    )

                if completed == 1 or completed % 10 == 0 or completed == total_requests:
                    print(
                        f"[progress] {completed}/{total_requests} "
                        f"ok={len(dataset_rows)} fail={failed} "
                        f"lang={language} key={key} var={variant_idx + 1}",
                        flush=True,
                    )

                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

    if not dataset_rows:
        print("[ERROR] Dataset generation failed: no valid rows collected")
        if failure_reasons:
            top_reasons = sorted(failure_reasons.items(), key=lambda item: item[1], reverse=True)[:5]
            print(f"- Top fail reasons: {top_reasons}")
        return 1

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in dataset_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("QLoRA dataset generation complete.")
    print(f"- Teacher model: {args.model}")
    print(f"- Rows written: {len(dataset_rows)}")
    print(f"- Failed samples: {failed}")
    if failure_reasons:
        top_reasons = sorted(failure_reasons.items(), key=lambda item: item[1], reverse=True)[:5]
        print(f"- Top fail reasons: {top_reasons}")
    print(f"- Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
