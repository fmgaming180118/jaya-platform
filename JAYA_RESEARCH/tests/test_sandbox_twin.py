import asyncio
from pathlib import Path

import pytest
from evolution.twin import DigitalTwin

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class MemoryStub:
    def __init__(self) -> None:
        self.thoughts = []

    def log_thought(self, content, mood="neutral", context=None):
        thought = {
            "content": content,
            "mood": mood,
            "context": context or {},
        }
        self.thoughts.append(thought)
        return thought


async def test_twin_sandbox(tmp_path: Path):
    twin = DigitalTwin(
        source_root=tmp_path,
        outbox_dir=tmp_path / "outbox",
        memory=MemoryStub(),
        cycle_interval_seconds=0,
    )
    marker = tmp_path / "marker.txt"
    code = f"open({str(marker)!r}, 'w').write('executed')\n"

    receipt = await twin.experiment(code)

    assert receipt["status"] == "SIMULATION_CANDIDATE_EXPORTED"
    assert receipt["candidate_executed"] is False
    assert receipt["source_mutated"] is False
    assert not marker.exists()
    assert "SIMULATION_CANDIDATE_EXPORTED" in twin.memory.thoughts[-1]["content"]


if __name__ == "__main__":
    asyncio.run(test_twin_sandbox(Path(".tmp_twin_test")))
