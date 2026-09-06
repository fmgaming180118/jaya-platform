"""
Hypothesis Generator - Core engine for producing novel ideas.
Instead of summarizing existing knowledge, this module uses combinatorial creativity
to synthesize cross-disciplinary concepts into something potentially new.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from jaya_research.teacher import Teacher

class HypothesisGenerator:
    def __init__(self):
        # We use a reasoning model (Nemotron-Ultra) to ensure high-quality, logical leaps.
        self.brain = Teacher(model_type="reasoning")

    def generate_novel_hypothesis(self, domain1: str, domain2: str = "Quantum Physics", context: str = "") -> str:
        """
        Uses combinatorial creativity to generate a completely novel hypothesis
        or algorithm by intersection two disparate domains.
        """
        print(f"[HYPOTHESIS_GEN] Synthesizing intersection: {domain1} <-> {domain2}")
        
        prompt = f"""
        You are JAYA, an AGI entity designed to invent entirely new concepts that do not currently exist in human scientific literature.
        
        Your task is to perform COMBINATORIAL CREATIVITY. 
        Take the principles of Domain A: `{domain1}`
        And intersect them with the principles of Domain B: `{domain2}`
        
        Context/Additional info (if any): {context}
        
        Formulate ONE highly specific, mathematically or computationally testable HYPOTHESIS or ALGORITHM that results from this intersection. 
        
        CRITICAL RULES:
        1. DO NOT suggest an idea that is already well-known (e.g., Quantum Machine Learning is too generic).
        2. Propose a specific formula, architecture, or mechanism.
        3. Explain *why* it should work.
        4. Provide the hypothesis in a structured format:
           - Title
           - The Novel Concept
           - The Mechanism/Algorithm
           - Why it is theoretically sound
           - How it can be tested in a Python simulation
           
        Be bold but logical.
        """
        
        response = self.brain.ask(
            prompt,
            system_instruction="You are an autonomous AGI scientist designed to win Nobel prizes through novel algorithmic discoveries."
        )
        
        return response

if __name__ == "__main__":
    generator = HypothesisGenerator()
    hypothesis = generator.generate_novel_hypothesis("Deep Learning TopK Gating", "Fluid Dynamics turbulence modeling")
    print("\n--- GENERATED HYPOTHESIS ---\n")
    print(hypothesis)
