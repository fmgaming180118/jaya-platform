"""Tests for the Phase 3C intent-to-UI pipeline without workspace writes."""

from __future__ import annotations

import json
from pathlib import Path

from jaya_core.brain_v2.engine.intent_engine import IntentEngine
from jaya_core.os_kernel.feature_bridge import JayaBridge
from jaya_core.os_kernel.feature_compiler import FeatureCompiler
from jaya_core.os_kernel.feature_registry import FeatureRegistry
from jaya_core.os_kernel.feature_runtime import (
    ButtonWidget,
    EventBus,
    FeatureRuntime,
    create_standard_dispatcher,
)
from jaya_core.os_kernel.intent_to_ui import IntentToUIPipeline
from jaya_core.os_kernel.ui_spec import (
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
        assert output_path.is_dir()
        assert (output_path / f"{expected_template}.py").is_file()
        assert (output_path / "manifest.json").is_file()

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
    assert scene.root.rect is not None
    scene.root.rect.width = None
    scene.root.metadata["boolean_literal_probe"] = True

    feature_path = Path(
        FeatureCompiler().save_feature(
            scene,
            str(tmp_path),
            "test_dialog",
        )
    )
    source_path = feature_path / "test_dialog.py"
    manifest_path = feature_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8")
    compile(source, str(source_path), "exec")
    assert "null" not in source
    assert manifest["name"] == scene.name
    assert manifest["entry_point"] == "test_dialog.run_feature"
    assert manifest["id"] == scene.id
class _BindingButton(ButtonWidget):
    def __init__(self, widget_id: str) -> None:
        super().__init__(widget_id=widget_id, label=widget_id)
        self.applied_state: dict[str, object] | None = None

    def apply_bindings(self, state: dict[str, object]) -> None:
        self.applied_state = dict(state)


def test_feature_runtime_applies_bindings_and_stops_without_factory_side_effect(
) -> None:
    root = _BindingButton("root")
    child = _BindingButton("child")
    root.add_child(child)
    runtime = FeatureRuntime(
        feature_id="feature-1",
        feature_name="binding-test",
        mount_point="body",
        root_widget=root,
        event_bus=EventBus(),
    )
    root.mount()

    runtime.update_state({"count": 1})
    assert root.applied_state == {"count": 1}
    assert child.applied_state == {"count": 1}

    result = runtime.stop()
    assert result is None
    assert runtime.status == "stopped"

def test_ui_runtime_never_fabricates_external_side_effects() -> None:
    root = _BindingButton("root")
    runtime = FeatureRuntime(
        feature_id="feature-2",
        feature_name="external-action-test",
        mount_point="body",
        root_widget=root,
        event_bus=EventBus(),
    )
    dispatcher = create_standard_dispatcher(runtime)

    for action in (
        "jaya:save_file",
        "jaya:load_file",
        "jaya:copy_to_clipboard",
        "jaya:navigate",
        "jaya:open_url",
    ):
        result = dispatcher.dispatch(action, {"path": "ignored"})
        assert result == {
            "success": False,
            "error_code": "ACTION_ADAPTER_UNAVAILABLE",
            "action": action,
            "message": "A capability-authorized OS adapter is required",
        }
