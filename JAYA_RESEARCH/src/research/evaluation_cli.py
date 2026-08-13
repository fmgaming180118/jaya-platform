"""CLI for the deterministic RAG contract-smoke evaluation.

This command evaluates the harness and grounding contract against the sources
embedded in a licensed fixture dataset.  It does not claim production retrieval
quality; a representative corpus and attested real retriever run remain a
separate external gate.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .rag_evaluation import (
    EvaluationRunContext,
    RAGEvaluationDataset,
    evaluate_retriever,
    load_evaluation_dataset,
    write_evaluation_report,
)
from .retrieval_evidence import enrich_chunk_metadata

_STOPWORDS = {
    "apa",
    "does",
    "digunakan",
    "gunakan",
    "use",
    "which",
    "yang",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w-]+", value.casefold(), flags=re.UNICODE)
        if len(token) >= 3 and token not in _STOPWORDS
    }


def build_fixture_retriever(
    dataset: RAGEvaluationDataset,
) -> Callable[[str, int], list[dict[str, Any]]]:
    """Create a deterministic lexical retriever over dataset-owned sources."""

    def retrieve(query: str, top_k: int) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        ranked: list[dict[str, Any]] = []
        for source in dataset.sources:
            content = str(source["content"])
            source_tokens = _tokens(content)
            denominator = max(1, min(len(query_tokens), len(source_tokens)))
            score = len(query_tokens.intersection(source_tokens)) / denominator
            if score < 0.55:
                continue
            metadata = enrich_chunk_metadata(
                content,
                {
                    "source_id": source["source_id"],
                    "source_uri": source["source_uri"],
                    "page_number": 1,
                    "word_start": 0,
                    "word_end": len(content.split()),
                    "license_id": source["license_id"],
                },
                accessed_at=str(dataset.provenance["created_at"]),
            )
            ranked.append(
                {
                    "content": content,
                    "snippet": content,
                    "score": round(score, 6),
                    "score_kind": "TOKEN_OVERLAP_COEFFICIENT",
                    "metadata": metadata,
                    "document": metadata,
                }
            )
        ranked.sort(
            key=lambda item: (
                -float(item["score"]),
                str(item["metadata"]["source_id"]),
            )
        )
        return ranked[:top_k]

    return retrieve


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run the local RAG grounding contract smoke gate."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "evaluation" / "rag_smoke_v2.json",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--target", type=float, default=0.85)
    parser.add_argument("--runner-id", default="LOCAL_UNATTESTED")
    parser.add_argument("--commit-sha", default="NOASSERTION")
    parser.add_argument("--environment-id", default="LOCAL_UNATTESTED")
    args = parser.parse_args(argv)

    dataset = load_evaluation_dataset(args.dataset)
    report = evaluate_retriever(
        dataset,
        build_fixture_retriever(dataset),
        top_k=args.top_k,
        target=args.target,
        run_context=EvaluationRunContext(
            runner_id=args.runner_id,
            commit_sha=args.commit_sha,
            environment_id=args.environment_id,
        ),
    )
    if args.report is not None:
        write_evaluation_report(report, args.report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["local_target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
