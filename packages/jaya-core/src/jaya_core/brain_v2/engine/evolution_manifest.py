"""Phase 2 — Signed evolution candidate manifest helpers."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from jaya_core.brain_v2.engine.evolution_gate import EvolutionCandidate, EvolutionGate

MANIFEST_VERSION = "0.1"


def _canonical_candidate_hash(candidate: EvolutionCandidate) -> str:
    payload = candidate.canonical_for_signature().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_signed_manifest(
    candidate: EvolutionCandidate,
    gate: EvolutionGate,
    baseline_ref: str,
    notes: str = "",
) -> Dict[str, Any]:
    if not candidate.signature:
        gate.sign_candidate(candidate, key_id=candidate.key_id or "local")

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": round(time.time(), 6),
        "baseline_ref": baseline_ref,
        "notes": notes,
        "candidate_hash": _canonical_candidate_hash(candidate),
        "candidate": candidate.to_dict(),
    }
    return manifest


def save_manifest(manifest: Dict[str, Any], file_path: str) -> str:
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return str(p)


def load_manifest(file_path: str) -> Dict[str, Any]:
    p = Path(file_path)
    return json.loads(p.read_text(encoding="utf-8"))


def verify_manifest(manifest: Dict[str, Any], gate: EvolutionGate) -> Tuple[bool, str]:
    if str(manifest.get("manifest_version")) != MANIFEST_VERSION:
        return False, "unsupported manifest version"

    raw_candidate = manifest.get("candidate")
    if not isinstance(raw_candidate, dict):
        return False, "missing candidate payload"

    candidate = EvolutionCandidate.from_dict(raw_candidate)

    expected_hash = _canonical_candidate_hash(candidate)
    got_hash = str(manifest.get("candidate_hash") or "")
    if expected_hash != got_hash:
        return False, "candidate hash mismatch"

    ok_sig, reason_sig = gate.verify_candidate_signature(candidate)
    if not ok_sig:
        return False, f"signature invalid: {reason_sig}"

    return True, "ok"
