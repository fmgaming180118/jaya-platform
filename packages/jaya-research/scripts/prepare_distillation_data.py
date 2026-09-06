#!/usr/bin/env python3
"""Convert distilled knowledge to training dataset for student model."""

import json
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

def convert_distilled_to_training(distilled_path: Path, output_path: Path):
    """Convert distilled_nemotron.json to instruction-response format for distillation."""
    with open(distilled_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    items = data.get("items", [])
    training_data = []
    
    for item in items:
        prompt = item.get("prompt", "").strip()
        response = item.get("response", "").strip()
        
        if prompt and response:
            training_data.append({
                "instruction": prompt,
                "response": response,
                "source": "nim_distillation",
                "model": item.get("model", "nvidia/nemotron-3-ultra-550b-a55b"),
                "elapsed_seconds": item.get("elapsed_seconds", 0)
            })
    
    # Write as JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for item in training_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    print(f"Converted {len(training_data)} items to {output_path}")
    return len(training_data)

if __name__ == "__main__":
    distilled_path = Path("distilled_nemotron.json")
    output_path = (
        WORKSPACE_ROOT
        / "data"
        / "jaya-research"
        / "distillation"
        / "student_training_data.jsonl"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not distilled_path.exists():
        print(f"ERROR: {distilled_path} not found")
        sys.exit(1)
    
    convert_distilled_to_training(distilled_path, output_path)
