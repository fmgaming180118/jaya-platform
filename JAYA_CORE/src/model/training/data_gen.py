"""
Librarian Training Data Generator.
Creates structured JSON examples for fine-tuning the JAYA Core Model.
This enforces the rule: NO PARAMETRIC MEMORIZATION.
The model must learn to output structured JSON and request retrieval if evidence is missing.
"""

import json
from pathlib import Path
import random

def generate_curriculum_item(prompt_text: str, json_completion: dict) -> dict:
    return {
        "prompt": f"""You are JAYA Librarian Core, an expert assistant that reasons step-by-step and strictly outputs JSON.
You do NOT hallucinate facts. If the information is not in the EVIDENCE LIBRARY and you don't know it, you set retrieval_required to true.
If there are no context blocks, you must request retrieval by generating retrieval_queries.

{prompt_text}

Respond in the following JSON format ONLY:
{{
  "intent": "...",
  "information_needs": ["..."],
  "retrieval_required": true/false,
  "retrieval_queries": ["..."],
  "answer": "...",
  "evidence_refs": ["..."],
  "confidence": 0.0-1.0,
  "unknowns": ["..."],
  "jaya_ir": null
}}
""",
        "completion": json.dumps(json_completion, indent=2)
    }

def generate_librarian_dataset(output_path: Path, num_samples: int = 100):
    dataset = []
    
    # 1. Retrieval Need Detection
    for _ in range(num_samples // 4):
        dataset.append(generate_curriculum_item(
            "USER QUERY: What does PaymentProcessor.process() do?",
            {
                "intent": "Understand function purpose",
                "information_needs": ["Definition of PaymentProcessor.process"],
                "retrieval_required": True,
                "retrieval_queries": ["PaymentProcessor.process definition"],
                "answer": "INSUFFICIENT_EVIDENCE",
                "evidence_refs": [],
                "confidence": 0.0,
                "unknowns": ["What PaymentProcessor.process does"],
                "jaya_ir": None
            }
        ))
        
    # 2. Single-Source Synthesis
    for _ in range(num_samples // 4):
        dataset.append(generate_curriculum_item(
            "EVIDENCE LIBRARY:\n---\n[Source: core@v1:src/pay.py#process]\ndef process():\n    return 'OK'\n\nUSER QUERY: What does process return?",
            {
                "intent": "Extract return value",
                "information_needs": ["Return value of process"],
                "retrieval_required": False,
                "retrieval_queries": [],
                "answer": "The `process` function returns the string 'OK'.",
                "evidence_refs": ["core@v1:src/pay.py#process"],
                "confidence": 1.0,
                "unknowns": [],
                "jaya_ir": None
            }
        ))

    # 3. Caller/Callee Reasoning
    for _ in range(num_samples // 4):
        dataset.append(generate_curriculum_item(
            "EVIDENCE LIBRARY:\n---\n[Source: core@v1:src/pay.py#process]\nCalls: stripe.Charge.create\nCalled By: run_checkout\n\nUSER QUERY: What calls process?",
            {
                "intent": "Find callers",
                "information_needs": ["Callers of process"],
                "retrieval_required": False,
                "retrieval_queries": [],
                "answer": "The `process` function is called by `run_checkout`.",
                "evidence_refs": ["core@v1:src/pay.py#process"],
                "confidence": 1.0,
                "unknowns": [],
                "jaya_ir": None
            }
        ))
        
    # 4. Conflicting Sources / Version Mismatch
    for _ in range(num_samples - (3 * (num_samples // 4))):
        dataset.append(generate_curriculum_item(
            "EVIDENCE LIBRARY:\n---\n[Source: core@v1:src/pay.py#process]\ndef process(): return 'A'\n---\n[Source: core@v2:src/pay.py#process]\ndef process(): return 'B'\n\nUSER QUERY: What does process return in v2?",
            {
                "intent": "Extract return value for specific version",
                "information_needs": ["Return value of process in v2"],
                "retrieval_required": False,
                "retrieval_queries": [],
                "answer": "In version v2, `process` returns 'B'.",
                "evidence_refs": ["core@v2:src/pay.py#process"],
                "confidence": 0.95,
                "unknowns": [],
                "jaya_ir": None
            }
        ))

    random.shuffle(dataset)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
            
    print(f"Generated {len(dataset)} Librarian training samples at {output_path}")

if __name__ == "__main__":
    out_path = Path(__file__).parent.parent.parent.parent / "data" / "librarian_dataset.jsonl"
    generate_librarian_dataset(out_path, num_samples=500)
