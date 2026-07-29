"""Tests for the Phase 3C intent-to-UI pipeline without workspace writes."""

from __future__ import annotations

import json
from pathlib import Path

from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_registry import FeatureRegistry
from src.os_kernel.intent_to_ui import IntentToUIPipeline
from src.os_kernel.ui_spec import (
    LayoutType,
    SceneGraph,
    create_button,
    create_label,
    create_panel,
    create_window,
)


def test_intent_to_ui_pipeline_uses_isolated_output(tmp_path: Path) -> None:
    feature_root = tmp_path / "features"
    registry = FeatureRegistry(str(feature_root))
    bridge = JayaBridge(features_dir=str(feature_root))
    intent_engine = IntentEngine()
    pipeline = IntentToUIPipeline(bridge, intent_engine)

    templates = pipeline.list_templates()
    assert templates
    assert {item["name"] for item in templates} >= {
        "login_dialog",
        "dashboard",
        "settings_dialog",
    }

    for prompt, expected_template in (
        ("show login dialog", "login_dialog"),
        ("create a dashboard", "dashboard"),
        ("open settings", "settings_dialog"),
    ):
        matches = pipeline.match_intent(prompt)
        assert matches
        assert matches[0].suggested_ui == expected_template
        template = pipeline.templates[expected_template]
        parameters = pipeline.extract_parameters(prompt, expected_template)
        scene = template.builder(**parameters)
        output_path = Path(
            FeatureCompiler().save_feature(
                scene,
                str(feature_root),
                expected_template,
            )
        ).resolve()
        assert output_path.is_relative_to(feature_root.resolve())
        assert output_path.is_file()

    discovered = registry.discover_features()
    assert len(discovered) == 3


def test_intent_engine_learns_without_global_state() -> None:
    engine = IntentEngine()
    engine.learn("show login dialog")
    engine.learn("show login dialog with username and password")
    engine.learn("create dashboard with metrics")

    predictions = engine.predict_intent("show login", top_k=3)
    assert predictions
    assert predictions[0][1] > 0


def test_feature_compiler_emits_consistent_manifest(tmp_path: Path) -> None:
    scene = SceneGraph(
        name="Test Dialog",
        description="Test dialog for compiler",
        root=create_window(
            title="Test",
            width="400px",
            height="300px",
            children=[
                create_panel(
                    layout=LayoutType.FLEX_COL,
                    children=[
                        create_label("Hello World"),
                        create_button(label="Click Me", on_click="jaya:run_task"),
                    ],
                ),
            ],
        ),
    )

    source_path = Path(
        FeatureCompiler().save_feature(
            scene,
            str(tmp_path),
            "test_dialog",
        )
    )
    manifest_path = source_path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert source_path.is_file()
    assert manifest["name"] == "test_dialog"
    assert manifest["entry_point"] == "run_feature"
    assert manifest["id"]