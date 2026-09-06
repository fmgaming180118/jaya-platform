#!/usr/bin/env python3
"""Benchmark suite for Pillar 04 Multimodal Reflex."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import wave
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter  # noqa: E402
from jaya_core.pillars.media_capability import MediaObservationCapability  # noqa: E402


def _write_wav(path: Path, sample_rate: int = 16000, frames: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * frames)


def _make_minimal_png(width: int = 64, height: int = 32) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc

    raw_scanlines = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    compressed = zlib.compress(raw_scanlines)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc

    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    return signature + ihdr + idat + iend


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p04_"))
    media_root = temp_dir / "media_store"
    media_root.mkdir(parents=True, exist_ok=True)
    db_path = media_root / "media.sqlite3"

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    service = MediaObservationCapability(root=media_root, database_path=db_path)
    service.health_check()
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    service.health_check()
    warm_boot_ms = (time.perf_counter() - t_warm_start) * 1000.0

    # Prepare fixtures
    wav_path = media_root / "bench.wav"
    _write_wav(wav_path, sample_rate=16000, frames=16000)

    png_path = media_root / "bench.png"
    png_path.write_bytes(_make_minimal_png(64, 32))

    doc_path = media_root / "bench.txt"
    doc_path.write_text("JAYA Multimodal reflex benchmark paragraph content.\n" * 5, encoding="utf-8")

    meter = None
    start_sample = None
    if sys.platform.startswith("win"):
        try:
            meter = WindowsEmiEnergyMeter()
            start_sample = meter.sample()
        except EnergyMeterError:
            meter = None
            start_sample = None

    proc = psutil.Process(os.getpid())
    rss_initial = proc.memory_info().rss

    audio_latencies_ms: list[float] = []
    image_latencies_ms: list[float] = []
    doc_latencies_ms: list[float] = []

    t_bench_start = time.perf_counter()

    for i in range(iterations):
        # Audio
        t0 = time.perf_counter()
        service.execute({"action": "observe_file", "path": "bench.wav"})
        audio_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        # Image
        t1 = time.perf_counter()
        service.execute({"action": "observe_file", "path": "bench.png"})
        image_latencies_ms.append((time.perf_counter() - t1) * 1000.0)

        # Document
        t2 = time.perf_counter()
        service.execute({"action": "observe_file", "path": "bench.txt"})
        doc_latencies_ms.append((time.perf_counter() - t2) * 1000.0)

    elapsed_total = time.perf_counter() - t_bench_start
    total_ops = iterations * 3

    # Energy measurement
    energy_joules = 0.0
    energy_method = "SOFTWARE_FALLBACK"
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules or (elapsed_total * 28.0))
            energy_method = "WINDOWS_EMI"
        except EnergyMeterError:
            energy_joules = elapsed_total * 28.0
    else:
        energy_joules = elapsed_total * 28.0

    rss_final = proc.memory_info().rss
    rss_growth = max(0, rss_final - rss_initial)
    db_size = db_path.stat().st_size
    bytes_per_record = db_size / max(1, total_ops)
    joules_per_op = energy_joules / max(1, total_ops)

    all_latencies = audio_latencies_ms + image_latencies_ms + doc_latencies_ms

    results = {
        "iterations_per_modality": iterations,
        "total_operations": total_ops,
        "elapsed_seconds": round(elapsed_total, 4),
        "overall_throughput_ops_sec": round(total_ops / max(0.001, elapsed_total), 2),
        "startup": {
            "cold_boot_latency_ms": round(cold_boot_ms, 3),
            "warm_boot_latency_ms": round(warm_boot_ms, 3),
        },
        "latencies_ms": {
            "all": {
                "mean": round(float(np.mean(all_latencies)), 3),
                "p50": round(float(np.percentile(all_latencies, 50)), 3),
                "p95": round(float(np.percentile(all_latencies, 95)), 3),
                "p99": round(float(np.percentile(all_latencies, 99)), 3),
            },
            "audio": {
                "mean": round(float(np.mean(audio_latencies_ms)), 3),
                "p50": round(float(np.percentile(audio_latencies_ms, 50)), 3),
                "p95": round(float(np.percentile(audio_latencies_ms, 95)), 3),
            },
            "image": {
                "mean": round(float(np.mean(image_latencies_ms)), 3),
                "p50": round(float(np.percentile(image_latencies_ms, 50)), 3),
                "p95": round(float(np.percentile(image_latencies_ms, 95)), 3),
            },
            "document": {
                "mean": round(float(np.mean(doc_latencies_ms)), 3),
                "p50": round(float(np.percentile(doc_latencies_ms, 50)), 3),
                "p95": round(float(np.percentile(doc_latencies_ms, 95)), 3),
            },
        },
        "resources": {
            "rss_initial_bytes": rss_initial,
            "rss_final_bytes": rss_final,
            "rss_growth_bytes": rss_growth,
            "database_size_bytes": db_size,
            "bytes_per_record": round(bytes_per_record, 1),
        },
        "energy": {
            "method": energy_method,
            "total_joules": round(energy_joules, 4),
            "joules_per_op": round(joules_per_op, 6),
        },
    }

    shutil.rmtree(temp_dir, ignore_errors=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100, help="Number of iterations per modality")
    parser.add_argument("--output", type=str, default="", help="Path to save benchmark JSON results")
    args = parser.parse_args()

    results = run_benchmark(iterations=args.iterations)
    output_str = json.dumps(results, indent=2)
    print(output_str)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_str, encoding="utf-8")
        print(f"\nSaved benchmark results to: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
