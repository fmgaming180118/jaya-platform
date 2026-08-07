"""
test_nlu_symbolic_bridge_unit.py — Targeted Unit Tests for NLU Symbolic Bridge P0 Fixes.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from JAYA_CORE.src.ai_connectors.cognitive_model_adapter import CognitiveModelAdapter, CognitiveResponse
from JAYA_CORE.src.cognitive.contracts import Intent, IntentType
from JAYA_CORE.src.nlu.symbolic_bridge import (
    NLUSymbolicBridge,
    NLUResult,
    SymbolicPlan,
    ClarificationNeeded,
    create_nlu_symbolic_bridge,
)
from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
from JAYA_CORE.src.reasoning.symbolic_reasoner import SymbolicReasoner, ResourceProfile
from JAYA_CORE.src.reasoning.constraint_solver import ConstraintSolver
from JAYA_CORE.src.reasoning.logic_engine import LogicEngine
from JAYA_CORE.src.cognitive.planner import GenericHierarchicalPlanner


def test_cognitive_model_adapter_accepts_temperature():
    """Test P0.1: CognitiveModelAdapter.generate accepts temperature without TypeError."""
    adapter = CognitiveModelAdapter(enable_cloud=False)
    # Call generate with temperature=0.1
    response = adapter.generate(
        prompt="Test prompt",
        temperature=0.1,
        force_local=True,
    )
    assert isinstance(response, CognitiveResponse)
    assert response.source in ["local_llm", "fallback_rule_based"]


def test_intent_creation_contains_all_required_fields():
    """Test P0.2: Intent contract requires intent_id, intent_type, domain, confidence."""
    intent = Intent(
        intent_id="intent-1234",
        intent_type=IntentType.CREATE_PLAN,
        domain="planning",
        confidence=0.9,
    )
    assert intent.intent_id == "intent-1234"
    assert intent.intent_type == IntentType.CREATE_PLAN
    assert intent.domain == "planning"
    assert intent.confidence == 0.9

    d = intent.to_dict()
    assert d["intent_id"] == "intent-1234"
    assert d["intent_type"] == "CREATE_PLAN"
    assert d["domain"] == "planning"


def test_nlu_bridge_structured_json_with_mock_nlu():
    """Test P0.1 & P0.2 & P0.4: Structured LLM output parsing, Intent creation, schema validation."""
    mock_nlu = MagicMock(spec=CognitiveModelAdapter)
    mock_nlu.is_local_available.return_value = True
    mock_nlu.is_cloud_available.return_value = False

    llm_json_output = json.dumps({
        "intent": "CREATE_PLAN",
        "confidence": 0.95,
        "entities": {"TOPIC": ["Python"], "DURATION": ["30 hari"]},
        "slots": {"topic": "Python", "duration": "30 hari"},
        "constraints": {"max_hours": 10},
        "relations": [{"subject": "Python", "predicate": "learn", "object": "course"}],
        "ambiguity": [],
        "alternative_intents": [{"intent": "ASK_INFORMATION", "confidence": 0.05}],
    })

    mock_nlu.generate.return_value = CognitiveResponse(
        text=llm_json_output,
        source="local_llm",
        model_used="mock_model",
        confidence=0.95,
        metadata={},
    )

    cap_registry = CapabilityRegistry()
    cap_registry.register(CapabilityManifest(
        capability_id="core.reason",
        version="1.0",
        provider="built_in",
        execution_location="local",
    ))
    cap_registry.register(CapabilityManifest(
        capability_id="fs.read",
        version="1.0",
        provider="built_in",
        execution_location="local",
    ))

    symbolic_reasoner = SymbolicReasoner(
        htn_planner=GenericHierarchicalPlanner(),
        logic_engine=LogicEngine(),
        constraint_solver=ConstraintSolver(
            resource_profile=ResourceProfile(),
            capability_registry=cap_registry,
        ),
    )

    bridge = NLUSymbolicBridge(
        nlu_adapter=mock_nlu,
        symbolic_reasoner=symbolic_reasoner,
        confidence_threshold=0.7,
        capability_registry=cap_registry,
    )

    result = bridge.process("buat rencana belajar Python 30 hari")
    assert isinstance(result, SymbolicPlan)
    assert result.nlu_result.intent.intent_id.startswith("intent-")
    assert result.nlu_result.intent.intent_type == IntentType.CREATE_PLAN
    assert result.nlu_result.confidence == 0.95
    assert result.nlu_result.slots["topic"] == "Python"
    # Ensure temperature=0.1 was passed
    mock_nlu.generate.assert_called_once()
    assert mock_nlu.generate.call_args.kwargs.get("temperature") == 0.1


def test_factory_returns_shared_capability_registry():
    """Test P0.5: Factory returns bridge with shared CapabilityRegistry populated."""
    bridge = create_nlu_symbolic_bridge()
    assert bridge.capability_registry is not None
    assert bridge.capability_registry.has_capability("core.reason")
    assert bridge.capability_registry.has_capability("fs.read")
    assert bridge.capability_registry.has_capability("process.execute")


def test_schema_validation_rejects_invalid_json():
    """Test P0.4: Schema validation rejects invalid intent or missing confidence."""
    bridge = create_nlu_symbolic_bridge()
    invalid_data = bridge._parse_structured_nlu('{"intent": "NOT_AN_INTENT", "confidence": "high"}')
    assert invalid_data is None
