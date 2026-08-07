"""
Librarian Training Data Generator.
Creates structured JSON examples for fine-tuning the JAYA Core Model.
This enforces the rule: NO PARAMETRIC MEMORIZATION.
The model must learn to output structured JSON and request retrieval if evidence is missing.
"""

import json
from pathlib import Path
import random

def generate_librarian_dataset(output_path: Path, num_samples: int = 100):
    dataset = []
    
    # Template 1: Missing Information (Needs Retrieval)
    queries_needing_retrieval = [
        "What does process_payment() do?",
        "How is the capability sandbox implemented?",
        "Explain the JAYA routing logic.",
        "Where are the API keys stored?",
        "How to add a new cognitive planner?",
    ]
    
    for q in queries_needing_retrieval * (num_samples // 10):
        dataset.append({
            "prompt": f"""You are JAYA Librarian Core, an expert assistant that reasons step-by-step and strictly outputs JSON.
You do NOT hallucinate facts. If the information is not in the EVIDENCE LIBRARY and you don't know it, you set retrieval_required to true.
If there are no context blocks, you must request retrieval by generating retrieval_queries.


USER QUERY: {q}

Respond in the following JSON format ONLY:
{{
  "information_needs": ["..."],
  "retrieval_required": true/false,
  "retrieval_queries": ["..."],
  "answer": "...",
  "evidence_refs": ["..."],
  "confidence": 0.0-1.0
}}
""",
            "completion": json.dumps({
                "information_needs": [f"Understand {q.split()[-1]}"],
                "retrieval_required": True,
                "retrieval_queries": [f"{q.split()[-1]} definition", f"{q.split()[-1]} callers"],
                "answer": "INSUFFICIENT_EVIDENCE",
                "evidence_refs": [],
                "confidence": 0.0
            }, indent=2)
        })

    # Template 2: Has Evidence (Grounded Answer)
    evidence_examples = [
        (
            "What does process_payment() do?",
            "[Source: core_repo@v1:src/payment.py#process_payment]\ndef process_payment(amount):\n    '''Processes a transaction via Stripe.'''\n    return stripe.Charge.create(amount=amount)",
            "process_payment(amount)",
            "Processes a transaction via Stripe.",
            "core_repo@v1:src/payment.py#process_payment"
        ),
        (
            "Who created JAYA?",
            "[Source: doc@v1:docs/authors.md]\nJAYA was created by the fmgaming180118 team.",
            "JAYA author",
            "JAYA was created by the fmgaming180118 team.",
            "doc@v1:docs/authors.md"
        )
    ]
    
    for (q, ctx, info, ans, ref) in evidence_examples * (num_samples // 10):
        dataset.append({
            "prompt": f"""You are JAYA Librarian Core, an expert assistant that reasons step-by-step and strictly outputs JSON.
You do NOT hallucinate facts. If the information is not in the EVIDENCE LIBRARY and you don't know it, you set retrieval_required to true.
If there are no context blocks, you must request retrieval by generating retrieval_queries.

EVIDENCE LIBRARY:
---
{ctx}


USER QUERY: {q}

Respond in the following JSON format ONLY:
{{
  "information_needs": ["..."],
  "retrieval_required": true/false,
  "retrieval_queries": ["..."],
  "answer": "...",
  "evidence_refs": ["..."],
  "confidence": 0.0-1.0
}}
""",
            "completion": json.dumps({
                "information_needs": [info],
                "retrieval_required": False,
                "retrieval_queries": [],
                "answer": ans,
                "evidence_refs": [ref],
                "confidence": 0.95
            }, indent=2)
        })

    # Shuffle dataset
    random.shuffle(dataset)
    
    # Save to JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
            
    print(f"Generated {len(dataset)} Librarian training samples at {output_path}")

if __name__ == "__main__":
    out_path = Path(__file__).parent.parent.parent.parent / "data" / "librarian_dataset.jsonl"
    generate_librarian_dataset(out_path, num_samples=500)
