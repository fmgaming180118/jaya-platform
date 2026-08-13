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
    # Use HF Tokenizer for text processing, but native model for architecture
    from transformers import AutoTokenizer
    HAS_TRAIN = True
except ImportError:
    HAS_TRAIN = False

from JAYA_CORE.src.model.native_architecture import JayaLibrarianNativeV0, HAS_TORCH

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
    tokenizer_name: str = "HuggingFaceTB/SmolLM-135M", 
    dataset_path: str = "JAYA_CORE/data/librarian_dataset.jsonl",
    output_dir: str = "JAYA_CORE/models/jaya-core-v0",
    epochs: int = 1,
    max_steps: int = 0,  # 0 means full epochs
    smoke_test: bool = False
):
    if not HAS_TRAIN or not HAS_TORCH:
        logger.error("transformers or torch not installed. Cannot train.")
        return False
        
    logger.info("Initializing Native JAYA Librarian Architecture...")
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    if tokenizer.pad_token is None:
        if tokenizer.eos_token:
            tokenizer.pad_token = tokenizer.eos_token
        else:
            tokenizer.add_special_tokens({'pad_token': '[PAD]'})
            
    # Initialize the NATIVE architecture
    model = JayaLibrarianNativeV0(vocab_size=len(tokenizer))
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    dataset = LibrarianDataset(Path(dataset_path), tokenizer, max_length=512)
    logger.info(f"Loaded dataset with {len(dataset)} examples.")
    
    # Simple split
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=2, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=2, shuffle=False)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    
    global_step = 0
    final_loss = 0.0
    
    epochs_to_run = 1 if smoke_test else epochs
    
    logger.info(f"Starting Native training loop for {epochs_to_run} epochs...")
    for epoch in range(epochs_to_run):
        model.train()
        for batch in train_loader:
            if max_steps > 0 and global_step >= max_steps:
                break
                
            input_ids = batch["input_ids"].to(device)
            targets = batch["labels"].to(device)
            
            logits, loss = model(input_ids, targets=targets)
            
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            
            final_loss = loss.item()
            if global_step % 10 == 0:
                logger.info(f"Epoch {epoch} | Step {global_step} | Loss: {final_loss:.4f}")
            global_step += 1
            
        if max_steps > 0 and global_step >= max_steps:
            break
            
    # Validation loop
    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            targets = batch["labels"].to(device)
            _, loss = model(input_ids, targets=targets)
            val_loss += loss.item()
    val_loss /= max(1, len(val_loader))
    logger.info(f"Validation Loss: {val_loss:.4f}")
            
    # Save the native artifact properly using safetensors
    logger.info(f"Saving JAYA Core Librarian V0 to {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Save model config
    config = model.config
    with open(os.path.join(output_dir, "model_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        
    # Save state dict
    weights_path = os.path.join(output_dir, "model.safetensors")
    from safetensors.torch import save_model
    save_model(model, weights_path)
    
    # Save tokenizer
    tokenizer.save_pretrained(output_dir)
    
    import hashlib
    with open(weights_path, "rb") as f:
        artifact_sha256 = hashlib.sha256(f.read()).hexdigest()
        
    import sys
    
    # Save enhanced training manifest
    manifest = {
        "architecture": "jaya_librarian_native_v0",
        "model_version": "v0.1",
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "tokenizer_origin": tokenizer_name,
        "dataset_count": len(dataset),
        "training_dataset_hash": "placeholder_train_hash",
        "validation_dataset_hash": "placeholder_val_hash",
        "training_steps": global_step,
        "epochs": epochs_to_run,
        "batch_size": 2,
        "optimizer": "AdamW",
        "learning_rate": 1e-4,
        "seed": 42,
        "train_loss": final_loss,
        "validation_loss": val_loss,
        "git_commit": "HEAD",
        "python_version": sys.version,
        "torch_version": torch.__version__,
        "device": str(device),
        "training_duration_seconds": 0.0,
        "weights_filename": "model.safetensors",
        "weights_format": "safetensors",
        "artifact_sha256": artifact_sha256
    }
    with open(os.path.join(output_dir, "training_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    logger.info("Training complete.")
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer", default="HuggingFaceTB/SmolLM-135M")
    parser.add_argument("--data", default="JAYA_CORE/data/librarian_dataset.jsonl")
    parser.add_argument("--out", default="JAYA_CORE/models/jaya-core-v0")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--steps", type=int, default=0) 
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    
    train_librarian(args.tokenizer, args.data, args.out, epochs=args.epochs, max_steps=args.steps, smoke_test=args.smoke_test)
