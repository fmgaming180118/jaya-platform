import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from proactive_research import ProactiveResearchAgent


class TestProactiveResearchAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ProactiveResearchAgent()

    def test_add_research_topic(self):
        self.agent.add_research_topic("Quantum Computing")
        self.assertEqual(len(self.agent.research_topics), 1)
        self.assertEqual(self.agent.research_topics[0], "Quantum Computing")

    def test_get_next_research_topic(self):
        self.agent.add_research_topic("AI Ethics")
        self.agent.add_research_topic("ML Safety")
        topic = self.agent.get_next_research_topic()
        self.assertEqual(topic, "AI Ethics")
        self.assertEqual(len(self.agent.research_topics), 1)

    def test_generate_hypothesis(self):
        hypothesis = self.agent.generate_hypothesis("Climate Change")
        self.assertIsInstance(hypothesis, dict)
        self.assertEqual(hypothesis["topic"], "Climate Change")
        self.assertIn("statement", hypothesis)

    def test_suggest_experiment(self):
        hypothesis = self.agent.generate_hypothesis("Climate Change")
        experiment = self.agent.suggest_experiment(hypothesis)
        self.assertIn("Experiment Plan", experiment)

if __name__ == '__main__':
    unittest.main()