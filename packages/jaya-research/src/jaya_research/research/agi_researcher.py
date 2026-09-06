"""
AGI Research Module
Specialized researcher for Recursive Self-Improvement and Neural Compilation
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jaya_research.research.agent import ResearchAgent
from jaya_research.research.config import get_config

class AGIResearcher(ResearchAgent):
    """
    Specialized agent for AGI research.
    Enforces AGI-specific prompts and focus areas.
    """
    
    def __init__(self, topic: str):
        # Enforce AGI focus
        focus_areas = "Recursive Self-Improvement, Neural Compilation, Meta-Learning, Gödel Machines, AI Safety"
        super().__init__(topic=topic, focus_areas=focus_areas)
        
    def generate_plan(self):
        """Override to ensure AGI prompt is used"""
        print("[AGI RESEARCH] 🧠 Initializing Deep AGI Research Protocol")
        return super().generate_plan()
        
    def run(self, human_in_loop: bool = True):
        """Run with specialized logging"""
        print("="*60)
        print(f"🤖 AGI RESEARCHER: {self.topic}")
        print("="*60)
        return super().run(human_in_loop)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AGI Research Assistant")
    parser.add_argument("topic", help="Research topic")
    args = parser.parse_args()
    
    agent = AGIResearcher(topic=args.topic)
    agent.run(human_in_loop=True)
