"""Pillar 16 — Quantum-Resistant Skin (PQC).

Provides post-quantum cryptographic signing and verification for
inter-device communication and .jay manifest integrity.

Backends (in priority order):
1. ``liboqs`` — NIST PQC finalist algorithms (Dilithium3, Kyber).
2. ``cryptography`` — ECDSA P-256 (pre-quantum but strong conventional).
3. Pure-Python HMAC-SHA3-256 — fallback, symmetric only.

Usage
-----
    pqc = PQCWrapper()
    sig = pqc.sign(b"my payload")
    ok  = pqc.verify(b"my payload", sig)
    print(pqc.algorithm)   # "DILITHIUM3" / "ECDSA_P256" / "HMAC_SHA3"
"""

import hashlib
import hmac
import logging
import os
from typing import Any, Dict

logger = logging.getLogger("PQC")

# Backend detection
_backend: str = "HMAC_SHA3"    # fallback
_oqs_available: bool = False
_ecdsa_available: bool = False

try:
    import oqs as _oqs_lib  # type: ignore[import]
    _oqs_available = True
    _backend = "DILITHIUM3"
except ImportError:
    _oqs_lib = None  # type: ignore[assignment]

if not _oqs_available:
    try:
        from cryptography.hazmat.backends import default_backend  # type: ignore[import]
        from cryptography.hazmat.primitives import (  # type: ignore[import]
            hashes,
            serialization,
        )
        from cryptography.hazmat.primitives.asymmetric import ec  # type: ignore[import]
        _ecdsa_available = True
        _backend = "ECDSA_P256"
    except ImportError:
        pass

logger.debug("[PQC] backend selected: %s", _backend)


# ---------------------------------------------------------------------------
# PQCWrapper
# ---------------------------------------------------------------------------

class PQCWrapper:
    """Post-quantum (or best-available) cryptographic signing wrapper.

    Parameters
    ----------
    secret_key:
        Used only for the HMAC fallback backend.  For OQS/ECDSA the key
        pair is generated/loaded internally.
    """

    def __init__(self, secret_key: bytes = b""):
        self._secret = secret_key or os.urandom(32)
        self.algorithm = _backend
        self._sign_count:   int = 0
        self._verify_count: int = 0

        # Initialise backend-specific state
        self._private_key: Any = None
        self._public_key:  Any = None
        self._oqs_sig:     Any = None

        if _oqs_available and _oqs_lib is not None:
            self._oqs_sig = _oqs_lib.Signature("Dilithium3")  # type: ignore[union-attr]
            self._public_key = self._oqs_sig.generate_keypair()  # type: ignore[union-attr]
        elif _ecdsa_available:
            from cryptography.hazmat.backends import default_backend as _be
            from cryptography.hazmat.primitives.asymmetric import ec as _ec
            self._private_key = _ec.generate_private_key(
                _ec.SECP256R1(), _be()
            )
            self._public_key = self._private_key.public_key()

    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> bytes:
        """Return a signature for *data*."""
        self._sign_count += 1
        if _oqs_available and self._oqs_sig:
            return bytes(self._oqs_sig.sign(data))
        if _ecdsa_available and self._private_key:
            from cryptography.hazmat.primitives import hashes as _h
            from cryptography.hazmat.primitives.asymmetric import ec as _ec
            return self._private_key.sign(data, _ec.ECDSA(_h.SHA256()))  # type: ignore[no-any-return]
        # HMAC fallback
        return hmac.new(self._secret, data, hashlib.sha3_256).digest()

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Return True if *signature* is valid for *data*."""
        self._verify_count += 1
        try:
            if _oqs_available and self._oqs_sig:
                return bool(self._oqs_sig.verify(data, signature, self._public_key))
            if _ecdsa_available and self._public_key:
                from cryptography.exceptions import InvalidSignature
                from cryptography.hazmat.primitives import hashes as _h
                from cryptography.hazmat.primitives.asymmetric import ec as _ec
                try:
                    self._public_key.verify(
                        signature, data, _ec.ECDSA(_h.SHA256())
                    )
                    return True
                except InvalidSignature:
                    return False
            # HMAC fallback
            expected = hmac.new(self._secret, data, hashlib.sha3_256).digest()
            return hmac.compare_digest(expected, signature)
        except Exception as exc:
            logger.warning("[PQC] verify error: %s", exc)
            return False

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "algorithm":    self.algorithm,
            "oqs":          _oqs_available,
            "ecdsa":        _ecdsa_available,
            "signs":        self._sign_count,
            "verifies":     self._verify_count,
        }
