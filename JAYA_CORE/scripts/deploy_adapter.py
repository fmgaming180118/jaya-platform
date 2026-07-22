#!/usr/bin/env python3
"""Deploy accepted QLoRA adapter to JAYA_CORE runtime."""

import json
import shutil
from pathlib import Path
import sys

# Add JAYA_CORE to path
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from src.brain_v2.engine.evolution_manifest import load_manifest, verify_manifest
from src.brain_v2.engine.evolution_gate import EvolutionGate


def main():
    # Paths
    manifest_file = Path("evolution/manifests/qlora-language-adapter-v2_manifest.json")
    adapter_src = Path("../JAYA_RESEARCH/data/qlora/adapter-qwen-from-nemotron-v2")
    adapter_dst = Path("data/policies/qlora-language-adapter-v2")
    
    # Load and verify manifest
    print("Loading manifest...")
    manifest = load_manifest(str(manifest_file))
    
    gate = EvolutionGate(require_signed=True)
    ok, reason = verify_manifest(manifest, gate)
    print(f"Manifest verification: {ok} ({reason})")
    
    if not ok:
        print("ERROR: Manifest verification failed!")
        return 1
    
    candidate = manifest["candidate"]
    candidate_id = candidate["candidate_id"]
    print(f"Deploying candidate: {candidate_id}")
    
    # Create policies directory
    adapter_dst.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy adapter files
    print(f"Copying adapter from {adapter_src} to {adapter_dst}...")
    if adapter_dst.exists():
        shutil.rmtree(adapter_dst)
    shutil.copytree(adapter_src, adapter_dst)
    
    # Create policy registry entry
    registry_file = Path("data/policies/registry.json")
    registry = {}
    if registry_file.exists():
        with open(registry_file, "r") as f:
            registry = json.load(f)
    
    registry[candidate_id] = {
        "type": "qlora_adapter",
        "path": str(adapter_dst),
        "base_model": "Qwen/Qwen3-4B-Instruct-2507",
        "manifest": str(manifest_file),
        "deployed_at": round(__import__('time').time(), 6),
        "status": "active",
        "metadata": candidate.get("metadata", {})
    }
    
    with open(registry_file, "w") as f:
        json.dump(registry, f, indent=2)
    
    print(f"Registry updated: {registry_file}")
    print(f"Adapter deployed to: {adapter_dst}")
    
    # Verify adapter files
    adapter_files = list(adapter_dst.glob("*"))
    print(f"\nAdapter files:")
    for f in adapter_files:
        size = f.stat().st_size / (1024*1024)
        print(f"  {f.name}: {size:.1f} MB")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())