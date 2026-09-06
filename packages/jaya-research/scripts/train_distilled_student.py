#!/usr/bin/env python3
"""Train tiny student model via knowledge distillation from NIM teacher."""

import argparse
import json
import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_DATA_ROOT = WORKSPACE_ROOT / "data" / "jaya-research"

def main():
    p = argparse.ArgumentParser(description="Distill NIM teacher knowledge to tiny student model")
    p.add_argument('--student', default='Qwen/Qwen2.5-0.5B-Instruct', help='Student model (HF)')
    p.add_argument('--train-data', default=str(RESEARCH_DATA_ROOT / 'distillation' / 'student_training_data.jsonl'), help='Training data JSONL')
    p.add_argument('--out-dir', default=str(RESEARCH_DATA_ROOT / 'distillation' / 'student-qwen-0.5b'), help='Output directory')
    p.add_argument('--epochs', type=int, default=3, help='Training epochs')
    p.add_argument('--batch-size', type=int, default=2, help='Batch size')
    p.add_argument('--grad-accum', type=int, default=8, help='Gradient accumulation')
    p.add_argument('--max-seq-length', type=int, default=512, help='Max sequence length')
    p.add_argument('--learning-rate', type=float, default=2e-4, help='Learning rate')
    p.add_argument('--lora-r', type=int, default=8, help='LoRA rank')
    p.add_argument('--lora-alpha', type=int, default=16, help='LoRA alpha')
    p.add_argument('--dry-run', action='store_true', help='Validate setup only')
    args = p.parse_args()

    # Load env
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE_ROOT / ".env")

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, 
            Trainer, TrainingArguments, BitsAndBytesConfig, DataCollatorForLanguageModeling
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from datasets import load_dataset
    except ImportError as e:
        print(f"[ERROR] Missing dependencies: {e}")
        print('Install: pip install -e "packages/jaya-research[torch]"')
        return 1

    # Check CUDA
    has_cuda = torch.cuda.is_available()
    if not has_cuda and not args.dry_run:
        print("[ERROR] CUDA required for training")
        return 1

    # Load dataset
    print(f"Loading dataset: {args.train_data}")
    dataset = load_dataset('json', data_files=args.train_data, split='train')
    print(f"Dataset size: {len(dataset)}")

    # Format for instruction tuning
    def format_instruction(example):
        instruction = example.get('instruction', '').strip()
        response = example.get('response', '').strip()
        if instruction and response:
            return {"text": f"<|im_start|>user\n{instruction}<|im_end|>\n<|im_start|>assistant\n{response}<|im_end|>"}
        return {"text": ""}

    dataset = dataset.map(format_instruction)
    dataset = dataset.filter(lambda x: len(x['text']) > 0)
    print(f"Formatted dataset size: {len(dataset)}")

    if args.dry_run:
        print("Dry run successful!")
        return 0

    # Load student model (4-bit QLoRA)
    print(f"Loading student model: {args.student}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        args.student,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.student, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Prepare for QLoRA
    model = prepare_model_for_kbit_training(model)
    
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Tokenize
    def tokenize(ex):
        return tokenizer(ex['text'], truncation=True, max_length=args.max_seq_length, padding=False)

    tokenized = dataset.map(tokenize, remove_columns=dataset.column_names)

    # Training args
    training_args = TrainingArguments(
        output_dir=args.out_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        remove_unused_columns=False,
        report_to="none",
    )

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=data_collator,
    )

    print("Starting distillation training...")
    trainer.train()
    trainer.save_model(args.out_dir)
    tokenizer.save_pretrained(args.out_dir)
    
    print(f"Student model saved to: {args.out_dir}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
