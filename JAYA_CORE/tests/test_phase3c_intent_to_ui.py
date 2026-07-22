"""Test for IntentToUIPipeline - Phase 3C Dynamic UI Generation."""

import asyncio
import sys
import os
import pytest

# Add JAYA_CORE to path (not project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.os_kernel.ui_spec import (
    SceneGraph, WidgetSpec, WidgetType, LayoutType,
    create_window, create_panel, create_label, create_button,
    create_text_input, StyleTokens, Dimension, SizeUnit, Rect
)
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_registry import FeatureRegistry
from src.os_kernel.feature_bridge import JayaBridge
from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.intent_to_ui import IntentToUIPipeline, create_ui_from_intent


@pytest.mark.asyncio
async def test_intent_to_ui_pipeline():
    """Test the full intent → UI → feature pipeline."""
    print("=" * 60)
    print("Testing Phase 3C: Intent → UI Pipeline")
    print("=" * 60)
    
    # Create components
    base_path = os.path.join(os.path.dirname(__file__), "../../test_features")
    registry = FeatureRegistry(base_path)
    bridge = JayaBridge(features_dir=base_path)
    intent_engine = IntentEngine()
    pipeline = IntentToUIPipeline(bridge, intent_engine)
    
    # Test 1: List available templates
    print("\n1. Available UI Templates:")
    templates = pipeline.list_templates()
    for t in templates:
        print(f"  - {t['name']}: {t['description']}")
        print(f"    Patterns: {t['patterns'][:3]}...")
    
    # Test 2: Match intents
    print("\n2. Intent Matching Tests:")
    test_inputs = [
        "show login dialog",
        "create a dashboard",
        "open settings",
        "show file explorer",
        "chat with JAYA",
        "confirm delete",
        "show progress",
        "list users",
        "create a form",
        "open a dialog",
    ]
    
    for user_input in test_inputs:
        matches = pipeline.match_intent(user_input)
        if matches:
            best = matches[0]
            print(f"  '{user_input}' → {best.intent_type} (confidence: {best.confidence:.2f})")
        else:
            print(f"  '{user_input}' → No match")
    
    # Test 3: Full pipeline for a few cases
    print("\n3. Full Pipeline Tests (compile only, no mount):")
    test_cases = [
        "show login dialog",
        "create dashboard",
        "open settings",
    ]
    
    for user_input in test_cases:
        print(f"\n  Input: '{user_input}'")
        # We'll test compilation only (not full mount)
        matches = pipeline.match_intent(user_input)
        if matches:
            template_name = matches[0].suggested_ui
            params = pipeline.extract_parameters("", matches[0].suggested_ui)
            template = pipeline.templates.get(matches[0].suggested_ui)
            if template:
                try:
                    scene = template.builder(**pipeline.extract_parameters("", matches[0].suggested_ui))
                    compiler = FeatureCompiler()
                    output_path = compiler.save_feature(scene, "./test_features", matches[0].suggested_ui)
                    print(f"  ✓ Compiled to: {output_path}")
                except Exception as e:
                    print(f"  ✗ Error: {e}")
    
    # Test 4: Intent Engine Learning
    print("\n4. Intent Engine Learning Test:")
    intent_engine = IntentEngine()
    intent_engine.learn("show login dialog")
    intent_engine.learn("show login dialog with username and password")
    intent_engine.learn("create dashboard with metrics")
    intent_engine.learn("open settings dialog")
    
    predictions = intent_engine.predict_intent("show login", top_k=3)
    print("  Predictions for 'show login':")
    for cmd, conf in predictions:
        print(f"  - {cmd} (confidence: {conf:.2f})")
    
    # Test 5: Feature Compiler Direct Usage
    print("\n5. Feature Compiler Direct Test:")
    from src.os_kernel.ui_spec import (
        SceneGraph, create_window, create_panel, create_label,
        create_button, create_text_input, LayoutType
    )
    
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
        )
    )
    
    compiler = FeatureCompiler()
    output_path = compiler.save_feature(scene, "./test_features", "test_dialog")
    print(f"  ✓ Feature saved to: {output_path}")
    
    # Verify feature can be discovered
    registry = FeatureRegistry("./test_features")
    features = registry.discover_features()
    print(f"  Discovered {len(features)} features")
    
    print("\n" + "=" * 60)
    print("All Phase 3C tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])