from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class TestNarrativeSigner:
    """Test-only signer implementation; never imported by production code."""

    __test__ = False

    def __init__(self) -> None:
        self._private = Ed25519PrivateKey.generate()

    @property
    def actor_id(self) -> str:
        return "test-brain"

    @property
    def key_id(self) -> str:
        return "test-brain:1"

    def sign(self, purpose: str, payload_sha256: str) -> dict[str, object]:
        message = f"{purpose}:{payload_sha256}".encode()
        return {
            "purpose": purpose,
            "payload_sha256": payload_sha256,
            "signature": base64.b64encode(self._private.sign(message)).decode(),
        }

    def verify(self, attestation: dict[str, object]) -> bool:
        try:
            purpose = str(attestation["purpose"])
            digest = str(attestation["payload_sha256"])
            signature = base64.b64decode(str(attestation["signature"]), validate=True)
            self._private.public_key().verify(
                signature, f"{purpose}:{digest}".encode()
            )
            return True
        except (KeyError, ValueError, InvalidSignature):
            return False

    def health_check(self) -> bool:
        return True
