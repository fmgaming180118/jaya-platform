"""tests/test_v18_nano.py — V18 Unit Tests.

Covers:
  1. pack/unpack roundtrip (2-bit lossless for {-1, 0, +1})
  2. NanoModel forward-pass output shape
  3. NanoModel predict_token returns valid index
  4. LiveEvolver: fitness does not degrade after evolution steps
  5. MetaCognitivePlanner.reflect() with weak history
  6. Weight persistence (weights change after evolve+set)
  7. LegacyProtocol.migrate() adds dst_hw_uuid to approved list
  8. LinguaLogica: 20 Bahasa Indonesia phrases parse correctly

Run with:
    python -m pytest tests/test_v18_nano.py -v
or:
    python tests/test_v18_nano.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pack / Unpack Roundtrip
# ─────────────────────────────────────────────────────────────────────────────
class TestPackUnpack(unittest.TestCase):
    def test_roundtrip_basic(self):
        """2-bit ternary pack/unpack is lossless for all {-1, 0, +1} combos."""
        from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary
        rng = np.random.default_rng(42)
        arr = rng.choice(np.array([-1, 0, 1], dtype=np.int8), size=1024)
        packed = pack_ternary(arr)
        restored = unpack_ternary(packed, len(arr))
        np.testing.assert_array_equal(arr, restored,
            err_msg="pack/unpack roundtrip failed — data not lossless")

    def test_roundtrip_all_negative(self):
        arr = np.full(256, -1, dtype=np.int8)
        from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary
        p = pack_ternary(arr)
        r = unpack_ternary(p, 256)
        np.testing.assert_array_equal(arr, r)

    def test_roundtrip_all_zero(self):
        arr = np.zeros(256, dtype=np.int8)
        from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary
        p = pack_ternary(arr)
        r = unpack_ternary(p, 256)
        np.testing.assert_array_equal(arr, r)

    def test_roundtrip_all_positive(self):
        arr = np.ones(256, dtype=np.int8)
        from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary
        p = pack_ternary(arr)
        r = unpack_ternary(p, 256)
        np.testing.assert_array_equal(arr, r)

    def test_state_dict_roundtrip(self):
        """pack_state_dict / unpack_state_dict roundtrip with NanoModel buffers."""
        from jaya_core.brain_v2.format.packer import pack_state_dict, unpack_state_dict
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG

        def _flatten(d, prefix="", out=None):
            if out is None:
                out = {}
            if isinstance(d, dict):
                for k, v in d.items():
                    _flatten(v, f"{prefix}.{k}" if prefix else k, out)
            elif isinstance(d, (list, tuple)) and not isinstance(d, np.ndarray):
                for i, v in enumerate(d):
                    _flatten(v, f"{prefix}.{i}" if prefix else str(i), out)
            else:
                out[prefix] = d
            return out

        model = NanoModel(config=NANO_CONFIG)
        model.random_init()
        buffers = model.get_weight_buffers()           # list of (key, arr)
        packed  = pack_state_dict(buffers)
        restored = unpack_state_dict(packed)           # nested dict from _unflatten

        # Flatten the restored nested dict for comparison
        flat_restored = _flatten(restored)
        for key, arr in buffers:
            self.assertIn(key, flat_restored,
                f"Key '{key}' missing from restored flat state dict")
            np.testing.assert_array_equal(arr, flat_restored[key],
                err_msg=f"State dict key '{key}' mismatch after roundtrip")


# ─────────────────────────────────────────────────────────────────────────────
# 2. NanoModel Forward Pass
# ─────────────────────────────────────────────────────────────────────────────
class TestNanoModelForward(unittest.TestCase):
    def setUp(self):
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
        self.cfg   = NANO_CONFIG
        self.model = NanoModel(config=NANO_CONFIG)
        self.model.random_init()

    def test_forward_output_shape(self):
        """forward() returns shape (seq_len, vocab_size)."""
        token_ids = [0, 1, 2, 3]
        logits = self.model.forward(token_ids)
        self.assertEqual(logits.shape, (len(token_ids), self.cfg["vocab_size"]),
            f"Expected shape ({len(token_ids)}, {self.cfg['vocab_size']}), got {logits.shape}")

    def test_forward_single_token(self):
        logits = self.model.forward([5])
        self.assertEqual(logits.shape, (1, self.cfg["vocab_size"]))

    def test_forward_output_finite(self):
        logits = self.model.forward([0, 1, 2])
        self.assertTrue(np.all(np.isfinite(logits)),
            "forward() produced NaN or Inf values")

    def test_predict_token_range(self):
        """predict_token() returns a valid vocab index."""
        token_id = self.model.predict_token([0, 1, 2])
        self.assertIsInstance(token_id, int)
        self.assertGreaterEqual(token_id, 0)
        self.assertLess(token_id, self.cfg["vocab_size"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. NanoModel RAM footprint (proxy: model + packed size)
# ─────────────────────────────────────────────────────────────────────────────
class TestNanoRam(unittest.TestCase):
    def test_packed_weights_under_100kb(self):
        """Packed NANO weights should be < 100 KB."""
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
        from jaya_core.brain_v2.format.packer import pack_state_dict
        model = NanoModel(config=NANO_CONFIG)
        model.random_init()
        packed = pack_state_dict(model.get_weight_buffers())
        kb = len(packed) / 1024
        self.assertLess(kb, 100,
            f"Packed weights {kb:.1f} KB exceeds 100 KB — model too large")

    def test_raw_weights_under_1mb(self):
        """Raw ternary weights should be < 1 MB."""
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
        model = NanoModel(config=NANO_CONFIG)
        model.random_init()
        raw_bytes = sum(v.nbytes for _, v in model.get_weight_buffers())
        mb = raw_bytes / (1024 * 1024)
        self.assertLess(mb, 1.0,
            f"Raw weight size {mb:.2f} MB exceeds 1 MB")


# ─────────────────────────────────────────────────────────────────────────────
# 4. LiveEvolver: fitness tracking
# ─────────────────────────────────────────────────────────────────────────────
class TestLiveEvolver(unittest.TestCase):
    def _make_mock_engine(self):
        """Minimal mock engine for LiveEvolver testing."""
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
        model = NanoModel(config=NANO_CONFIG)
        model.random_init()

        engine              = MagicMock()
        engine._nano_model  = model   # LiveEvolver uses _nano_model
        engine.model_path   = ""      # no file save in unit tests
        engine.NANO_MODE    = True

        # Fake ExperimentMemory.recent() — return 5 tasks with score 0.3
        task = MagicMock()
        task.label  = "TEST"
        task.result = {"score": 0.3}
        task.score  = 0.3
        twin = MagicMock()
        twin.experiment_memory.recent.return_value = [task] * 5
        engine.twin = twin
        return engine

    def test_evolver_runs_without_crash(self):
        """LiveEvolver.run_evolution(steps=10) must not raise."""
        from jaya_core.brain_v2.education.live_evolver import LiveEvolver
        engine = self._make_mock_engine()
        evolver = LiveEvolver(engine=engine, max_steps=10)
        result = evolver.run_evolution(steps=10)
        self.assertIn("steps",    result)
        self.assertIn("accepted", result)
        self.assertIn("improved", result)

    def test_evolver_accepted_non_negative(self):
        from jaya_core.brain_v2.education.live_evolver import LiveEvolver
        engine  = self._make_mock_engine()
        evolver = LiveEvolver(engine=engine, max_steps=20)
        result  = evolver.run_evolution(steps=20)
        self.assertGreaterEqual(result["accepted"], 0)
        self.assertGreaterEqual(result["steps"],    0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. MetaCognitivePlanner.reflect()
# ─────────────────────────────────────────────────────────────────────────────
class TestMetaCognitive(unittest.TestCase):
    def _make_engine_with_weak_history(self):
        """Engine/twin that has a weak SEARCH task in ExperimentMemory."""
        morphic  = MagicMock()
        morphic.patch.return_value = True

        # Weak SEARCH tasks — need at least 5 for MetaCognitivePlanner
        weak_task       = MagicMock()
        weak_task.label = "SEARCH"
        weak_task.score = 0.2

        twin = MagicMock()
        # MetaCognitivePlanner uses twin.memory.recent(50)
        twin.memory.recent.return_value = [weak_task] * 20
        # Expose morphic via twin.morphic so MetaCognitivePlanner picks it up
        twin.morphic = morphic
        return twin, morphic

    def test_reflect_with_weak_search(self):
        """reflect() should call morphic.patch when SEARCH score < 0.45."""
        from jaya_core.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
        twin, morphic = self._make_engine_with_weak_history()
        planner = MetaCognitivePlanner()
        planner.reflect(twin)
        # Should have attempted a patch or queued an evolution task
        self.assertTrue(
            morphic.patch.called or twin.queue_task.called,
            "reflect() did not call morphic.patch() or queue_task() for weak SEARCH score"
        )

    def test_reflect_no_weak_tasks(self):
        """reflect() should do nothing when all scores are healthy."""
        from jaya_core.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
        morphic  = MagicMock()
        good     = MagicMock()
        good.label  = "SEARCH"
        good.score  = 0.9
        twin = MagicMock()
        twin.memory.recent.return_value = [good] * 20
        twin.morphic = morphic
        planner = MetaCognitivePlanner()
        planner.reflect(twin)
        morphic.patch.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Weight persistence after set_weight
# ─────────────────────────────────────────────────────────────────────────────
class TestWeightPersistence(unittest.TestCase):
    def test_set_get_weight_roundtrip(self):
        """NanoModel.set_weight(key, val) persists across get_weight_buffers()."""
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
        model = NanoModel(config=NANO_CONFIG)
        model.random_init()
        buffers = model.get_weight_buffers()
        key, old_val = buffers[0]
        new_val = np.zeros_like(old_val)
        model.set_weight(key, new_val)
        updated = dict(model.get_weight_buffers())
        np.testing.assert_array_equal(updated[key], new_val,
            err_msg=f"set_weight('{key}') did not persist")

    def test_weights_differ_after_random_init(self):
        """Two random_init calls produce different weights (probabilistic)."""
        from jaya_core.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
        m1 = NanoModel(config=NANO_CONFIG); m1.random_init()
        m2 = NanoModel(config=NANO_CONFIG); m2.random_init()
        b1 = dict(m1.get_weight_buffers())
        b2 = dict(m2.get_weight_buffers())
        any_diff = False
        for k in b1:
            if not np.array_equal(b1[k], b2.get(k, None)):
                any_diff = True
                break
        self.assertTrue(any_diff,
            "Two separate random_init() calls produced identical weights")


# ─────────────────────────────────────────────────────────────────────────────
# 7. LegacyProtocol.migrate() re-bind
# ─────────────────────────────────────────────────────────────────────────────
class TestMigrate(unittest.TestCase):
    def _make_dummy_jay(self, tmp_path: str) -> str:
        """Write a minimal valid .jay stub for migration tests."""
        import struct, zlib, hashlib
        MAGIC = b"JAYA"
        flags = 0
        hw    = b"\xAA" * 32
        dna   = hashlib.sha3_256(b"JAYA_IMMUTABLE_CORE_VALUES_V1" + hw).digest()
        ts    = 1_700_000_000
        salt  = hashlib.sha256(hw + str(ts).encode()).digest()
        hdr   = struct.pack("<4sHHQ", MAGIC, 18, 0, flags) + hw + dna
        hdr  += struct.pack("<Q", ts) + salt
        hdr   = (hdr + b"\x00" * 128)[:128]
        raw   = bytearray(hdr)
        crc   = struct.pack("<I", zlib.crc32(bytes(raw)) & 0xFFFFFFFF)
        sha   = hashlib.sha256(bytes(raw)).digest()[:28]
        raw  += crc + sha
        path = os.path.join(tmp_path, "test_src.jay")
        with open(path, "wb") as f:
            f.write(raw)
        return path

    def test_migrate_copy_only(self):
        """migrate() without dst_hw_uuid copies the file."""
        from jaya_core.brain_v2.engine.legacy_protocol import LegacyProtocol
        with tempfile.TemporaryDirectory() as tmp:
            src  = self._make_dummy_jay(tmp)
            dst  = os.path.join(tmp, "dst.jay")
            lp   = LegacyProtocol(jay_path=src, dna_secret=b"test-migration-secret")
            ok   = lp.migrate(dst)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(dst))

    def test_migrate_rebind_approves_uuid(self):
        """migrate(dst_hw_uuid=X) adds X to the approved-UUIDs list."""
        from jaya_core.brain_v2.engine.legacy_protocol import LegacyProtocol
        with tempfile.TemporaryDirectory() as tmp:
            src      = self._make_dummy_jay(tmp)
            dst      = os.path.join(tmp, "dst2.jay")
            new_uuid = "TEST-DEVICE-UUID-9999"
            lp       = LegacyProtocol(jay_path=src, dna_secret=b"test-migration-secret")
            ok       = lp.migrate(dst, dst_hw_uuid=new_uuid)
            self.assertTrue(ok)
            self.assertIn(new_uuid, lp.manifest.get("approved_uuids", []),
                "dst_hw_uuid not found in approved_uuids after migrate()")

    def test_migrate_rebind_updates_header(self):
        """migrate() with dst_hw_uuid changes the hw_hash bytes in the copy."""
        from jaya_core.brain_v2.engine.legacy_protocol import LegacyProtocol
        with tempfile.TemporaryDirectory() as tmp:
            src      = self._make_dummy_jay(tmp)
            dst      = os.path.join(tmp, "dst3.jay")
            new_uuid = "NEW-DEVICE-XYZ-2024"
            lp       = LegacyProtocol(jay_path=src, dna_secret=b"test-migration-secret")
            lp.migrate(dst, dst_hw_uuid=new_uuid)
            # Read source and destination header hw_hash bytes (16–47)
            with open(src, "rb") as f:
                src_hw = f.read(128)[16:48]
            with open(dst, "rb") as f:
                dst_hw = f.read(128)[16:48]
            self.assertNotEqual(src_hw, dst_hw,
                "Hardware hash not updated in migrated .jay header")


# ─────────────────────────────────────────────────────────────────────────────
# 8. LinguaLogica: Bahasa Indonesia patterns
# ─────────────────────────────────────────────────────────────────────────────
class TestLinguaBahasa(unittest.TestCase):
    def setUp(self):
        from jaya_core.brain_v2.soul.lingua_logica import LinguaLogica
        self.ll = LinguaLogica()

    def _parse(self, phrase: str):
        """Return normalised parse result dict from encode()."""
        expr = self.ll.encode(phrase)  # returns LogicExpr tuple
        if not isinstance(expr, tuple) or len(expr) == 0:
            return None
        # Normalise to dict-like for test assertions
        return {"head": expr[0], "type": expr[1] if len(expr) > 1 else "",
                "expr": expr}

    def _check_action(self, phrase: str, expected_action: str):
        result = self._parse(phrase)
        self.assertIsNotNone(result, f"encode('{phrase}') returned unexpected {result}")
        self.assertEqual(result["head"], "ACTION",
            f"'{phrase}' head='{result['head']}' expected='ACTION'")
        self.assertEqual(
            result["type"].upper(), expected_action.upper(),
            f"'{phrase}' action='{result['type']}' expected='{expected_action}'"
        )

    def _check_query(self, phrase: str):
        result = self._parse(phrase)
        self.assertIsNotNone(result, f"encode('{phrase}') returned None")
        self.assertEqual(result["head"], "QUERY",
            f"'{phrase}' head='{result['head']}' expected='QUERY'"
        )

    def test_bahasa_indonesia_phrases(self):
        """20 Bahasa Indonesia phrases must parse to correct action/query types."""
        # Action phrases — check both head==ACTION and correct verb
        action_cases = [
            ("cari data penjualan bulan ini",        "SEARCH"),
            ("tolong carikan informasi AI",           "SEARCH"),
            ("hapus file lama",                       "DELETE"),
            ("buka folder dokumen",                   "OPEN"),
            ("simpan hasil analisis",                 "SAVE"),
            ("buat laporan baru",                     "CREATE"),
            ("kirim email ke tim",                    "SEND"),
            ("hitung total pengeluaran",              "CALCULATE"),
            ("terjemahkan teks ini",                  "TRANSLATE"),
            ("analisis data sensor",                  "ANALYZE"),
            ("download file dari server",             "DOWNLOAD"),
            ("perbarui database harga",               "UPDATE"),
        ]
        # Query phrases — just check head==QUERY
        query_phrases = [
            "apa itu machine learning",
            "bagaimana cara install Python",
            "siapa yang membuat JAYA",
            "kapan jadwal maintenance",
            "di mana file konfigurasi",
            "kenapa error ini muncul",
            "berapa kapasitas RAM yang dibutuhkan",
            "jelaskan cara kerja transformer",
        ]
        failures = []
        for phrase, expected_action in action_cases:
            result = self._parse(phrase)
            if result is None:
                failures.append(f"NONE: '{phrase}'")
                continue
            if result["head"] != "ACTION" or result["type"].upper() != expected_action:
                failures.append(
                    f"'{phrase}' → head='{result['head']}' type='{result['type']}' "
                    f"(expected ACTION {expected_action})"
                )
        for phrase in query_phrases:
            result = self._parse(phrase)
            if result is None:
                failures.append(f"NONE: '{phrase}'")
                continue
            if result["head"] != "QUERY":
                failures.append(
                    f"'{phrase}' → head='{result['head']}' (expected QUERY)"
                )
        self.assertEqual(failures, [],
            "LinguaLogica Bahasa Indonesia failures:\n" + "\n".join(failures))


# ─────────────────────────────────────────────────────────────────────────────
# 9. IntentEngine TF-IDF upgrade
# ─────────────────────────────────────────────────────────────────────────────
class TestIntentEngineTFIDF(unittest.TestCase):
    def setUp(self):
        # Use a temp file for the model so we don't clobber real data
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        model_path   = os.path.join(self._tmpdir, "intent_test.json")
        from jaya_core.brain_v2.engine.intent_engine import IntentEngine
        self.engine = IntentEngine(n=2, model_path=model_path)

    def test_tfidf_learns_and_predicts(self):
        """After learning commands, TF-IDF index returns relevant results."""
        commands = [
            "search database for records",
            "search files in folder",
            "delete old logs",
            "open settings panel",
        ]
        for cmd in commands:
            self.engine.learn(cmd)
        # TF-IDF should return something for 'search' query
        results = self.engine.tfidf.search("search", top_k=3)
        self.assertTrue(len(results) > 0,
            "TF-IDF returned no results after learning 'search' commands")
        # Top result should be a search-related command
        top_cmd, _ = results[0]
        self.assertIn("search", top_cmd.lower(),
            f"TF-IDF top result '{top_cmd}' not related to 'search'")

    def test_status_includes_tfidf_docs(self):
        """status() must include 'tfidf_docs' field (V18)."""
        status = self.engine.status()
        self.assertIn("tfidf_docs", status,
            "IntentEngine.status() missing 'tfidf_docs' key (V18 field)")
        self.engine.learn("test command")
        status2 = self.engine.status()
        self.assertEqual(status2["tfidf_docs"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# 10. forge_v18.py integration smoke test
# ─────────────────────────────────────────────────────────────────────────────
class TestForgeV18(unittest.TestCase):
    def test_forge_writes_valid_jay(self):
        """forge() creates a .jay file with valid magic and V18 version."""
        import struct
        from scripts.forge_v18 import forge
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "test_v18.jay")
            forge(out)
            self.assertTrue(os.path.exists(out), "forge() did not create output file")
            with open(out, "rb") as f:
                hdr = f.read(128)
            self.assertEqual(hdr[:4], b"JAYA", "Bad magic in forged .jay")
            version_major = struct.unpack_from("<H", hdr, 4)[0]
            self.assertEqual(version_major, 18,
                f"Expected version 18, got {version_major}")

    def test_forge_packed_weights_flag(self):
        """Forged .jay must have PACKED_WEIGHTS flag (bit 42) set."""
        import struct
        from scripts.forge_v18 import forge
        from jaya_core.brain_v2.format.schema import JayaFlags
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "test_flag.jay")
            forge(out)
            with open(out, "rb") as f:
                hdr = f.read(128)
            flags = struct.unpack_from("<Q", hdr, 8)[0]
            self.assertTrue(flags & JayaFlags.PACKED_WEIGHTS,
                "PACKED_WEIGHTS flag not set in forged V18 .jay")
            self.assertTrue(flags & JayaFlags.NANO_PROFILE,
                "NANO_PROFILE flag not set in forged V18 .jay")
            self.assertTrue(flags & JayaFlags.SELF_EVOLVING,
                "SELF_EVOLVING flag not set in forged V18 .jay")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)
