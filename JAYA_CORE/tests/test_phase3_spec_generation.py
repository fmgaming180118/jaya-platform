"""
test_phase3_spec_generation.py — Integration tests for Phase 3 Brain-Side Spec Generation in JAYA_CORE
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.os_kernel.intent_to_ui import IntentMatch
from src.brain_v2.engine.spec_generators import (
    SpecBundle, FeatureManifest, UITemplateRegistry, UISpecGenerator,
    FeatureSpecGenerator, TaskSpecGenerator, ActionSpecGenerator,
    SpecGeneratorRouter, ExecutionPlan, ActionSpec
)
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_registry import FeatureRegistry
from src.os_kernel.feature_bridge import JayaBridge


def test_ui_template_registry():
    """Test that all 10 built-in UI templates are properly registered and build SceneGraphs."""
    registry = UITemplateRegistry()
    templates = registry.list_templates()
    assert len(templates) >= 10, f"Expected at least 10 UI templates, got {len(templates)}"

    expected_names = [
        "login_dialog", "dashboard", "settings_dialog", "file_explorer",
        "chat_interface", "confirm_dialog", "progress_dialog", "list_view",
        "form", "generic_dialog"
    ]

    for name in expected_names:
        tmpl = registry.get(name)
        assert tmpl is not None, f"Template {name} missing"
        scene = tmpl["builder"](title=f"Test {name}")
        assert scene is not None
        assert scene.root is not None
        assert scene.root.type in ["window", "WINDOW"]


def test_ui_spec_generator():
    """Test UISpecGenerator creating SpecBundle containing SceneGraph."""
    gen = UISpecGenerator()
    intent = IntentMatch(
        intent_type="show_login",
        confidence=0.95,
        suggested_ui="login_dialog",
        parameters={"title": "Custom Login"}
    )

    assert gen.can_handle(intent)
    bundle = gen.generate(intent)
    assert isinstance(bundle, SpecBundle)
    assert bundle.ui_spec is not None
    assert bundle.ui_spec.name == "Login Dialog"
    assert bundle.ui_spec.root is not None


def test_feature_spec_generator():
    """Test FeatureSpecGenerator creating FeatureManifest specs."""
    gen = FeatureSpecGenerator()
    intent = IntentMatch(
        intent_type="run_analysis",
        confidence=0.90,
        suggested_ui=None,
        parameters={"dataset": "academic_qa"}
    )

    assert gen.can_handle(intent)
    bundle = gen.generate(intent)
    assert bundle.feature_spec is not None
    assert isinstance(bundle.feature_spec, FeatureManifest)
    assert bundle.feature_spec.name == "analysis_module"
    assert "fs_read" in bundle.feature_spec.permissions


def test_task_spec_generator():
    """Test TaskSpecGenerator creating ExecutionPlan DAG specs."""
    gen = TaskSpecGenerator()
    intent = IntentMatch(
        intent_type="compute_qlora_loss",
        confidence=0.88,
        suggested_ui=None,
        parameters={"batch_size": 16}
    )

    assert gen.can_handle(intent)
    bundle = gen.generate(intent)
    assert bundle.task_spec is not None
    assert isinstance(bundle.task_spec, ExecutionPlan)
    assert len(bundle.task_spec.steps) == 3
    assert bundle.task_spec.estimated_latency_ms > 0.0


def test_action_spec_generator():
    """Test ActionSpecGenerator creating ActionSpec IPC specs."""
    gen = ActionSpecGenerator()
    intent = IntentMatch(
        intent_type="status",
        confidence=0.99,
        suggested_ui=None,
        parameters={}
    )

    assert gen.can_handle(intent)
    bundle = gen.generate(intent)
    assert bundle.action_spec is not None
    assert isinstance(bundle.action_spec, ActionSpec)
    assert bundle.action_spec.channel == "observability"
    assert bundle.action_spec.action == "get_status"


def test_spec_generator_router():
    """Test SpecGeneratorRouter combining multi-spec bundles."""
    router = SpecGeneratorRouter()
    intent = IntentMatch(
        intent_type="run_analysis",
        confidence=0.92,
        suggested_ui="dashboard",
        parameters={"title": "Analysis Dashboard"}
    )

    bundle = router.route(intent)
    assert not bundle.is_empty()
    assert bundle.ui_spec is not None
    assert bundle.feature_spec is not None


@pytest.mark.asyncio
async def test_brain_to_house_end_to_end(tmp_path):
    """End-to-end integration: Brain SpecGeneratorRouter -> SpecBundle -> House FeatureCompiler & JayaBridge."""
    test_dir = str(tmp_path)
    router = SpecGeneratorRouter()

    # 1. Brain generates UI spec bundle
    intent = IntentMatch(
        intent_type="open_settings",
        confidence=0.94,
        suggested_ui="settings_dialog",
        parameters={"title": "Sovereign Settings"}
    )
    bundle = router.route(intent)
    assert bundle.ui_spec is not None

    # 2. House compiles UI spec into feature package
    from src.os_kernel.ui_spec import create_window as house_create_window, SceneGraph as HouseSceneGraph
    house_scene = HouseSceneGraph(
        name=bundle.ui_spec.name,
        description=bundle.ui_spec.description,
        root=house_create_window(title="Settings Dialog", width="500px", height="400px")
    )
    compiler = FeatureCompiler()
    feature_dir = compiler.save_feature(house_scene, test_dir, "settings_dialog")
    assert os.path.exists(feature_dir)

    # 3. House registers and mounts feature via JayaBridge
    registry = FeatureRegistry(test_dir)
    features = registry.discover_features()
    target_feature = next(f for f in features if f.name == "Settings Dialog")
    assert target_feature is not None

    bridge = JayaBridge(features_dir=test_dir)
    from src.os_kernel.feature_bridge import BridgeAction
    resp = await bridge.dispatch(BridgeAction.MOUNT_FEATURE, {"feature_id": target_feature.id})
    assert resp.success is True, f"Mount failed: {resp.error}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
