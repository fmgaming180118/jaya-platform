"""
Test script for Meta-Analysis
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from research.meta_analysis import MetaAnalyst
from memory import DiscoveryMemory

# 1. Setup Dummy Data in Memory
print("=" * 60)
print("Setting up dummy research reports in memory...")
print("=" * 60)

# Use main evolution memory to test integration
memory = DiscoveryMemory("data/evolution_memory.json")

# Dummy Report 1
memory.add_experience(
    code="Report 1 Content: JIT compilation using Numba is effective but has overhead.",
    result="RESEARCH_REPORT",
    metadata={
        "topic": "JIT Compilation",
        "timestamp": time.time() - 1000,
        "report_path": "dummy_1.md"
    }
)

# Dummy Report 2
memory.add_experience(
    code="Report 2 Content: LLVM IR optimization can significantly reduce JIT overhead.",
    result="RESEARCH_REPORT",
    metadata={
        "topic": "LLVM Optimization",
        "timestamp": time.time() - 500,
        "report_path": "dummy_2.md"
    }
)

# Dummy Report 3
memory.add_experience(
    code="Report 3 Content: Hybrid approach using both Numba and custom LLVM passes yields best results.",
    result="RESEARCH_REPORT",
    metadata={
        "topic": "Hybrid JIT",
        "timestamp": time.time(),
        "report_path": "dummy_3.md"
    }
)

# 2. Run Meta-Analysis
print("\n" + "=" * 60)
print("Running Meta-Analysis...")
print("=" * 60)

analyst = MetaAnalyst()
history = analyst.get_research_history("JIT")
print(f"Debug: Found {len(history)} reports for topic 'JIT'")

report = analyst.run_meta_analysis("JIT", lookback_days=1)

print("\n" + "=" * 60)
print("Meta-Analysis Result:")
print("=" * 60)
print(report)

# 3. Verify Memory Storage of Meta-Report
print("\n" + "=" * 60)
print("Verifying Meta-Report Memory Storage...")
print("=" * 60)

history = analyst.memory.history
meta_reports = [h for h in history if h.get('result') == 'META_ANALYSIS']

if meta_reports:
    print(f"✅ Meta-Report found in memory!")
    print(f"Timestamp: {meta_reports[-1]['timestamp']}")
else:
    print("❌ Meta-Report NOT found in memory.")
