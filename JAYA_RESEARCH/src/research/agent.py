import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import config
"""
Research Agent - LangGraph Workflow for Deep Research
"""
import os
import sys
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from teacher import Teacher
from research.config import get_config

# Try to import enhanced RAG, fallback to simple RAG if not available
try:
    from research.enhanced_rag import EnhancedRAGClient as RAGClient
    print("[RESEARCH] Using Enhanced RAG with NVIDIA embeddings")
except ImportError:
    from research.rag_client import RAGClient
    print("[RESEARCH] Using simple keyword-based RAG")

# Try to import Graph RAG for knowledge graph capabilities
try:
    from research.graph_rag import GraphRAGEngine
    GRAPH_RAG_AVAILABLE = True
    print("[RESEARCH] Graph RAG available for knowledge graph construction")
except ImportError:
    GRAPH_RAG_AVAILABLE = False
    print("[RESEARCH] Graph RAG not available")


class ResearchAgent:
    """
    Deep Research Agent using LangGraph-inspired workflow.
    
    Workflow:
    1. Plan: Generate research questions
    2. Query: Execute parallel searches
    3. Write: Synthesize findings into report
    4. Review: Check for gaps
    5. Iterate or Finalize
    """
    
    def __init__(self, topic: str, focus_areas: str = "", workspace: str = "default"):
        """
        Initialize research agent.
        
        Args:
            topic: Research topic
            focus_areas: Optional focus areas (e.g., "Meta-Learning, Neural Compilation")
            workspace: Workspace name for isolated RAG memory (default: 'default')
        """
        self.topic = topic
        self.focus_areas = focus_areas or "General AGI research"
        self.workspace = workspace
        self.config = get_config()
        self.teacher = Teacher()
        
        # Load RAG scoped to the workspace's vector store
        try:
            from research.workspace_manager import WorkspaceManager
            wm = WorkspaceManager()
            ws_paths = wm.get_or_create_paths(workspace)
            self.rag = RAGClient(vector_store_path=ws_paths["vector_store"])
            print(f"[RESEARCH] 🗂️  Workspace: '{workspace}' → {ws_paths['vector_store']}")
        except Exception as e:
            print(f"[RESEARCH] ⚠️  Workspace init failed ({e}), using global RAG.")
            self.rag = RAGClient()
        
        # Research state
        self.plan = None
        self.queries = []
        self.findings = []
        self.report = None
        self.iteration = 0
        
        # Initialize Graph RAG if available
        self.graph_rag = None
        if GRAPH_RAG_AVAILABLE:
            try:
                from research.workspace_manager import WorkspaceManager
                wm = WorkspaceManager()
                ws_paths = wm.get_or_create_paths(workspace)
                graph_path = ws_paths["knowledge_graph"]
                self.graph_rag = GraphRAGEngine(storage_path=graph_path)
                print(f"[RESEARCH] 🕸️  Graph RAG initialized: {graph_path}")
            except Exception as e:
                print(f"[RESEARCH] ⚠️  Graph RAG init failed: {e}")
    
    def run(self, human_in_loop: bool = True) -> str:
        """
        Execute full research workflow.
        
        Args:
            human_in_loop: If True, ask for approval at checkpoints
            
        Returns:
            Final research report (markdown)
        """
        print(f"[RESEARCH] Starting research on: {self.topic}")
        print(f"[RESEARCH] Focus: {self.focus_areas}\n")
        
        # Step 1: Generate Plan
        self.plan = self.generate_plan()
        print(f"[RESEARCH] Generated research plan with {len(self.queries)} questions\n")
        
        if human_in_loop:
            print("--- RESEARCH PLAN ---")
            for i, q in enumerate(self.queries, 1):
                print(f"{i}. {q}")
            
            approval = input("\nProceed with this plan? [Y/n]: ").strip()
            if approval.lower() == 'n':
                print("Research cancelled.")
                return ""
        
        # Step 2: Execute Queries
        print("\n[RESEARCH] Executing research queries...")
        self.findings = self.execute_queries()
        print(f"[RESEARCH] Gathered {len(self.findings)} findings\n")
        
        # Step 3: Write Report
        print("[RESEARCH] Writing report...")
        self.report = self.write_report()
        
        # Step 4: Review (simple gap detection)
        gaps = self.review_report()
        
        # Step 5: Iterate if needed (limited iterations)
        max_iterations = self.config.max_iterations
        while gaps and self.iteration < max_iterations:
            print(f"\n[RESEARCH] Detected gaps. Iteration {self.iteration + 1}/{max_iterations}")
            self.findings.extend(self.execute_queries(gaps))
            self.report = self.write_report()
            gaps = self.review_report()
            self.iteration += 1
        
        # Save report
        self.save_report()
        
        print(f"\n[RESEARCH] ✅ Research complete!")
        print(f"[RESEARCH] Report saved to: {self.get_report_path()}")
        
        return self.report
    
    def generate_plan(self) -> Dict[str, Any]:
        """Generate research plan with specific questions"""
        # Detect AGI/Compiler topics for specialized prompts
        is_agi_topic = any(k in self.topic.lower() for k in ['agi', 'self-improvement', 'compiler', 'recursive', 'evolution'])
        
        prompt_name = 'agi_research_plan' if is_agi_topic else 'research_plan'
        
        prompt = self.config.get_prompt(
            prompt_name,
            topic=self.topic,
            focus_areas=self.focus_areas
        )
        
        if is_agi_topic:
            print("[RESEARCH] 🧠 Activated AGI Research Mode")
        
        # Ask Teacher to generate research questions
        response = self.teacher.ask(
            prompt,
            system_instruction="You are an expert Research Planner. Break down complex topics into specific, investigative questions."
        )
        
        # Parse questions (simple line-based parsing)
        lines = response.strip().split('\n')
        questions = []
        
        for line in lines:
            line = line.strip()
            # Look for numbered questions or bullet points
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('*')):
                # Clean up formatting
                question = line.lstrip('0123456789.-* ')
                if question:
                    questions.append(question)
        
        # Fallback if no questions found
        if not questions:
            questions = [
                f"What is {self.topic}?",
                f"What are the current approaches to {self.topic}?",
                f"What are the challenges in {self.topic}?",
                f"What are future directions for {self.topic}?"
            ]
        
        self.queries = questions[:self.config.max_queries]
        
        return {
            "topic": self.topic,
            "queries": self.queries,
            "focus": self.focus_areas
        }
    
    def execute_queries(self, queries: List[str] = None) -> List[Dict[str, Any]]:
        """Execute research queries in parallel using asyncio"""
        if queries is None:
            queries = self.queries
        
        # Import asyncio for parallel execution
        import asyncio
        
        # Check if web search available
        try:
            from research.web_search import WebSearchClient
            web_search = WebSearchClient()
        except ImportError:
            web_search = None
        
        async def execute_single_query(i: int, query: str) -> Dict[str, Any]:
            """Execute a single query asynchronously"""
            print(f"  [{i}/{len(queries)}] Searching: {query}")
            
            # Search RAG
            rag_results = self.rag.search(query, top_k=3)
            
            # Check if RAG returned sufficient results
            has_good_results = len(rag_results) > 0 and any(r['score'] > 0.5 for r in rag_results)
            
            # Fallback to web search if needed
            if not has_good_results and web_search and web_search.is_available():
                print(f"      └─ RAG insufficient, searching web...")
                web_results = web_search.search(query, max_results=3)
                rag_results.extend(web_results)
            
            # Prepare context for Teacher
            context = "\n\n".join([
                f"Source: {r['document'].get('file_name') or r['document'].get('title', 'Web')}\n{r['snippet']}"
                for r in rag_results[:5]  # Use top 5 results
            ])
            
            if not context:
                context = "No relevant documents found in memory or web."

            # Add graph context from prior ingested findings when available
            graph_context = ""
            if self.graph_rag:
                try:
                    graph_context = self.graph_rag.get_context(query)
                except Exception as e:
                    print(f"[RESEARCH] ⚠️  Graph context retrieval failed: {e}")
            
            answer_prompt = f"""Question: {query}
            
Context from Documents:
{context}

Context from Knowledge Graph:
{graph_context or 'No graph context yet.'}

Please provide a comprehensive answer to the question based on the context.
If the context is insufficient, note what additional information would be helpful."""
            
            # This is still synchronous (Teacher API call), but queries run in parallel
            answer = self.teacher.ask(
                answer_prompt,
                system_instruction="You are a precise Research Assistant. Answer the question using only the provided context. If the context is insufficient, state what is missing."
            )
            
            sources = [
                r['document'].get('file_name') or r['document'].get('title', 'Web')
                for r in rag_results
            ]

            # Ingest the answer into graph knowledge for next queries
            if self.graph_rag and answer:
                try:
                    source_id = f"{self.topic}:{i}:{int(time.time())}"
                    triple_count = self.graph_rag.ingest_document(answer, source_id=source_id)
                    if triple_count:
                        print(f"      └─ Graph updated with {triple_count} triples")
                except Exception as e:
                    print(f"[RESEARCH] ⚠️  Graph ingestion failed: {e}")
            
            return {
                "query": query,
                "answer": answer,
                "sources": sources,
                "source_count": len(rag_results)
            }
        
        async def execute_all_queries():
            """Execute all queries in parallel"""
            tasks = [
                execute_single_query(i+1, query)
                for i, query in enumerate(queries)
            ]
            return await asyncio.gather(*tasks)
        
        # Run async queries
        try:
            findings = asyncio.run(execute_all_queries())
        except RuntimeError:
            # Fallback to sequential if async fails
            print("[RESEARCH] ⚠️  Async failed, falling back to sequential execution")
            findings = []
            for i, query in enumerate(queries, 1):
                # Call the old sequential logic
                result = asyncio.run(execute_single_query(i, query))
                findings.append(result)
        
        return findings
    
    def write_report(self) -> str:
        """Synthesize findings into markdown report"""
        # Prepare findings text
        findings_text = "\n\n".join([
            f"Q: {f['query']}\nA: {f['answer']}\nSources: {', '.join(f['sources']) if f['sources'] else 'Web/General Knowledge'}"
            for f in self.findings
        ])
        
        prompt = self.config.get_prompt(
            'report_writing',
            topic=self.topic,
            findings=findings_text
        )
        
        report = self.teacher.ask(
            prompt,
            system_instruction="You are a Scientific Writer. Synthesize the findings into a clear, structured markdown report."
        )
        
        return report
    
    def review_report(self) -> List[str]:
        """Review report for gaps using LLM-as-a-judge (Peer Reviewer)"""
        if not self.report:
            return []
            
        print("[RESEARCH] 🕵️  Peer Reviewer is analyzing the report for scientific gaps...")
        
        prompt = self.config.get_prompt(
            'gap_detection',
            topic=self.topic,
            report=self.report
        )
        
        response = self.teacher.ask(
            prompt,
            system_instruction="You are a strict, critical Scientific Peer Reviewer. Output ONLY a numbered list of new questions."
        )
        
        # Parse questions (similar to generate_plan)
        lines = response.strip().split('\n')
        gaps = []
        
        for line in lines:
            line = line.strip()
            # Look for numbered questions or bullet points
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('*')):
                # Clean up formatting
                question = line.lstrip('0123456789.-* ')
                if question:
                    gaps.append(question)
                    
        if gaps:
            print(f"[RESEARCH] Peer Reviewer found {len(gaps)} gaps requiring further investigation.")
        else:
            print("[RESEARCH] Peer Reviewer found no significant gaps. Synthesis is solid.")
            
        return gaps
    
    def save_report(self):
        """Save report to file and memory"""
        report_path = self.get_report_path()
        
        # Create reports directory
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        
        # Save to file
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(self.report)
        
        # Store in DiscoveryMemory for future retrieval
        try:
            from memory import DiscoveryMemory
            # Use the main discovery memory file
            memory = DiscoveryMemory(config.DISCOVERY_MEMORY_PATH)
            
            # Store report as research experience
            memory.add_experience(
                code=self.report,
                result="RESEARCH_REPORT",
                metadata={
                    "topic": self.topic,
                    "focus_areas": self.focus_areas,
                    "queries_count": len(self.queries),
                    "findings_count": len(self.findings),
                    "report_path": report_path,
                    "timestamp": time.time()
                }
            )
            print(f"[RESEARCH] 💾 Report stored in memory")
        except Exception as e:
            print(f"[RESEARCH] ⚠️  Could not store in memory: {e}")
    
    def get_report_path(self) -> str:
        """Get output path for report"""
        reports_dir = self.config.reports_dir
        timestamp = int(time.time())
        safe_topic = "".join(c if c.isalnum() else "_" for c in self.topic)[:50]
        filename = f"{safe_topic}_{timestamp}.md"
        
        return os.path.join(reports_dir, filename)


# Example usage
if __name__ == "__main__":
    import sys
    
    topic = sys.argv[1] if len(sys.argv) > 1 else "Meta-Learning for Neural Compilation"
    
    agent = ResearchAgent(topic=topic)
    report = agent.run(human_in_loop=True)
    
    print("\n" + "="*60)
    print(report[:500] + "..." if len(report) > 500 else report)
