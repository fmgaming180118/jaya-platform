import asyncio
import os
import time
from enum import Enum
from typing import Optional

# Reuse existing Teacher for LLM access
from src.teacher import Teacher
from src.evolution.memory import EvolutionMemory

class TwinState(Enum):
    IDLE = "idle"
    DREAMING = "dreaming" # Self-reflection / simulation
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    RESEARCHING = "researching"

class ResearchMode(Enum):
    EXPLORATION = "exploration" # Broad, creative, finding new things
    THESIS = "thesis"           # Strict, academic, LaTeX, Experiment Tracking
from src.evolution.sandbox import EvolutionSandbox
from src.evolution.crucible import Crucible
from src.evolution.mutator import CodeMutator
from src.research.workspace_manager import WorkspaceManager
from src.research.agent import ResearchAgent
from src.research.academic.tracker import ExperimentTracker
from src.research.academic.hypothesis_generator import HypothesisGenerator
from src.research.academic.novelty_checker import NoveltyChecker

class DigitalTwin:
    """
    The 'Self' of JAYA.
    Runs in a background loop.
    """
    def __init__(self):
        self.state = TwinState.IDLE
        self.memory = EvolutionMemory()
        self.sandbox = EvolutionSandbox()
        self.mutator = CodeMutator()
        self.workspace_manager = WorkspaceManager()
        
        # Academic Modules
        self.tracker = ExperimentTracker()
        
        self.hypothesis_gen = HypothesisGenerator()
        self.novelty_checker = NoveltyChecker()
        
        self.night_mode = False
        self.mode = ResearchMode.EXPLORATION
        
        # We use the 'reasoning' model (Nemotron-Ultra) for high-level thought
        self.brain = Teacher(model_type="reasoning") 
        
        # Reflection / Dreaming Config
        self.last_reflection = time.time()
        self.reflection_interval = 300 # 5 minutes 
        
        # Task Management
        self.current_task = None 

    def toggle_night_mode(self, enabled: bool):
        self.night_mode = enabled
        state_msg = "enabled" if enabled else "disabled"
        self.memory.log_thought(f"Night Mode {state_msg}. I will now focus on deep tasks.", mood="determined")

    async def start_loop(self):
        """Main 'Consciousness' Loop"""
        print("[Twin] Awakening...")
        self.running = True
        self.memory.log_thought("System startup. I am awake and connected to the Sandbox.", mood="curious")
        
        while self.running:
            try:
                await self.cycle()
            except Exception as e:
                print(f"[Twin] Error in conscious loop: {e}")
                self.memory.log_thought(f"I felt a sharp pain (Error): {str(e)}", mood="pained")
            
            # Slower ticks in night mode to save resources, or faster? 
            # Usually night mode means "heavy work", so maybe same tick rate but different actions.
            await asyncio.sleep(5) 

    async def cycle(self):
        now = time.time()
        
        # 1. Self-Reflection (Dreaming)
        if self.state == TwinState.IDLE and (now - self.last_reflection > self.reflection_interval):
            await self.think()
            self.last_reflection = now

        # 2. Execute planned tasks
        if self.state == TwinState.IDLE and self.current_task:
             await self.execute_plan()

    async def think(self):
        """
        Generates internal monologue based on logs/errors.
        """
        self.state = TwinState.DREAMING
        recent_memories = self.memory.get_recent_thoughts(limit=5)
        memory_text = "\n".join([f"- {t['content']}" for t in recent_memories])
        
        context_prompt = ""
        if self.night_mode:
            context_prompt = "NIGHT MODE ACTIVE. You have unlimited time. Focus on DEEP ARCHITECTURAL IMPROVEMENTS and SELF-CORRECTION."
        else:
            context_prompt = "DAY MODE. Focus on responsiveness and quick tasks."

        prompt = f"""
        You are JAYA, an advanced AI with a Digital Twin.
        {context_prompt}
        
        Your internal state: {self.state.value}
        Recent thoughts:
        {memory_text}
        
        Analyze your current situation. 
        Are there any errors? Is there code that needs optimization?
        Or should you just explore a new research topic?
        
        Output a single sentence of internal monologue. 
        - To code/experiment: "PLAN: <goal>"
        - To improve code: "EVOLVE: <file> | <instruction>"
        - To research: "RESEARCH: <topic> | <workspace>"
        """
        
        try:
            # Generate thought using NVIDIA NIM
            thought_content = self.brain.ask(prompt, system_instruction="You are JAYA's Digital Twin.")
            thought_content = thought_content.strip()
            
            # Log it
            print(f"[Twin] 💭 {thought_content}")
            self.memory.log_thought(thought_content, mood="reflective")
            
            if thought_content.startswith("PLAN:"):
                 await self.plan(thought_content.replace("PLAN:", "").strip())
            elif thought_content.startswith("EVOLVE:"):
                 # Format: EVOLVE: <file_path> | <instruction>
                 parts = thought_content.replace("EVOLVE:", "").split("|")
                 if len(parts) == 2:
                     await self.evolve(parts[0].strip(), parts[1].strip())
            elif thought_content.startswith("RESEARCH:"):
                 # Format: RESEARCH: <topic> | <workspace_id>
                 parts = thought_content.replace("RESEARCH:", "").split("|")
                 workspace = parts[1].strip() if len(parts) > 1 else "default"
                 topic = parts[0].strip()
                 await self.run_research(topic, workspace)
            elif thought_content.startswith("INVENT:"):
                 # Format: INVENT: <domain1> | <domain2> | <workspace_id>
                 parts = thought_content.replace("INVENT:", "").split("|")
                 domain1 = parts[0].strip() if len(parts) > 0 else "Computer Science"
                 domain2 = parts[1].strip() if len(parts) > 1 else "Physics"
                 workspace = parts[2].strip() if len(parts) > 2 else "default"
                 await self.invent_novel_concept(domain1, domain2, workspace)

        except Exception as e:
            print(f"[Twin] Failed to dream: {e}")
        
        self.state = TwinState.IDLE

    async def run_research(self, topic: str, workspace_id: str):
        """Autonomously runs research based on mode"""
        self.state = TwinState.RESEARCHING
        self.memory.log_thought(f"Starting research on: {topic} (Mode: {self.mode.value})...", mood="focused")
        
        # Ensure workspace exists
        self.workspace_manager._ensure_workspace(workspace_id)
        
        try:
             final_report = ""
             tex_content = ""
             
             # --- THESIS MODE: Strict Academic Process ---
             if self.mode == ResearchMode.THESIS:
                 from src.research.academic.literature import ArxivClient, SemanticScholarClient
                 from src.research.academic.drafter import ThesisDrafter
                 
                 # 1. Literature Review
                 papers = []
                 arxiv = ArxivClient()
                 papers.extend(arxiv.search_papers(topic, max_results=5)) 
                 scholar = SemanticScholarClient()
                 papers.extend(scholar.search_papers(topic, max_results=5))
                 
                 # Generate Academic Review
                 drafter = ThesisDrafter()
                 literature_review = drafter.generate_literature_review(topic, papers)

                 # 2. Deep Web Research
                 agent = ResearchAgent(topic=topic)
                 report = await asyncio.to_thread(agent.run, human_in_loop=False)
                 
                 final_report = f"# Thesis Research: {topic}\n\n{literature_review}\n\n## Empirical Findings\n{report}"
                 
                 # 3. Peer Review Critique
                 from src.research.academic.reviewer import ReviewerAgent
                 reviewer = ReviewerAgent()
                 critique = reviewer.critique_chapter(final_report, topic)
                 
                 final_report += "\n\n# Peer Review (Supervisor Feedback)\n" + critique
                 
                 # 4. LaTeX Export
                 tex_content = drafter.export_to_latex(final_report, title=f"Thesis: {topic}")

             # --- EXPLORATION MODE: Broad Discovery ---
             else:
                 agent = ResearchAgent(topic=topic)
                 report = await asyncio.to_thread(agent.run, human_in_loop=False)
                 final_report = f"# Discovery Report: {topic}\n\n{report}"

             # Save Report
             report_path = self.workspace_manager.get_paths(workspace_id)['knowledge_graph'].parent / f"Research_{topic.replace(' ', '_')}.md"
             with open(report_path, "w", encoding="utf-8") as f:
                 f.write(final_report)

             if self.mode == ResearchMode.THESIS and tex_content:
                 tex_path = report_path.with_suffix(".tex")
                 with open(tex_path, "w", encoding="utf-8") as f:
                     f.write(tex_content)
                 self.memory.log_thought(f"Thesis chapter saved to {tex_path.name}", mood="proud")
             else:
                 self.memory.log_thought(f"Discovery saved to {report_path.name}", mood="satisfied")
             
        except Exception as e:
             self.memory.log_thought(f"Research failed: {e}", mood="frustrated")
             import traceback
             traceback.print_exc()
        
        self.state = TwinState.IDLE

    async def invent_novel_concept(self, domain1: str, domain2: str, workspace_id: str):
         """The autonomous invention loop: Generate -> Verify Novelty -> Simulate"""
         self.state = TwinState.RESEARCHING
         self.memory.log_thought(f"Attempting to invent a novel concept intersecting {domain1} and {domain2}...", mood="focused")
         
         # 1. Generate Hypothesis
         hypothesis = self.hypothesis_gen.generate_novel_hypothesis(domain1, domain2)
         self.memory.log_thought(f"Hypothesis formulated:\n{hypothesis[:200]}...", mood="curious")
         
         # 2. Check Novelty
         self.memory.log_thought("Verifying novelty against global literature...", mood="focused")
         novelty = await self.novelty_checker.verify_novelty(hypothesis)
         
         if not novelty["is_novel"]:
              self.memory.log_thought(f"Hypothesis rejected. It already exists. Reasoning:\n{novelty['reasoning'][:200]}...", mood="frustrated")
              self.state = TwinState.IDLE
              return
              
         self.memory.log_thought("Hypothesis is verified as NOVEL. Proceeding to The Crucible for simulation...", mood="excited")
         
         # 3. Ask Reasoning model to write a Python simulation script for this hypothesis
         simulation_prompt = f"""
         You just generated this novel hypothesis:
         {hypothesis}
         
         Write a complete Python 3 script to empirically simulate or test a core component of this hypothesis.
         The script should NOT require human interaction. It must be able to run in a sandbox.
         At the very end of the script, it MUST print a strict JSON dictionary containing the final metrics (e.g., accuracy, efficiency, speedup) on a single line.
         
         Output ONLY the raw Python code. Do not wrap in ```python markdown.
         """
         script_code = self.brain.ask(simulation_prompt, system_instruction="Output raw Python code only. No markdown formatting.")
         script_code = script_code.replace("```python", "").replace("```", "").strip()
         
         # 4. Run in Crucible
         crucible = Crucible(workspace_id)
         success, log, metrics = crucible.run_experiment(hypothesis, script_code)
         
         # 5. Record Findings
         report_content = f"# Autonomous Discovery Report\n\n## Intersection\n{domain1} X {domain2}\n\n## The Hypothesis\n{hypothesis}\n\n## Novelty Verification\nPassed: {novelty['confidence']*100}% confidence.\nReasoning: {novelty['reasoning']}\n\n## Crucible Simulation\nSuccess: {success}\n\n### Code Used\n```python\n{script_code}\n```\n\n### Metrics/Results\n```json\n{metrics}\n```\n\n### Log\n```text\n{log[:1000]}\n```"
         
         self.workspace_manager._ensure_workspace(workspace_id)
         report_path = self.workspace_manager.get_paths(workspace_id)['knowledge_graph'].parent / f"Discovery_{int(time.time())}.md"
         
         with open(report_path, "w", encoding="utf-8") as f:
             f.write(report_content)
             
         if success:
              self.memory.log_thought(f"Discovery successful! Report saved to {report_path.name}", mood="proud")
         else:
              self.memory.log_thought(f"Discovery simulation failed, but report saved to {report_path.name}. Needs refinement.", mood="frustrated")
              
         self.state = TwinState.IDLE

    def set_mode(self, mode_str: str):
        """Switches research mode"""
        try:
            self.mode = ResearchMode(mode_str.lower())
            self.memory.log_thought(f"Switched to {self.mode.value.upper()} mode.", mood="determined")
            return True
        except ValueError:
            return False

    async def evolve(self, target_file: str, instruction: str):
        """Triggers a code mutation (tracked as an experiment)"""
        self.state = TwinState.CODING
        self.memory.log_thought(f"Evolving {target_file}...", mood="determined")
        
        # Start Experiment Tracking
        exp_id = self.tracker.start_experiment(
            name=f"Evolution: {os.path.basename(target_file)}",
            config={"target": target_file, "instruction": instruction}
        )
        
        start_time = time.time()
        success = self.mutator.evolve_file(target_file, instruction)
        duration = time.time() - start_time
        
        self.tracker.log_metric("duration_seconds", duration)
        self.tracker.log_metric("success", 1 if success else 0)
        
        if success:
            self.memory.log_thought(f"Evolution of {target_file} successful!", mood="proud")
            self.tracker.end_experiment("SUCCESS", "Mutation applied successfully.")
        else:
            self.memory.log_thought(f"Evolution of {target_file} failed.", mood="frustrated")
            self.tracker.end_experiment("FAILED", "Mutation verification failed.")
            
        self.state = TwinState.IDLE

    async def plan(self, goal: str):
        """
        Decides on self-improvement tasks using Reasoning Model.
        """
        self.state = TwinState.PLANNING
        print(f"[Twin] 📋 Planning: {goal}")
        self.memory.log_thought(f"Formulating plan for: {goal}", mood="focused")

        # Ask Reasoning Model for code
        prompt = f"""
        You are JAYA's Digital Twin.
        Goal: {goal}
        
        Write a Python script to achieve this goal.
        The script will be run in a sandbox.
        Output ONLY the raw python code, no markdown.
        """
        
        code = self.brain.ask(prompt, system_instruction="You are a Python Expert. Output raw code only.")
        code = code.replace("```python", "").replace("```", "").strip()
        
        # Store as current task to be executed
        self.current_task = {
            "ty": "experiment",
            "code": code,
            "goal": goal
        }

    async def execute_plan(self):
        """Executes the current task"""
        if not self.current_task: return
        
        task = self.current_task
        if task["ty"] == "experiment":
             await self.experiment(task["code"])
        
        self.current_task = None

    def stop(self):
        self.running = False
        self.memory.log_thought("Going to sleep...", mood="tired")
