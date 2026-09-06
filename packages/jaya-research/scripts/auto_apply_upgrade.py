"""Export one sourced Research candidate; never execute or deploy it.

This file keeps the legacy command name for operator compatibility. Its former
auto-apply behavior is intentionally removed: Research only owns discovery and
an immutable outbox, while approval and installation belong to Core.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_SRC = RESEARCH_ROOT / "src"
if str(RESEARCH_SRC) not in sys.path:
    sys.path.insert(0, str(RESEARCH_SRC))

from jaya_research.research.academic.literature import ArxivClient  # noqa: E402
from jaya_research.research.ecosystem_bridge import (  # noqa: E402
    ResearchEcosystemBridge,
    ResearchFinding,
)


class CandidateExportError(RuntimeError):
    """Raised when a sourced candidate cannot be exported honestly."""


def _paper_source_id(paper: dict[str, Any]) -> str:
    source_id = str(
        paper.get("id")
        or paper.get("url")
        or paper.get("entry_id")
        or ""
    ).strip()
    if not source_id:
        raise CandidateExportError("Paper has no stable source identifier")
    return source_id


def _select_sourced_paper(
    client: ArxivClient,
    *,
    query: str,
) -> dict[str, Any]:
    papers = client.search_papers(query=query, max_results=5)
    if not papers:
        raise CandidateExportError(
            "No source was returned; synthetic fallback papers are forbidden"
        )
    paper = dict(papers[0])
    _paper_source_id(paper)
    if not str(paper.get("title") or "").strip():
        raise CandidateExportError("Paper title is missing")
    return paper


def export_review_candidate(
    *,
    query: str,
    outbox_dir: Path | None = None,
    client: ArxivClient | None = None,
) -> dict[str, Any]:
    """Fetch one real source and export an unverified literature candidate."""
    paper = _select_sourced_paper(client or ArxivClient(), query=query)
    source_id = _paper_source_id(paper)
    source_sha256 = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    title = str(paper["title"]).strip()
    raw_authors = paper.get("authors") or []
    authors = (
        [str(author).strip() for author in raw_authors if str(author).strip()]
        if isinstance(raw_authors, list)
        else [str(raw_authors).strip()]
    )
    summary = str(paper.get("summary") or paper.get("abstract") or "").strip()
    if not summary:
        raise CandidateExportError("Paper abstract/summary is missing")

    finding = ResearchFinding(
        finding_id=f"literature-{source_sha256[:20]}",
        paper_title=title,
        authors=authors,
        topic=query,
        gap_summary=summary,
        suggested_patch_type="literature_review_candidate",
        patch_code=(
            "No executable patch was generated. Review the cited source, "
            "extract falsifiable claims, and design an empirical study first."
        ),
        confidence_score=0.0,
        evidence_kind="UNVERIFIED",
        source_hashes=[source_sha256],
        dataset_sha256="",
        license_id=str(paper.get("license") or ""),
        reproduction_runs=0,
        reproduced=False,
    )
    result = ResearchEcosystemBridge(outbox_dir=outbox_dir).submit_research_upgrade(
        finding
    )
    return {
        **result,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "candidate_executed": False,
        "core_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export one sourced, review-only Research candidate."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Required acknowledgement that exactly one bounded scan will run.",
    )
    parser.add_argument(
        "--query",
        default="cat:cs.AI AND all:agent",
        help="Explicit ArXiv query for the bounded scan.",
    )
    parser.add_argument(
        "--outbox",
        type=Path,
        help="Optional Research-owned outbox directory.",
    )
    args = parser.parse_args()
    if not args.once:
        parser.error("--once is required; autonomous daemon mode is disabled")

    try:
        result = export_review_candidate(
            query=args.query,
            outbox_dir=args.outbox,
        )
    except CandidateExportError as exc:
        print(json.dumps({"status": "BLOCKED_NO_VALID_SOURCE", "error": str(exc)}))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
