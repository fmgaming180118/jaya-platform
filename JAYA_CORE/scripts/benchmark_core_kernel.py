"""
benchmark_core_kernel.py — Resource and latency benchmark for JAYA Core Portable Cognitive Kernel.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Measures cold import
start_import = time.perf_counter()

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

import psutil
from src.cognitive.contracts import UserRequest
from src.cognitive.runtime import JayaCoreRuntime
from src.memory.events import MemoryEvent

end_import = time.perf_counter()
cold_import_ms = (end_import - start_import) * 1000.0


def get_rss_mb() -> float:
    proc = psutil.Process()
    return proc.memory_info().rss / (1024.0 * 1024.0)


def run_benchmark() -> dict:
    rss_before_mb = get_rss_mb()

    # Measure runtime init
    t0 = time.perf_counter()
    tmp_db_path = Path(__file__).parent / "benchmark_temp.db"
    if tmp_db_path.exists():
        tmp_db_path.unlink()

    runtime = JayaCoreRuntime(db_path=tmp_db_path, node_id="bench-node")
    t1 = time.perf_counter()
    runtime_init_ms = (t1 - t0) * 1000.0

    rss_after_mb = get_rss_mb()

    # Measure request processing latency
    req = UserRequest(
        request_id="bench-req-001",
        raw_prompt="Buat rencana untuk merapikan file proyek saya.",
        user_id="bench_user",
    )
    t2 = time.perf_counter()
    resp = runtime.process(req)
    t3 = time.perf_counter()
    request_latency_ms = (t3 - t2) * 1000.0

    # Measure episodic write latency (100 events)
    t4 = time.perf_counter()
    for i in range(100):
        ev = MemoryEvent(
            event_id=f"bench-evt-{i}",
            event_type="BENCHMARK_EVENT",
            session_id="bench_session",
            goal_id="bench_goal",
            payload={"index": i, "data": "test_payload"},
            sequence_number=i,
        )
        runtime.episodic_memory.append_event(ev)
    t5 = time.perf_counter()
    episodic_write_ms = (t5 - t4) * 1000.0

    # Measure db size
    db_size_bytes = tmp_db_path.stat().st_size if tmp_db_path.exists() else 0

    runtime.episodic_memory.close()
    if tmp_db_path.exists():
        tmp_db_path.unlink()

    metrics = {
        "cold_import_ms": round(cold_import_ms, 2),
        "runtime_init_ms": round(runtime_init_ms, 2),
        "rss_before_mb": round(rss_before_mb, 2),
        "rss_after_mb": round(rss_after_mb, 2),
        "rss_delta_mb": round(rss_after_mb - rss_before_mb, 2),
        "request_latency_ms": round(request_latency_ms, 2),
        "episodic_write_100_events_ms": round(episodic_write_ms, 2),
        "db_size_after_100_events_bytes": db_size_bytes,
        "network_used": False,
        "heavy_model_loaded": False,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "cpu_count": os.cpu_count() or 1,
        },
    }

    return metrics


def main() -> None:
    results = run_benchmark()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
