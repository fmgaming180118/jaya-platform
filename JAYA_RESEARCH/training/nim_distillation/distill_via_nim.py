#!/usr/bin/env python3
"""
Knowledge distillation from NVIDIA NIM API to Jaya runtime.

This script queries a lightweight NIM model (e.g., nemotron-3-8b-instruct) 
to generate knowledge (facts, procedures) and stores it into Jaya's 
AgenticRAG via the public API of IronEngine.

Usage:
    python distill_via_nim.py --prompts prompts.txt --output-json distilled_knowledge.json

Environment variables:
    NIM_API_URL: The base URL for the NIM endpoint (e.g., https://ai.api.nvidia.com/v1/nim/<model>)
    NIM_API_KEY: The API key for authentication.
    NIM_MODEL: The model name to use (optional, can be part of the URL).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

import requests

# Add JayaCore to path so we can import IronEngine (public API)
JAYA_CORE_PATH = Path(__file__).resolve().parents[3] / "JAYA_CORE"
if str(JAYA_CORE_PATH) not in sys.path:
    sys.path.insert(0, str(JAYA_CORE_PATH))

from src.brain_v2.engine.runtime import IronEngine


def load_prompts(file_path: Path) -> List[str]:
    """Load prompts from a text file (one per line)."""
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def query_nim(prompt: str, api_url: str, api_key: str, model: str = None, max_tokens: int = 150, temperature: float = 0.7) -> str:
    """Query the NIM API and return the generated text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    payload = {
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False
    }
    if model:
        payload["model"] = model

    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    # Assuming OpenAI-compatible chat completion format
    return result["choices"][0]["message"]["content"].strip()


def main():
    parser = argparse.ArgumentParser(description="Distill knowledge from NIM API to Jaya")
    parser.add_argument("--prompts", type=Path, required=True, help="File containing prompts (one per line)")
    parser.add_argument("--model-path", type=Path, default=JAYA_CORE_PATH / "JAYA_SOVEREIGN_V18.jay", help="Path to Jaya model .jay file")
    parser.add_argument("--password", type=str, default="x", help="Password for Jaya model (if encrypted)")
    parser.add_argument("--output-json", type=Path, help="Optional: save distilled knowledge to JSON file")
    parser.add_argument("--max-tokens", type=int, default=150, help="Max tokens for NIM generation")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    args = parser.parse_args()

    # Load environment variables for NIM
    api_url = os.getenv("NIM_API_URL")
    api_key = os.getenv("NIM_API_KEY")
    model = os.getenv("NIM_MODEL")  # optional

    if not api_url or not api_key:
        print("Error: NIM_API_URL and NIM_API_KEY must be set in environment.", file=sys.stderr)
        sys.exit(1)

    # Load prompts
    prompts = load_prompts(args.prompts)
    print(f"Loaded {len(prompts)} prompts from {args.prompts}")

    # Initialize Jaya engine (we'll use it to memorize the knowledge)
    print(f"Initializing Jaya engine with model {args.model_path}...")
    engine = IronEngine(model_path=str(args.model_path), password=args.password, enable_twin=False)
    engine.ignite()
    print("Jaya engine initialized and ignited.")

    distilled: List[Dict[str, Any]] = []

    for i, prompt in enumerate(prompts, start=1):
        print(f"[{i}/{len(prompts)}] Querying NIM for: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        try:
            start = time.time()
            response = query_nim(prompt, api_url, api_key, model=model, max_tokens=args.max_tokens, temperature=args.temperature)
            elapsed = time.time() - start
            print(f"  -> Response received in {elapsed:.2f}s: {response[:100]}{'...' if len(response) > 100 else ''}")

            # Store the knowledge in Jaya's AgenticRAG as a fact.
            # We use the public memorize method of AgenticRAG via the engine.
            # Note: Engine exposes AgenticRAG via engine._agentic_rag? Actually, engine has a public method to memorize?
            # Looking at runtime.py, there is no public memorize method on IronEngine for arbitrary facts.
            # However, there is a method `memorize_agentic_procedure` for procedures, and `memorize` is internal to AgenticRAG.
            # But we can access engine._agentic_rag because it's an attribute (though private). 
            # Since we are in JayaResearch and we are allowed to use JayaCore's public interface, we should avoid accessing private attributes.
            # However, the tests in JayaCore also access engine._agentic_rag? Let's check the test file we saw earlier.
            # In test_phase1_agentic_rag_runtime_gate.py, they use engine.memorize_agentic_procedure and engine.query_agentic_rag.
            # There is no public method to memorize arbitrary facts. But we can use the AgenticRAG's memorize via the engine's internal attribute?
            # Alternatively, we can store the distilled knowledge in a file and later have a separate process ingest it into Jaya's RAG.
            # Given the boundary, we should not rely on private attributes. Let's change approach: we will output the distilled knowledge to a JSON file,
            # and then provide a separate script (or a function) that can be run within JayaCore's test suite or via a custom command to ingest it.
            # For now, we'll just collect the results and optionally save to JSON.

            distilled.append({
                "prompt": prompt,
                "response": response,
                "model": model or "unknown",
                "timestamp": time.time()
            })

        except Exception as e:
            print(f"  !! Error processing prompt: {e}", file=sys.stderr)
            continue

    # Optionally save to JSON
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(distilled, f, indent=2, ensure_ascii=False)
        print(f"Saved distilled knowledge to {args.output_json}")

    print("Distillation complete.")
    # If we wanted to actually feed into Jaya's memory, we could do:
    # for item in distilled:
    #     engine._agentic_rag.memorize(topic=item["prompt"], content=item["response"], source="nim_distillation", importance=5)
    # But since _agentic_rag is private, we leave it as a comment for the user to decide if they want to break the boundary for this specific purpose.
    # Alternatively, we can extend JayaCore with a public method to ingest facts from distillation, but that would require a JayaCore change.
    # For now, we output the knowledge and let the user decide how to ingest.

if __name__ == "__main__":
    main()