"""
Research-Guided Digital Twin Compiler
Integrates Research Assistant with Digital Twin for autonomous improvement
"""
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from digital_twin_compiler import DigitalTwinCompiler
from research.agent import ResearchAgent


class ResearchGuidedTwin(DigitalTwinCompiler):
    """
    Enhanced Digital Twin that conducts research before evolution.
    
    Workflow:
    1. Identify stagnation
    2. Research optimization techniques
    3. Apply research insights to mutations
    4. Evolve compiler
    """
    
    def __init__(self, research_enabled: bool = True):
        """
        Initialize research-guided twin.
        
        Args:
            research_enabled: If True, conduct research during stagnation
        """
        super().__init__()
        self.research_enabled = research_enabled
        self.research_cache = {}  # Cache research to avoid redundant queries
    
    def conduct_research(self, topic: str) -> str:
        """
        Conduct research on a topic.
        
        Args:
            topic: Research topic
            
        Returns:
            Research insights as text
        """
        # Check cache first
        if topic in self.research_cache:
            print(f"[RESEARCH TWIN] 📚 Using cached research: {topic}")
            return self.research_cache[topic]
        
        print(f"[RESEARCH TWIN] 🔬 Researching: {topic}")
        
        try:
            # Create research agent
            agent = ResearchAgent(
                topic=topic,
                focus_areas="Compiler optimization, JIT compilation, LLVM IR"
            )
            
            # Run research (no human-in-loop for autonomous mode)
            report = agent.run(human_in_loop=False)
            
            # Cache for future use
            self.research_cache[topic] = report
            
            return report
        
        except Exception as e:
            print(f"[RESEARCH TWIN] ⚠️  Research failed: {e}")
            return "No research insights available."
    
    def run_evolution_loop(self, generations: int = 1000, forever: bool = False, research_interval: int = 10):
        """
        Run evolution loop with periodic research.
        
        Args:
            generations: Number of generations
            forever: Run indefinitely
            research_interval: Conduct research every N stagnation cycles
        """
        print("[RESEARCH TWIN] 🧬 Starting Research-Guided Evolution")
        print(f"[RESEARCH TWIN] Research: {'Enabled' if self.research_enabled else 'Disabled'}")
        print(f"[RESEARCH TWIN] Research Interval: Every {research_interval} stagnation cycles\n")
        
        current_syntax = self.load_or_initialize_syntax()
        current_compiler = self.load_or_initialize_compiler()
        
        best_score = self.evaluate_compiler(current_syntax, current_compiler)
        print(f"[RESEARCH TWIN] 🎯 Initial Score: {best_score:.2f}\n")
        
        stagnation_counter = 0
        generation = 0
        research_stagnation = 0  # Track stagnation for research trigger
        
        while forever or generation < generations:
            generation += 1
            print(f"\n{'='*60}")
            print(f"[RESEARCH TWIN] Generation {generation} | Best: {best_score:.2f} | Stagnation: {stagnation_counter}")
            print(f"{'='*60}")
            
            # Determine mutation mode
            if stagnation_counter >= 20:
                mode = "Radical Rewrite"
            elif stagnation_counter >= 10:
                mode = "Aggressive"
            else:
                mode = "Conservative"
            
            # Research intervention on stagnation
            research_context = None
            if self.research_enabled and stagnation_counter >= 5 and research_stagnation >= research_interval:
                print(f"\n[RESEARCH TWIN] 🔬 RESEARCH INTERVENTION TRIGGERED")
                research_context = self.conduct_research(
                    topic=f"Advanced compiler optimization techniques for JIT compilation"
                )
                research_stagnation = 0  # Reset research stagnation counter
                print(f"[RESEARCH TWIN] ✅ Research complete, applying insights...\n")
            
            # Evolve with research context
            new_syntax = self.evolve_syntax(current_syntax, mode=mode)
            new_compiler = self.evolve_compiler(
                new_syntax,
                current_compiler,
                mode=mode,
                research_context=research_context
            )
            
            # Evaluation
            new_score = self.evaluate_compiler(new_syntax, new_compiler)
            
            # Acceptance criteria
            is_improvement = new_score > best_score
            is_radical_escape = mode == "Radical Rewrite" and new_score > 0
            
            if is_improvement or is_radical_escape:
                if is_radical_escape and not is_improvement:
                    print(f"[RESEARCH TWIN] ☢️  RADICAL ACCEPTANCE! Score: {new_score:.2f}")
                else:
                    print(f"[RESEARCH TWIN] 🚀 IMPROVEMENT! (+{new_score - best_score:.2f})")
                
                best_score = new_score
                current_syntax = new_syntax
                current_compiler = new_compiler
                stagnation_counter = 0
                research_stagnation = 0
                
                # Save to Memory
                try:
                    self.memory.add_variant(
                        syntax=new_syntax,
                        compiler=new_compiler,
                        generation=generation,
                        score=new_score
                    )
                except Exception as e:
                    print(f"[RESEARCH TWIN] ⚠️  Memory save failed: {e}")
            else:
                print(f"[RESEARCH TWIN] 📉 Regression ({new_score:.2f}). Discarded")
                stagnation_counter += 1
                research_stagnation += 1
            
            __import__('time').sleep(1)
    
    def evolve_compiler(self, syntax: str, current_compiler: str, mode: str = "Conservative", research_context: str = None) -> str:
        """
        Evolve compiler with optional research context.
        
        Args:
            syntax: Language syntax
            current_compiler: Current compiler code
            mode: Mutation aggressiveness
            research_context: Research insights to guide evolution
            
        Returns:
            New compiler code
        """
        prompt = f"""You are evolving a neural compiler for a custom language.

Current Syntax:
{syntax[:500]}...

Current Compiler:
{current_compiler[:1000]}...

Mode: {mode}

"""
        
        if research_context:
            prompt += f"""
Research Insights (apply these techniques):
{research_context[:2000]}...

IMPORTANT: Use the research insights above to guide your optimization.
Apply the most relevant techniques to improve compilation speed and code quality.

"""
        
        prompt += f"""
Task: Generate an improved compiler that is faster and produces better code.
Focus on: JIT compilation, LLVM IR optimization, Numba integration.

Return ONLY the complete compiler.py code, no explanations.
"""
        
        return self.teacher.suggest_optimization(prompt, focus="Compiler Evolution")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--forever", action="store_true", help="Run indefinitely")
    parser.add_argument("--gens", type=int, default=1000, help="Number of generations")
    parser.add_argument("--no-research", action="store_true", help="Disable research")
    parser.add_argument("--research-interval", type=int, default=10, help="Research every N stagnation cycles")
    args = parser.parse_args()
    
    twin = ResearchGuidedTwin(research_enabled=not args.no_research)
    twin.run_evolution_loop(
        generations=args.gens,
        forever=args.forever,
        research_interval=args.research_interval
    )
