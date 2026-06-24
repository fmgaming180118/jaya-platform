from src.teacher import Teacher

class AcademicEditor:
    """
    Automated Editor that revises drafts based on critique.
    """
    def __init__(self):
        self.editor = Teacher(model_type="reasoning")

    def revise_chapter(self, draft: str, critique: str, context: str = "") -> str:
        """
        Rewrites the draft to address the critique points.
        """
        print("[Editor] Revising chapter based on feedback...")
        
        prompt = f"""
        You are a Professional Academic Editor.
        
        TASK: Rewrite the following Thesis Draft to address the Reviewer's Critique.
        
        ORIGINAL DRAFT:
        {draft[:8000]}
        
        REVIEWER CRITIQUE:
        {critique}
        
        ADDITIONAL CONTEXT (Topic/Abstract):
        {context}
        
        INSTRUCTIONS:
        1. Keep the original structure but improve clarity, flow, and tone.
        2. Specifically address every weakness mentioned in the critique.
        3. Ensure citations are preserved (or added if requested).
        4. Make the language strictly academic (no casual phrases).
        
        OUTPUT:
        The full revised chapter content in Markdown.
        """
        
        revised_content = self.editor.generate_completion(prompt)
        return revised_content

if __name__ == "__main__":
    editor = AcademicEditor()
    draft = "AI is cool because it helps people."
    critique = "Too informal. Needs citations. What specific help?"
    print(editor.revise_chapter(draft, critique))
