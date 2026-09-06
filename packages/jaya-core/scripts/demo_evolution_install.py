#!/usr/bin/env python3
"""Local P24 lifecycle demo using the production manifest installer.

This demo generates a signed local manifest and approval, installs a real JSON
capability artifact, executes a content-validating canary, reconstructs the
installer to simulate restart, and performs an idempotent rollback. It is a
local verification workflow, not a production approval or deployment tool.
"""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jaya_core.brain_v2.engine.evolution_installer import EvolutionInstaller
from jaya_core.brain_v2.engine.evolution_manifest_v1 import (
    ABSENT_RESTORE_DIGEST,
    EvolutionManifestSigner,
    EvolutionManifestVerifier,
    EvolutionTrustStore,
    build_manifest_v1,
    canonical_json,
    digest_bytes,
    digest_file,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local signed evolution install/canary/rollback demo"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--approver", required=True)
    return parser


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(payload))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_root = Path(args.output_dir).expanduser().resolve()
    capability = str(args.capability).strip()
    approver = str(args.approver).strip()
    if not capability or not approver:
        raise SystemExit("--capability and --approver must not be empty")

    run_id = uuid.uuid4().hex
    run_root = output_root / run_id
    staging_root = run_root / "staging"
    data_root = run_root / "data"
    registry_root = run_root / "registry"
    staging_root.mkdir(parents=True)
    data_root.mkdir()
    registry_root.mkdir()

    now = time.time()
    artifact = staging_root / "capability.json"
    artifact_payload = {
        "schema_version": 1,
        "capability": capability,
        "created_at": now,
        "run_id": run_id,
    }
    _write_json(artifact, artifact_payload)

    manifest_key = secrets.token_bytes(32)
    approval_key = secrets.token_bytes(32)
    signer = EvolutionManifestSigner(
        manifest_key_id="local-demo-manifest",
        manifest_key=manifest_key,
        approval_key_id="local-demo-approval",
        approval_key=approval_key,
    )
    trust_store = EvolutionTrustStore(
        manifest_keys={"local-demo-manifest": manifest_key},
        approval_keys={"local-demo-approval": approval_key},
        environment="development",
    )
    verifier = EvolutionManifestVerifier(
        trust_store=trust_store,
        runtime="JAYA_CORE",
        runtime_version="local-demo-v1",
    )

    test_receipt_digest = digest_bytes(
        canonical_json(
            {
                "type": "test",
                "artifact_digest": digest_file(artifact),
                "passed": artifact_payload["schema_version"] == 1,
            }
        )
    )
    benchmark_receipt_digest = digest_bytes(
        canonical_json(
            {
                "type": "benchmark",
                "artifact_size_bytes": artifact.stat().st_size,
                "passed": artifact.stat().st_size > 0,
            }
        )
    )
    verified_receipts = {
        test_receipt_digest,
        benchmark_receipt_digest,
    }
    manifest = build_manifest_v1(
        signer=signer,
        manifest_id=f"manifest-{run_id}",
        candidate_id=f"candidate-{run_id}",
        payload={"capability": capability, "schema_version": 1},
        artifact_path=artifact,
        artifact_name=artifact.name,
        artifact_media_type="application/json",
        provenance={
            "source_uri": artifact.as_uri(),
            "source_revision": digest_file(artifact),
            "builder_id": "local-demo-builder",
            "built_at": now,
            "reproducible": True,
        },
        license_info={
            "spdx_id": "MIT",
            "redistribution_allowed": True,
            "source_notice": "Locally generated JAYA evolution demo artifact",
        },
        compatibility={
            "runtime": "JAYA_CORE",
            "target_versions": ["local-demo-v1"],
            "platform_tags": [
                f"{sys.platform}-{platform.machine() or 'unknown'}"
            ],
        },
        evidence_receipts=[
            {
                "receipt_type": "test",
                "receipt_digest": test_receipt_digest,
                "verifier_key_id": "local-demo-verifier",
                "verified": True,
            },
            {
                "receipt_type": "benchmark",
                "receipt_digest": benchmark_receipt_digest,
                "verifier_key_id": "local-demo-verifier",
                "verified": True,
            },
        ],
        target_path="capabilities/capability.json",
        registry_key=f"candidate-{run_id}",
        canary_check_id="json-capability-v1",
        expected_restore_digest=ABSENT_RESTORE_DIGEST,
        approver=approver,
        approval_id=f"approval-{run_id}",
        approval_issued_at=now,
        approval_expires_at=now + 900.0,
        created_at=now,
    )
    _write_json(run_root / "manifest.json", manifest)

    def canary(target: Path, verified: Any) -> dict[str, Any]:
        try:
            observed = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"passed": False, "reason": "artifact_not_valid_json"}
        passed = (
            observed == artifact_payload
            and digest_file(target) == verified.artifact_digest
        )
        return {
            "passed": passed,
            "schema_version": observed.get("schema_version"),
            "capability": observed.get("capability"),
            "observed_digest": digest_file(target),
        }

    installer = EvolutionInstaller(
        verifier=verifier,
        registry_root=registry_root,
        data_root=data_root,
        canary_runner=canary,
    )
    installed = installer.install(
        manifest,
        artifact_source=artifact,
        verified_receipt_digests=verified_receipts,
    )
    target = data_root / installed.target_path
    if not target.is_file() or json.loads(target.read_text(encoding="utf-8")) != artifact_payload:
        raise RuntimeError("installed artifact could not be reopened and verified")

    restarted_installer = EvolutionInstaller(
        verifier=verifier,
        registry_root=registry_root,
        data_root=data_root,
        canary_runner=canary,
    )
    rolled_back = restarted_installer.rollback(installed.registry_key)
    repeated = restarted_installer.rollback(installed.registry_key)
    if target.exists() or rolled_back.idempotent or not repeated.idempotent:
        raise RuntimeError("rollback or idempotency verification failed")

    print(
        json.dumps(
            {
                "status": "INTEGRATED_EVOLUTION_DEMO_COMPLETED",
                "run_root": str(run_root),
                "artifact_digest": digest_file(artifact),
                "manifest_digest": installed.manifest_digest,
                "canary_receipt_path": installed.canary_receipt_path,
                "rollback_status": rolled_back.status,
                "restart_idempotent": repeated.idempotent,
                "installed_target_exists_after_rollback": target.exists(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
