"""
verify_real_code_execution.py — Live Empirical Verification Script
Proves that auto_research_patch.py is physically written and functionally executed by Python in RAM.
"""

import sys
import os
import time
import importlib.util

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure sys.path includes JAYA_CORE
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(ROOT_DIR, "JAYA_CORE")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)


def verify():
    patch_path = os.path.join(CORE_DIR, "src", "brain_v2", "engine", "auto_research_patch.py")
    
    print("=" * 70)
    print("📂 1. VERIFIKASI PEMBARUAN FISIK BERKAS (PHYSICAL FILE CHECK)")
    print("=" * 70)
    print(f"Location       : {patch_path}")
    print(f"File Exists    : {os.path.exists(patch_path)}")
    
    if not os.path.exists(patch_path):
        print("❌ FILE NOT FOUND!")
        return

    stat = os.stat(patch_path)
    print(f"Last Modified  : {time.ctime(stat.st_mtime)}")
    print(f"File Size      : {stat.st_size} bytes")

    with open(patch_path, "r", encoding="utf-8") as f:
        raw_code = f.read()

    print("\n" + "=" * 70)
    print("📜 2. BUKTI KODE MURNI DI DALAM BERKAS (RAW SOURCE CODE)")
    print("=" * 70)
    lines = raw_code.strip().split("\n")
    for i, line in enumerate(lines[:20], 1):
        print(f"{i:02d}: {line}")
    if len(lines) > 20:
        print(f"... ({len(lines) - 20} lines remaining)")

    print("\n" + "=" * 70)
    print("🧠 3. EKSEKUSI NYATA DARI KODE DALAM RAM (REAL PYTHON EXECUTION)")
    print("=" * 70)
    
    spec = importlib.util.spec_from_file_location("auto_research_patch", patch_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cls_name = "SynthesizedResearchModule" if hasattr(module, "SynthesizedResearchModule") else "LiveDynamicResearchModule"
    mod_cls = getattr(module, cls_name)
    instance = mod_cls()

    print(f"Instantiated Class  : {cls_name}")
    print(f"Paper Title Metadata: {getattr(instance, 'paper_title', 'N/A')}")
    print(f"Paper Hash Metadata : {getattr(instance, 'paper_hash', 'N/A')}")

    if hasattr(instance, "optimize_kernel_data"):
        sample_data = [0.05, 0.42, 0.91, 0.12, 0.85, 0.33, 0.99]
        exec_result = instance.optimize_kernel_data(sample_data)
        print("\n⚡ EXECUTION TEST RESULT (REAL-TIME COMPUTATION):")
        print(f"   Input Array      : {sample_data}")
        print(f"   Output Metrics   : {exec_result}")
    
    print("\n" + "=" * 70)
    print("🎉 BUKTI EMPIRIS: BERKAS TERKINI TERHUBUNG & BERJALAN AKTIF DI MEMORI!")
    print("=" * 70)


if __name__ == "__main__":
    verify()
