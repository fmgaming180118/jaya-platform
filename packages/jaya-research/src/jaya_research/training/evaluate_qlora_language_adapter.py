import argparse
import gc
import importlib
import json
import os
import random
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

REQUIRED_PLACEHOLDERS: Dict[str, tuple[str, ...]] = {
    "intent_action": ("{intent}",),
    "intent_query": ("{intent}",),
    "segment_no_memory": ("{index}",),
    "segment_clarify": ("{index}",),
    "segment_with_memory": ("{index}", "{summary}"),
    "procedure_step": ("{index}", "{step}"),
    "procedure_meta": ("{source}", "{confidence}"),
}

GATE_METRICS = (
    "avg_exact",
    "avg_similarity",
    "avg_placeholder_score",
    "avg_weighted_score",
)


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


def _import_eval_stack() -> Dict[str, Any]:
    try:
        torch = importlib.import_module("torch")
        transformers_mod = importlib.import_module("transformers")
        peft_mod = importlib.import_module("peft")
    except Exception as exc:
        raise RuntimeError(
            "Evaluation stack is missing. Install with: pip install -e \"packages/jaya-research[torch]\""
        ) from exc

    return {
        "torch": torch,
        "AutoModelForCausalLM": getattr(transformers_mod, "AutoModelForCausalLM"),
        "AutoTokenizer": getattr(transformers_mod, "AutoTokenizer"),
        "BitsAndBytesConfig": getattr(transformers_mod, "BitsAndBytesConfig", None),
        "PeftModel": getattr(peft_mod, "PeftModel"),
    }


def _default_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "qlora" / "language_policy_qlora_dataset.jsonl"


def _default_report_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "qlora" / "eval_report.json"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _normalize_prediction(text: str) -> str:
    clean = text.strip()
    clean = re.sub(r"^<\|assistant\|>\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<\|end[^>]*\|>", "", clean, flags=re.IGNORECASE)

    if clean.startswith("{") and clean.endswith("}"):
        try:
            payload = json.loads(clean)
            if isinstance(payload, dict):
                payload_map = cast(Dict[str, Any], payload)
                inner = payload_map.get("text")
                if isinstance(inner, str):
                    return _normalize_text(inner)
        except Exception:
            pass

    return _normalize_text(clean)


