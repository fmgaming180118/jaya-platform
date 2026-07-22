#!/usr/bin/env python3
"""Merge LoRA adapter into base model for edge deployment."""

import json
import sys
from pathlib import Path

# Add JAYA_CORE to path
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

def main():
    # Paths
    adapter_src = Path("../JAYA_RESEARCH/data/distillation/student-qwen-0.5b")
    merged_dir = Path("data/policies/distilled-student-qwen-0.5b-v1-merged")
    
    print(f"Merging adapter: {adapter_src}")
    print(f"Output: {merged_dir}")
    
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError as e:
        print(f"[ERROR] Missing dependencies: {e}")
        return 1
    
    # Load base model
    base_model = "Qwen/Qwen2.5-0.5B-Instruct"
    print(f"Loading base model: {base_model}")
    
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    
    # Load and merge adapter
    print(f"Loading adapter: {adapter_src}")
    model = PeftModel.from_pretrained(model, str(adapter_src))
    
    print("Merging adapter...")
    model = model.merge_and_unload()
    
    # Save merged model
    print(f"Saving merged model to: {merged_dir}")
    merged_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(merged_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(merged_dir))
    
    # Create deployment manifest
    manifest = {
        "policy": "distilled-student-qwen-0.5b-v1",
        "type": "merged_model",
        "base_model": base_model,
        "adapter_source": str(adapter_src),
        "merged_path": str(merged_dir),
        "size_mb": round(sum(f.stat().st_size for f in merged_dir.rglob("*") if f.is_file()) / (1024*1024), 1),
        "target_vram_mb": 500,
        "quantization": "fp16 (ready for GGUF conversion)",
        "created_at": __import__('time').time(),
        "notes": "Merged LoRA adapter into base model. Ready for GGUF conversion via llama.cpp",
    }
    
    manifest_file = merged_dir / "deploy_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"MERGED MODEL READY FOR EDGE DEPLOYMENT")
    print(f"{'='*50}")
    print(f"Path: {merged_dir}")
    print(f"Size: {manifest['size_mb']} MB")
    print(f"Target VRAM: {manifest['target_vram_mb']} MB (fp16)")
    print(f"Manifest: {manifest_file}")
    print(f"\nNext steps for GGUF conversion:")
    print(f"  1. Install llama.cpp: git clone https://github.com/ggerganov/llama.cpp")
    print(f"  2. Build: cd llama.cpp && make")
    print(f"  3. Convert: python llama.cpp/convert_hf_to_gguf.py {merged_dir} --outfile model.gguf --outtype q4_k_m")
    print(f"  4. Run: llama.cpp/main -m model.gguf -p 'Apa itu machine learning?' -n 100")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())