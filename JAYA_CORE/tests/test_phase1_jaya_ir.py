"""Phase 1 tests for JayaIR schema, translator, executor, and runtime hook."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.jaya_ir import (
    IRInstruction,
    JayaIRGraph,
    OpCode,
    ValidationMode,
    contract_metadata,
    validate_graph,
)
from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
from src.brain_v2.engine.jaya_ir_translator import logic_expr_to_ir
from src.brain_v2.engine.runtime import IronEngine


class TestJayaIRSchema(unittest.TestCase):
    def test_opcode_scope_is_aggressive(self):
        self.assertGreaterEqual(len(list(OpCode)), 20)

    def test_contract_is_phase1_frozen(self):
        md = contract_metadata()
        self.assertEqual(md["version"], "0.1")
        self.assertEqual(md["phase_state"], "phase1_frozen")
        self.assertGreaterEqual(md["opcode_count"], 24)

    def test_lenient_validator_marks_unknown_as_non_executable(self):
        graph = JayaIRGraph(
            instructions=[
                IRInstruction(opcode="UNKNOWN_OPCODE", args=("x",), target="out"),
                IRInstruction(opcode=OpCode.RETURN, args=("out",)),
            ],
            source="unit",
        )
        report = validate_graph(graph, mode=ValidationMode.LENIENT)
        self.assertTrue(report.is_valid)
        self.assertFalse(report.has_critical)
        self.assertFalse(graph.instructions[0].executable)
        self.assertIn("validation_error", graph.instructions[0].metadata)


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

    def test_lenient_invalid_instruction_is_skipped(self):
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
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"], "safe")


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
