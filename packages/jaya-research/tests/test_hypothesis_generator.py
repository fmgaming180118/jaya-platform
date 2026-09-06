import json

import pytest

from jaya_research.research.hypothesis_generator import HypothesisGenerator
from proactive_research import ProactiveResearchAgent


def test_missing_corpus_is_explicitly_ungrounded():
    generator = HypothesisGenerator()

    gap = generator.detect_knowledge_gaps("Graph Neural Networks")[0]
    hypothesis = generator.generate_hypothesis("Graph Neural Networks")

    assert gap["type"] == "insufficient_evidence"
    assert gap["grounded"] is False
    assert gap["evidence_ids"] == []
    assert hypothesis["grounding_status"] == "UNGROUNDED_SEED"
    assert hypothesis["evidence_kind"] == "UNVERIFIED"
    assert hypothesis["promotion_eligible"] is False


def test_novelty_is_not_invented_without_corpus():
    generator = HypothesisGenerator()

    assert generator.compute_novelty_score("A new approach") == 0.0

    hypothesis = generator.generate_hypothesis("A research topic")
    assert hypothesis["novelty_score"] == 0.0
    assert hypothesis["novelty_status"] == "NOT_EVALUATED"


def test_novelty_uses_supplied_corpus_without_artificial_floor():
    generator = HypothesisGenerator()
    generator.add_to_corpus(
        "Quantum entanglement allows instant state correlation.",
        source_id="paper:quantum-1",
    )

    similar = generator.compute_novelty_score("Quantum entanglement state correlation.")
    unrelated = generator.compute_novelty_score(
        "Organic semiconductor thermal efficiency limits."
    )

    assert 0.0 <= similar <= 1.0
    assert 0.0 <= unrelated <= 1.0
    assert unrelated > similar


def test_generated_template_contains_no_fabricated_measurement():
    hypothesis = HypothesisGenerator().generate_hypothesis("Edge LLM Compression")

    assert "%" not in hypothesis["statement"]
    assert "p-value" not in hypothesis["statement"].casefold()
    assert "sub-50" not in hypothesis["statement"].casefold()
    assert hypothesis["variables"]["independent"]
    assert hypothesis["variables"]["dependent"]


class FakeTeacher:
    def ask(self, *_args, **_kwargs):
        return json.dumps(
            {
                "statement": "Changing batch size changes measured latency.",
                "independent_variables": ["batch size"],
                "dependent_variables": ["measured latency"],
                "control_variables": ["hardware"],
                "predicted_relationship": "A measurable difference.",
                "falsifiability_criteria": "Use the preregistered threshold.",
            }
        )


def test_explicit_model_injection_is_supported_but_stays_unverified():
    hypothesis = HypothesisGenerator(teacher=FakeTeacher()).generate_hypothesis(
        "Batch Latency"
    )

    assert hypothesis["llm_generated"] is True
    assert hypothesis["evidence_kind"] == "UNVERIFIED"
    assert hypothesis["promotion_eligible"] is False


def test_empty_topic_is_rejected():
    with pytest.raises(ValueError, match="topic"):
        HypothesisGenerator().generate_hypothesis("   ")


def test_proactive_agent_keeps_proposal_unverified():
    agent = ProactiveResearchAgent()
    agent.add_research_topic("Autonomous Systems")

    hypothesis = agent.generate_hypothesis(agent.get_next_research_topic())
    plan = agent.suggest_experiment(hypothesis)

    assert hypothesis["topic"] == "Autonomous Systems"
    assert hypothesis["promotion_eligible"] is False
    assert "Experiment Plan" in plan
