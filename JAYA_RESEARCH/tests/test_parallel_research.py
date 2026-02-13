"""
Test script for parallel research execution and web search
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from research.agent import ResearchAgent

# Test with a topic that won't have RAG results (to trigger web search)
topic = "Latest advancements in quantum computing 2026"

print("=" * 60)
print("Testing Parallel Queries + Web Search Fallback")
print("=" * 60)
print(f"\nTopic: {topic}\n")

agent = ResearchAgent(topic=topic)

# Generate plan
agent.plan = agent.generate_plan()

print(f"\nGenerated {len(agent.queries)} research questions:")
for i, q in enumerate(agent.queries, 1):
    print(f"  {i}. {q}")

print("\n" + "=" * 60)
print("Executing queries in PARALLEL...")
print("=" * 60)

# Execute queries (will run in parallel + web search fallback)
import time
start = time.time()
findings = agent.execute_queries()
duration = time.time() - start

print(f"\n✅ Completed in {duration:.2f} seconds")
print(f"   Total findings: {len(findings)}")

for finding in findings:
    source_count = finding.get('source_count', 0)
    print(f"   - {finding['query'][:50]}... → {source_count} sources")
