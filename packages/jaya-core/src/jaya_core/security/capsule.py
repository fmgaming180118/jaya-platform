"""Portable one-file JAYA capsule backed by P13 Cryptographic Skin."""

from __future__ import annotations

import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Protocol

from jaya_core.brain_v2.protection.pqc import AgileSignatureEnvelope
from jaya_core.security.cryptographic_skin import CryptographicSkin, SealedEnvelope

_MAGIC = b"JAYA-CAPSULE\x00\x01\n"
_MAX_CONTAINER_BYTES = 96 * 1024 * 1024


class CapsuleKind(str, Enum):
    BRAIN = "brain"
    BACKUP = "backup"
    PUZZLE = "puzzle"
    MESH = "mesh"


class CapsuleError(RuntimeError):
    """Raised when a capsule is malformed or violates its expected scope."""


class QuantumCapsuleAuthority(Protocol):
    def sign(self, payload: bytes) -> AgileSignatureEnvelope:
        ...

    def verify(self, payload: bytes, envelope: AgileSignatureEnvelope) -> bool:
        ...


class JayaCapsuleCodec:
    """Encode and decode strict portable `.jayac` files through P13."""

    def __init__(
        self,
        cryptographic_skin: CryptographicSkin,
        *,
        quantum_authority: QuantumCapsuleAuthority | None = None,
        quantum_required: bool = False,
    ) -> None:
        if quantum_required and quantum_authority is None:
            raise CapsuleError("quantum-required capsule needs a P16 authority")
        self._skin = cryptographic_skin
        self._quantum = quantum_authority
        self._quantum_required = quantum_required

    def seal(
        self,
        payload: bytes,
        *,
        kind: CapsuleKind,
        subject: str,
        ttl_seconds: int = 31_536_000,
    ) -> bytes:
        envelope = self._skin.seal(
            payload,
            purpose=f"jaya.capsule.{kind.value}",
            subject=subject,
            content_type="application/vnd.jaya.capsule-payload",
            ttl_seconds=ttl_seconds,
        )
        p13 = envelope.to_dict()
        signed_payload = json.dumps(
            p13, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        quantum = self._quantum.sign(signed_payload) if self._quantum else None
        body = json.dumps(
            {"p13": p13, "p16": quantum.to_dict() if quantum else None},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        container = _MAGIC + body
        if len(container) > _MAX_CONTAINER_BYTES:
            raise CapsuleError("capsule exceeds the container resource limit")
        return container

    def open(
        self,
        container: bytes,
        *,
        expected_kind: CapsuleKind,
        expected_subject: str,
    ) -> bytes:
        raw = bytes(container)
        if len(raw) > _MAX_CONTAINER_BYTES or not raw.startswith(_MAGIC):
            raise CapsuleError("capsule header or size is invalid")
        try:
            value = json.loads(raw[len(_MAGIC) :])
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CapsuleError("capsule body is invalid") from exc
        if not isinstance(value, dict) or set(value) != {"p13", "p16"}:
            raise CapsuleError("capsule body must contain P13 and P16 fields")
        if not isinstance(value["p13"], dict):
            raise CapsuleError("capsule P13 envelope is invalid")
        signed_payload = json.dumps(
            value["p13"], sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if value["p16"] is None:
            if self._quantum_required:
                raise CapsuleError("capsule is missing its required P16 signature")
        else:
            if self._quantum is None or not isinstance(value["p16"], dict):
                raise CapsuleError("capsule P16 authority is unavailable")
            quantum = AgileSignatureEnvelope.from_dict(value["p16"])
            if self._quantum.verify(signed_payload, quantum) is not True:
                raise CapsuleError("capsule P16 signature is invalid")
        envelope = SealedEnvelope.from_dict(value["p13"])
        if (
            envelope.purpose != f"jaya.capsule.{expected_kind.value}"
            or envelope.subject != expected_subject
            or envelope.content_type != "application/vnd.jaya.capsule-payload"
        ):
            raise CapsuleError("capsule kind or subject does not match its boundary")
        return self._skin.open(envelope)

    def seal_file(
        self,
        source: Path | str,
        destination: Path | str,
        *,
        kind: CapsuleKind,
        subject: str,
        ttl_seconds: int = 31_536_000,
    ) -> Path:
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        try:
            payload = source_path.read_bytes()
        except OSError as exc:
            raise CapsuleError("capsule source cannot be read") from exc
        container = self.seal(
            payload,
            kind=kind,
            subject=subject,
            ttl_seconds=ttl_seconds,
        )
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            dir=destination_path.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(container)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination_path)
        except OSError as exc:
            raise CapsuleError("capsule cannot be persisted atomically") from exc
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        return destination_path

    def open_file(
        self,
        source: Path | str,
        *,
        expected_kind: CapsuleKind,
        expected_subject: str,
    ) -> bytes:
        try:
            container = Path(source).resolve().read_bytes()
        except OSError as exc:
            raise CapsuleError("capsule file cannot be read") from exc
        return self.open(
            container,
            expected_kind=expected_kind,
            expected_subject=expected_subject,
        )


__all__ = ["CapsuleError", "CapsuleKind", "JayaCapsuleCodec"]
