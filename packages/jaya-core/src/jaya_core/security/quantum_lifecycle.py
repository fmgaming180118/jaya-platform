"""Persistent P16 ML-DSA key lifecycle sealed by P13."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jaya_core.brain_v2.protection.pqc import (
    AgileSignatureEnvelope,
    OQSMLDSA65Provider,
    QuantumFailureCode,
    QuantumPolicy,
    QuantumSecurityError,
    QuantumSignatureAuthority,
    QuantumSuite,
)
from jaya_core.security.cryptographic_skin import CryptographicSkin, SealedEnvelope


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


class PersistentQuantumAuthority:
    """Own one active ML-DSA key and preserve retired verification lineage."""

    def __init__(
        self,
        db_path: Path | str,
        cryptographic_skin: CryptographicSkin,
        policy: QuantumPolicy,
        *,
        current_year: int,
        provider_cls: type = OQSMLDSA65Provider,
    ) -> None:
        self._connection = sqlite3.connect(Path(db_path).resolve(), timeout=5.0)
        self._connection.row_factory = sqlite3.Row
        self._skin = cryptographic_skin
        self.policy = policy
        self.current_year = current_year
        self._provider_cls = provider_cls
        try:
            self._create_schema()
            self._provider, self.active_key_id = self._load_or_create_active()
            self._authority = QuantumSignatureAuthority(
                policy,
                pq_provider=self._provider,
                current_year=current_year,
            )
        except Exception:
            self._connection.close()
            raise

    def sign(self, payload: bytes) -> AgileSignatureEnvelope:
        return self._authority.sign(
            payload, QuantumSuite.HYBRID_ED25519_ML_DSA_65
        )

    def verify(
        self, payload: bytes, envelope: AgileSignatureEnvelope
    ) -> bool:
        public_key = envelope.pq_public_key
        if not public_key:
            return False
        fingerprint = hashlib.sha256(_decode(public_key)).hexdigest()
        row = self._connection.execute(
            "SELECT state FROM quantum_keys WHERE public_sha256 = ?",
            (fingerprint,),
        ).fetchone()
        if row is not None and row["state"] == "REVOKED":
            raise QuantumSecurityError(
                QuantumFailureCode.KEY_REVOKED,
                "ML-DSA signature belongs to a revoked key",
            )
        return self._authority.verify(payload, envelope)

    def rotate(self) -> str:
        with self._connection:
            self._connection.execute(
                "UPDATE quantum_keys SET state = 'RETIRED' WHERE state = 'ACTIVE'"
            )
        if hasattr(self._provider, "close"):
            self._provider.close()
        self._provider, self.active_key_id = self._create_key()
        self._authority = QuantumSignatureAuthority(
            self.policy,
            pq_provider=self._provider,
            current_year=self.current_year,
        )
        return self.active_key_id

    def revoke(self, key_id: str) -> None:
        with self._connection:
            changed = self._connection.execute(
                "UPDATE quantum_keys SET state = 'REVOKED' WHERE key_id = ?",
                (key_id,),
            ).rowcount
        if changed != 1:
            raise QuantumSecurityError(
                QuantumFailureCode.INVALID_INPUT, "ML-DSA key does not exist"
            )

    def status(self) -> dict[str, object]:
        counts = dict(
            self._connection.execute(
                "SELECT state, COUNT(*) FROM quantum_keys GROUP BY state"
            ).fetchall()
        )
        versions = self._provider.versions() if hasattr(self._provider, "versions") else {}
        return {
            "ready": self._provider.available(),
            "active_key_id": self.active_key_id,
            "provider": self._provider.provider_id,
            "versions": versions,
            "active_keys": counts.get("ACTIVE", 0),
            "retired_keys": counts.get("RETIRED", 0),
            "revoked_keys": counts.get("REVOKED", 0),
        }

    def close(self) -> None:
        if hasattr(self._provider, "close"):
            self._provider.close()
        self._connection.close()

    def _load_or_create_active(self) -> tuple[Any, str]:
        row = self._connection.execute(
            """
            SELECT key_id, public_key, secret_envelope_json, row_sha256
            FROM quantum_keys WHERE state = 'ACTIVE'
            """
        ).fetchone()
        if row is None:
            return self._create_key()
        material = f"{row['key_id']}:{row['public_key']}:{row['secret_envelope_json']}"
        if hashlib.sha256(material.encode()).hexdigest() != row["row_sha256"]:
            raise QuantumSecurityError(
                QuantumFailureCode.INVALID_ENVELOPE,
                "persistent ML-DSA key record is corrupt",
            )
        envelope = SealedEnvelope.from_dict(json.loads(row["secret_envelope_json"]))
        secret = self._skin.open(envelope)
        return (
            self._provider_cls(
                secret_key=secret,
                public_key=_decode(row["public_key"]),
            ),
            str(row["key_id"]),
        )

    def _create_key(self) -> tuple[Any, str]:
        provider = self._provider_cls()
        if not provider.available():
            raise QuantumSecurityError(
                QuantumFailureCode.PROVIDER_UNAVAILABLE,
                f"{getattr(provider, 'provider_id', 'liboqs ML-DSA-65')} provider is unavailable",
            )
        key_id = f"ml-dsa-65-{uuid.uuid4().hex}"
        public = _encode(provider.public_key())
        secret_envelope = self._skin.seal(
            provider.export_secret_key(),
            purpose="quantum.private-key",
            subject=key_id,
            content_type="application/vnd.jaya.ml-dsa-private-key",
            ttl_seconds=31_536_000,
        )
        serialized = json.dumps(
            secret_envelope.to_dict(), sort_keys=True, separators=(",", ":")
        )
        material = f"{key_id}:{public}:{serialized}"
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO quantum_keys(
                    key_id, public_key, public_sha256, secret_envelope_json,
                    state, created_at, row_sha256
                ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (
                    key_id,
                    public,
                    hashlib.sha256(provider.public_key()).hexdigest(),
                    serialized,
                    datetime.now(timezone.utc).isoformat(),
                    hashlib.sha256(material.encode()).hexdigest(),
                ),
            )
        return provider, key_id

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS quantum_keys(
                    key_id TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL,
                    public_sha256 TEXT NOT NULL UNIQUE,
                    secret_envelope_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('ACTIVE','RETIRED','REVOKED')),
                    created_at TEXT NOT NULL,
                    row_sha256 TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_quantum_one_active
                ON quantum_keys(state) WHERE state = 'ACTIVE';
                """
            )


__all__ = ["PersistentQuantumAuthority"]
