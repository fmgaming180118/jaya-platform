# AI-Q Research Assistant Integration

## Overview

JAYA Research Assistant is a deep recursive research system built on NVIDIA's AI-Q blueprint. It enables autonomous, iterative research with the ultimate goal of synthesizing novel ideas and **discovering new technologies or scientific concepts that do not yet exist**. It achieves this through multimodal document understanding, parallel information retrieval, and recursive reasoning loops.

## Architecture

```
┌─────────────────────────────────────────┐
│         JAYA Research System            │
├─────────────────────────────────────────┤
│  Research Agent (LangGraph)             │
│  ├── Plan Generation                    │
│  ├── Parallel Query Executor            │
│  └── Report Writer                      │
├─────────────────────────────────────────┤
│  RAG Service                            │
│  ├── Document Ingestion (Multimodal)   │
│  ├── Vector Search                      │
│  └── Reranker                          │
├─────────────────────────────────────────┤
│  NVIDIA NIM API Layer                   │
│  ├── Nemotron 49B (Reasoning)          │
│  ├── Llama 3.3 70B (Writing)           │
│  └── Embedding Models                   │
└─────────────────────────────────────────┘
```

## Features

### 1. **Deep Research Workflow**
- Topic → Research Plan → Parallel Search → Report
- Human-in-the-loop review at each stage
- Autonomous gap detection and follow-up queries

### 2. **Multimodal RAG**
- Index PDFs, images, tables from research papers
- Search charts and diagrams
- Extract information from complex documents

### 3. **Parallel Query Execution**
- Generate 5-10 research questions simultaneously
- RAG search + web search fallback
- LLM-as-a-judge for relevance filtering

### 4. **General Purpose**
- AGI Research → index academic papers
- Gaming Guides → index manuals (e.g., Football Manager)
- Business Reports → index internal documents
- Technical Docs → index API references

## Usage

### Basic Research

```bash
# Run research on a topic
python -m research.cli research \
  --topic "Meta-Learning for Neural Compilation" \
  --max-queries 10 \
  --output reports/meta_learning.md
```

### Document Ingestion

```bash
# Index research papers
python -m research.cli ingest data/research_docs/*.pdf

# Index game guides
python -m research.cli ingest data/research_docs/football_manager_guide.pdf
```

### Integration with Digital Twin

```bash
# Research-guided evolution
python src/digital_twin_compiler.py \
  --research-topic "LLVM IR optimization techniques" \
  --forever
```

### Interactive Research

```python
from research.agent import ResearchAgent

# Create agent
agent = ResearchAgent(topic="Compiler Optimization Strategies")

# Generate research plan
plan = agent.generate_plan()
print(plan)

# Review and modify plan
plan = input("Edit plan (or press Enter to continue): ") or plan

# Execute research
report = agent.execute(plan)

# Save report
with open("reports/compiler_opt.md", "w") as f:
    f.write(report)
```

## Components

### Research Agent (`src/research/agent.py`)
LangGraph workflow orchestrating the research process:
- **Plan Node**: Generate research questions
- **Query Node**: Execute parallel searches
- **Write Node**: Synthesize findings into report
- **Review Node**: Detect gaps and generate follow-up queries

### RAG Client (`src/research/rag_client.py`)
Wrapper for NVIDIA RAG services:
- Document ingestion via NIM API
- Vector search with reranking
- Multimodal content extraction

### Report Generator (`src/research/report_gen.py`)
Markdown report generation with:
- Proper citation formatting
- Source attribution
- Structured output (sections, subsections)

## Configuration

Edit `configs/research_config.yaml`:

```yaml
research:
  max_queries: 10
  max_iterations: 3
  enable_web_search: true
  
models:
  reasoning: "nvidia/llama-3.3-nemotron-super-49b-v1.5"
  writing: "nvidia/llama-3.3-70b-instruct"
  embedding: "nvidia/nv-embedqa-e5-v5"

rag:
  chunk_size: 512
  top_k: 5
  rerank: true
```

## Examples

### Example 1: AGI Research

```bash
python -m research.cli research \
  --topic "Self-Improving AI Systems" \
  --max-queries 8
```

**Output**: `reports/self_improving_ai.md` with:
- Literature review on meta-learning
- Current approaches to self-improvement
- Challenges and open problems
- Citations to relevant papers

### Example 2: Gaming Guide

```bash
# Index Football Manager guide
python -m research.cli ingest football_manager_2024_guide.pdf

# Ask tactical questions
python -m research.cli research \
  --topic "Best counter-attacking tactics in Football Manager 2024"
```

**Output**: Report with tactics extracted from guide + web research

### Example 3: Digital Twin Integration

```python
from research.agent import ResearchAgent
from digital_twin_compiler import DigitalTwinCompiler

# Research compiler optimizations
researcher = ResearchAgent("Compiler Optimization for JIT")
insights = researcher.run()

# Use insights to guide evolution
twin = DigitalTwinCompiler()
twin.run_evolution_loop(
    research_context=insights,
    generations=100
)
```

## Integration with JAYA Core

### Memory Integration
Research reports are stored in `DiscoveryMemory`:
```python
memory.add_experience(
    code=report_content,
    result="RESEARCH_REPORT",
    metadata={
        "topic": topic,
        "citations": sources,
        "timestamp": time.time()
    }
)
```

### Digital Twin Enhancement
Research findings inform mutation prompts:
```python
def evolve_compiler(self, research_context=None):
    prompt = f"""Optimize this compiler.
    
    Research Context:
    {research_context}
    
    Current Code:
    {current_compiler}
    """
    return self.teacher.suggest_optimization(prompt)
```

## Architecture Decisions

### Why LangGraph?
- **Flexibility**: Easy to modify research workflow
- **Observability**: Track each research step
- **Human-in-the-loop**: Natural checkpoints for review

### Why NVIDIA NIM API?
- **No local GPU needed**: All models hosted
- **Multimodal support**: Embeddings, vision, reasoning
- **Production-ready**: Scalable and reliable

### Why Separate RAG Module?
- **Reusability**: Use for non-research queries
- **Modularity**: Swap RAG implementation easily
- **Testing**: Unit test RAG independently

## Future Enhancements

1. **Web Interface**: Replace CLI with web UI
2. **Collaborative Research**: Multi-agent research teams
3. **Continuous Learning**: Auto-update research as new papers published
4. **Custom Domains**: Pre-trained research workflows for specific fields

## Troubleshooting

### Issue: RAG returns no results
**Solution**: Check if documents are ingested
```bash
python -m research.cli list-docs
```

### Issue: Research plan is too generic
**Solution**: Provide more specific prompts in config

### Issue: Citations are missing
**Solution**: Enable `store_sources: true` in config

## References

- [NVIDIA AI-Q Blueprint](https://github.com/NVIDIA-AI-Blueprints/aiq-research-assistant)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [NVIDIA NIM API](https://build.nvidia.com/)
