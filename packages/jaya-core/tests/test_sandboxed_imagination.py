"""Comprehensive test suite for Pilar 23: Sandboxed Imagination (core.sandbox.expression)."""

from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

import pytest

from jaya_core.brain_v2.engine.jaya_ir import (
    IRInstruction,
    JayaIRGraph,
    OpCode,
)
from jaya_core.brain_v2.engine.jaya_ir_exec import (
    JayaIRExecutor,
)
from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyEffect,
    PolicyRisk,
    PolicyRule,
    default_core_policy,
)
from jaya_core.capabilities.puzzle import (
    CapabilityPuzzleRegistry,
    PuzzleManifest,
)
from jaya_core.pillars.foundation_capabilities import (
    SANDBOX_CAPABILITY_ID,
    SandboxedImaginationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError


def test_p23_legitimate_declarative_evaluation() -> None:
    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)
    assert sandbox.health_check() is True

    # Arithmetic & boolean logic
    res1 = sandbox.evaluate("(10 + 5) * 2 == 30 and (100 / 4) == 25")
    assert res1.data["result"] is True
    assert res1.data["epistemic_label"] == "SIMULATION"
    assert res1.data["epistemic_status"] == "UNVERIFIED"
    assert res1.data["cleanup_verified"] is True
    assert res1.data["duration_ns"] > 0

    # String & collection manipulation
    res2 = sandbox.evaluate("['alpha', 'beta', 'gamma'][1] == 'beta'")
    assert res2.data["result"] is True

    # Dict evaluation
    res3 = sandbox.evaluate("{'score': 42, 'active': True}['score'] * 2")
    assert res3.data["result"] == 84

    # Execute interface
    res4 = sandbox.execute({"action": "evaluate", "expression": "100 - 37"})
    assert res4.data["result"] == 63


def test_p23_security_adversarial_rejections() -> None:
    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)

    # Imports
    with pytest.raises(LocalPillarError) as exc_import:
        sandbox.evaluate("__import__('os').system('echo pwned')")
    assert exc_import.value.code == "SECURITY_VIOLATION"

    # Builtins and reflection
    with pytest.raises(LocalPillarError) as exc_getattr:
        sandbox.evaluate("getattr(__builtins__, 'eval')('1+1')")
    assert exc_getattr.value.code == "SECURITY_VIOLATION"

    # Class hierarchy traversal
    with pytest.raises(LocalPillarError) as exc_class:
        sandbox.evaluate("().__class__.__bases__[0].__subclasses__()")
    assert exc_class.value.code == "SECURITY_VIOLATION"

    # File open
    with pytest.raises(LocalPillarError) as exc_open:
        sandbox.evaluate("open('secret.txt', 'r').read()")
    assert exc_open.value.code == "SECURITY_VIOLATION"

    # Lambda and function definitions
    with pytest.raises(LocalPillarError) as exc_func:
        sandbox.evaluate("(lambda x: x + 1)(5)")
    assert exc_func.value.code == "SECURITY_VIOLATION"


def test_p23_resource_limits_and_dos_protection() -> None:
    sandbox = SandboxedImaginationCapability(timeout_seconds=1.0)

    # Power exponent bomb
    with pytest.raises(LocalPillarError) as exc_pow:
        sandbox.evaluate("2 ** 999999")
    assert exc_pow.value.code == "SECURITY_VIOLATION"

    # Base limit for power
    with pytest.raises(LocalPillarError) as exc_pow_base:
        sandbox.evaluate("1000000 ** 5")
    assert exc_pow_base.value.code == "SECURITY_VIOLATION"

    # Division by zero
    with pytest.raises(LocalPillarError) as exc_div:
        sandbox.evaluate("100 / 0")
    assert exc_div.value.code == "ARITHMETIC_ERROR"

    # Deeply nested AST (depth bomb)
    nested_expr = "(" * 40 + "1" + " + 1)" * 40
    with pytest.raises(LocalPillarError) as exc_depth:
        sandbox.evaluate(nested_expr)
    assert exc_depth.value.code == "RESOURCE_LIMIT"

    # Too many AST nodes
    many_nodes = " + ".join(["1"] * 300)
    with pytest.raises(LocalPillarError) as exc_nodes:
        sandbox.evaluate(many_nodes)
    assert exc_nodes.value.code == "RESOURCE_LIMIT"

    # Excessive input size (>4096 characters)
    huge_input = "1 + " * 1500 + "1"
    with pytest.raises(LocalPillarError) as exc_input:
        sandbox.evaluate(huge_input)
    assert exc_input.value.code in {"INVALID_INPUT", "RESOURCE_LIMIT"}


