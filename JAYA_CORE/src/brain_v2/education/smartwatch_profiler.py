"""
JAYA Smartwatch Profile Analyzer
Fase 3 — Mengukur kesiapan deployment ke smartwatch 200MB RAM

Mengukur:
  1. RAM footprint aktual saat runtime
  2. Ukuran model packed vs unpacked
  3. Inferensi latency (token per detik)
  4. Kesiapan deployment di berbagai target device
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict

import numpy as np

logger = logging.getLogger("SmartwatchProfiler")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

TARGET_RAM_MB = 200.0  # Target smartwatch RAM

DEVICE_PROFILES = {
    "smartwatch_basic":  {"ram_mb": 200,  "cpu_mhz": 400,  "label": "Smartwatch Basic (200MB)"},
    "smartwatch_mid":    {"ram_mb": 512,  "cpu_mhz": 800,  "label": "Smartwatch Mid (512MB)"},
    "raspberry_pi_zero": {"ram_mb": 512,  "cpu_mhz": 1000, "label": "Raspberry Pi Zero"},
    "raspberry_pi_4":    {"ram_mb": 4096, "cpu_mhz": 1800, "label": "Raspberry Pi 4"},
    "smartphone_low":    {"ram_mb": 2048, "cpu_mhz": 1200, "label": "Smartphone Low-end (2GB)"},
    "laptop":            {"ram_mb": 8192, "cpu_mhz": 2400, "label": "Laptop/Desktop"},
}


class SmartwatchProfiler:
    """
    Mengukur footprint JAYA NanoModel untuk deployment di edge devices.
    """

    def __init__(self):
        self._results: Dict[str, Any] = {}

    def profile_model(self, model: Any, config_name: str = "INDONESIAN") -> Dict[str, Any]:
        """Ukur RAM dan performance NanoModel secara aktual."""
        from src.brain_v2.model.nano_inference import INDONESIAN_CONFIG

        if not model._initialized:
            model.random_init()

        # ── Ukuran parameter ───────────────────────────────────────────────
        buffers  = model.get_weight_buffers()
        raw_bytes = sum(arr.nbytes for _, arr in buffers)
        packed_bytes = raw_bytes // 4  # 2-bit packing: 4 nilai per byte

        # ── RAM footprint aktual dengan tracemalloc ────────────────────────
        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        # Jalankan beberapa forward pass untuk mengukur peak RAM
        dummy_input = [1, 2, 3, 4, 5, 6, 7, 8]
        for _ in range(10):
            _ = model.forward(dummy_input)

        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "lineno")
        extra_ram = sum(s.size_diff for s in stats if s.size_diff > 0)
        python_overhead_mb = 20.0  # estimasi Python runtime
        total_ram_mb = (raw_bytes / 1_000_000) + python_overhead_mb + (extra_ram / 1_000_000)

        # ── Latency benchmark ─────────────────────────────────────────────
        n_runs     = 100
        t0         = time.perf_counter()
        for _ in range(n_runs):
            _ = model.forward(dummy_input)
        t1         = time.perf_counter()
        ms_per_run = (t1 - t0) * 1000 / n_runs
        tokens_per_sec = 1000.0 / ms_per_run * len(dummy_input)

        result = {
            "config":            config_name,
            "vocab_size":        model.vocab_size,
            "d_model":           model.d_model,
            "n_layers":          model.n_layers,
            "n_params":          sum(arr.size for _, arr in buffers),
            "raw_size_kb":       round(raw_bytes / 1024, 1),
            "packed_size_kb":    round(packed_bytes / 1024, 1),
            "estimated_ram_mb":  round(total_ram_mb, 1),
            "latency_ms":        round(ms_per_run, 2),
            "tokens_per_sec":    round(tokens_per_sec, 1),
        }
        self._results["model"] = result
        return result

    def check_device_compatibility(self, model_ram_mb: float) -> Dict[str, Any]:
        """Periksa kompatibilitas dengan berbagai profil perangkat."""
        compat: Dict[str, Any] = {}
        for device_id, profile in DEVICE_PROFILES.items():
            ram = profile["ram_mb"]
            # JAYA butuh model RAM + OS overhead (~50MB) + buffer 20%
            needed = model_ram_mb + 50
            fits   = needed <= ram * 0.8  # gunakan max 80% RAM
            compat[device_id] = {
                "label":       profile["label"],
                "ram_mb":      ram,
                "needed_mb":   round(needed, 1),
                "fits":        fits,
                "headroom_mb": round(ram - needed, 1),
                "status":      "✅ LOLOS" if fits else "❌ TIDAK CUKUP",
            }
        return compat

    def full_report(self, model: Any) -> Dict[str, Any]:
        """Laporan profil lengkap."""
        model_profile  = self.profile_model(model)
        compat         = self.check_device_compatibility(model_profile["estimated_ram_mb"])

        smartwatch_ok  = compat.get("smartwatch_basic", {}).get("fits", False)

        report = {
            "model_profile":     model_profile,
            "device_compat":     compat,
            "smartwatch_ready":  smartwatch_ok,
            "recommendation":    self._make_recommendation(model_profile, smartwatch_ok),
        }
        return report

    def _make_recommendation(self, profile: Dict[str, Any], sw_ok: bool) -> str:
        ram   = profile["estimated_ram_mb"]
        vocab = profile["vocab_size"]
        if sw_ok:
            return (
                f"✅ JAYA siap untuk smartwatch 200MB! "
                f"RAM terpakai: ~{ram:.0f}MB dari 200MB. "
                f"Tersisa ~{200 - ram:.0f}MB untuk OS dan aplikasi lain."
            )
        elif ram <= 100:
            return f"⚠️ RAM {ram:.0f}MB aman, namun perlu cek overhead OS smartwatch."
        else:
            return (
                f"❌ RAM {ram:.0f}MB melebihi target. "
                f"Pertimbangkan: kurangi vocab_size ({vocab} → {vocab // 2}) "
                f"atau kurangi d_model."
            )

    def print_report(self, report: Dict[str, Any]) -> None:
        m = report["model_profile"]
        print("\n" + "=" * 60)
        print("  JAYA SMARTWATCH DEPLOYMENT PROFILER")
        print("=" * 60)
        print(f"  Config    : {m['config']}")
        print(f"  Vocab     : {m['vocab_size']:,} token")
        print(f"  d_model   : {m['d_model']}")
        print(f"  n_layers  : {m['n_layers']}")
        print(f"  Params    : {m['n_params']:,}")
        print(f"  Size raw  : {m['raw_size_kb']:.0f} KB")
        print(f"  Packed    : {m['packed_size_kb']:.0f} KB")
        print(f"  RAM est.  : {m['estimated_ram_mb']:.1f} MB")
        print(f"  Latency   : {m['latency_ms']:.1f} ms/inference")
        print(f"  Throughput: {m['tokens_per_sec']:.0f} token/detik")
        print()
        print("  KOMPATIBILITAS PERANGKAT:")
        for dev_id, info in report["device_compat"].items():
            print(f"  {info['status']}  {info['label']}")
            print(f"         RAM: {info['needed_mb']:.0f}MB dibutuhkan / {info['ram_mb']}MB tersedia")
        print()
        print(f"  REKOMENDASI: {report['recommendation']}")
        print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    from src.brain_v2.model.nano_inference import NanoModel, INDONESIAN_CONFIG

    model = NanoModel(config=INDONESIAN_CONFIG)
    model.random_init()

    profiler = SmartwatchProfiler()
    report   = profiler.full_report(model)
    profiler.print_report(report)

    # Simpan laporan
    out = core_config.DATA_DIR / "smartwatch_profile.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Laporan disimpan: {out}")
