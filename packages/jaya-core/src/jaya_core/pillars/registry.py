"""Application service for a dynamic, non-executable pillar catalog."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .manifest import load_manifest, validate_catalog
from .models import (
    PillarDefinition,
    PillarRecord,
    PillarStatus,
    PillarValidationError,
    canonical_pillar_id,
)
from .repository import PillarRepository

_MATURITY = {
    PillarStatus.NOT_IMPLEMENTED: 0,
    PillarStatus.IDEA: 1,
    PillarStatus.PLANNED: 2,
    PillarStatus.PROTOTYPE: 3,
    PillarStatus.IMPLEMENTED_LOCAL: 4,
    PillarStatus.INTEGRATED: 5,
    PillarStatus.VERIFIED: 6,
    PillarStatus.PRODUCTION: 7,
    PillarStatus.BLOCKED_EXTERNAL: -1,
    PillarStatus.FAILED: -2,
}


class DynamicPillarRegistry:
    """Validated facade over manifests and the durable pillar repository."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        manifest_paths: Iterable[str | Path],
    ) -> None:
        resolved_paths = tuple(Path(path).expanduser().resolve() for path in manifest_paths)
        if not resolved_paths:
            raise PillarValidationError("MANIFEST_REQUIRED", "at least one pillar manifest is required")
        definitions_by_origin: list[tuple[PillarDefinition, str]] = []
        catalog: list[PillarDefinition] = []
        for path in resolved_paths:
            definitions = load_manifest(path)
            origin = f"baseline:{path.name}"
            definitions_by_origin.extend((definition, origin) for definition in definitions)
            catalog.extend(definitions)
        validate_catalog(catalog, require_resolved_dependencies=True)
        self.repository = PillarRepository(database_path)
        self.repository.seed(definitions_by_origin)

    def health_check(self) -> bool:
        return self.repository.health_check() and bool(self.repository.list())

    def list(self) -> tuple[PillarRecord, ...]:
        return self.repository.list()

    def get(self, pillar_id: str | int) -> PillarRecord:
        return self.repository.get(canonical_pillar_id(pillar_id)[0])

    def register_candidate(
        self,
        definition: PillarDefinition,
        *,
        origin: str,
        idempotency_key: str,
        actor: str,
    ) -> tuple[PillarRecord, bool]:
        current = self.repository.list()
        existing = next(
            (item for item in current if item.definition.pillar_id == definition.pillar_id),
            None,
        )
        if existing is None:
            validate_catalog(
                [item.definition for item in current] + [definition],
                require_resolved_dependencies=True,
            )
        return self.repository.register_candidate(
            definition,
            origin=origin,
            idempotency_key=idempotency_key,
            actor=actor,
        )

    def register_candidate_file(
        self,
        path: str | Path,
        *,
        idempotency_key: str,
        actor: str,
    ) -> tuple[PillarRecord, bool]:
        source = Path(path).expanduser().resolve()
        definitions = load_manifest(source)
        if len(definitions) != 1:
            raise PillarValidationError(
                "SINGLE_CANDIDATE_REQUIRED",
                "candidate registration accepts exactly one pillar per request",
            )
        return self.register_candidate(
            definitions[0],
            origin=f"candidate:{source.name}",
            idempotency_key=idempotency_key,
            actor=actor,
        )

    def transition_status(
        self,
        pillar_id: str | int,
        target: PillarStatus,
        *,
        expected_revision: int,
        evidence_refs: Sequence[str],
        actor: str,
        approval_reference: str | None = None,
    ) -> PillarRecord:
        record = self.get(pillar_id)
        if _MATURITY[target] >= _MATURITY[PillarStatus.IMPLEMENTED_LOCAL]:
            by_id = {item.definition.pillar_id: item for item in self.list()}
            unavailable = [
                dependency
                for dependency in record.definition.dependencies
                if dependency not in by_id
                or _MATURITY[by_id[dependency].status]
                < _MATURITY[PillarStatus.IMPLEMENTED_LOCAL]
            ]
            if unavailable:
                raise PillarValidationError(
                    "DEPENDENCY_NOT_IMPLEMENTED",
                    f"pillar dependencies are not implemented: {', '.join(unavailable)}",
                )
        return self.repository.transition_status(
            record.definition.pillar_id,
            target,
            expected_revision=expected_revision,
            evidence_refs=evidence_refs,
            actor=actor,
            approval_reference=approval_reference,
        )

    def events(self, pillar_id: str | int) -> tuple[dict[str, Any], ...]:
        return self.repository.events(canonical_pillar_id(pillar_id)[0])

    def catalog_snapshot(self) -> dict[str, Any]:
        records = self.list()
        statuses = Counter(record.status.value for record in records)
        return {
            "ready": self.health_check(),
            "total": len(records),
            "canonical_40_present": all(
                any(item.definition.pillar_id == f"P{number:03d}" for item in records)
                for number in range(1, 41)
            ),
            "dynamic_total": sum(
                1
                for item in records
                if item.definition.legacy_id is None
            ),
            "status_counts": dict(sorted(statuses.items())),
            "pillars": [item.to_dict() for item in records],
        }
