#!/usr/bin/env python3
"""Exercise nine operational pillars through one canonical JAYA Core runtime."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import sys
import time
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CORE_SRC = _ROOT / "packages" / "jaya-core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.agentic_rag_capability import RAG_CAPABILITY_ID  # noqa: E402
from jaya_core.pillars.control_capabilities import INTENT_CAPABILITY_ID  # noqa: E402
from jaya_core.pillars.foundation_capabilities import SPARSE_CAPABILITY_ID  # noqa: E402
from jaya_core.pillars.local_capabilities import (  # noqa: E402
    BINARY_DOT_CAPABILITY_ID,
    LINEAGE_CAPABILITY_ID,
)
from jaya_core.pillars.maintenance_capabilities import (  # noqa: E402
    BOOTSTRAP_CAPABILITY_ID,
    LEGACY_CAPABILITY_ID,
    REGENERATION_CAPABILITY_ID,
    LegacyProtocolCapability,
)
from jaya_core.pillars.media_capability import MEDIA_CAPABILITY_ID  # noqa: E402
from jaya_core.pillars.moe_capability import MOE_CAPABILITY_ID  # noqa: E402


class DemoConfigurationError(ValueError):
    """Raised when explicit demo configuration is unusable."""

    @classmethod
    def missing(cls, name: str) -> DemoConfigurationError:
        return cls(f"{name} must be configured")

    @classmethod
    def short_key(cls) -> DemoConfigurationError:
        return cls("JAYA_LINEAGE_SIGNING_KEY must contain at least 32 bytes")


class RecoveryVerificationError(RuntimeError):
    """Raised when the restored bytes differ from the protected input."""

    def __init__(self) -> None:
        super().__init__("recovery output did not match the original state")


_MINIMUM_KEY_BYTES = 32


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--media-file", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--owner-id", required=True)
    return parser


def _environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DemoConfigurationError.missing(name)
    return value


def _write_expert(
    root: Path,
    key: bytes,
    expert_id: str,
    weights: list[list[float]],
    routing: list[float],
) -> None:
    manifest = {
        "schema_version": 1,
        "expert_id": expert_id,
        "version": "1.0",
        "task_kinds": ["RESEARCH_SCORE"],
        "input_dimension": 3,
        "output_dimension": 2,
        "weight_matrix": weights,
        "bias": [0.1, -0.1],
        "routing_vector": routing,
        "capacity": 64,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    wrapper = {
        "manifest": manifest,
        "signature": hmac.new(key, canonical, hashlib.sha256).hexdigest(),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{expert_id}.expert.json").write_text(
        json.dumps(wrapper, sort_keys=True), encoding="utf-8"
    )


def _prepare_experts(root: Path, key: bytes) -> None:
    _write_expert(
        root,
        key,
        "logic-expert",
        [[1.0, 0.0, 0.2], [0.0, 1.0, -0.2]],
        [1.0, 0.1, 0.0],
    )
    _write_expert(
        root,
        key,
        "evidence-expert",
        [[0.8, 0.1, 0.0], [0.1, 0.9, 0.1]],
        [0.2, 1.0, 0.1],
    )
    _write_expert(
        root,
        key,
        "risk-expert",
        [[0.5, 0.2, 0.4], [0.3, 0.4, 0.7]],
        [0.0, 0.2, 1.0],
    )


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _runtime(  # noqa: PLR0913
    run_root: Path,
    *,
    key: bytes,
    media_file: Path,
    expert_root: Path,
    base_url: str,
    model: str,
    timeout: float,
) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        local_pillar_data_dir=run_root / "pillars",
        node_id="operational-demo-node",
        lineage_signing_key=key,
        local_media_root=media_file.parent,
        local_expert_root=expert_root,
        ollama_base_url=base_url,
        local_model_name=model,
        local_model_timeout_seconds=timeout,
    )


def main() -> int:  # noqa: PLR0914, PLR0915
    args = _parser().parse_args()
    try:  # noqa: PLW0717
        base_url = _environment("JAYA_OLLAMA_BASE_URL")
        model = _environment("JAYA_LOCAL_PILLAR_MODEL")
        timeout = float(_environment("JAYA_LOCAL_MODEL_TIMEOUT_SECONDS"))
        key = _environment("JAYA_LINEAGE_SIGNING_KEY").encode("utf-8")
        if len(key) < _MINIMUM_KEY_BYTES:
            raise DemoConfigurationError.short_key()
        media_file = args.media_file.expanduser().resolve(strict=True)
        evidence_file = args.evidence_file.expanduser().resolve(strict=True)
        evidence_content = evidence_file.read_text(encoding="utf-8")
    except (DemoConfigurationError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "INVALID_CONFIG", "error": str(exc)}), file=sys.stderr)
        return 2

    run_id = uuid.uuid4().hex
    run_root = args.work_dir.expanduser().resolve() / run_id
    expert_root = run_root / "experts"
    _prepare_experts(expert_root, key)
    runtime = _runtime(
        run_root,
        key=key,
        media_file=media_file,
        expert_root=expert_root,
        base_url=base_url,
        model=model,
        timeout=timeout,
    )
    started = time.perf_counter()
    try:  # noqa: PLW0717
        ingested = runtime.execute_local_pillar(
            RAG_CAPABILITY_ID,
            {
                "action": "ingest",
                "source_ref": f"file:{evidence_file.as_posix()}",
                "title": evidence_file.name,
                "content": evidence_content,
            },
        )
        evidence_id = runtime.advanced_pillar_capabilities.rag.retrieve(args.query, 1)[0][
            "evidence_id"
        ]
        media = runtime.execute_local_pillar(
            MEDIA_CAPABILITY_ID,
            {"action": "observe_file", "path": media_file.name},
        )

        recovery_root = run_root / "pillars" / "maintenance" / "recovery"
        recovery_root.mkdir(parents=True, exist_ok=True)
        recovery_source = recovery_root / "runtime-state.json"
        original_state = b'{"mode":"integrated","revision":1}'
        recovery_source.write_bytes(original_state)
        recovery_backup = runtime.execute_local_pillar(
            REGENERATION_CAPABILITY_ID,
            {
                "action": "backup",
                "artifact_id": "runtime-state",
                "version": 1,
                "source_path": recovery_source.name,
                "content_type": "JSON",
            },
        )
        recovery_source.write_bytes(b"corrupt")
        recovery_restore = runtime.execute_local_pillar(
            REGENERATION_CAPABILITY_ID,
            {
                "action": "restore",
                "artifact_id": "runtime-state",
                "version": 1,
                "destination_path": recovery_source.name,
                "corruption_signal": "CHECKSUM_MISMATCH",
            },
        )
        if recovery_source.read_bytes() != original_state:
            raise RecoveryVerificationError

        migration_root = run_root / "pillars" / "maintenance" / "migration"
        migration_root.mkdir(parents=True, exist_ok=True)
        legacy_payload = {
            "schema_version": 1,
            "brain_id": "operational-demo-brain",
            "identity": {"owner_id": args.owner_id},
            "memory": [{"event": "integrated-demo"}],
            "policy": {"remote": False},
        }
        legacy_bytes = LegacyProtocolCapability.LEGACY_MAGIC + json.dumps(
            legacy_payload
        ).encode()
        (migration_root / "legacy.jaya1").write_bytes(legacy_bytes)
        source_digest = f"sha256:{hashlib.sha256(legacy_bytes).hexdigest()}"
        migration_material = (
            f"migrate|{source_digest}|current.jaya|approval-migration|{args.owner_id}"
        ).encode()
        migrated = runtime.execute_local_pillar(
            LEGACY_CAPABILITY_ID,
            {
                "action": "migrate",
                "source_path": "legacy.jaya1",
                "output_path": "current.jaya",
                "owner_id": args.owner_id,
                "approval_id": "approval-migration",
                "signature": _sign(key, migration_material),
            },
        )

        candidate_id = f"mean-{run_id}"
        proposed = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {
                "action": "propose",
                "candidate_id": candidate_id,
                "capability_id": "research.aggregate.mean",
                "capability_gap": "Aggregate bounded measurements reproducibly",
                "operation": "mean",
                "evidence_ids": [evidence_id],
                "acceptance_cases": [
                    {"values": [1, 2, 3], "expected": 2},
                    {"values": [4, 8], "expected": 6},
                ],
            },
        )
        validated = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {"action": "validate", "candidate_id": candidate_id},
        )
        install_material = (
            f"install|{candidate_id}|{proposed.data['artifact_digest']}|"
            f"{validated.data['validation_digest']}|approval-bootstrap|{args.owner_id}"
        ).encode()
        installed = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {
                "action": "install",
                "candidate_id": candidate_id,
                "approval_id": "approval-bootstrap",
                "approved_by": args.owner_id,
                "signature": _sign(key, install_material),
            },
        )

        lineage = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {
                "action": "append",
                "generation_id": f"generation-{run_id}",
                "payload": {"candidate_id": candidate_id, "classification": "CANDIDATE"},
                "evidence_refs": [evidence_id],
                "approval_ref": "approval-bootstrap",
            },
        )
        binary = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "benchmark",
                "left": [1 if index % 3 else -1 for index in range(1_024)],
                "right": [1 if index % 5 else -1 for index in range(1_024)],
                "iterations": 25,
            },
        )
        moe = runtime.execute_local_pillar(
            MOE_CAPABILITY_ID,
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": [0.9, 0.6, 0.2],
                "top_k": 2,
                "maximum_quality_regression": 1.0,
            },
        )
        sparse = runtime.execute_local_pillar(
            SPARSE_CAPABILITY_ID,
            {
                "action": "run",
                "values": [-5.0, 4.0, 0.1, -0.2],
                "top_k": 2,
                "operation": "relu",
                "maximum_quality_regression": 1.0,
            },
        )
        now = time.time()
        runtime.execute_local_pillar(
            INTENT_CAPABILITY_ID,
            {
                "action": "record_consent",
                "owner_id": args.owner_id,
                "receipt_id": f"consent-{run_id}",
                "granted_at": now,
                "expires_at": now + 600,
            },
        )
        sequence = ["open research", "inspect evidence", "write report"]
        for _ in range(2):
            runtime.execute_local_pillar(
                INTENT_CAPABILITY_ID,
                {"action": "observe", "owner_id": args.owner_id, "sequence": sequence},
            )
        intent = runtime.execute_local_pillar(
            INTENT_CAPABILITY_ID,
            {
                "action": "predict",
                "owner_id": args.owner_id,
                "current_intent": "inspect evidence",
            },
        )
        feedback = runtime.execute_local_pillar(
            INTENT_CAPABILITY_ID,
            {
                "action": "feedback",
                "prediction_id": intent.data["prediction_id"],
                "confirmed": False,
            },
        )
    finally:
        runtime.close()

    restarted = _runtime(
        run_root,
        key=key,
        media_file=media_file,
        expert_root=expert_root,
        base_url=base_url,
        model=model,
        timeout=timeout,
    )
    try:
        restart_checks = {
            "lineage": restarted.execute_local_pillar(
                LINEAGE_CAPABILITY_ID, {"action": "verify"}
            ).to_dict(),
            "migration": restarted.execute_local_pillar(
                LEGACY_CAPABILITY_ID, {"action": "inspect", "path": "current.jaya"}
            ).to_dict(),
            "bootstrap": restarted.execute_local_pillar(
                BOOTSTRAP_CAPABILITY_ID,
                {"action": "invoke", "candidate_id": candidate_id, "values": [10, 20, 30]},
            ).to_dict(),
        }
    finally:
        restarted.close()

    report = {
        "status": "INTEGRATED_OPERATIONAL_DEMO_COMPLETED",
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "environment": {
            "python": platform.python_version(),
            "model": model,
            "ffprobe_input": str(media_file),
        },
        "pillars": {
            "P004": media.to_dict(),
            "P009": {"backup": recovery_backup.to_dict(), "restore": recovery_restore.to_dict()},
            "P019": migrated.to_dict(),
            "P025": lineage.to_dict(),
            "P028": installed.to_dict(),
            "P029": binary.to_dict(),
            "P034": moe.to_dict(),
            "P035": sparse.to_dict(),
            "P040": {"prediction": intent.to_dict(), "feedback": feedback.to_dict()},
        },
        "rag_evidence": ingested.to_dict(),
        "restart_checks": restart_checks,
    }
    report_path = run_root / "integrated-operational-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "artifact": str(report_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
