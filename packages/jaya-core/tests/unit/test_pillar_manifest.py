from pathlib import Path

import pytest

from jaya_core.pillars import PillarDefinition, PillarValidationError, load_manifest
from jaya_core.pillars.manifest import validate_catalog

ROOT = Path(__file__).resolve().parents[4]
BASELINE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "src"
    / "jaya_core"
    / "contracts"
    / "40_pillars.yaml"
)
CANDIDATE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "examples"
    / "pillar-041-adaptive-evidence.yaml"
)


def test_baseline_contains_the_stable_40_and_runtime_binding() -> None:
    definitions = load_manifest(BASELINE)

    assert len(definitions) == 40
    assert {item.pillar_id for item in definitions} == {
        f"P{number:03d}" for number in range(1, 41)
    }
    pure_logic = next(item for item in definitions if item.pillar_id == "P001")
    assert pure_logic.source_flag == "JayaFlags.PURE_LOGIC"
    assert pure_logic.capability_id == "core.logic.evaluate"


def test_future_pillar_is_not_forced_into_legacy_binary_flags() -> None:
    definition = load_manifest(CANDIDATE)[0]

    assert definition.pillar_id == "P041"
    assert definition.legacy_id is None
    assert definition.source_flag is None


def test_dynamic_pillar_cannot_allocate_a_jaya_flag() -> None:
    with pytest.raises(PillarValidationError) as error:
        PillarDefinition.from_mapping(
            {
                "id": 41,
                "name": "Unsafe Future Flag",
                "layer": "TRANSCENDENTAL",
                "architectural_owners": ["RUNTIME"],
                "status": "IDEA",
                "source_flag": "JayaFlags.UNSAFE_FUTURE_FLAG",
            }
        )

    assert error.value.code == "DYNAMIC_FLAG_FORBIDDEN"


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(PillarValidationError) as error:
        PillarDefinition.from_mapping(
            {
                "id": 41,
                "name": "Unknown Field Pillar",
                "layer": "TRANSCENDENTAL",
                "architectural_owners": ["RUNTIME"],
                "status": "IDEA",
                "auto_activate": True,
            }
        )

    assert error.value.code == "UNKNOWN_FIELD"


def test_missing_dependencies_and_cycles_fail_closed() -> None:
    first = PillarDefinition.from_mapping(
        {
            "id": 41,
            "name": "Cycle Alpha",
            "layer": "TRANSCENDENTAL",
            "architectural_owners": ["RUNTIME"],
            "status": "IDEA",
            "dependencies": [42],
        }
    )
    second = PillarDefinition.from_mapping(
        {
            "id": 42,
            "name": "Cycle Beta",
            "layer": "TRANSCENDENTAL",
            "architectural_owners": ["RUNTIME"],
            "status": "IDEA",
            "dependencies": [41],
        }
    )

    with pytest.raises(PillarValidationError) as cycle:
        validate_catalog([first, second])
    assert cycle.value.code == "DEPENDENCY_CYCLE"

    with pytest.raises(PillarValidationError) as missing:
        validate_catalog([first])
    assert missing.value.code == "MISSING_DEPENDENCY"
