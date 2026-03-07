"""Tests for CoreTwin, TaskPlanner, ExperimentMemory and IronEngine."""
import asyncio
import os
import sys

# Ensure JAYA_CORE root is on the path
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)

from src.brain_v2.extensions.twin.core_twin import CoreTwin, _compute_score
from src.brain_v2.extensions.twin.task_planner import Task, TaskPlanner, Priority
from src.brain_v2.extensions.twin.experiment_memory import ExperimentMemory

# Convenience factory for tests that need a fresh, isolated memory
def _fresh_mem() -> ExperimentMemory:
    return ExperimentMemory(in_memory=True)


# ---------------------------------------------------------------------------
# Scoring helper
# ---------------------------------------------------------------------------

def test_score_clean_run():
    assert _compute_score({"x": 1}) == 1.0

def test_score_error():
    assert _compute_score({"__error__": "oops"}) == 0.0

def test_score_explicit():
    assert _compute_score({"score": 0.75}) == 0.75


# ---------------------------------------------------------------------------
# ExperimentMemory
# ---------------------------------------------------------------------------

def test_memory_record_and_summary(tmp_path):
    mem = ExperimentMemory(path=str(tmp_path / "exp.jsonl"))
    mem.record("x=1", {"x": 1}, score=0.9, label="EXPLORE")
    mem.record("bad", {"__error__": "fail"}, score=0.0, label="ERROR")
    s = mem.summary()
    assert s["total"] == 2
    assert s["errors"] == 1
    assert s["avg_score"] == 0.45

def test_memory_best(tmp_path):
    mem = ExperimentMemory(path=str(tmp_path / "exp.jsonl"))
    for i in range(5):
        mem.record(f"x={i}", {"x": i}, score=float(i), label="EXPLORE")
    best = mem.best(n=1)
    assert best[0].score == 4.0


# ---------------------------------------------------------------------------
# TaskPlanner
# ---------------------------------------------------------------------------

def test_planner_priority_order():
    planner = TaskPlanner()
    planner.push(Task(priority=Priority.LOW, label="L", code=""))
    planner.push(Task(priority=Priority.CRITICAL, label="C", code=""))
    planner.push(Task(priority=Priority.MEDIUM, label="M", code=""))
    assert planner.pop().label == "C"
    assert planner.pop().label == "M"
    assert planner.pop().label == "L"

def test_planner_suggest_repair(tmp_path):
    mem = ExperimentMemory(path=str(tmp_path / "exp.jsonl"))
    mem.record("bad", {"__error__": "fail"}, score=0.0, label="ERROR")
    planner = TaskPlanner()
    task = planner.suggest_from_memory(mem)
    assert task is not None
    assert task.label == "REPAIR"


# ---------------------------------------------------------------------------
# CoreTwin — lifecycle and experiments
# ---------------------------------------------------------------------------

def test_twin_start_stop():
    async def run():
        twin = CoreTwin(None, reflection_interval=9999)
        await twin.start()
        assert twin.running
        await twin.stop()
        assert not twin.running
    asyncio.run(run())


def test_twin_run_experiment():
    async def run():
        twin = CoreTwin(None, reflection_interval=9999, memory=_fresh_mem())
        res = await twin.run_experiment("score = 0.8")
        assert res.get("score") == 0.8
        # memory should have one entry
        assert twin.memory.summary()["total"] == 1
    asyncio.run(run())


def test_twin_report():
    async def run():
        twin = CoreTwin(None, memory=_fresh_mem())
        twin.report({"score": 0.5, "note": "external"})
        assert twin.memory.summary()["total"] == 1
    asyncio.run(run())


def test_twin_queue_task():
    async def run():
        twin = CoreTwin(None, reflection_interval=9999)
        twin.queue_task("score = 1.0", label="OPTIMIZE")
        assert len(twin.planner) == 1
    asyncio.run(run())


def test_twin_status():
    twin = CoreTwin(None)
    st = twin.status()
    assert "cycles" in st
    assert "experiments" in st
    assert "queue_depth" in st


# ---------------------------------------------------------------------------
# IronEngine integration
# ---------------------------------------------------------------------------

def test_engine_twin_integration():
    from src.brain_v2.engine.runtime import IronEngine
    engine = IronEngine("fake.jay", "pw", enable_twin=True)
    engine.ignite()
    assert engine.is_awake
    assert engine.twin is not None

def test_engine_agi_config_feedback():
    from src.brain_v2.engine.runtime import IronEngine
    engine = IronEngine("fake.jay", "pw")
    engine.ignite()
    engine.config.apply_feedback({"topk_ratio": 0.05})
    assert engine.config.topk_ratio == 0.05
    assert engine.config.version == 1

def test_engine_status():
    from src.brain_v2.engine.runtime import IronEngine
    engine = IronEngine("fake.jay", "pw", enable_twin=True)
    engine.ignite()
    st = engine.status()
    assert st["is_awake"]
    assert st["twin"] is not None

