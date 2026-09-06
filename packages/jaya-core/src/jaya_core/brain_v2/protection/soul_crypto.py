"""Soul payload cryptography for serializer and migration pipelines.

Primary backend uses AES-GCM (cryptography). If unavailable, this module
falls back to an authenticated pure-Python stream cipher.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Optional, Tuple

import msgpack

try:
    from cryptography.exceptions import InvalidTag  # type: ignore[import]
    from cryptography.hazmat.primitives.ciphers.aead import (
        AESGCM,  # type: ignore[import]
    )

    _HAS_AESGCM = True
except Exception:
    InvalidTag = Exception  # type: ignore[misc, assignment]
    AESGCM = None  # type: ignore[assignment]
    _HAS_AESGCM = False


_STRICT_ENV = "JAYA_STRICT_CRYPTO"


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


class SoulCrypto:
    """Encrypt/decrypt SOUL payloads with explicit backend selection.

    Backends:
    - AES_GCM (preferred when cryptography is installed)
    - HMAC_XOR_STREAM (pure-Python fallback)
    """

    def __init__(self, force_backend: Optional[str] = None):
        strict = _is_truthy(os.getenv(_STRICT_ENV, "0"))
        backend = force_backend

        if backend is None:
            backend = "AES_GCM" if _HAS_AESGCM else "HMAC_XOR_STREAM"

        if backend == "AES_GCM" and not _HAS_AESGCM:
            raise RuntimeError("AES_GCM backend requested but cryptography is unavailable")

        if strict and backend != "AES_GCM":
            raise RuntimeError(
                "Strict crypto mode requires AES_GCM backend "
                f"({_STRICT_ENV}=1)."
            )

        self.backend = backend
        self.key: Optional[bytes] = None

    def derive_key(
        self,
        password: str,
        hardware_id: bytes | str,
        salt: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes]:
        if salt is None:
            salt = os.urandom(16)

        hw = hardware_id if isinstance(hardware_id, (bytes, bytearray)) else hardware_id.encode("utf-8")
        material = password.encode("utf-8") + bytes(hw)

        key = hashlib.pbkdf2_hmac("sha256", material, salt, 200_000, dklen=32)
        return key, salt

    def encrypt(self, payload: Any) -> Tuple[bytes, bytes, bytes]:
        if not self.key:
            raise ValueError("Crypto key is not initialised")

        plaintext = msgpack.packb(payload, use_bin_type=True)

        if self.backend == "AES_GCM":
            nonce = os.urandom(12)
            ct = AESGCM(self.key).encrypt(nonce, plaintext, None)  # type: ignore[misc]
            return nonce, ct[:-16], ct[-16:]

        nonce = os.urandom(16)
        stream = self._keystream(len(plaintext), nonce)
        cipher = bytes(p ^ s for p, s in zip(plaintext, stream))
        tag = hmac.new(self.key, nonce + cipher, hashlib.sha256).digest()
        return nonce, cipher, tag

    def decrypt(self, nonce: bytes, cipher: bytes, tag: bytes) -> Any:
        if not self.key:
            raise ValueError("Crypto key is not initialised")

        if self.backend == "AES_GCM":
            try:
                plaintext = AESGCM(self.key).decrypt(nonce, cipher + tag, None)  # type: ignore[misc]
            except InvalidTag as exc:  # pragma: no cover - depends on backend
                raise ValueError("SOUL payload authentication failed") from exc
        else:
            expected = hmac.new(self.key, nonce + cipher, hashlib.sha256).digest()
            if not hmac.compare_digest(expected, tag):
                raise ValueError("SOUL payload authentication failed")
            stream = self._keystream(len(cipher), nonce)
            plaintext = bytes(c ^ s for c, s in zip(cipher, stream))

        return msgpack.unpackb(plaintext, raw=False)

    def _keystream(self, length: int, nonce: bytes) -> bytes:
        # Expand deterministic keystream via keyed HMAC counter blocks.
        blocks = []
        counter = 0
        while sum(len(b) for b in blocks) < length:
            block = hmac.new(
                self.key,
                nonce + counter.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()
            blocks.append(block)
            counter += 1
        return b"".join(blocks)[:length]
