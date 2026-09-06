#!/usr/bin/env python3
"""
Automatic prompt generation for Jaya knowledge distillation.

This script helps generate training prompts for the NIM-based distillation process
by creating variations of base concepts/topics. This reduces the manual effort
of creating prompt files while ensuring comprehensive coverage of important topics.

Usage:
    python generate_prompts.py --base-concepts concepts.txt --output prompts.txt
    python generate_prompts.py --auto-from-jaya --output prompts.txt  # Experimental
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Set


def _discover_repository_root() -> Path:
    """Return the workspace root containing the canonical Core package."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "packages" / "jaya-core"
        ).is_dir():
            return candidate
    raise RuntimeError("canonical JAYA repository root is unavailable")


REPOSITORY_ROOT = _discover_repository_root()
JAYA_CORE_PATH = REPOSITORY_ROOT / "packages" / "jaya-core"


def load_base_concepts(file_path: Path) -> List[str]:
    """Load base concepts/topics from a text file (one per line)."""
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def extract_concepts_from_jaya_docs() -> List[str]:
    """Extract key concepts from Jaya documentation (experimental)."""
    concepts = set()
    
    # Concepts from JayaCore README and key documents
    doc_files = [
        JAYA_CORE_PATH / "README.md",
        REPOSITORY_ROOT / "docs" / "ARCHITECTURE.md",
        REPOSITORY_ROOT / "docs" / "DECISIONS.md",
        REPOSITORY_ROOT / "docs" / "STATUS.md",
    ]
    
    # Key Jaya concepts to always include
    core_concepts = {
        "Jaya Core", "JayaIR", "Agentic RAG", "Dynamic Sparsity MoE", 
        "Activation Sparsity", "Meta Cognitive Planner", "Nano Mode",
        "Digital Twin", "Collective Pulse", "Narrative Continuity",
        "Intent Engine", "Lingua Logica", "Indonesian Responder",
        "Zero Trust", "Adaptive Policy Tuning", "Policy Feedback Loop",
        "Resource Monitor", "Self Bootstrap", "Live Evolver", "Morphic Kernel",
        "Ethical Heart", "Hybrid Mode", "Speculative Execution",
        "Machine Learning", "Artificial Intelligence", "Retrieval Augmented Generation",
        "Sovereign AI", "Low Resource Operation", "Adaptive Memory",
        "Procedural Ranking", "Procedural Maintenance", "Language Capability"
    }
    
    concepts.update(core_concepts)
    
    # Try to extract from documentation files
    for doc_file in doc_files:
        if doc_file.exists():
            try:
                content = doc_file.read_text(encoding="utf-8")
                # Simple extraction: look for capitalized phrases and key terms
                lines = content.split('\n')
                for line in lines:
                    # Look for headers and emphasized text
                    if line.startswith('#') or '**' in line or '##' in line:
                        # Extract potential concepts (simplified)
                        words = line.replace('#', '').replace('*', '').replace('-', '').split()
                        for word in words:
                            if len(word) > 3 and word[0].isupper():
                                concepts.add(word.strip('.,:;'))
            except (OSError, UnicodeError):
                continue  # Skip if file can't be read
    
    return sorted(list(concepts))


def generate_prompt_variations(concepts: List[str]) -> List[str]:
    """Generate various prompt formulations for each concept."""
    prompt_templates = [
        "What is {concept}?",
        "Explain {concept} in simple terms.",
        "How does {concept} work?",
        "What are the key features of {concept}?",
        "Why is {concept} important in Jaya?",
        "Describe the role of {concept} in Jaya AI.",
        "What are the benefits of {concept}?",
        "How is {concept} implemented in Jaya?",
        "What problem does {concept} solve?",
        "Compare {concept} with traditional approaches.",
        "What are the limitations of {concept}?",
        "How to implement {concept} in an AI system?",
        "Best practices for using {concept}.",
        "Common mistakes when implementing {concept}.",
        "Future developments for {concept}."
    ]
    
    prompts = []
    for concept in concepts:
        for template in prompt_templates:
            prompts.append(template.format(concept=concept))
    
    return prompts


def save_prompts(prompts: List[str], output_path: Path):
    """Save prompts to a text file (one per line)."""
    with open(output_path, "w", encoding="utf-8") as f:
        for prompt in prompts:
            f.write(prompt + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate prompts for Jaya knowledge distillation")
    parser.add_argument("--base-concepts", type=Path, help="File containing base concepts (one per line)")
    parser.add_argument("--output", type=Path, required=True, help="Output file for generated prompts")
    parser.add_argument("--auto-from-jaya", action="store_true", 
                       help="Automatically extract concepts from Jaya documentation (experimental)")
    parser.add_argument("--max-prompts", type=int, default=100, 
                       help="Maximum number of prompts to generate")
    
    args = parser.parse_args()
    
    # Get base concepts
    if args.auto_from_jaya:
        print("Extracting concepts from Jaya documentation (experimental)...")
        concepts = extract_concepts_from_jaya_docs()
        print(f"Found {len(concepts)} concepts from Jaya documentation")
    elif args.base_concepts and args.base_concepts.exists():
        print(f"Loading base concepts from {args.base_concepts}")
        concepts = load_base_concepts(args.base_concepts)
        print(f"Loaded {len(concepts)} base concepts")
    else:
        # Default concepts if nothing specified
        concepts = [
            "Machine Learning", "Artificial Intelligence", "Jaya Core", "JayaIR",
            "Agentic RAG", "Dynamic Sparsity MoE", "Activation Sparsity",
            "Meta Cognitive Planner", "Digital Twin", "Collective Pulse",
            "Narrative Continuity", "Intent Engine", "Lingua Logica",
            "Indonesian Responder", "Zero Trust", "Adaptive Policy Tuning",
            "Policy Feedback Loop", "Resource Monitor", "Self Bootstrap",
            "Live Evolver", "Morphic Kernel", "Ethical Heart", "Hybrid Mode",
            "Speculative Execution", "Retrieval Augmented Generation",
            "Sovereign AI", "Low Resource Operation"
        ]
        print(f"Using {len(concepts)} default Jaya/AI concepts")
    
    # Generate prompt variations
    print("Generating prompt variations...")
    all_prompts = generate_prompt_variations(concepts)
    
    # Limit if requested
    if len(all_prompts) > args.max_prompts:
        print(f"Limiting to {args.max_prompts} prompts (from {len(all_prompts)} generated)")
        all_prompts = all_prompts[:args.max_prompts]
    
    # Save prompts
    save_prompts(all_prompts, args.output)
    print(f"Saved {len(all_prompts)} prompts to {args.output}")
    
    # Show first few as examples
    print("\nFirst 5 generated prompts:")
    for i, prompt in enumerate(all_prompts[:5]):
        print(f"  {i+1}. {prompt}")


if __name__ == "__main__":
    main()
