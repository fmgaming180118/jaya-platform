"""
demo_autonomous_research_upgrade.py — Live Autonomous Research & JAYA_CORE Upgrade Demonstration
"""

import sys
import os
import time
import json

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure sys.path includes JAYA_RESEARCH and JAYA_CORE
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.join(ROOT_DIR, "JAYA_RESEARCH")
CORE_DIR = os.path.join(ROOT_DIR, "JAYA_CORE")

for d in [ROOT_DIR, RESEARCH_DIR, CORE_DIR]:
    if os.path.exists(d) and d not in sys.path:
        sys.path.insert(0, d)

from JAYA_RESEARCH.src.research.ecosystem_bridge import ResearchEcosystemBridge, ResearchFinding
from src.brain_v2.engine.evolution_gate import EvolutionGate


def run_demo():
    print("=" * 70)
    print("🔬 1. JAYA_RESEARCH: MEMULAI PENELITIAN OTONOM BARU")
    print("=" * 70)
    
    finding = ResearchFinding(
        finding_id="res-2026-quantized-sparsity",
        paper_title="Dynamic Quantized Attention Sparsity for Low-Latency Brain Kernels",
        authors=["JAYA Autonomous Research Agent", "ArXiv Synthesis Engine"],
        topic="quantum_attention_sparsity",
        gap_summary="Existing static attention bounds cause unnecessary RAM overhead during idle turns. Dynamic top-k sparsity reduces memory by 18% with zero accuracy drop.",
        suggested_patch_type="sparsity_optimization_patch",
        patch_code="""
def dynamic_topk_sparsity(activation_tensor, threshold=0.15):
    # Autonomous Research Patch: Dynamic Top-K Activation Sparsity
    import numpy as np
    return np.where(activation_tensor > threshold, activation_tensor, 0.0)
""",
        confidence_score=0.98
    )

    print(f"📌 Judul Penelitian  : {finding.paper_title}")
    print(f"👥 Penulis          : {', '.join(finding.authors)}")
    print(f"💡 Celah Penelitian  : {finding.gap_summary}")
    print(f"⚡ Kode Patch Usulan: {finding.patch_code.strip()}")
    print(f"🎯 Skor Kepercayaan  : {finding.confidence_score * 100}%")

    print("\n" + "=" * 70)
    print("🌐 2. MENGHUBUNGKAN JEMBATAN OTOMATIS: JAYA_RESEARCH ➔ JAYA_CORE")
    print("=" * 70)

    bridge = ResearchEcosystemBridge()

    print("\n" + "=" * 70)
    print("🛡️ 3. MENGAJUKAN KANDIDAT KEPADA JAYA_CORE EVOLUTION GATE")
    print("=" * 70)

    result = bridge.submit_research_upgrade(finding)

    print("\n" + "=" * 70)
    print("✅ 4. HASIL EVALUASI EVOLUTION GATE (JAYA_CORE)")
    print("=" * 70)
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 70)
    if result["gate_passed"]:
        print("🎉 BERHASIL! JAYA_RESEARCH BERHASIL MELAKUKAN PENELITIAN DAN MEMPERBARUI JAYA_CORE SECARA OTONOM!")
    else:
        print("⚠️ EVOLUTION GATE MENOLAK KANDIDAT.")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
