"""
test_fase1_slm_engine.py — Unit tests for SLMEngine (Fase 1 JAYA_CORE)

Tests cover:
  - Domain detection (detect_domain)
  - Sliding context window push + H2O eviction
  - Tool call JSON validation
  - SLMEngine stub instantiation & status
  - Server import chain health check
"""
import sys
from pathlib import Path

# Add JAYA_CORE to path
repo_root = Path(__file__).resolve().parent.parent.parent
jaya_core_dir = repo_root / "JAYA_CORE"
sys.path.insert(0, str(jaya_core_dir))

import pytest
from src.brain_v2.engine.slm_engine import (
    detect_domain,
    validate_tool_call,
    SlidingContextWindow,
    SLMEngine,
    JAYA_SYSTEM_PROMPT,
    TOOL_SCHEMAS,
)


# ---------------------------------------------------------------------------
# Domain Detection Tests
# ---------------------------------------------------------------------------

class TestDomainDetection:
    def test_thesis_domain(self):
        assert detect_domain("bantu saya menulis bab pendahuluan skripsi") == "thesis"

    def test_code_domain(self):
        assert detect_domain("ada bug di fungsi kotlin saya") == "code"

    def test_math_domain(self):
        assert detect_domain("hitung integral x kuadrat") == "math"

    def test_conversation_default(self):
        assert detect_domain("halo apa kabar") == "conversation"

    def test_thesis_priority_over_conversation(self):
        assert detect_domain("riset saya tentang federated learning untuk skripsi") == "thesis"


# ---------------------------------------------------------------------------
# Sliding Context Window Tests
# ---------------------------------------------------------------------------

class TestSlidingContextWindow:
    def test_push_and_build(self):
        ctx = SlidingContextWindow(max_tokens=500, system_prompt="System.")
        ctx.push("user", "Halo JAYA")
        ctx.push("assistant", "Halo Bos!")
        msgs = ctx.build_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_h2o_eviction(self):
        ctx = SlidingContextWindow(max_tokens=20, system_prompt="")
        # Push until eviction is triggered
        for i in range(10):
            ctx.push("user", f"turn {i} " * 3)
        # Context should stay bounded
        assert ctx.token_count <= 30  # allow some tolerance

    def test_clear_resets(self):
        ctx = SlidingContextWindow(max_tokens=500, system_prompt="")
        ctx.push("user", "test")
        ctx.clear()
        assert ctx.token_count == 0
        assert ctx.build_messages() == []


# ---------------------------------------------------------------------------
# Tool Call Validation Tests
# ---------------------------------------------------------------------------

class TestToolCallValidation:
    def test_valid_rag_search_tool(self):
        import json
        output = json.dumps({"tool": "rag_search", "args": {"query": "indonesia"}})
        result = validate_tool_call(output)
        assert result is not None
        assert result["tool"] == "rag_search"

    def test_invalid_tool_name(self):
        output = '{"tool": "unknown_tool", "args": {}}'
        result = validate_tool_call(output)
        assert result is None

    def test_no_json_in_output(self):
        result = validate_tool_call("Halo Bos, saya siap membantu!")
        assert result is None

    def test_valid_calculate_tool(self):
        import json
        output = json.dumps({"tool": "calculate", "args": {"expression": "2 + 3"}})
        result = validate_tool_call(output)
        assert result is not None
        assert result["tool"] == "calculate"


# ---------------------------------------------------------------------------
# SLMEngine Status Tests (no actual model load)
# ---------------------------------------------------------------------------

class TestSLMEngineStatus:
    def test_initial_status(self):
        engine = SLMEngine(model_key="smollm2_135m")
        status = engine.status()
        assert status["loaded"] is False
        assert status["model_key"] == "smollm2_135m"
        assert status["inference_count"] == 0
        assert status["active_domain"] is None

    def test_reset_context(self):
        engine = SLMEngine()
        engine._context.push("user", "test message")
        engine.reset_context()
        # After clear, token_count = system prompt word count
        expected = len(JAYA_SYSTEM_PROMPT.split())
        assert engine._context.token_count == expected

    def test_tool_schemas_not_empty(self):
        assert len(TOOL_SCHEMAS) >= 4
        assert "rag_search" in TOOL_SCHEMAS
        assert "calculate" in TOOL_SCHEMAS

    def test_system_prompt_exists(self):
        assert "JAYA" in JAYA_SYSTEM_PROMPT
        assert len(JAYA_SYSTEM_PROMPT) > 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
