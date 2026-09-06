"""Phase 1 capability gate for language quality in local sovereign mode.

Covers:
1. Clear no-memory Indonesian response.
2. Intent hint presence for tool-use-like action commands.
3. Sentence-level mixed ID/EN switching.
4. Ambiguity clarification behavior.
5. Structured local summary when RAG context exists.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.jaya_shell import process_offline_response
from jaya_core.brain_v2.soul.language_policy import get_policy
from jaya_core.brain_v2.soul.lingua_logica import LinguaLogica


class TestPhase1LanguageCapabilityGate(unittest.TestCase):
    def setUp(self):
        self.lingua = LinguaLogica()
        self.id_pack = get_policy("id")
        self.en_pack = get_policy("en")

    def test_no_memory_indonesian_is_clear_and_portable(self):
        response = process_offline_response(
            "Jelaskan arsitektur lokal JAYA",
            [],
            rag_instance=None,
            lingua=self.lingua,
        )
        self.assertIn(self.id_pack["no_memory"], response)
        self.assertIn(self.id_pack["portable"], response)

    def test_no_memory_action_includes_intent_hint(self):
        response = process_offline_response(
            "buka pengaturan sistem",
            [],
            rag_instance=None,
            lingua=self.lingua,
        )
        self.assertIn("{intent}", self.id_pack["intent_action"])
        self.assertIn("open", response)

    def test_mixed_language_is_switched_per_sentence(self):
        response = process_offline_response(
            "Buka folder lokal. Then explain why migration still works.",
            [],
            rag_instance=None,
            lingua=self.lingua,
        )
        self.assertIn(self.id_pack["mixed_notice"], response)
        self.assertIn(self.id_pack["segment_no_memory"].format(index=1), response)
        self.assertIn(self.en_pack["segment_no_memory"].format(index=2), response)

    def test_ambiguous_request_triggers_clarification(self):
        response = process_offline_response(
            "ini gimana?",
            [],
            rag_instance=None,
            lingua=self.lingua,
        )
        self.assertIn(self.id_pack["clarify"], response)

    def test_with_rag_returns_structured_summary(self):
        rag_results = [
            {
                "topic": "Fonologi",
                "content": "Fonologi mempelajari sistem bunyi bahasa. Fokusnya termasuk pola vokal dan konsonan.",
            },
            {
                "topic": "Morfologi",
                "content": "Morfologi mempelajari struktur kata. Kajiannya mencakup prefiks, sufiks, dan reduplikasi.",
            },
        ]
        response = process_offline_response(
            "Apa itu linguistik dasar",
            rag_results,
            rag_instance=None,
            lingua=self.lingua,
        )
        self.assertIn(self.id_pack["header"], response)
        self.assertIn("1. Fonologi", response)
        self.assertIn("2. Morfologi", response)


if __name__ == "__main__":
    unittest.main()
