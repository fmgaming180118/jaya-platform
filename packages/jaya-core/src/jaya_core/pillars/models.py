"""Strict contracts for the extensible JAYA pillar catalog."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

_PILLAR_ID = re.compile(r"^P[0-9]{3,6}$")
_ARCHITECTURE_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_SOURCE_FLAG = re.compile(r"^JayaFlags\.[A-Z][A-Z0-9_]{1,63}$")
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{2,255}$")


class PillarError(RuntimeError):
    """Base error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PillarValidationError(PillarError):
    """Raised when untrusted pillar input violates its contract."""


class PillarStorageError(PillarError):
    """Raised when persistent pillar state cannot be trusted."""


class PillarStatus(str, Enum):
    """Truthful lifecycle states shared with JAYA governance."""

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    IDEA = "IDEA"
    PLANNED = "PLANNED"
    PROTOTYPE = "PROTOTYPE"
    IMPLEMENTED_LOCAL = "IMPLEMENTED_LOCAL"
    INTEGRATED = "INTEGRATED"
    VERIFIED = "VERIFIED"
    PRODUCTION = "PRODUCTION"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    FAILED = "FAILED"


_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "pillar_id",
        "name",
        "layer",
        "architectural_owners",
        "status",
        "source_flag",
        "dependencies",
        "capability_id",
        "description",
        "model_role",
        "runtime_role",
        "schema_version",
    }
)


def canonical_pillar_id(value: object) -> tuple[str, int | None]:
    """Normalize legacy numeric IDs and new stable catalog IDs."""

    if isinstance(value, bool):
        raise PillarValidationError("INVALID_PILLAR_ID", "pillar id must be numeric or P-prefixed")
    if isinstance(value, int):
        if not 1 <= value <= 999_999:
            raise PillarValidationError("INVALID_PILLAR_ID", "numeric pillar id is outside the supported range")
        return f"P{value:03d}", value
    text = str(value or "").strip().upper()
    if not _PILLAR_ID.fullmatch(text):
        raise PillarValidationError("INVALID_PILLAR_ID", "pillar id must match P followed by 3-6 digits")
    numeric = int(text[1:])
    if numeric < 1:
        raise PillarValidationError("INVALID_PILLAR_ID", "pillar id must be positive")
    return text, numeric


