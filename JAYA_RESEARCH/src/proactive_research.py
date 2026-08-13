"""
Proactive Research Agent.
Delegates hypothesis generation and knowledge gap detection to HypothesisGenerator.
"""

from typing import Any, Dict, List, Optional

from research.hypothesis_generator import HypothesisGenerator


class ProactiveResearchAgent:
    def __init__(self, graph_engine: Optional[Any] = None, teacher: Optional[Any] = None):
        self.research_topics: List[str] = []
        self.generator = HypothesisGenerator(graph_engine=graph_engine, teacher=teacher)
        self.generated_hypotheses: List[Dict[str, Any]] = []

    def add_research_topic(self, topic: str):
        """Add a research topic to the agent's queue."""
        if topic not in self.research_topics:
            self.research_topics.append(topic)

    def get_next_research_topic(self) -> Optional[str]:
        """Get the next research topic to investigate."""
        if self.research_topics:
            return self.research_topics.pop(0)
        return None

    def generate_hypothesis(self, topic: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Generate a structured hypothesis for the given research topic using HypothesisGenerator."""
        hypothesis = self.generator.generate_hypothesis(topic, context=context)
        self.generated_hypotheses.append(hypothesis)
        return hypothesis

    def suggest_experiment(self, hypothesis: Any) -> str:
        """Suggest an experiment to test the hypothesis."""
        if isinstance(hypothesis, dict):
            hyp_id = hypothesis.get("hypothesis_id", "HYP")
            statement = hypothesis.get("statement", "")
            vars_dict = hypothesis.get("variables", {})
            ind = ", ".join(vars_dict.get("independent", []))
            dep = ", ".join(vars_dict.get("dependent", []))
            return (
                f"[{hyp_id}] Experiment Plan:\n"
                f"- Objective: Test if {statement}\n"
                f"- Independent Variable(s): {ind}\n"
                f"- Dependent Variable(s): {dep}\n"
                f"- Procedure: Measure variance in dependent variable under controlled changes of independent variable."
            )
        return f"Experiment to test: {hypothesis}"
