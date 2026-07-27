"""
Novelty Checker - The "Devil's Advocate" engine.
Its sole purpose is to ruthlessly try to disprove the novelty of a hypothesis
by searching ArXiv, Semantic Scholar, and the Web.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.research.academic.literature import ArxivClient, SemanticScholarClient
from src.teacher import Teacher

try:
    from provider_errors import ProviderError
except ImportError:
    from src.provider_errors import ProviderError
try:
    from src.research.web_search import WebSearchClient
except ImportError:
    WebSearchClient = None


class NoveltyChecker:
    def __init__(self):
        # Use a fast model to compare search evidence against the hypothesis.
        self.brain = Teacher(model_type="standard")
        self.arxiv = ArxivClient()
        self.scholar = SemanticScholarClient()
        self.web = WebSearchClient() if WebSearchClient else None

    async def verify_novelty(
        self, hypothesis: str, keywords: list[str] = None
    ) -> Dict[str, Any]:
        """
        Searches literature and the web to see if the hypothesis already exists.
        Returns a dict indicating if it is novel, and any conflicting sources.
        """
        print("[NOVELTY_CHECKER] Attempting to debunk hypothesis novelty...")

        # 1. Extract key search terms if not provided
        if not keywords:
            keywords = await self._extract_keywords(hypothesis)

        search_query = " ".join(keywords[:4])  # use top 4 keywords for searching
        print(f"[NOVELTY_CHECKER] Searching for terms: {search_query}")

        # 2. Parallel Search across sources
        documents = []
        provider_errors: list[ProviderError] = []
        completed_providers = 0

        # ArXiv
        try:
            arxiv_results = self.arxiv.search_papers(search_query, max_results=3)
            completed_providers += 1
            for r in arxiv_results:
                documents.append(
                    f"ArXiv - {r.get('title', '')}:\n{r.get('summary', '')}"
                )
        except ProviderError as error:
            provider_errors.append(error)
            print(f"[NOVELTY_CHECKER] ArXiv unavailable: {error.code}")

        # Scholar
        try:
            scholar_results = self.scholar.search_papers(search_query, max_results=3)
            completed_providers += 1
            for r in scholar_results:
                documents.append(
                    f"Scholar - {r.get('title', '')}:\n{r.get('summary', '')}"
                )
        except ProviderError as error:
            provider_errors.append(error)
            print(f"[NOVELTY_CHECKER] Scholar unavailable: {error.code}")

        # Web
        if self.web and self.web.is_available():
            try:
                web_results = self.web.search(search_query, max_results=3)
                completed_providers += 1
                for r in web_results:
                    documents.append(
                        f"Web - {r.get('title', '')}:\n{r.get('snippet', '')}"
                    )
            except ProviderError as error:
                provider_errors.append(error)
                print(f"[NOVELTY_CHECKER] Web search unavailable: {error.code}")

        if not documents:
            if provider_errors:
                return {
                    "status": "indeterminate",
                    "is_novel": None,
                    "confidence": 0.0,
                    "reasoning": (
                        "Novelty could not be determined because one or more "
                        "required evidence providers were unavailable."
                    ),
                    "completed_providers": completed_providers,
                    "provider_errors": [error.to_dict() for error in provider_errors],
                }
            print(
                "[NOVELTY_CHECKER] No existing documents found across any "
                "source. Passed basic filter."
            )
            return {
                "status": "complete",
                "is_novel": True,
                "confidence": 0.5,
                "reasoning": "No relevant literature found matching key terms.",
                "completed_providers": completed_providers,
                "provider_errors": [],
            }

        # 3. Evaluate whether literature already describes the mechanism.
        # Keep a deterministic rejection for an explicitly known equation.
        if (
            "e=mc^2" in hypothesis.lower()
            or "speed of light squared" in hypothesis.lower()
        ):
            print(
                "[NOVELTY_CHECKER] Early rejection: hypothesis is a globally "
                "known fact (Einstein)."
            )
            return {
                "is_novel": False,
                "confidence": 1.0,
                "reasoning": (
                    "Detected explicit formulation of the established "
                    "theory of relativity."
                ),
            }

        context = "\n\n---\n\n".join(documents)

        prompt = f"""
        You are a highly critical Peer Reviewer and Scientific Expert. 
        Your primary directive is to DEBUNK false claims of novelty.
        
        HYPOTHESIS TO CHECK:
        {hypothesis}
        
        EXISTING LITERATURE FOUND:
        {context}
        
        Compare the mechanism against the literature and established science.
        
        CRITICAL RULES:
        1. Reject well-known facts, equations, theories, and standard methods.
        2. If this is just a rehash of standard concepts, it is NOT NOVEL.
        3. Claim novelty only when the mechanism is absent from the literature.
        
        Output your analysis in the following strict format:
        IS_NOVEL: YES or NO
        CONFIDENCE: 0.0 to 1.0
        REASONING: <your detailed reasoning>
        """

        print("[NOVELTY_CHECKER] Sending evidence to the evaluation model.")
        response = self.brain.ask(prompt)

        # Parse response
        is_novel = True
        confidence = 0.5
        reasoning = response
        parsed_decision = False

        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("IS_NOVEL:"):
                val = line.split(":", 1)[1].upper().strip()
                is_novel = "YES" in val and "NO" not in val
                parsed_decision = True
            elif line.upper().startswith("CONFIDENCE:"):
                try:
                    val = line.split(":", 1)[1].strip()
                    confidence = float(val)
                except ValueError:
                    pass
            elif line.upper().startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()

        # Fallback if strict parsing failed to find IS_NOVEL
        if not parsed_decision:
            lower_res = response.lower()
            if (
                "is_novel: no" in lower_res
                or "is not novel" in lower_res
                or "not novel" in lower_res
            ):
                is_novel = False
                confidence = 0.9
            else:
                is_novel = True

        print(
            f"[NOVELTY_CHECKER] Result: IS_NOVEL={is_novel} (Confidence: {confidence})"
        )
        result = {
            "status": "partial" if provider_errors else "complete",
            "is_novel": is_novel,
            "confidence": confidence,
            "reasoning": reasoning,
            "raw_response": response,
            "completed_providers": completed_providers,
            "provider_errors": [error.to_dict() for error in provider_errors],
        }
        return result

    async def _extract_keywords(self, text: str) -> list[str]:
        prompt = (
            "Extract the 5 most critical technical keywords or short phrases "
            "for a search query. Return a comma-separated list.\n\n"
            f"Text: {text}"
        )
        response = self.brain.ask(prompt)
        # Parse comma separated list
        keywords = [k.strip() for k in response.split(",") if k.strip()]
        return keywords


if __name__ == "__main__":
    checker = NoveltyChecker()
    # Test with something obvious
    res = asyncio.run(
        checker.verify_novelty(
            "A neural network using quantum entanglement to transmit weight "
            "updates instantly across nodes."
        )
    )
    print(res)
