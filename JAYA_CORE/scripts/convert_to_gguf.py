#!/usr/bin/env python3
"""Phase 4: Convert distilled student model to GGUF for edge deployment."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(description="Convert student model to GGUF for edge deployment")
    p.add_argument('--policy', default='distilled-student-qwen-0.5b-v1', help='Policy name in registry')
    p.add_argument('--out-dir', default='JAYA_CORE/data/edge_deploy', help='Output directory for GGUF')
    p.add_argument('--quantization', default='q4_k_m', choices=['q4_k_m', 'q4_k_s', 'q5_k_m', 'q8_0', 'f16'], help='GGUF quantization')
    p.add_argument('--llama-cpp-dir', default=None, help='Path to llama.cpp repo (for conversion)')
    args = p.parse_args()

    # Load registry
    registry_file = Path("data/policies/registry.json")
    if not registry_file.exists():
        print("ERROR: Registry not found")
        return 1
    
    with open(registry_file, "r") as f:
        registry = json.load(f)
    
    if args.policy not in registry:
        print(f"ERROR: Policy {args.policy} not found in registry")
        return 1
    
    policy = registry[args.policy]
    adapter_path = Path(policy["path"])
    base_model = policy["base_model"]
    
    print(f"Converting policy: {args.policy}")
    print(f"Base model: {base_model}")
    print(f"Adapter: {adapter_path}")
    print(f"Quantization: {args.quantization}")
    
    # Check if llama.cpp is available
    llama_cpp_dir = Path(args.llama_cpp_dir) if args.llama_cpp_dir else Path(os.getenv("LLAMA_CPP_DIR", ""))
    if not llama_cpp_dir.exists():
        # Try to find llama.cpp
        possible_paths = [
            Path.home() / "llama.cpp",
            Path("C:/llama.cpp"),
            Path("D:/llama.cpp"),
            Path("../llama.cpp"),
        ]
        for p in possible_paths:
            if p.exists():
                llama_cpp_dir = p
                break
    
    if not llama_cpp_dir or not llama_cpp_dir.exists():
        print("ERROR: llama.cpp not found. Please install llama.cpp and set LLAMA_CPP_DIR env var")
        print("  git clone https://github.com/ggerganov/llama.cpp")
        print("  cmake -B build && cmake --build build --config Release")
        return 1
    
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        print(f"ERROR: convert_hf_to_gguf.py not found in {llama_cpp_dir}")
        return 1
    
    # Create output directory
    out_dir = Path(args.out_dir) / args.policy
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Merge adapter with base model (create merged HF model)
    print("\n[1/3] Merging adapter with base model...")
    merged_dir = out_dir / "merged_hf"
    if merged_dir.exists():
        shutil.rmtree(merged_dir)
    
    merge_cmd = [
        sys.executable, "-c", f"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base = AutoModelForCausalLM.from_pretrained(
    "{base_model}",
    torch_dtype=torch.float16,
    device_map="cpu",
    trust_remote_code=True
)
model = PeftModel.from_pretrained(base, "{adapter_path}")
merged = model.merge_and_unload()
merged.save_pretrained("{merged_dir}")
AutoTokenizer.from_pretrained("{base_model}", trust_remote_code=True).save_pretrained("{merged_dir}")
print("Merge complete")
"""
    ]
    
    result = subprocess.run(merge_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR merging: {result.stderr}")
        return 1
    print("Merge complete")
    
    # Step 2: Convert to GGUF
    print("\n[2/3] Converting to GGUF...")
    gguf_file = out_dir / f"{args.policy}-{args.quantization}.gguf"
    
    convert_cmd = [
        sys.executable, str(convert_script),
        str(merged_dir),
        "--outfile", str(gguf_file),
        "--outtype", args.quantization,
    ]
    
    result = subprocess.run(convert_cmd, capture_output=True, text=True, cwd=str(llama_cpp_dir))
    if result.returncode != 0:
        print(f"ERROR converting: {result.stderr}")
        return 1
    print(f"GGUF created: {gguf_file}")
    
    # Step 3: Verify GGUF
    print("\n[3/3] Verifying GGUF...")
    quantize_tool = llama_cpp_dir / "build" / "bin" / "Release" / "llama-quantize.exe"
    if not quantize_tool.exists():
        quantize_tool = llama_cpp_dir / "build" / "bin" / "llama-quantize"
    
    if quantize_tool.exists():
        # Quick test: try to load with llama.cpp
        test_cmd = [
            str(quantize_tool),
            str(gguf_file),
            str(out_dir / "test.gguf"),
            "q4_k_m"
        ]
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("GGUF verification passed")
            (out_dir / "test.gguf").unlink(missing_ok=True)
        else:
            print(f"Warning: GGUF verification failed: {result.stderr}")
    else:
        print("Warning: llama-quantize not found, skipping verification")
    
    # Create deployment manifest
    deploy_manifest = {
        "policy": args.policy,
        "base_model": base_model,
        "gguf_file": str(gguf_file.relative_to(out_dir)),
        "quantization": args.quantization,
        "size_mb": round(gguf_file.stat().st_size / (1024*1024), 1),
        "target_vram_mb": policy.get("metadata", {}).get("target_vram_mb", 500),
        "llama_cpp_version": "latest",
        "created_at": __import__('time').time(),
    }
    
    manifest_file = out_dir / "deploy_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(deploy_manifest, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"EDGE DEPLOYMENT READY")
    print(f"{'='*50}")
    print(f"GGUF: {gguf_file}")
    print(f"Size: {deploy_manifest['size_mb']} MB")
    print(f"Quantization: {args.quantization}")
    print(f"Target VRAM: {deploy_manifest['target_vram_mb']} MB")
    print(f"Manifest: {manifest_file}")
    print(f"\nTo run on edge device:")
    print(f"  llama.cpp/main -m {gguf_file.name} -p 'Apa itu machine learning?' -n 100")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())