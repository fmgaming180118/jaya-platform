import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, cast


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


def _import_training_stack() -> Dict[str, Any]:
    try:
        torch = importlib.import_module("torch")
        datasets_mod = importlib.import_module("datasets")
        peft_mod = importlib.import_module("peft")
        transformers_mod = importlib.import_module("transformers")
        trl_mod = importlib.import_module("trl")
    except Exception as exc:
        raise RuntimeError(
            "QLoRA stack is missing. Install with: pip install -e \"packages/jaya-research[torch]\""
        ) from exc

    load_dataset = getattr(datasets_mod, "load_dataset")
    LoraConfig = getattr(peft_mod, "LoraConfig")
    prepare_model_for_kbit_training = getattr(peft_mod, "prepare_model_for_kbit_training")
    AutoModelForCausalLM = getattr(transformers_mod, "AutoModelForCausalLM")
    AutoTokenizer = getattr(transformers_mod, "AutoTokenizer")
    BitsAndBytesConfig = getattr(transformers_mod, "BitsAndBytesConfig")
    TrainingArguments = getattr(transformers_mod, "TrainingArguments")
    SFTTrainer = getattr(trl_mod, "SFTTrainer")

    return {
        "torch": torch,
        "load_dataset": load_dataset,
        "LoraConfig": LoraConfig,
        "prepare_model_for_kbit_training": prepare_model_for_kbit_training,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "TrainingArguments": TrainingArguments,
        "SFTTrainer": SFTTrainer,
    }


def _default_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "qlora" / "language_policy_qlora_dataset.jsonl"


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "qlora" / "adapter-qwen-language"


def _render_chat(messages: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for msg in messages:
        role_raw = str(msg.get("role", "user")).strip().lower()
        role = role_raw if role_raw in {"system", "user", "assistant"} else "user"
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"<|{role}|>\n{content}")
    return "\n".join(lines)


def _is_nonempty_text_row(row: Dict[str, Any]) -> bool:
    text = row.get("text")
    return isinstance(text, str) and bool(text.strip())


