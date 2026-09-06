import unittest

from jaya_research.research.experiment_designer import ExperimentDesigner
from jaya_research.research.hypothesis_generator import HypothesisGenerator
from jaya_research.research.protocol_database import ProtocolDatabase
from jaya_research.research.safety_interlock import SafetyInterlock


class TestSafetyInterlock(unittest.TestCase):
    def setUp(self):
        self.interlock = SafetyInterlock()

    def test_evaluate_safe_protocol(self):
        safe_data = {
            "hypothesis": "Increasing memory cache size reduces database lookup latency.",
            "variables": {"independent": ["cache_size"], "dependent": ["latency"]},
        }
        is_safe, reason, score = self.interlock.evaluate_safety(safe_data)
        self.assertTrue(is_safe)
        self.assertEqual(reason, "PASSED")
        self.assertLessEqual(score, 0.1)

    def test_evaluate_unsafe_protocol(self):
        unsafe_data = {
            "hypothesis": "Testing explosive chemical compound stability under heat.",
            "variables": {"independent": ["toxic_exposure"]},
        }
        is_safe, reason, score = self.interlock.evaluate_safety(unsafe_data)
        self.assertFalse(is_safe)
        self.assertIn("Safety Block", reason)
        self.assertGreater(score, 0.3)

    def test_verify_human_token(self):
        self.assertFalse(self.interlock.verify_approval_token("anything"))
        token = "a" * 32
        configured = SafetyInterlock(secret_token=token)
        self.assertTrue(configured.verify_approval_token(token))
        self.assertFalse(self.interlock.verify_approval_token("INVALID-TOKEN"))


class TestProtocolDatabase(unittest.TestCase):
    def setUp(self):
        self.db = ProtocolDatabase()

    def test_get_default_protocol(self):
        proto = self.db.get_protocol("controlled_comparison")
        self.assertIsNotNone(proto)
        self.assertIn("steps", proto)

    def test_search_protocol(self):
        results = self.db.search_protocols("Sensitivity")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["type"], "Sensitivity Analysis")


class TestExperimentDesigner(unittest.TestCase):
    def setUp(self):
        self.generator = HypothesisGenerator()
        self.designer = ExperimentDesigner()

    def test_design_experiment_from_hypothesis(self):
        hyp = self.generator.generate_hypothesis("Graph Neural Networks")
        exp = self.designer.design_experiment(hyp)

        self.assertIsInstance(exp, dict)
        self.assertIn("experiment_id", exp)
        self.assertIn("hypothesis_id", exp)
        self.assertIn("procedure_steps", exp)
        self.assertIn("safety_status", exp)
        self.assertEqual(exp["safety_status"], "APPROVED")
        self.assertGreaterEqual(exp["feasibility_score"], 0.7)

    def test_design_experiment_blocked_by_safety(self):
        unsafe_hyp = {
            "hypothesis_id": "HYP-UNSAFE-001",
            "statement": "Synthetic creation of pathogen weapon in laboratory.",
            "variables": {"independent": ["toxic_level"], "dependent": ["lethality"]},
        }
        exp = self.designer.design_experiment(unsafe_hyp)
        self.assertEqual(exp["safety_status"], "BLOCKED")
        self.assertIn("Safety Block", exp["safety_reason"])


if __name__ == "__main__":
    unittest.main()
