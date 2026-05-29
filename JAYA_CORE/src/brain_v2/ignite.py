"""
ignite.py — JAYA V16.0 The Loyal Sovereign

Identity: JAYA (Jaya's Advanced Yield Architecture)
Architecture: Neural Liquid (TopK Sparse Ternary)
"""

import argparse
import logging
import os
import sys
import time

# Load centralized config (no hardcoded secrets)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.core_config import core_config
core_config.validate()

# Add JAYA_CORE root to path so "src.*" imports resolve
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BASE_DIR)

# Basic logging — show INFO and above
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

try:
    from src.brain_v2.engine.runtime import IronEngine
except ImportError as e:
    print(f"CRITICAL ERROR: Failed to load JAYA Binary Cortex: {e}")
    sys.exit(1)

# ---- Configuration (loaded from .env via core_config) ----
JAYA_MODEL_PATH = core_config.MODEL_PATH
JAYA_PASSWORD   = core_config.SOUL_PASSWORD


def _banner(engine: IronEngine) -> None:
    cfg = engine.config.snapshot()
    print("\n" + "=" * 54)
    print("   J A Y A  V 1 6 . 0  —  T H E  L O Y A L  S O V E R E I G N")
    print("=" * 54)
    print(f"   TopK ratio      : {cfg['topk_ratio']:.0%}")
    print(f"   Dream interval  : {cfg['dream_interval']:.0f}s")
    print(f"   Uncertainty thr : {cfg['uncertainty_threshold']:.0%}")
    print(f"   Twin enabled    : {engine.enable_twin}")
    print(f"   Omniverse       : {engine.omniverse_requested}")
    print("=" * 54 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Start the JAYA engine")
    parser.add_argument("--enable-voice",  action="store_true",
                        help="Enable voice I/O")
    parser.add_argument("--enable-twin",   action="store_true",
                        help="Start the digital twin subsystem")
    parser.add_argument("--omniverse",     action="store_true",
                        help="Attempt Omniverse SDK init (stub if unavailable)")
    parser.add_argument("--dream-interval", type=float, default=300.0,
                        help="Seconds between dreaming cycles (default 300)")
    args = parser.parse_args()

    engine = IronEngine(
        JAYA_MODEL_PATH,
        JAYA_PASSWORD,
        enable_voice        = args.enable_voice,
        enable_twin         = args.enable_twin,
        omniverse_requested = args.omniverse,
    )
    engine.config.dream_interval = args.dream_interval

    engine.ignite()

    if not engine.is_awake:
        print("[FATAL] Engine failed to wake up.")
        sys.exit(1)

    _banner(engine)

    print("[BOOT] Running initial dream burst …")
    for i in range(3):
        print(f"  [Dream {i+1}/3] Calibrating sparse pathways …")
        engine.dream()
        time.sleep(0.3)

    print("\n" + engine.greet())
    print("[SYSTEM] Magnum Cycle berjalan…  (Ctrl-C untuk berhenti)\n")

    try:
        engine.run_magnum_cycle()
    except KeyboardInterrupt:
        pass

    print("\n[!] JAYA memasuki mode hibernasi. Selamat tinggal, Bos.")
    st = engine.status()
    print(f"    Uptime      : {st['uptime']}s")
    print(f"    Dreams      : {st['dreams']}")
    print(f"    Feedback rx : {st['feedbacks']}")
    if st["twin"]:
        tw = st["twin"]
        print(f"    Experiments : {tw['experiments']}")
        print(f"    Mem total   : {tw['memory']['total']}")
    print("=== SYSTEM HYBRIDIZED & ENCRYPTED ===\n")


if __name__ == "__main__":
    main()