def _load_local_dataset(dataset_path: Path):
    if dataset_path.is_dir():
        # Try to find a train file inside the directory
        candidates = [
            "train_preprocess.jsonl",
            "train_preprocess.json",
            "train_preprocess.csv",
            "train_preprocess.tsv",
            "train.csv",
            "train.tsv",
        ]
        for name in candidates:
            candidate = dataset_path / name
            if candidate.exists():
                dataset_path = candidate
                break

    suffix = dataset_path.suffix.lower()
    if suffix in {".json", ".jsonl"}:
        return "json", {"data_files": str(dataset_path)}
    if suffix == ".csv":
        return "csv", {"data_files": str(dataset_path)}
    if suffix == ".tsv":
        return "csv", {"data_files": str(dataset_path), "delimiter": "\t"}

    raise ValueError(
        f"Unsupported local dataset format: {dataset_path}. "
        "Use .json, .jsonl, .csv, .tsv, or point to a Hugging Face dataset identifier."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Train QLoRA adapter for JAYA language policy")
    parser.add_argument("--dataset", default=str(_default_dataset_path()), help="JSONL dataset path or Hugging Face dataset identifier (e.g. indonlu)")
    parser.add_argument(
        "--base-model",
        default=os.getenv("QLORA_BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
        help="Hugging Face base model (same family as Ollama teacher)",
    )
    parser.add_argument("--output-dir", default=str(_default_output_dir()), help="Adapter output directory")
    parser.add_argument("--epochs", type=float, default=2.0, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=1, help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=16, help="Gradient accumulation steps")
    parser.add_argument("--learning-rate", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--max-seq-length", type=int, default=768, help="Max sequence length")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--lora-dropout", type=float, default=0.05, help="LoRA dropout")
    parser.add_argument(
        "--target-modules",
        default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
        help="Comma-separated target modules",
    )
    parser.add_argument("--save-steps", type=int, default=100, help="Checkpoint save steps")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup and dataset only")
    args = parser.parse_args()

    _load_env()

    try:
        stack = _import_training_stack()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    torch = stack["torch"]
    load_dataset = stack["load_dataset"]
    LoraConfig = stack["LoraConfig"]
    prepare_model_for_kbit_training = stack["prepare_model_for_kbit_training"]
    AutoModelForCausalLM = stack["AutoModelForCausalLM"]
    AutoTokenizer = stack["AutoTokenizer"]
    BitsAndBytesConfig = stack["BitsAndBytesConfig"]
    TrainingArguments = stack["TrainingArguments"]
    SFTTrainer = stack["SFTTrainer"]

    has_cuda = bool(torch.cuda.is_available())
    if not has_cuda and not args.dry_run:
        torch_version = getattr(torch, "__version__", "unknown")
        cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
        print("[ERROR] CUDA GPU is required for practical QLoRA training")
        print(f"- Python executable: {sys.executable}")
        print(f"- torch version: {torch_version}")
        print(f"- torch CUDA build: {cuda_version}")
        print("- Hint: run packages/jaya-research/setup_qlora_cuda_env.cmd")
        return 1

    dataset_path = Path(args.dataset)
    if dataset_path.exists():
        loader, loader_kwargs = _load_local_dataset(dataset_path)
        dataset = load_dataset(loader, split="train", **loader_kwargs)
    else:
        print(f"[INFO] Loading Hugging Face dataset: {args.dataset}")
        loaded = load_dataset(args.dataset)
        if hasattr(loaded, "keys"):
            if "train" in loaded:
                dataset = loaded["train"]
            else:
                first_split = next(iter(loaded.keys()))
                dataset = loaded[first_split]
        else:
            dataset = loaded

    def _to_text(example: Dict[str, Any]) -> Dict[str, str]:
        if isinstance(example.get("text"), str):
            return {"text": example["text"].strip()}

        messages_raw = example.get("messages")
        if isinstance(messages_raw, list):
            messages = cast(List[Dict[str, Any]], messages_raw)
            return {"text": _render_chat(messages)}

        text_fields: List[str] = []
        for key, value in example.items():
            if isinstance(value, str) and value.strip():
                text_fields.append(value.strip())
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                text_fields.append(" ".join(item.strip() for item in value if item.strip()))

        return {"text": "\n".join(text_fields)}

    dataset = dataset.map(_to_text)
    dataset = dataset.filter(_is_nonempty_text_row)

    if len(dataset) == 0:
        print("[ERROR] Dataset has no valid rows after preprocessing")
        return 1

    if args.dry_run:
        print("QLoRA dry-run successful.")
        print(f"- Base model: {args.base_model}")
        print(f"- Dataset rows: {len(dataset)}")
        print(f"- Max sequence length: {args.max_seq_length}")
        print(f"- CUDA available: {'yes' if has_cuda else 'no'}")
        if not has_cuda:
            print("- Note: training requires CUDA; run setup_qlora_cuda_env.cmd before full run")
        return 0

    bf16_available = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    compute_dtype = torch.bfloat16 if bf16_available else torch.float16

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    target_modules = [part.strip() for part in args.target_modules.split(",") if part.strip()]
    lora_config = LoraConfig(
        r=max(4, int(args.lora_r)),
        lora_alpha=max(8, int(args.lora_alpha)),
        lora_dropout=max(0.0, min(float(args.lora_dropout), 0.5)),
        target_modules=target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=max(0.2, float(args.epochs)),
        per_device_train_batch_size=max(1, int(args.batch_size)),
        gradient_accumulation_steps=max(1, int(args.grad_accum)),
        learning_rate=max(1e-6, float(args.learning_rate)),
        warmup_ratio=0.03,
        logging_steps=5,
        save_steps=max(20, int(args.save_steps)),
        save_total_limit=2,
        fp16=not bf16_available,
        bf16=bf16_available,
        optim="paged_adamw_8bit",
        lr_scheduler_type="cosine",
        gradient_checkpointing=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        formatting_func=lambda example: example["text"],
        peft_config=lora_config,
    )

    trainer.train()
    trainer.model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    report_path = output_dir / "training_report.json"
    report: Dict[str, Any] = {
        "base_model": args.base_model,
        "dataset": str(dataset_path),
        "rows": int(len(dataset)),
        "epochs": float(args.epochs),
        "batch_size": int(args.batch_size),
        "grad_accum": int(args.grad_accum),
        "learning_rate": float(args.learning_rate),
        "max_seq_length": int(args.max_seq_length),
        "target_modules": target_modules,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("QLoRA training complete.")
    print(f"- Adapter output: {output_dir}")
    print(f"- Report: {report_path}")
    print("- Runtime note: keep adapter in training path only; deploy distilled lightweight policy for JAYA runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
