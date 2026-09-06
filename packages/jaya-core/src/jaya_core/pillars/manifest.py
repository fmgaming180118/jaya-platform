"""Bounded YAML/JSON loading and whole-catalog validation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from .models import PillarDefinition, PillarValidationError

DEFAULT_MAX_MANIFEST_BYTES = 1_048_576
_ROOT_FIELDS = frozenset({"schema_version", "manifest_version", "name", "pillars"})


def _manifest_payload(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        unknown = sorted(set(value) - _ROOT_FIELDS)
        if unknown:
            raise PillarValidationError("UNKNOWN_MANIFEST_FIELD", f"unknown manifest fields: {', '.join(unknown)}")
        if value.get("schema_version", 1) != 1:
            raise PillarValidationError("UNSUPPORTED_SCHEMA", "only manifest schema version 1 is supported")
        value = value.get("pillars")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PillarValidationError("INVALID_MANIFEST", "manifest must contain a pillar list")
    if not 1 <= len(value) <= 10_000:
        raise PillarValidationError("INVALID_MANIFEST", "manifest must contain 1-10000 pillars")
    result: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise PillarValidationError("INVALID_MANIFEST", "every pillar entry must be an object")
        result.append(item)
    return result


def load_manifest(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
) -> tuple[PillarDefinition, ...]:
    source = Path(path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise PillarValidationError("MANIFEST_NOT_FOUND", "pillar manifest is unavailable")
    if source.suffix.casefold() not in {".yaml", ".yml", ".json"}:
        raise PillarValidationError("UNSUPPORTED_MANIFEST", "pillar manifest must be YAML or JSON")
    try:
        size = source.stat().st_size
        if size <= 0 or size > max_bytes:
            raise PillarValidationError("MANIFEST_SIZE_INVALID", "pillar manifest size is outside the configured limit")
        text = source.read_text(encoding="utf-8")
        raw = json.loads(text) if source.suffix.casefold() == ".json" else yaml.safe_load(text)
    except PillarValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise PillarValidationError("MANIFEST_INVALID", "pillar manifest could not be parsed") from exc
    definitions = tuple(PillarDefinition.from_mapping(item) for item in _manifest_payload(raw))
    validate_catalog(definitions, require_resolved_dependencies=False)
    return definitions


def load_manifests(paths: Iterable[str | Path]) -> tuple[PillarDefinition, ...]:
    definitions: list[PillarDefinition] = []
    for path in paths:
        definitions.extend(load_manifest(path))
    validate_catalog(definitions, require_resolved_dependencies=True)
    return tuple(definitions)


def validate_catalog(
    definitions: Iterable[PillarDefinition],
    *,
    require_resolved_dependencies: bool = True,
) -> None:
    items = tuple(definitions)
    by_id: dict[str, PillarDefinition] = {}
    names: set[str] = set()
    for definition in items:
        if definition.pillar_id in by_id:
            raise PillarValidationError("DUPLICATE_PILLAR_ID", "pillar catalog contains duplicate IDs")
        normalized_name = definition.name.casefold()
        if normalized_name in names:
            raise PillarValidationError("DUPLICATE_PILLAR_NAME", "pillar catalog contains duplicate names")
        by_id[definition.pillar_id] = definition
        names.add(normalized_name)
    if require_resolved_dependencies:
        missing = sorted(
            dependency
            for definition in items
            for dependency in definition.dependencies
            if dependency not in by_id
        )
        if missing:
            raise PillarValidationError("MISSING_DEPENDENCY", f"unresolved pillar dependencies: {', '.join(dict.fromkeys(missing))}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(pillar_id: str) -> None:
        if pillar_id in visited or pillar_id not in by_id:
            return
        if pillar_id in visiting:
            raise PillarValidationError("DEPENDENCY_CYCLE", "pillar dependency graph contains a cycle")
        visiting.add(pillar_id)
        for dependency in by_id[pillar_id].dependencies:
            visit(dependency)
        visiting.remove(pillar_id)
        visited.add(pillar_id)

    for pillar_id in by_id:
        visit(pillar_id)
