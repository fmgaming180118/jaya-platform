from typing import Dict, List
from src.teacher import Teacher

class ReviewerAgent:
    """
    Simulates a harsh Thesis Supervisor / Peer Reviewer.
    Critiques drafts for academic rigor.
    """
    def __init__(self):
        # Uses reasoning model for critical analysis
        self.critic = Teacher(model_type="reasoning")

    def critique_chapter(self, chapter_content: str, topic: str) -> str:
        """
        Reviews a chapter and provides specific feedback.
        """
        prompt = f"""
        You are a strict Senior Thesis Supervisor.
        
        TOPIC: {topic}
        
        TASK: Critique the following Thesis Chapter draft.
        
        CRITERIA:
        1. **Logical Flow**: Is the argument coherent?
        2. **Citations**: Are claims supported by (placeholder) citations?
        3. **Tone**: Is it formal and objective?
        4. **Methodology**: (If applicable) Is the approach sound?
        
        DRAFT CONTENT:
        {chapter_content[:8000]} # Truncate if too long
        
        OUTPUT:
        Provide a structured critique in Markdown:
        - ## Overall Assessment (Pass/Major Revision/Reject)
        - ## Weaknesses
        - ## Specific Recommendations
        - ## Missing Perspectives (What did the student miss?)
        """
        
        print(f"[Reviewer] Critiquing draft for {topic}...")
        critique = self.critic.generate_completion(prompt)
        return critique

    def generate_defense_questions(self, topic: str, abstract: str) -> List[str]:
        """
        Generates Viva Voce (Thesis Defense) questions.
        """
        prompt = f"""
        Generate 5 tough Thesis Defense questions for:
        Topic: {topic}
        Abstract: {abstract}
        
        The questions should challenge the methodology, validity, and contribution of the work.
        """
        response = self.critic.generate_completion(prompt)
        return response

if __name__ == "__main__":
    reviewer = ReviewerAgent()
    critique = reviewer.critique_chapter("# Introduction\nAI is good.", "AI Ethics")
    print(critique)
