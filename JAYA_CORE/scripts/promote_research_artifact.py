#!/usr/bin/env python3
"""Promote research artifact to JAYA_CORE.

This script copies an artifact from a source path to a destination directory
within JAYA_CORE. It respects domain isolation by not depending on any
JAYA_RESEARCH code.

Usage:
    python promote_research_artifact.py --artifact-path <path> --dest-dir <dir> [--artifact-type <type>] [--validate]

Arguments:
    --artifact-path: Absolute or relative path to the artifact to promote.
    --dest-dir: Absolute or relative path to the destination directory in JAYA_CORE.
    --artifact-type: Type of artifact (e.g., 'lora_adapter', 'graphrag_enhancement', 'proactive_agent').
                     Default: 'generic'.
    --validate: Run validation checks on the artifact before promotion.

The script will:
    1. Validate the artifact exists and meets basic criteria (size, type) if --validate is specified.
    2. Copy the artifact to the destination directory.
    3. Create a manifest file (JSON) describing the artifact and its promotion.

Note: The user must ensure the artifact is from JAYA_RESEARCH and the destination is in JAYA_CORE.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, List

def validate_artifact(artifact_path: Path, artifact_type: str) -> Dict[str, Any]:
    """Perform validation based on artifact type.
    
    Returns a dictionary of validation results.
    """
    validation = {
        "passed": True,
        "checks": [],  # type: List[Dict[str, Any]]
        "artifact_type": artifact_type,
        "size_bytes": artifact_path.stat().st_size if artifact_path.is_file() else sum(f.stat().st_size for f in artifact_path.rglob('*') if f.is_file())
    }
    
    # Size check: for LoRA adapters, we expect < 5 MB
    if artifact_type == "lora_adapter":
        max_size = 5 * 1024 * 1024  # 5 MB
        if validation["size_bytes"] > max_size:
            validation["passed"] = False
            validation["checks"].append({
                "check": "size_limit",
                "passed": False,
                "message": f"Artifact size {validation['size_bytes']} bytes exceeds {max_size} bytes for LoRA adapter"
            })
        else:
            validation["checks"].append({
                "check": "size_limit",
                "passed": True,
                "message": f"Artifact size {validation['size_bytes']} bytes is within limit"
            })
    
    # For directories, we might check for required files
    if artifact_path.is_dir():
        if artifact_type == "lora_adapter":
            required_files = ["adapter_config.json", "adapter_model.bin"]
            for req_file in required_files:
                if not (artifact_path / req_file).exists():
                    validation["passed"] = False
                    validation["checks"].append({
                        "check": "required_file",
                        "passed": False,
                        "message": f"Missing required file: {req_file}"
                    })
                else:
                    validation["checks"].append({
                        "check": "required_file",
                        "passed": True,
                        "message": f"Found required file: {req_file}"
                    })
    
    # If no specific checks failed, add a general passed check
    if validation["passed"] and not any(not check["passed"] for check in validation["checks"] if check.get("check") != "size_limit"):
        validation["checks"].append({
            "check": "general",
            "passed": True,
            "message": "Artifact validation passed"
        })
    
    return validation

def copy_artifact(artifact_path: Path, dest_dir: Path) -> Path:
    """Copy the artifact to the destination directory."""
    if artifact_path.is_file():
        dest_path = dest_dir / artifact_path.name
        shutil.copy2(artifact_path, dest_path)
    else:
        dest_path = dest_dir / artifact_path.name
        if dest_path.exists():
            shutil.rmtree(dest_path)
        shutil.copytree(artifact_path, dest_path)
    return dest_path

def create_manifest(artifact_path: Path, dest_dir: Path, artifact_type: str, validation: Dict[str, Any]) -> Path:
    """Create a manifest file recording the promotion."""
    manifest = {
        "artifact": {
            "source_path": str(artifact_path),
            "destination_path": str(dest_dir / artifact_path.name),
            "type": artifact_type,
            "size_bytes": validation["size_bytes"],
            "sha256": _calculate_sha256(artifact_path)
        },
        "validation": validation,
        "promotion_timestamp": __import__('time').time()
    }
    
    manifest_path = dest_dir / f"{artifact_path.name}.manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    return manifest_path

def _calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 hash of a file or directory."""
    sha256_hash = hashlib.sha256()
    if file_path.is_file():
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
    else:
        # For directory, hash all files in sorted order
        for root, _, files in sorted(os.walk(file_path)):
            for file in sorted(files):
                file_path = Path(root) / file
                with open(file_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Promote research artifact to JAYA_CORE")
    parser.add_argument("--artifact-path", type=str, required=True, help="Path to the artifact to promote")
    parser.add_argument("--dest-dir", type=str, required=True, help="Destination directory in JAYA_CORE")
    parser.add_argument("--artifact-type", type=str, default="generic", help="Type of artifact (e.g., lora_adapter, graphrag_enhancement)")
    parser.add_argument("--validate", action="store_true", help="Run validation checks before promotion")
    
    args = parser.parse_args()
    
    try:
        # Resolve paths to absolute
        artifact_path = Path(args.artifact_path).resolve()
        dest_dir = Path(args.dest_dir).resolve()
        
        # Validate artifact if requested
        validation_result = None
        if args.validate:
            validation_result = validate_artifact(artifact_path, args.artifact_type)
            if not validation_result["passed"]:
                print("Validation failed:")
                for check in validation_result["checks"]:
                    if not check["passed"]:
                        print(f"  - {check['message']}")
                sys.exit(1)
            else:
                print("Validation passed.")
                for check in validation_result["checks"]:
                    if check["passed"]:
                        print(f"  - {check['message']}")
        
        # Copy artifact
        dest_path = copy_artifact(artifact_path, dest_dir)
        print(f"Artifact copied to: {dest_path}")
        
        # Create manifest
        manifest_path = create_manifest(artifact_path, dest_dir, args.artifact_type, validation_result or {})
        print(f"Manifest created at: {manifest_path}")
        
        print("Promotion successful.")
        
    except Exception as e:
        print(f"Error during promotion: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()