def _bounded_text(value: object, field: str, *, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise PillarValidationError("INVALID_FIELD", f"{field} must be text")
    normalized = " ".join(value.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise PillarValidationError(
            "INVALID_FIELD",
            f"{field} must contain {minimum}-{maximum} characters",
        )
    return normalized


def _identifier_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PillarValidationError("INVALID_FIELD", f"{field} must be a list")
    if not 1 <= len(value) <= 16:
        raise PillarValidationError("INVALID_FIELD", f"{field} must contain 1-16 entries")
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip().upper()
        if not _ARCHITECTURE_ID.fullmatch(text):
            raise PillarValidationError("INVALID_FIELD", f"{field} contains an invalid identifier")
        if text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _role_list(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PillarValidationError("INVALID_FIELD", f"{field} must be a list")
    if len(value) > 32:
        raise PillarValidationError("INVALID_FIELD", f"{field} exceeds 32 entries")
    roles: list[str] = []
    for item in value:
        role = str(item or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", role):
            raise PillarValidationError("INVALID_FIELD", f"{field} contains an invalid role")
        if role not in roles:
            roles.append(role)
    return tuple(roles)


@dataclass(frozen=True, slots=True)
class PillarDefinition:
    """Immutable architecture definition; lifecycle state is stored separately."""

    pillar_id: str
    legacy_id: int | None
    name: str
    layer: str
    architectural_owners: tuple[str, ...]
    initial_status: PillarStatus
    dependencies: tuple[str, ...] = ()
    capability_id: str | None = None
    source_flag: str | None = None
    description: str = ""
    model_roles: tuple[str, ...] = ()
    runtime_roles: tuple[str, ...] = ()
    schema_version: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PillarDefinition:
        if not isinstance(value, Mapping):
            raise PillarValidationError("INVALID_PILLAR", "pillar entry must be an object")
        unknown = sorted(set(value) - _ALLOWED_FIELDS)
        if unknown:
            raise PillarValidationError("UNKNOWN_FIELD", f"unknown pillar fields: {', '.join(unknown)}")
        raw_id = value.get("pillar_id", value.get("id"))
        pillar_id, numeric_id = canonical_pillar_id(raw_id)
        name = _bounded_text(value.get("name"), "name", minimum=3, maximum=120)
        layer = str(value.get("layer") or "").strip().upper()
        if not _ARCHITECTURE_ID.fullmatch(layer):
            raise PillarValidationError("INVALID_FIELD", "layer must be an uppercase architecture identifier")
        owners = _identifier_list(value.get("architectural_owners"), "architectural_owners")
        try:
            status = PillarStatus(str(value.get("status") or "").strip().upper())
        except ValueError as exc:
            raise PillarValidationError("INVALID_STATUS", "pillar status is not recognized") from exc

        raw_dependencies = value.get("dependencies", ())
        if not isinstance(raw_dependencies, Sequence) or isinstance(raw_dependencies, (str, bytes)):
            raise PillarValidationError("INVALID_FIELD", "dependencies must be a list")
        if len(raw_dependencies) > 64:
            raise PillarValidationError("INVALID_FIELD", "dependencies exceed 64 entries")
        dependencies = tuple(dict.fromkeys(canonical_pillar_id(item)[0] for item in raw_dependencies))
        if pillar_id in dependencies:
            raise PillarValidationError("SELF_DEPENDENCY", "a pillar cannot depend on itself")

        source_flag_value = value.get("source_flag")
        source_flag = None if source_flag_value in (None, "") else str(source_flag_value).strip()
        if source_flag is not None and not _SOURCE_FLAG.fullmatch(source_flag):
            raise PillarValidationError("INVALID_SOURCE_FLAG", "source_flag must reference JayaFlags")
        if source_flag is not None and (numeric_id is None or numeric_id > 40):
            raise PillarValidationError(
                "DYNAMIC_FLAG_FORBIDDEN",
                "dynamic pillars must not allocate legacy JayaFlags bits",
            )

        capability_value = value.get("capability_id")
        capability_id = None if capability_value in (None, "") else str(capability_value).strip()
        if capability_id is not None and not _CAPABILITY_ID.fullmatch(capability_id):
            raise PillarValidationError("INVALID_CAPABILITY_ID", "capability_id has an invalid format")

        description_value = value.get("description", "")
        description = "" if description_value in (None, "") else _bounded_text(
            description_value,
            "description",
            minimum=3,
            maximum=2_000,
        )
        schema_version = value.get("schema_version", 1)
        if isinstance(schema_version, bool) or schema_version != 1:
            raise PillarValidationError("UNSUPPORTED_SCHEMA", "only pillar schema version 1 is supported")
        return cls(
            pillar_id=pillar_id,
            legacy_id=numeric_id if numeric_id is not None and numeric_id <= 40 else None,
            name=name,
            layer=layer,
            architectural_owners=owners,
            initial_status=status,
            dependencies=dependencies,
            capability_id=capability_id,
            source_flag=source_flag,
            description=description,
            model_roles=_role_list(value.get("model_role"), "model_role"),
            runtime_roles=_role_list(value.get("runtime_role"), "runtime_role"),
            schema_version=1,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pillar_id": self.pillar_id,
            "legacy_id": self.legacy_id,
            "name": self.name,
            "layer": self.layer,
            "architectural_owners": list(self.architectural_owners),
            "initial_status": self.initial_status.value,
            "dependencies": list(self.dependencies),
            "capability_id": self.capability_id,
            "source_flag": self.source_flag,
            "description": self.description,
            "model_roles": list(self.model_roles),
            "runtime_roles": list(self.runtime_roles),
            "schema_version": self.schema_version,
        }

    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PillarRecord:
    definition: PillarDefinition
    status: PillarStatus
    revision: int
    origin: str
    evidence_refs: tuple[str, ...]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        payload = self.definition.to_dict()
        payload.update(
            {
                "status": self.status.value,
                "revision": self.revision,
                "origin": self.origin,
                "evidence_refs": list(self.evidence_refs),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )
        return payload


def validate_reference(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_REFERENCE.fullmatch(normalized):
        raise PillarValidationError("INVALID_REFERENCE", f"{field} contains an unsafe reference")
    return normalized


def definition_from_storage(value: Mapping[str, Any]) -> PillarDefinition:
    """Rebuild a definition from the canonical stored representation."""

    adapted = {
        "pillar_id": value["pillar_id"],
        "name": value["name"],
        "layer": value["layer"],
        "architectural_owners": value["architectural_owners"],
        "status": value["initial_status"],
        "dependencies": value.get("dependencies", []),
        "capability_id": value.get("capability_id"),
        "source_flag": value.get("source_flag"),
        "description": value.get("description", ""),
        "model_role": value.get("model_roles", []),
        "runtime_role": value.get("runtime_roles", []),
        "schema_version": value.get("schema_version", 1),
    }
    return PillarDefinition.from_mapping(adapted)
