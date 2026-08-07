"""
JAYA Librarian Core V0 - Trainer (Custom PyTorch Loop)
Bypasses HuggingFace Trainer to avoid torchvision import errors.
"""

import json
import logging
from pathlib import Path
import os
import argparse
import math

try:
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoModelForCausalLM, AutoTokenizer
    HAS_TRAIN = True
except ImportError:
    HAS_TRAIN = False

logger = logging.getLogger("LibrarianTrainer")

class LibrarianDataset(torch.utils.data.Dataset):
    def __init__(self, jsonl_path: Path, tokenizer, max_length=1024):
        self.input_ids = []
        self.attention_mask = []
        self.labels = []
        
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                prompt = item["prompt"]
                completion = item["completion"]
                
                full_text = prompt + completion + tokenizer.eos_token
                
                tokenized = tokenizer(
                    full_text, 
                    truncation=True, 
                    max_length=max_length,
                    padding="max_length"
                )
                
                prompt_tokens = tokenizer(prompt, truncation=True, max_length=max_length)
                prompt_len = len(prompt_tokens["input_ids"])
                
                labels = tokenized["input_ids"].copy()
                labels[:prompt_len] = [-100] * prompt_len
                
                self.input_ids.append(torch.tensor(tokenized["input_ids"], dtype=torch.long))
                self.attention_mask.append(torch.tensor(tokenized["attention_mask"], dtype=torch.long))
                self.labels.append(torch.tensor(labels, dtype=torch.long))

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, idx):
        return {
            "input_ids": self.input_ids[idx],
            "attention_mask": self.attention_mask[idx],
            "labels": self.labels[idx]
        }

def train_librarian(
    base_model: str = "HuggingFaceTB/SmolLM-135M", 
    dataset_path: str = "JAYA_CORE/data/librarian_dataset.jsonl",
    output_dir: str = "JAYA_CORE/models/jaya-core-v0",
    epochs: int = 1,
    max_steps: int = 2,  
):
    if not HAS_TRAIN:
        logger.error("transformers or torch not installed. Cannot train.")
        return False
        
    logger.info(f"Loading Base Model for Fine-Tuning: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        if tokenizer.eos_token:
            tokenizer.pad_token = tokenizer.eos_token
        else:
            tokenizer.add_special_tokens({'pad_token': '[PAD]'})
            
    model = AutoModelForCausalLM.from_pretrained(base_model)
    if len(tokenizer) > model.config.vocab_size:
        model.resize_token_embeddings(len(tokenizer))
        
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    dataset = LibrarianDataset(Path(dataset_path), tokenizer, max_length=512) # Shorten for speed
    logger.info(f"Loaded dataset with {len(dataset)} examples.")
    
    dataloader = DataLoader(dataset, batch_size=1, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
    
    model.train()
    global_step = 0
    final_loss = 0.0
    
    logger.info("Starting custom training loop...")
    for epoch in range(epochs):
        for batch in dataloader:
            if global_step >= max_steps:
                break
                
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss
            
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            
            final_loss = loss.item()
            logger.info(f"Step {global_step} | Loss: {final_loss:.4f}")
            global_step += 1
            
        if global_step >= max_steps:
            break
            
    # Save the artifact
    logger.info(f"Saving JAYA Core Librarian V0 to {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    # Save training manifest
    manifest = {
        "base_model": base_model,
        "dataset_count": len(dataset),
        "steps_trained": global_step,
        "final_loss": final_loss,
        "model_version": "v0",
    }
    with open(os.path.join(output_dir, "training_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        
    logger.info("Training complete.")
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HuggingFaceTB/SmolLM-135M")
    parser.add_argument("--data", default="JAYA_CORE/data/librarian_dataset.jsonl")
    parser.add_argument("--out", default="JAYA_CORE/models/jaya-core-v0")
    parser.add_argument("--steps", type=int, default=2) 
    args = parser.parse_args()
    
    train_librarian(args.base, args.data, args.out, max_steps=args.steps)