def test_p23_invalid_schema_and_config() -> None:
    # Invalid timeout config
    with pytest.raises(LocalPillarError) as exc_cfg:
        SandboxedImaginationCapability(timeout_seconds=0.05)
    assert exc_cfg.value.code == "INVALID_CONFIG"

    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)

    # Unknown fields
    with pytest.raises(LocalPillarError) as exc_field:
        sandbox.execute({"action": "evaluate", "expression": "1+1", "unknown_field": True})
    assert exc_field.value.code == "UNKNOWN_FIELD"

    # Unsupported action
    with pytest.raises(LocalPillarError) as exc_action:
        sandbox.execute({"action": "execute_arbitrary_code", "expression": "1+1"})
    assert exc_action.value.code == "UNSUPPORTED_ACTION"

    # Non-string expression
    with pytest.raises(LocalPillarError) as exc_type:
        sandbox.evaluate(12345)
    assert exc_type.value.code == "INVALID_INPUT"


def test_p23_concurrent_isolated_executions() -> None:
    sandbox = SandboxedImaginationCapability(timeout_seconds=3.0)

    def worker_job(index: int) -> tuple[int, Any]:
        expr = f"({index} * 10) + {index} == {index * 11}"
        res = sandbox.evaluate(expr)
        return index, res.data["result"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_job, i) for i in range(1, 17)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 16
    for idx, ok in results:
        assert ok is True


class _SandboxPuzzleAdapter:
    def __init__(self, capability: SandboxedImaginationCapability) -> None:
        self.capability = capability

    def health_check(self) -> bool:
        return self.capability.health_check()

    def invoke(self, payload: Any) -> dict[str, object]:
        res = self.capability.execute(payload)
        return {"ok": True, "result": res.data}


def test_p23_jayair_and_dual_gate_security_integration(tmp_path: Path) -> None:
    """Verify P23 invocation through JayaIR with Ethical Heart policy validation."""
    from jaya_core.brain_v2.soul.ethical_heart import PolicyBundle

    policy = PolicyBundle(
        policy_id="test.sandbox-policy",
        version=1,
        brain_id="brain:main",
        rules=(
            PolicyRule(
                rule_id="allow.sandbox",
                effect=PolicyEffect.ALLOW,
                capability_ids=(SANDBOX_CAPABILITY_ID,),
                risk_classes=(PolicyRisk.READ_ONLY,),
                reason_code="SANDBOX_ALLOWED",
            ),
        ),
        default_effect=PolicyEffect.REQUIRE_APPROVAL,
        default_reason_code="EXPLICIT_APPROVAL_REQUIRED",
    )
    heart = EthicalHeart(tmp_path / "sandbox-policy.db", policy)
    registry = CapabilityPuzzleRegistry()
    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)

    adapter = _SandboxPuzzleAdapter(sandbox)
    registry.attach(
        PuzzleManifest(
            puzzle_id="puzzle.sandbox.expression",
            capability_id=SANDBOX_CAPABILITY_ID,
            version="1.0.0",
            risk_class="READ_ONLY",
        ),
        adapter,
    )

    payload = {"action": "evaluate", "expression": "(15 + 25) * 2"}
    graph = JayaIRGraph(
        instructions=(
            IRInstruction(
                opcode=OpCode.CALL_CAPABILITY,
                args=(
                    SANDBOX_CAPABILITY_ID,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
                target="res",
            ),
            IRInstruction(
                opcode=OpCode.RETURN,
                args=("res",),
            ),
        ),
        source="p23-sandbox-test",
    )

    executor = JayaIRExecutor(
        puzzle_registry=registry,
        policy_engine=heart,
        actor_brain_id="brain:main",
        node_id="node:primary",
    )

    try:
        execution_result = executor.execute_graph(graph)
    finally:
        registry.close()
        heart.close()

    assert execution_result["ok"] is True
    result_data = execution_result["result"]["result"]
    assert result_data["result"] == 80
    assert result_data["epistemic_label"] == "SIMULATION"
    assert result_data["epistemic_status"] == "UNVERIFIED"
    assert "policy_receipt" in execution_result["result"]
