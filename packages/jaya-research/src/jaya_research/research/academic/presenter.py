from jaya_research.teacher import Teacher
from typing import List, Dict

class SlideDeckGenerator:
    """
    Generates slide decks from Thesis Chapters using Marp (Markdown Presentation Ecosystem).
    """
    def __init__(self):
        self.brain = Teacher(model_type="reasoning")

    def generate_slides(self, topic: str, content: str, num_slides: int = 10) -> str:
        """
        Converts detailed thesis content into a Marp Markdown slide deck.
        """
        print(f"[Presenter] Generating {num_slides} slides for: {topic}")
        
        prompt = f"""
        You are a Presentation Expert.
        
        TOPIC: {topic}
        TARGET AUDIENCE: Thesis Defense Committee (Academic Experts).
        
        SOURCE CONTENT:
        {content[:15000]} # Truncated
        
        TASK:
        Create a {num_slides}-slide presentation in Marp Markdown format.
        
        REQUIREMENTS:
        1. **Title Slide**: Project Title, Author (JAYA Twin), Date.
        2. **Problem Statement**: Clear bullet points.
        3. **Methodology**: Diagrammatic description (using text or mermaid).
        4. **Results**: Placeholders for charts.
        5. **Conclusion**: Summary + Future Work.
        6. **Style**: Professional, Modern.
        
        OUTPUT FORMAT:
        ---
        marp: true
        theme: gaia
        class: lead
        backgroundColor: #fff
        backgroundImage: url('https://marp.app/assets/hero-background.jpg')
        ---
        
        # [Title]
        
        ---
        
        # [Slide Header]
        - Point 1
        - Point 2
        
        """
        
        slides = self.brain.generate_completion(prompt)
        return slides

if __name__ == "__main__":
    gen = SlideDeckGenerator()
    slides = gen.generate_slides("AI in Healthcare", "# Full Thesis Content...")
    print(slides)
