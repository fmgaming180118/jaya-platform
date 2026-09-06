"""Contract checks for generated OS feature fixtures."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "test_features"


@pytest.mark.parametrize(
    "feature_name",
    ("dashboard", "login_dialog", "settings_dialog", "test_dialog"),
)
def test_generated_feature_exports_manifest_matching_registry(
    feature_name: str,
) -> None:
    feature_dir = FIXTURE_ROOT / feature_name
    source_path = feature_dir / f"{feature_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"jaya_os_fixture_{feature_name}",
        source_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generated = module.feature_manifest()
    persisted = json.loads(
        (feature_dir / "manifest.json").read_text(encoding="utf-8")
    )

    assert generated["id"] == persisted["id"]
    assert generated["version"] == persisted["version"]
    assert generated["description"] == persisted["description"]
    assert generated["protocol_version"] == persisted["protocol_version"]
    assert generated["entry_point"] == "run_feature"
    assert set(generated["capabilities"]) == set(persisted["capabilities"])
    assert set(generated["permissions"]) == set(persisted["permissions"])

