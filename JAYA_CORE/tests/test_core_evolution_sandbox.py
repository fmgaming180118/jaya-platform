"""Deterministic security tests for the Core evolution sandbox."""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.evolution_sandbox import (  # noqa: E402
    EvolutionSandbox,
    SandboxFailureCode,
)
from src.brain_v2.engine.morphic import MorphicKernel  # noqa: E402
from src.brain_v2.extensions.twin.core_twin import CoreTwin  # noqa: E402
from src.brain_v2.extensions.twin.experiment_memory import (  # noqa: E402
    ExperimentMemory,
)


def test_experiment_runs_in_separate_worker_process():
    sandbox = EvolutionSandbox()

    result = sandbox.run_experiment("score = round(0.4 + 0.4, 1)")

    assert result.ok is True
    assert result.outcome == {"score": 0.8}
    assert result.worker_pid is not None
    assert result.worker_pid != os.getpid()


@pytest.mark.parametrize(
    "candidate",
    [
        "import os\nscore = 1.0",
        "open('forbidden.txt', 'w')",
        "score = (1).__class__",
        "score = __import__('socket')",
    ],
)
def test_filesystem_network_import_and_introspection_are_rejected(candidate):
    sandbox = EvolutionSandbox()

    result = sandbox.run_experiment(candidate)

    assert result.ok is False
    assert result.failure_code is SandboxFailureCode.POLICY_REJECTED


def test_experiment_timeout_is_typed_and_bounded():
    sandbox = EvolutionSandbox(timeout_s=0.25, cpu_time_s=1)

    result = sandbox.run_experiment("score = sum(range(10 ** 12))")

    assert result.ok is False
    assert result.failure_code is SandboxFailureCode.TIMEOUT
    assert result.duration_ms < 2_000


def test_experiment_memory_limit_is_typed_and_bounded():
    sandbox = EvolutionSandbox(
        timeout_s=2.0,
        memory_limit_mb=64,
        cpu_time_s=1,
    )

    result = sandbox.run_experiment(
        "payload = [0] * (10 ** 8)\nscore = 1.0"
    )

    assert result.ok is False
    assert result.failure_code is SandboxFailureCode.RESOURCE_LIMIT
    assert result.duration_ms < 2_000


def test_core_twin_records_sandbox_rejection_as_zero_score():
    async def run() -> None:
        memory = ExperimentMemory(in_memory=True)
        twin = CoreTwin(None, memory=memory)

        outcome = await twin.run_experiment("import socket")

        assert outcome["__failure_code__"] == "policy_rejected"
        assert memory.records[-1].label == "ERROR"
        assert memory.records[-1].score == 0.0
        assert twin.experiments_run == 0

    asyncio.run(run())


def test_morphic_patch_and_digest_verified_rollback():
    class Brain:
        def greet(self) -> str:
            return "hello"

    brain = Brain()
    kernel = MorphicKernel()

    applied = kernel.patch(
        brain,
        "greet",
        "def greet(self) -> str:\n    return 'ciao'",
    )

    assert applied is True
    assert brain.greet() == "ciao"
    active = kernel.status()["active_digests"]
    assert len(active) == 1
    assert active[0]["baseline"] != active[0]["patched"]

    assert kernel.rollback("greet") == 1
    assert brain.greet() == "hello"
    rollback = kernel.status()["last_rollback"]
    assert rollback == {"ok": True, "restored": 1, "failures": []}


def test_morphic_rollback_does_not_clobber_external_mutation():
    class Brain:
        def greet(self) -> str:
            return "hello"

    brain = Brain()
    kernel = MorphicKernel()
    assert kernel.patch(
        brain,
        "greet",
        "def greet(self) -> str:\n    return 'ciao'",
    )

    def external_greet(_self: Brain) -> str:
        return "external"

    brain.greet = types.MethodType(external_greet, brain)

    assert kernel.rollback("greet") == 0
    assert brain.greet() == "external"
    rollback = kernel.status()["last_rollback"]
    assert rollback["ok"] is False
    assert rollback["failures"][0]["reason"] == "current_digest_mismatch"


def test_morphic_rejects_dynamic_candidate_code():
    class Brain:
        def greet(self) -> str:
            return "hello"

    kernel = MorphicKernel()
    candidate = (
        "def greet(self) -> str:\n"
        "    import os\n"
        "    return os.getenv('SECRET', '')\n"
    )

    assert kernel.patch(Brain(), "greet", candidate) is False
    assert kernel.status()["active"] == 0
