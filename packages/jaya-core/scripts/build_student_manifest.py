#!/usr/bin/env python3
"""Build signed manifest for accepted distilled student candidate."""

import json
import sys
from pathlib import Path

# Add JAYA_CORE to path
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from jaya_core.brain_v2.engine.evolution_gate import EvolutionCandidate, EvolutionGate
from jaya_core.brain_v2.engine.evolution_manifest import build_signed_manifest, save_manifest


def main():
    # Load the accepted candidate
    candidate_file = Path("evolution/candidates/distilled-student-qwen-0.5b-v1.json")
    with open(candidate_file, "r") as f:
        candidate_data = json.load(f)
    
    candidate = EvolutionCandidate.from_dict(candidate_data)
    
    # Create gate and verify signature
    gate = EvolutionGate(require_signed=True)
    ok_sig, reason = gate.verify_candidate_signature(candidate)
    print(f"Signature verification: {ok_sig} ({reason})")
    
    if not ok_sig:
        print("ERROR: Candidate signature invalid!")
        return 1
    
    # Build signed manifest
    manifest = build_signed_manifest(
        candidate=candidate,
        gate=gate,
        baseline_ref="phase1-closed-v0.1",
        notes="Distilled student model: Qwen2.5-0.5B + LoRA (r=8), trained on Nemotron-3-Ultra distilled knowledge, 3 epochs, edge deploy target (~500MB VRAM)"
    )
    
    # Save manifest
    manifest_dir = Path("evolution/manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / f"{candidate.candidate_id}_manifest.json"
    
    saved_path = save_manifest(manifest, str(manifest_file))
    print(f"Manifest saved to: {saved_path}")
    
    # Verify manifest
    from jaya_core.brain_v2.engine.evolution_manifest import verify_manifest
    ok, reason = verify_manifest(manifest, gate)
    print(f"Manifest verification: {ok} ({reason})")
    
    print(f"\nManifest content:")
    print(json.dumps(manifest, indent=2))
    
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())