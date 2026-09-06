"""Phase 1 gate: lightweight language-policy override loading."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.soul import language_policy as lp


class TestPhase1LanguagePolicyOverrideGate(unittest.TestCase):
    def setUp(self):
        self._core_backup = copy.deepcopy(lp.LANGUAGE_CORE)
        self._status_backup = lp.get_language_policy_status()
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        lp.LANGUAGE_CORE.clear()
        for lang, values in self._core_backup.items():
            lp.LANGUAGE_CORE[lang] = dict(values)

        lp._OVERRIDE_STATUS.update({
            "loaded": self._status_backup.get("loaded", False),
            "path": self._status_backup.get("path"),
            "updated_fields": self._status_backup.get("updated_fields", 0),
            "error": self._status_backup.get("error"),
        })
        self._tmpdir.cleanup()

    def test_load_override_updates_selected_fields(self):
        override_path = Path(self._tmpdir.name) / "override.json"
        payload = {
            "id": {
                "greeting": "JAYA override greeting ID.",
                "no_memory": "Memori belum ada, namun bahasa inti tetap aktif.",
            },
            "en": {
                "greeting": "JAYA override greeting EN.",
            },
            "_meta": {
                "source": "unit_test"
            },
        }
        override_path.write_text(json.dumps(payload), encoding="utf-8")

        ok = lp.load_language_policy_overrides(str(override_path))
        self.assertTrue(ok)

        status = lp.get_language_policy_status()
        self.assertTrue(status["loaded"])
        self.assertGreaterEqual(int(status.get("updated_fields", 0) or 0), 3)

        self.assertEqual(lp.get_policy("id")["greeting"], "JAYA override greeting ID.")
        self.assertEqual(lp.get_policy("en")["greeting"], "JAYA override greeting EN.")

    def test_unknown_language_and_unknown_keys_are_ignored(self):
        override_path = Path(self._tmpdir.name) / "override_unknown.json"
        payload = {
            "xx": {
                "greeting": "Unknown language should be ignored",
            },
            "id": {
                "unknown_key": "Ignored key",
            },
        }
        override_path.write_text(json.dumps(payload), encoding="utf-8")

        ok = lp.load_language_policy_overrides(str(override_path))
        self.assertFalse(ok)

        status = lp.get_language_policy_status()
        self.assertFalse(status["loaded"])
        self.assertEqual(int(status.get("updated_fields", 0) or 0), 0)

    def test_missing_override_file_returns_false(self):
        missing_path = Path(self._tmpdir.name) / "missing_override.json"
        ok = lp.load_language_policy_overrides(str(missing_path))
        self.assertFalse(ok)

        status = lp.get_language_policy_status()
        self.assertFalse(status["loaded"])
        self.assertEqual(int(status.get("updated_fields", 0) or 0), 0)


if __name__ == "__main__":
    unittest.main()
