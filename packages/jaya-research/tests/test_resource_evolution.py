"""Integration checks for bounded, resource-aware evolution behavior."""

from __future__ import annotations

import os

import psutil
import pytest
from jaya_research.evolution.twin import DigitalTwin
from jaya_research.optimizer import CandidateProposalError, Optimizer

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_ram_monitoring() -> None:
    process = psutil.Process(os.getpid())
    assert process.memory_info().rss > 0

    twin = DigitalTwin()
    result = await twin.cycle()

    assert result["status"] == "IDLE_NO_AUTONOMOUS_ACTION"
    assert result["provider_called"] is False
    assert result["source_mutated"] is False


async def test_resource_optimization_requires_injected_provider() -> None:
    optimizer = Optimizer(target_file="engine.py")

    with pytest.raises(CandidateProposalError, match="Teacher"):
        optimizer.evolve(
            target_file="engine.py",
            focus=(
                "speed, JIT compiler integration via Numba, and minimal "
                "memory overhead"
            ),
        )
