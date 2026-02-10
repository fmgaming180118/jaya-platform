import os
from typing import List, Dict
from src.teacher import Teacher

class ThesisDrafter:
    """
    Helps draft academic content for the Digital Twin.
    """
    def __init__(self):
        # Use the 'reasoning' model for high-quality writing
        self.writer = Teacher(model_type="reasoning")

    def generate_literature_review(self, topic: str, papers: List[Dict]) -> str:
        """
        Synthesizes a Literature Review chapter from a list of papers.
        """
        if not papers:
            return "## Literature Review\n\nNo papers found to review."

        # Prepare context from papers
        paper_context = ""
        for i, p in enumerate(papers, 1):
            source = p.get('source', 'Unknown')
            paper_context += f"Paper {i}:\nTitle: {p['title']}\nYear: {p['published']}\nSource: {source}\nAbstract: {p['summary']}\n\n"

        prompt = f"""
        You are an Academic Research Assistant writing a Thesis.
        
        TOPIC: {topic}
        
        TASK: Write a "Literature Review" chapter based ONLY on the provided papers.
        
        REQUIREMENTS:
        1.  **Academic Tone**: Formal, objective, and precise.
        2.  **Synthesis**: Do not just list papers. Group them by themes or methodology. Compare and contrast.
        3.  **Citations**: Use citation markers like [1], [2] corresponding to the list.
        4.  **Structure**:
            - **Introduction**: Brief overview of the state of the art.
            - **Thematic Analysis**: Discuss the papers grouped by concepts.
            - **Gaps**: Identify what is missing in the current research (based on these papers).
            - **Conclusion**: Summary.
        
        PAPERS:
        {paper_context}
        
        OUTPUT FORMAT: Markdown.
        """
        
        print(f"[Drafter] Writing Literature Review for {topic} with {len(papers)} papers...")
        review_content = self.writer.generate_completion(prompt, max_tokens=2000)
        
        # Append Bibliography
        bibliography = "\n\n## References\n"
        for i, p in enumerate(papers, 1):
            bibliography += f"[{i}] {p['authors'][0] if p['authors'] else 'Unknown'} et al. ({p['published']}). *{p['title']}*. {p.get('source', '')}. [Link]({p['pdf_link']})\n"
            
        return review_content + bibliography

    def generate_outline(self, topic: str) -> str:
        """
        Generates a standard Thesis Outline for the topic.
        """
        prompt = f"""
        Generate a comprehensive Thesis Proposal Outline for the topic: "{topic}".
        
        The outline should follow standard academic structure:
        1. Introduction (Background, Problem Statement, Objectives, Scope)
        2. Literature Review (Overview of key keys)
        3. Methodology (Proposed approach, tools, data)
        4. Expected Results
        5. References
        
        Provide a brief description for what should specifically go into each section for THIS topic.
        """
        return self.writer.generate_completion(prompt, max_tokens=1000)

    def export_to_latex(self, markdown_content: str, title: str = "Thesis Draft") -> str:
        """
        Converts simple Markdown to a basic LaTeX template.
        """
        latex_body = markdown_content
        
        # Simple replacements (Regex would be better for robust conversion)
        latex_body = latex_body.replace("# ", r"\chapter{").replace("## ", r"\section{").replace("### ", r"\subsection{")
        latex_body = latex_body.replace("**", r"\textbf{").replace("*", r"\textit{")
        # Close braces for headers (Heuristic: assumes headers are on single lines)
        lines = []
        for line in latex_body.split('\n'):
            if line.strip().startswith(r"\chapter{") or line.strip().startswith(r"\section{") or line.strip().startswith(r"\subsection{"):
                lines.append(line.strip() + "}")
            else:
                lines.append(line)
        
        latex_body = "\n".join(lines)

        template = r"""
\documentclass[12pt, a4paper]{report}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[utf8]{inputenc}

\title{""" + title + r"""}
\author{JAYA Research Assistant}
\date{\today}

\begin{document}

\maketitle
\tableofcontents

""" + latex_body + r"""

\end{document}
        """
        return template

if __name__ == "__main__":
    # Test
    drafter = ThesisDrafter()
    # print(drafter.generate_outline("Optimizing AI for Low-Resource Devices"))
    md = "# Introduction\nThis is a test.\n## Background\nAI is growing."
    print(drafter.export_to_latex(md))
