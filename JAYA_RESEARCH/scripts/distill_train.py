#!/usr/bin/env python3
"""Teacher -> Student distillation scaffold.

This is a minimal, configurable distillation script scaffold using HuggingFace Trainer APIs.
It is intended as a starting point — adapt datasets, tokenization, and teacher prompts to your needs.
"""
import argparse
import os

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--teacher', required=True, help='Teacher model name or path')
    p.add_argument('--student', required=True, help='Student model name or path (init)')
    p.add_argument('--train-data', required=True, help='Path to instruction JSONL or HF dataset identifier')
    p.add_argument('--out-dir', required=True, help='Output directory for student checkpoints')
    p.add_argument('--epochs', type=int, default=1)
    args = p.parse_args()

    # Lazy imports to keep startup fast when not used
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    from datasets import load_dataset

    tokenizer = AutoTokenizer.from_pretrained(args.student, use_fast=True)
    student = AutoModelForCausalLM.from_pretrained(args.student)

    # Load dataset either from file or HF id
    if os.path.exists(args.train_data):
        ds = load_dataset('json', data_files=args.train_data)['train']
    else:
        ds = load_dataset(args.train_data)

    # TODO: map dataset to tokenized inputs/labels for distillation
    def preprocess(ex):
        instr = ex.get('instruction') or ex.get('input') or ''
        resp = ex.get('response') or ex.get('output') or ''
        txt = instr + '\n' + resp
        return tokenizer(txt, truncation=True, max_length=512)

    tokenized = ds.map(preprocess, remove_columns=ds.column_names)

    training_args = TrainingArguments(
        output_dir=args.out_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=4,
        save_strategy='epoch',
        logging_steps=50,
    )

    trainer = Trainer(
        model=student,
        args=training_args,
        train_dataset=tokenized,
    )

    trainer.train()
    trainer.save_model(args.out_dir)

if __name__ == '__main__':
    main()
