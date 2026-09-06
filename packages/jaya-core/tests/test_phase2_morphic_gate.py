"""Regression tests for the quarantined in-process patch prototype.

Strict compliance checks according to AGENTS.md:
- Sandboxed evaluation in isolated worker process
- Rejection of forbidden targets, unsafe functions, and external execution
- Bytecode digest verified atomic patching and rollback
- Production runtime rejects direct object mutation
"""

from __future__ import annotations

from pathlib import Path
import pytest

from jaya_core.brain_v2.engine.morphic import MorphicKernel
from jaya_core.brain_v2.engine.runtime import IronEngine


class _SampleWorker:
    def __init__(self, mode: str = "standard"):
        self.mode = mode

    def compute_metric(self) -> dict:
        return {"status": "normal", "score": 10}


def test_morphic_kernel_valid_constant_patch():
    kernel = MorphicKernel()
    worker = _SampleWorker()

    assert worker.compute_metric() == {"status": "normal", "score": 10}

    valid_code = """
def compute_metric():
    return {"status": "optimized", "score": 99}
"""
    applied = kernel.patch(worker, "compute_metric", valid_code)
    assert applied is True
    assert worker.compute_metric() == {"status": "optimized", "score": 99}

    # Verify status reflects active patch
    st = kernel.status()
    assert st["patches"] == 1
    assert st["active"] == 1
    assert len(st["active_digests"]) == 1

    # Rollback
    restored = kernel.rollback("compute_metric")
    assert restored == 1
    assert worker.compute_metric() == {"status": "normal", "score": 10}
    assert kernel.status()["active"] == 0


def test_morphic_kernel_rejects_forbidden_targets():
    kernel = MorphicKernel()
    worker = _SampleWorker()

    code = "def __init__():\n    return {'bad': True}\n"
    assert kernel.patch(worker, "__init__", code) is False

    code2 = "def dna_anchor():\n    return {'bad': True}\n"
    assert kernel.patch(worker, "dna_anchor", code2) is False

    assert kernel.status()["rejected"] >= 2


def test_morphic_kernel_rejects_malicious_or_dynamic_code():
    kernel = MorphicKernel()
    worker = _SampleWorker()

    # Import attempt
    bad_code1 = """
def compute_metric():
    import os
    return {"status": "pwned"}
"""
    assert kernel.patch(worker, "compute_metric", bad_code1) is False

    # Function call attempt
    bad_code2 = """
def compute_metric():
    return {"time": open("test.txt", "w")}
"""
    assert kernel.patch(worker, "compute_metric", bad_code2) is False

    # Syntax error
    bad_code3 = "def compute_metric(:\n    return {}"
    assert kernel.patch(worker, "compute_metric", bad_code3) is False


def test_iron_engine_rejects_direct_morphic_mutation(tmp_path: Path):
    engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
    engine.ignite()

    worker = _SampleWorker()
    patch_code = """
def compute_metric():
    return {"status": "hot_patched", "version": 2}
"""
    res = engine.apply_morphic_patch(worker, "compute_metric", patch_code)
    assert res == {
        "ok": False,
        "error": "DIRECT_RUNTIME_PATCH_FORBIDDEN",
        "method": "compute_metric",
        "required_path": "signed_manifest_evolution_installer",
    }
    assert worker.compute_metric() == {"status": "normal", "score": 10}

    st = engine.status()
    assert st["morphic"] is None

    # Rollback via engine
    rb = engine.rollback_morphic_patch("compute_metric")
    assert rb["ok"] is False
    assert rb["error"] == "DIRECT_RUNTIME_PATCH_FORBIDDEN"
    assert rb["restored"] == 0
    assert worker.compute_metric() == {"status": "normal", "score": 10}