def _extract_sample(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    messages_raw = row.get("messages")
    if not isinstance(messages_raw, list):
        return None

    system_text = ""
    user_text = ""
    assistant_text = ""

    raw_messages = cast(List[Any], messages_raw)
    for message in raw_messages:
        if not isinstance(message, dict):
            continue
        message_map = cast(Dict[str, Any], message)
        role = str(message_map.get("role", "")).strip().lower()
        content = str(message_map.get("content", "")).strip()
        if not content:
            continue
        if role == "system" and not system_text:
            system_text = content
        elif role == "user":
            user_text = content
        elif role == "assistant":
            assistant_text = content

    if not user_text or not assistant_text:
        return None

    meta_raw = row.get("meta")
    meta = cast(Dict[str, Any], meta_raw) if isinstance(meta_raw, dict) else {}

    return {
        "system": system_text,
        "user": user_text,
        "expected": assistant_text,
        "language": str(meta.get("language", "")),
        "key": str(meta.get("key", "")),
    }


def _load_samples(dataset_path: Path, sample_count: int, seed: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            if isinstance(payload, dict):
                payload_map = cast(Dict[str, Any], payload)
                sample = _extract_sample(payload_map)
                if sample:
                    rows.append(sample)

    if not rows:
        return []

    rng = random.Random(seed)
    if sample_count < len(rows):
        rows = rng.sample(rows, sample_count)
    return rows


def _build_prompt(tokenizer: Any, sample: Dict[str, Any]) -> str:
    messages: List[Dict[str, str]] = []
    system_text = str(sample.get("system", "")).strip()
    user_text = str(sample.get("user", "")).strip()

    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": user_text})

    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_chat_template):
        try:
            return str(apply_chat_template(messages, tokenize=False, add_generation_prompt=True))
        except Exception:
            pass

    if system_text:
        return f"System:\n{system_text}\n\nUser:\n{user_text}\n\nAssistant:\n"
    return f"User:\n{user_text}\n\nAssistant:\n"


def _score_sample(predicted: str, expected: str, key: str, max_chars: int) -> Dict[str, Any]:
    pred = _normalize_prediction(predicted)
    exp = _normalize_text(expected)

    exact = int(pred == exp)
    similarity = float(SequenceMatcher(None, pred, exp).ratio())
    nonempty = int(bool(pred))
    within_limit = int(len(pred) <= max_chars)

    required = REQUIRED_PLACEHOLDERS.get(key, ())
    if required:
        present = sum(1 for token in required if token in pred)
        placeholder_score = present / len(required)
        missing = [token for token in required if token not in pred]
    else:
        placeholder_score = 1.0
        missing = []

    weighted = (
        0.55 * similarity
        + 0.20 * placeholder_score
        + 0.15 * nonempty
        + 0.10 * within_limit
    )

    return {
        "predicted": pred,
        "expected": exp,
        "exact": exact,
        "similarity": similarity,
        "nonempty": nonempty,
        "within_limit": within_limit,
        "placeholder_score": placeholder_score,
        "missing_placeholders": missing,
        "weighted_score": weighted,
        "predicted_length": len(pred),
    }


def _release_model(torch: Any, model: Any, tokenizer: Any) -> None:
    del model
    del tokenizer
    gc.collect()
    if bool(getattr(torch.cuda, "is_available", lambda: False)()):
        getattr(torch.cuda, "empty_cache", lambda: None)()


def _evaluate_model(
    label: str,
    samples: List[Dict[str, Any]],
    base_model: str,
    adapter_dir: Optional[Path],
    max_new_tokens: int,
    temperature: float,
    max_chars: int,
    device_map: str,
    load_4bit: bool,
    stack: Dict[str, Any],
) -> Dict[str, Any]:
    torch = stack["torch"]
    AutoModelForCausalLM = stack["AutoModelForCausalLM"]
    AutoTokenizer = stack["AutoTokenizer"]
    BitsAndBytesConfig = stack["BitsAndBytesConfig"]
    PeftModel = stack["PeftModel"]

    bf16_available = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    compute_dtype = torch.bfloat16 if bf16_available else torch.float16

    quantization_config = None
    if load_4bit and BitsAndBytesConfig is not None:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: Dict[str, Any] = {
        "device_map": device_map,
        "trust_remote_code": True,
    }
    if quantization_config is not None:
        model_kwargs["quantization_config"] = quantization_config
    else:
        model_kwargs["torch_dtype"] = compute_dtype

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
    if adapter_dir is not None:
        model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.eval()

    sample_reports: List[Dict[str, Any]] = []

    for sample in samples:
        prompt = _build_prompt(tokenizer, sample)
        encoded = tokenizer(prompt, return_tensors="pt")

        input_ids = encoded["input_ids"].to(model.device)
        attention_mask = encoded.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.to(model.device)

        do_sample = bool(temperature > 0.0)
        generation_kwargs: Dict[str, Any] = {
            "input_ids": input_ids,
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if attention_mask is not None:
            generation_kwargs["attention_mask"] = attention_mask
        if do_sample:
            generation_kwargs["temperature"] = max(0.05, temperature)

        with torch.no_grad():
            output_ids = model.generate(**generation_kwargs)

        new_tokens = output_ids[0][input_ids.shape[-1] :]
        predicted = tokenizer.decode(new_tokens, skip_special_tokens=True)

        key = str(sample.get("key", ""))
        metrics = _score_sample(predicted, str(sample.get("expected", "")), key=key, max_chars=max_chars)
        sample_reports.append(
            {
                "key": key,
                "language": str(sample.get("language", "")),
                "user": str(sample.get("user", "")),
                **metrics,
            }
        )

    _release_model(torch, model, tokenizer)

    count = len(sample_reports)
    exact_avg = (sum(item["exact"] for item in sample_reports) / count) if count else 0.0
    sim_avg = (sum(item["similarity"] for item in sample_reports) / count) if count else 0.0
    score_avg = (sum(item["weighted_score"] for item in sample_reports) / count) if count else 0.0
    placeholder_avg = (sum(item["placeholder_score"] for item in sample_reports) / count) if count else 0.0

    return {
        "label": label,
        "samples": count,
        "avg_exact": exact_avg,
        "avg_similarity": sim_avg,
        "avg_placeholder_score": placeholder_avg,
        "avg_weighted_score": score_avg,
        "details": sample_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate base model vs QLoRA adapter on language dataset")
    parser.add_argument("--dataset", default=str(_default_dataset_path()), help="JSONL dataset path")
    parser.add_argument(
        "--base-model",
        default=os.getenv("QLORA_BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
        help="Hugging Face base model",
    )
    parser.add_argument("--adapter-dir", default=None, help="Adapter directory from QLoRA training")
    parser.add_argument("--sample-count", type=int, default=32, help="Evaluation sample count")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sample pick")
    parser.add_argument("--max-new-tokens", type=int, default=96, help="Max generated tokens")
    parser.add_argument("--temperature", type=float, default=0.0, help="Generation temperature")
    parser.add_argument("--max-chars", type=int, default=220, help="Target max chars for templates")
    parser.add_argument("--device-map", default="auto", help="Model device_map")
    parser.add_argument("--base-only", action="store_true", help="Evaluate base only, skip adapter")
    parser.add_argument("--load-4bit", action=argparse.BooleanOptionalAction, default=True, help="Use 4-bit loading")
    parser.add_argument(
        "--gate-metric",
        default="avg_weighted_score",
        choices=GATE_METRICS,
        help="Metric used for pass/fail gate",
    )
    parser.add_argument(
        "--min-delta",
        type=float,
        default=None,
        help="Minimum adapter-base delta for selected gate metric",
    )
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit with code 2 if gate fails")
    parser.add_argument(
        "--require-adapter",
        action="store_true",
        help="Treat missing adapter evaluation as failure",
    )
    parser.add_argument("--out", default=str(_default_report_path()), help="JSON report output path")
    parser.add_argument("--dry-run", action="store_true", help="Validate stack and dataset only")
    args = parser.parse_args()

    _load_env()

    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        print(f"[ERROR] Dataset not found: {dataset_path}")
        return 1

    samples = _load_samples(
        dataset_path=dataset_path,
        sample_count=max(4, min(int(args.sample_count), 512)),
        seed=int(args.seed),
    )
    if not samples:
        print("[ERROR] No valid samples extracted from dataset")
        return 1

    try:
        stack = _import_eval_stack()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    if args.dry_run:
        print("Evaluator dry-run successful.")
        print(f"- Dataset: {dataset_path}")
        print(f"- Samples: {len(samples)}")
        print(f"- Base model: {args.base_model}")
        if args.adapter_dir:
            print(f"- Adapter: {Path(args.adapter_dir).resolve()}")
        return 0

    results: Dict[str, Any] = {}

    try:
        results["base"] = _evaluate_model(
            label="base",
            samples=samples,
            base_model=args.base_model,
            adapter_dir=None,
            max_new_tokens=max(32, min(int(args.max_new_tokens), 256)),
            temperature=max(0.0, min(float(args.temperature), 1.0)),
            max_chars=max(80, min(int(args.max_chars), 420)),
            device_map=str(args.device_map),
            load_4bit=bool(args.load_4bit),
            stack=stack,
        )

        adapter_path: Optional[Path] = None
        if not args.base_only and args.adapter_dir:
            adapter_path = Path(args.adapter_dir).resolve()
            if adapter_path.exists():
                results["adapter"] = _evaluate_model(
                    label="adapter",
                    samples=samples,
                    base_model=args.base_model,
                    adapter_dir=adapter_path,
                    max_new_tokens=max(32, min(int(args.max_new_tokens), 256)),
                    temperature=max(0.0, min(float(args.temperature), 1.0)),
                    max_chars=max(80, min(int(args.max_chars), 420)),
                    device_map=str(args.device_map),
                    load_4bit=bool(args.load_4bit),
                    stack=stack,
                )
            else:
                print(f"[WARN] Adapter dir not found, skip adapter eval: {adapter_path}")
    except Exception as exc:
        print(f"[ERROR] Evaluation failed: {exc}")
        return 1

    delta: Dict[str, float] = {}
    if "base" in results and "adapter" in results:
        for metric in ("avg_exact", "avg_similarity", "avg_placeholder_score", "avg_weighted_score"):
            base_val = float(results["base"].get(metric, 0.0) or 0.0)
            adapter_val = float(results["adapter"].get(metric, 0.0) or 0.0)
            delta[metric] = adapter_val - base_val

    gate_report: Dict[str, Any] = {
        "enabled": args.min_delta is not None,
        "metric": str(args.gate_metric),
        "min_delta": float(args.min_delta) if args.min_delta is not None else None,
        "observed_delta": None,
        "passed": None,
        "reason": None,
    }

    if bool(args.require_adapter) and "adapter" not in results:
        gate_report["enabled"] = True
        gate_report["passed"] = False
        gate_report["reason"] = "adapter_missing"

    if bool(gate_report["enabled"]) and gate_report["passed"] is None:
        if "adapter" not in results:
            gate_report["passed"] = False
            gate_report["reason"] = "adapter_missing"
        else:
            metric_name = str(args.gate_metric)
            observed_delta = float(delta.get(metric_name, 0.0) or 0.0)
            gate_report["observed_delta"] = observed_delta
            min_delta = float(args.min_delta) if args.min_delta is not None else 0.0
            gate_report["passed"] = bool(observed_delta >= min_delta)
            gate_report["reason"] = "ok" if gate_report["passed"] else "delta_below_threshold"

    report: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": str(dataset_path),
        "base_model": args.base_model,
        "adapter_dir": str(Path(args.adapter_dir).resolve()) if args.adapter_dir else None,
        "sample_count": len(samples),
        "config": {
            "max_new_tokens": int(args.max_new_tokens),
            "temperature": float(args.temperature),
            "max_chars": int(args.max_chars),
            "device_map": str(args.device_map),
            "load_4bit": bool(args.load_4bit),
        },
        "results": results,
        "delta": delta,
        "gate": gate_report,
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Evaluation complete.")
    print(f"- Report: {out_path}")
    if "base" in results:
        print(
            "- Base score: "
            f"{float(results['base'].get('avg_weighted_score', 0.0) or 0.0):.4f}"
        )
    if "adapter" in results:
        print(
            "- Adapter score: "
            f"{float(results['adapter'].get('avg_weighted_score', 0.0) or 0.0):.4f}"
        )
    if delta:
        print(
            "- Delta weighted: "
            f"{float(delta.get('avg_weighted_score', 0.0)):+.4f}"
        )

    if bool(gate_report.get("enabled", False)):
        print(
            "- Gate: "
            f"{'PASS' if bool(gate_report.get('passed', False)) else 'FAIL'} "
            f"({gate_report.get('metric')}, min={gate_report.get('min_delta')}, "
            f"observed={gate_report.get('observed_delta')}, reason={gate_report.get('reason')})"
        )

    if bool(args.fail_on_gate) and bool(gate_report.get("enabled", False)) and not bool(gate_report.get("passed", False)):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
