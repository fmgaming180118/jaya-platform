"""
Quick test of ResearchAgent memory storage
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from research.agent import ResearchAgent
from memory import DiscoveryMemory

# Test research with memory storage
print("=" * 60)
print("Testing Research Report Storage in Memory")
print("=" * 60)

topic = "JIT Compilation Optimization"
agent = ResearchAgent(topic=topic)

# Generate very small plan for quick test
agent.queries = [
    "What is JIT compilation?",
    "How can JIT compilation be optimized?"
]

print(f"\nTesting with 2 quick queries on: {topic}\n")

# Execute (sequential for  test speed)
findings = agent.execute_queries()

# Write report
agent.report = agent.write_report()

# Save (should store in memory)
print("\n" + "=" * 60)
print("Saving Report...")
print("=" * 60)
agent.save_report()

# Verify memory
print("\n" + "=" * 60)
print("Verifying Memory Storage...")
print("=" * 60)

memory = DiscoveryMemory()

# Find research reports
research_reports = [
    entry for entry in memory.history
    if entry.get('result') == 'RESEARCH_REPORT'
]

print(f"\nTotal research reports in memory: {len(research_reports)}")

if research_reports:
    latest = research_reports[-1]
    print(f"\nLatest Report:")
    print(f"  Topic: {latest.get('topic', 'N/A')}")
    print(f"  Queries: {latest.get('queries_count', 'N/A')}")
    print(f"  Findings: {latest.get('findings_count', 'N/A')}")
    print(f"  Path: {latest.get('report_path', 'N/A')}")
    print(f"  Timestamp: {latest.get('timestamp', 'N/A')}")
    
print("\n✅ Memory storage test complete!")
