#!/usr/bin/env python3
"""Phase 4: Automated llama.cpp install, build, and GGUF conversion for edge deployment."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd, cwd=None, timeout=600, shell=False):
    """Run command with logging."""
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=shell)
    if result.stdout:
        print(result.stdout[-2000:])  # Last 2000 chars
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-2000:]}")
    return result

def main():
    p = argparse.ArgumentParser(description="Install llama.cpp, build, and convert model to GGUF")
    p.add_argument('--policy', default='distilled-student-qwen-0.5b-v1', help='Policy name')
    p.add_argument('--quantization', default='q4_k_m', choices=['q4_k_m', 'q4_k_s', 'q5_k_m', 'q8_0', 'f16'], help='GGUF quantization')
    p.add_argument('--llama-cpp-dir', default=None, help='Existing llama.cpp directory (skip clone)')
    p.add_argument('--skip-clone', action='store_true', help='Skip git clone if exists')
    p.add_argument('--skip-build', action='store_true', help='Skip cmake build')
    p.add_argument('--cuda', action='store_true', help='Enable CUDA support in llama.cpp')
    args = p.parse_args()

    # Paths
    base_dir = Path(__file__).resolve().parents[1]  # JAYA_CORE root
    merged_model = base_dir / "data" / "policies" / "distilled-student-qwen-0.5b-v1-merged"
    out_dir = base_dir / "data" / "edge_deploy" / args.policy
    out_dir.mkdir(parents=True, exist_ok=True)
    
    gguf_file = out_dir / f"{args.policy}-{args.quantization}.gguf"
    
    # llama.cpp directory
    if args.llama_cpp_dir:
        llama_cpp_dir = Path(args.llama_cpp_dir)
    else:
        llama_cpp_dir = base_dir / "llama.cpp"
    
    print(f"{'='*60}")
    print(f"PHASE 4: GGUF CONVERSION FOR EDGE DEPLOYMENT")
    print(f"{'='*60}")
    print(f"Policy: {args.policy}")
    print(f"Merged model: {merged_model}")
    print(f"Output: {gguf_file}")
    print(f"Quantization: {args.quantization}")
    print(f"llama.cpp dir: {llama_cpp_dir}")
    print(f"CUDA: {args.cuda}")
    
    # Verify merged model exists
    if not merged_model.exists():
        print(f"ERROR: Merged model not found at {merged_model}")
        print("Run: python -m scripts.merge_student_adapter")
        return 1
    
    # Step 1: Clone llama.cpp
    if not args.skip_clone:
        if llama_cpp_dir.exists():
            print(f"\n[1/4] llama.cpp already exists at {llama_cpp_dir}")
        else:
            print(f"\n[1/4] Cloning llama.cpp...")
            result = run_cmd(["git", "clone", "https://github.com/ggerganov/llama.cpp", str(llama_cpp_dir)])
            if result.returncode != 0:
                print("ERROR: Failed to clone llama.cpp")
                return 1
    else:
        print(f"\n[1/4] Skipping clone (--skip-clone)")
    
    # Step 2: Build llama.cpp
    if not args.skip_build:
        print(f"\n[2/4] Building llama.cpp...")
        build_dir = llama_cpp_dir / "build"
        build_dir.mkdir(exist_ok=True)
        
        cmake_args = ["cmake", "-B", "build", "-S", "."]
        if args.cuda:
            cmake_args.append("-DGGML_CUDA=ON")
            print("  CUDA support enabled")
        else:
            cmake_args.append("-DGGML_CUDA=OFF")
            print("  CUDA disabled (CPU-only build)")
        
        result = run_cmd(cmake_args, cwd=llama_cpp_dir, timeout=300)
        if result.returncode != 0:
            print("ERROR: cmake configure failed")
            return 1
        
        result = run_cmd(["cmake", "--build", "build", "--config", "Release", "--target", "llama-quantize"], cwd=llama_cpp_dir, timeout=600)
        if result.returncode != 0:
            print("ERROR: cmake build failed")
            return 1
        print("  Build complete")
    else:
        print(f"\n[2/4] Skipping build (--skip-build)")
    
    # Step 3: Convert to GGUF
    print(f"\n[3/4] Converting to GGUF ({args.quantization})...")
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        # Try alternative location
        convert_script = llama_cpp_dir / "build" / "bin" / "Release" / "convert_hf_to_gguf.py"
    
    if not convert_script.exists():
        print(f"ERROR: convert_hf_to_gguf.py not found in {llama_cpp_dir}")
        return 1
    
    convert_cmd = [
        sys.executable, str(convert_script),
        str(merged_model),
        "--outfile", str(gguf_file),
        "--outtype", args.quantization,
    ]
    
    result = run_cmd(convert_cmd, cwd=llama_cpp_dir, timeout=300)
    if result.returncode != 0:
        print("ERROR: GGUF conversion failed")
        return 1
    
    if not gguf_file.exists():
        print(f"ERROR: GGUF file not created at {gguf_file}")
        return 1
    
    gguf_size_mb = round(gguf_file.stat().st_size / (1024*1024), 1)
    print(f"  GGUF created: {gguf_file} ({gguf_size_mb} MB)")
    
    # Step 4: Verify with llama-quantize
    print(f"\n[4/4] Verifying GGUF...")
    quantize_tool = llama_cpp_dir / "build" / "bin" / "Release" / "llama-quantize.exe"
    if not quantize_tool.exists():
        quantize_tool = llama_cpp_dir / "build" / "bin" / "llama-quantize"
    
    if quantize_tool.exists():
        test_file = out_dir / "test_verify.gguf"
        verify_cmd = [str(quantize_tool), str(gguf_file), str(test_file), args.quantization]
        result = run_cmd(verify_cmd, timeout=120)
        if result.returncode == 0:
            print("  Verification passed")
            test_file.unlink(missing_ok=True)
        else:
            print(f"  Warning: Verification failed: {result.stderr}")
    else:
        print("  Warning: llama-quantize not found, skipping verification")
    
    # Create deployment manifest
    deploy_manifest = {
        "policy": args.policy,
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "gguf_file": gguf_file.name,
        "quantization": args.quantization,
        "size_mb": gguf_size_mb,
        "target_vram_mb": 400,
        "llama_cpp_dir": str(llama_cpp_dir),
        "source_merged_model": str(merged_model),
        "created_at": __import__('time').time(),
        "notes": f"GGUF {args.quantization} converted via llama.cpp for edge deployment",
    }
    
    manifest_file = out_dir / "deploy_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(deploy_manifest, f, indent=2)
    
    # Update registry
    registry_file = base_dir / "data" / "policies" / "registry.json"
    if registry_file.exists():
        with open(registry_file, "r") as f:
            registry = json.load(f)
    else:
        registry = {}
    
    if args.policy in registry:
        registry[args.policy]["gguf"] = {
            "file": gguf_file.name,
            "quantization": args.quantization,
            "size_mb": gguf_size_mb,
            "path": str(gguf_file),
            "manifest": str(manifest_file),
        }
        with open(registry_file, "w") as f:
            json.dump(registry, f, indent=2)
        print(f"  Registry updated")
    
    print(f"\n{'='*60}")
    print(f"PHASE 4 COMPLETE: EDGE DEPLOYMENT READY")
    print(f"{'='*60}")
    print(f"GGUF: {gguf_file}")
    print(f"Size: {gguf_size_mb} MB")
    print(f"Quantization: {args.quantization}")
    print(f"Target VRAM: ~400 MB")
    print(f"Manifest: {manifest_file}")
    print(f"\nTo run on edge device:")
    print(f"  llama.cpp/build/bin/Release/main.exe -m {gguf_file.name} -p 'Apa itu machine learning?' -n 100")
    print(f"\nOr copy {gguf_file.name} to any device with llama.cpp installed.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())