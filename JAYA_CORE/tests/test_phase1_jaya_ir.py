"""Phase 1 tests for JayaIR schema, translator, executor, and runtime hook."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.jaya_ir import (  # noqa: E402
    IRFailureCode,
    IRInstruction,
    IRMutationError,
    JayaIRGraph,
    OpCode,
    ValidationMode,
    contract_metadata,
    validate_graph,
)
from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor  # noqa: E402
from src.brain_v2.engine.jaya_ir_translator import logic_expr_to_ir  # noqa: E402
from src.brain_v2.engine.runtime import IronEngine  # noqa: E402


class TestJayaIRSchema(unittest.TestCase):
    def test_opcode_scope_is_aggressive(self):
        self.assertGreaterEqual(len(list(OpCode)), 20)

    def test_contract_is_phase1_frozen(self):
        md = contract_metadata()
        self.assertEqual(md["version"], "0.1")
        self.assertEqual(md["phase_state"], "phase1_frozen")
        self.assertGreaterEqual(md["opcode_count"], 24)

    def test_lenient_validator_rejects_unknown_opcode(self):
        graph = JayaIRGraph(
            instructions=[
                IRInstruction(opcode="UNKNOWN_OPCODE", args=("x",), target="out"),
                IRInstruction(opcode=OpCode.RETURN, args=("out",)),
            ],
            source="unit",
        )
        report = validate_graph(graph, mode=ValidationMode.LENIENT)
        self.assertFalse(report.is_valid)
        self.assertTrue(report.has_critical)
        self.assertEqual(report.issues[0].code, IRFailureCode.UNKNOWN_OPCODE)
        self.assertTrue(graph.instructions[0].executable)


class TestTranslator(unittest.TestCase):
    def test_action_maps_to_action_opcode(self):
        graph = logic_expr_to_ir(("ACTION", "OPEN", "desktop"))
        self.assertEqual(graph.instructions[0].opcode, OpCode.ACTION_OPEN)

    def test_arith_maps_and_executes(self):
        graph = logic_expr_to_ir(("QUERY", "ARITH", ("ADD", 2, 3)))
        self.assertEqual(graph.instructions[2].opcode, OpCode.ARITH_ADD)


class TestExecutor(unittest.TestCase):
    def test_cache_hit_on_repeated_graph(self):
        ex = JayaIRExecutor(cache_size=16, ttl_s=300.0)
        graph = logic_expr_to_ir(("ACTION", "OPEN", "window"))

        out1 = ex.execute_graph(graph)
        out2 = ex.execute_graph(graph)

        self.assertTrue(out1["ok"])
        self.assertTrue(out2["ok"])
        self.assertFalse(out1["cache_hit"])
        self.assertTrue(out2["cache_hit"])
        self.assertGreaterEqual(ex.status()["hit_rate"], 0.5)

    def test_lenient_invalid_instruction_is_typed_failure(self):
        ex = JayaIRExecutor(mode=ValidationMode.LENIENT)
        graph = JayaIRGraph(
            instructions=[
                IRInstruction(opcode="UNKNOWN_OPCODE", args=("x",), target="out"),
                IRInstruction(opcode=OpCode.PASS_LITERAL, args=("safe",), target="out"),
                IRInstruction(opcode=OpCode.RETURN, args=("out",)),
            ],
            source="unit",
        )
        out = ex.execute_graph(graph)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], IRFailureCode.UNKNOWN_OPCODE.value)

    def test_unknown_action_requires_a_real_capability_puzzle(self):
        ex = JayaIRExecutor()
        graph = logic_expr_to_ir(("ACTION", "TURN_ON", "lamp"))

        out = ex.execute_graph(graph)

        self.assertFalse(out["ok"])
        self.assertEqual(
            out["error"],
            IRFailureCode.DEPENDENCY_UNAVAILABLE.value,
        )
        self.assertEqual(
            out["failure"]["instruction_index"],
            0,
        )

    def test_divide_by_zero_is_typed_failure(self):
        ex = JayaIRExecutor()
        graph = logic_expr_to_ir(("QUERY", "ARITH", ("DIV", 8, 0)))

        out = ex.execute_graph(graph)

        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], IRFailureCode.DIVIDE_BY_ZERO.value)

    def test_invalid_cfg_target_is_typed_failure(self):
        ex = JayaIRExecutor()
        graph = JayaIRGraph(
            instructions=[
                IRInstruction(opcode=OpCode.JUMP, args=(99,)),
                IRInstruction(opcode=OpCode.RETURN, args=("out",)),
            ],
            source="unit",
        )

        out = ex.execute_graph(graph)

        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], IRFailureCode.INVALID_CFG.value)

    def test_valid_branch_cfg_executes_deterministically(self):
        ex = JayaIRExecutor()
        graph = JayaIRGraph(
            instructions=[
                IRInstruction(
                    opcode=OpCode.LOAD_CONST,
                    args=(True,),
                    target="condition",
                ),
                IRInstruction(
                    opcode=OpCode.BRANCH_IF,
                    args=("condition", 2, 4),
                ),
                IRInstruction(
                    opcode=OpCode.PASS_LITERAL,
                    args=("yes",),
                    target="out",
                ),
                IRInstruction(opcode=OpCode.JUMP, args=(5,)),
                IRInstruction(
                    opcode=OpCode.PASS_LITERAL,
                    args=("no",),
                    target="out",
                ),
                IRInstruction(opcode=OpCode.RETURN, args=("out",)),
            ],
            source="unit",
        )

        out = ex.execute_graph(graph)

        self.assertTrue(out["ok"])
        self.assertEqual(out["result"], "yes")

    def test_validated_graph_is_immutable(self):
        graph = logic_expr_to_ir(("ACTION", "OPEN", "window"))
        report = validate_graph(graph)

        self.assertTrue(report.is_valid)
        self.assertTrue(graph.is_sealed)
        self.assertIsInstance(graph.instructions, tuple)
        with self.assertRaises(IRMutationError):
            graph.instructions[0].args = ("tampered",)
        with self.assertRaises(IRMutationError):
            graph.source = "tampered"
        with self.assertRaises(TypeError):
            graph.metadata["tampered"] = True

    def test_cache_rejects_forced_mutation_after_validation(self):
        ex = JayaIRExecutor()
        graph = logic_expr_to_ir(("ACTION", "OPEN", "window"))
        first = ex.execute_graph(graph)
        self.assertTrue(first["ok"])

        object.__setattr__(
            graph.instructions[0],
            "args",
            ("tampered",),
        )
        second = ex.execute_graph(graph)

        self.assertTrue(second["ok"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["result"]["target"], "window")

        ex.clear_cache()
        third = ex.execute_graph(graph)
        self.assertFalse(third["ok"])
        self.assertEqual(third["error"], IRFailureCode.IR_MUTATION.value)

    def test_unvalidated_graph_cannot_spoof_cached_signature(self):
        ex = JayaIRExecutor()
        safe_graph = logic_expr_to_ir(("ACTION", "OPEN", "window"))
        self.assertTrue(ex.execute_graph(safe_graph)["ok"])

        unsupported = JayaIRGraph(
            instructions=[
                IRInstruction(
                    opcode=OpCode.CALL_STUB,
                    args=("fallback",),
                    target="out",
                ),
                IRInstruction(opcode=OpCode.RETURN, args=("out",)),
            ],
            source="unit",
        )
        unsupported.signature = safe_graph.signature

        out = ex.execute_graph(unsupported)

        self.assertFalse(out["ok"])
        self.assertEqual(
            out["error"],
            IRFailureCode.UNSUPPORTED_OPCODE.value,
        )


class TestRuntimeIntegration(unittest.TestCase):
    def test_runtime_execute_intent_smoke(self):
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine._init_intelligence()

        out = engine.execute_intent("open desktop")
        self.assertTrue(out["ok"])
        self.assertIn("logic_expr", out)
        self.assertIn("result", out)

    def test_runtime_returns_error_when_executor_unavailable(self):
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine._init_intelligence()
        engine._jaya_ir_exec = None

        original_factory = engine._ensure_jaya_ir_executor
        engine._ensure_jaya_ir_executor = lambda log_on_ready=False: False
        try:
            out = engine.execute_intent("open desktop")
        finally:
            engine._ensure_jaya_ir_executor = original_factory

        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "jaya_ir_executor_unavailable")


if __name__ == "__main__":
    unittest.main()
