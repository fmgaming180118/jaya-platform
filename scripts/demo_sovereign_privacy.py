#!/usr/bin/env python3
"""Execute a real local P20 privacy lifecycle and print measured receipts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "JAYA_CORE"
for item in (ROOT, CORE_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from src.security.sovereign_privacy import (  # noqa: E402
    DataClassification,
    DataDestination,
    DataPurpose,
    PrivacyUseRequest,
    SovereignPrivacy,
    create_consent_grant,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=True)
    database = args.workspace / "privacy-demo.db"
    secret = os.environ.get("JAYA_PRIVACY_KEY_SECRET") or os.urandom(48).hex()
    owner = "owner-demo"
    payload_value = f"private-value-{os.urandom(12).hex()}"
    signer = Ed25519PrivateKey.generate()
    public_key = signer.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    started = time.perf_counter()
    privacy = SovereignPrivacy(
        database, secret, consent_public_keys={"owner-demo-key": public_key}
    )
    descriptor = privacy.store(
        actor_id=owner,
        owner_id=owner,
        subject_id=owner,
        data_id="demo-private-record",
        classification=DataClassification.CONFIDENTIAL,
        allowed_purposes=(DataPurpose.MEMORY, DataPurpose.EXPORT),
        payload={"value": payload_value},
        retention_seconds=300,
    )
    plaintext_absent = privacy.plaintext_absent(payload_value)
    privacy.close()

    privacy = SovereignPrivacy(
        database, secret, consent_public_keys={"owner-demo-key": public_key}
    )
    restored = privacy.retrieve(
        actor_id=owner,
        data_id=descriptor.data_id,
        purpose=DataPurpose.MEMORY,
    )
    now = datetime.now(timezone.utc)
    grant = create_consent_grant(
        approver_id="owner-demo-key",
        owner_id=owner,
        subject_id=owner,
        classifications=(DataClassification.CONFIDENTIAL,),
        purposes=(DataPurpose.MODEL_INFERENCE,),
        providers=("provider-demo",),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        signer=signer.sign,
    )
    request_fields = {
        "request_id": "privacy-demo-request",
        "actor_id": owner,
        "owner_id": owner,
        "subject_id": owner,
        "data_id": descriptor.data_id,
        "classification": DataClassification.CONFIDENTIAL,
        "purpose": DataPurpose.MODEL_INFERENCE,
        "destination": DataDestination.EXTERNAL_PROVIDER,
        "provider_id": "provider-demo",
        "payload_sha256": descriptor.plaintext_sha256,
    }
    denied = privacy.evaluate(PrivacyUseRequest(**request_fields))
    privacy.install_consent(grant)
    allowed = privacy.evaluate(
        PrivacyUseRequest(**request_fields, consent_id=grant.consent_id)
    )
    exported = privacy.export_owner(owner)
    deletion = privacy.delete_owner(owner)
    audit_valid = privacy.audit_chain_valid()
    privacy.close()
    elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
    result = {
        "status": "VERIFIED_LOCAL",
        "restart_restored": restored.get("value") == payload_value,
        "plaintext_absent": plaintext_absent
        and payload_value.encode() not in database.read_bytes(),
        "external_without_consent": denied.effect.value,
        "external_with_consent": allowed.effect.value,
        "export_records": len(exported["records"]),
        "deletion_event": deletion["event"],
        "audit_chain_valid": audit_valid,
        "elapsed_ms": elapsed_ms,
        "storage_bytes": database.stat().st_size,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if all(
            (
                result["restart_restored"],
                result["plaintext_absent"],
                result["external_without_consent"] == "DENY",
                result["external_with_consent"] == "ALLOW",
                result["audit_chain_valid"],
            )
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
