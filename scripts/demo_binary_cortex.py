#!/usr/bin/env python3
"""Run the authenticated P29 Binary Cortex production path locally."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "packages" / "jaya-core" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    DNAAnchorError,
    EncryptedFileKeyStore,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.binary_cortex import BinaryCortexService  # noqa: E402
from jaya_core.pillars.local_capabilities import (  # noqa: E402
    BINARY_DOT_CAPABILITY_ID,
)
from jaya_core.pillars.local_types import LocalPillarError  # noqa: E402
from jaya_core.security.cryptographic_skin import CryptographicSkin  # noqa: E402


def _components(
    workspace: Path, identity_secret: str, skin_secret: str
) -> tuple[DNAAnchor, CryptographicSkin]:
    identity_root = workspace / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    try:
        anchor.load_identity()
    except DNAAnchorError:
        anchor.enroll()
    skin = CryptographicSkin(
        workspace / "security.db",
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    return anchor, skin


def _runtime(workspace: Path, anchor: DNAAnchor, skin: CryptographicSkin) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=workspace / "runtime.db",
        local_pillar_data_dir=workspace / "pillar-capabilities",
        identity_anchor=anchor,
        cryptographic_skin=skin,
    )


def _weights(rows: int, features: int) -> list[list[int]]:
    return [
        [1 if (row * 11 + column * 5) % 7 else -1 for column in range(features)]
        for row in range(rows)
    ]


def _dense(weights: list[list[int]], vector: list[int]) -> list[int]:
    return [sum(a * b for a, b in zip(row, vector, strict=True)) for row in weights]


def _failure_code(action: object) -> str:
    try:
        action()  # type: ignore[operator]
    except LocalPillarError as exc:
        return exc.code
    return "UNEXPECTED_SUCCESS"


def main() -> int:  # noqa: PLR0914, PLR0915
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=False)

    identity_secret = os.environ.get("JAYA_DEMO_IDENTITY_SECRET") or secrets.token_urlsafe(48)
    skin_secret = os.environ.get("JAYA_DEMO_SKIN_SECRET") or secrets.token_urlsafe(48)
    features = 1_031
    weights = _weights(16, features)
    vector = [1 if index % 3 else -1 for index in range(features)]
    expected = _dense(weights, vector)

    anchor, skin = _components(workspace, identity_secret, skin_secret)
    runtime = _runtime(workspace, anchor, skin)
    try:
        profile = runtime.execute_local_pillar(BINARY_DOT_CAPABILITY_ID, {"action": "profile"})
        installed = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {"action": "install", "artifact_id": "demo-binary-model", "weights": weights},
        )
        inference = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "infer",
                "artifact_id": "demo-binary-model",
                "input": vector,
                "timeout_seconds": 2.0,
            },
        )
        receipt = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {"action": "verify_receipt", "receipt_id": inference.data["receipt_id"]},
        )
        benchmark = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "benchmark",
                "left": vector,
                "right": weights[0],
                "iterations": 100,
            },
        )
        shape_failure = _failure_code(
            lambda: runtime.execute_local_pillar(
                BINARY_DOT_CAPABILITY_ID,
                {
                    "action": "infer",
                    "artifact_id": "demo-binary-model",
                    "input": vector[:-1],
                },
            )
        )
        artifact_path = Path(installed.data["artifact_path"])
        plaintext_absent = b'"packed_rows"' not in artifact_path.read_bytes()
    finally:
        runtime.close()

    restarted_anchor, restarted_skin = _components(workspace, identity_secret, skin_secret)
    restarted = _runtime(workspace, restarted_anchor, restarted_skin)
    try:
        restart_inference = restarted.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "infer",
                "artifact_id": "demo-binary-model",
                "input": vector,
            },
        )
        fallback_service = BinaryCortexService(
            artifact_root=workspace / "pillar-capabilities" / "binary_cortex",
            cryptographic_skin=restarted_skin,
            kernel_probe=lambda: False,
        )
        fallback = fallback_service.infer("demo-binary-model", vector, allow_dense_fallback=True)
    finally:
        restarted.close()

    report = {
        "status": "VERIFIED_REPRESENTATIVE_DEMO",
        "kernel_profile": profile.data,
        "artifact_authenticated": installed.code == "BINARY_ARTIFACT_INSTALLED",
        "plaintext_absent": plaintext_absent,
        "binary_exact": inference.data["outputs"] == expected,
        "receipt_verified": receipt.code == "BINARY_RECEIPT_VERIFIED",
        "restart_exact": restart_inference.data["outputs"] == expected,
        "fallback_labeled": (
            fallback.code == "DENSE_FALLBACK_EXECUTED"
            and fallback.data["fallback_used"] is True
            and fallback.data["outputs"] == expected
        ),
        "shape_failure": shape_failure,
        "artifact": installed.data,
        "inference": {key: value for key, value in inference.data.items() if key != "outputs"},
        "benchmark": benchmark.data,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
