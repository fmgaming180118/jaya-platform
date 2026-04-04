"""Phase 1 sovereign foundation tests.

This gate validates pure-Python fallback foundations for:
- Pillar 14 hardware identity hashing.
- Soul payload crypto roundtrip and tamper detection.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.protection.hardware import get_system_uuid, get_system_uuid_with_source
from src.brain_v2.protection.soul_crypto import SoulCrypto


class TestHardwareIdentity(unittest.TestCase):
    def test_system_uuid_digest_shape_and_stability(self):
        first = get_system_uuid()
        second = get_system_uuid()

        self.assertIsInstance(first, (bytes, bytearray))
        self.assertEqual(len(first), 32)
        self.assertEqual(first, second)

    def test_strict_mode_rejects_fallback_identity(self):
        import src.brain_v2.protection.hardware as hw

        with patch.object(hw, "_probe_native_uuid", return_value=(None, "linux")):
            with patch.dict(os.environ, {"JAYA_STRICT_HARDWARE_LOCK": "1"}, clear=False):
                with self.assertRaises(RuntimeError):
                    hw.get_system_uuid_with_source()

    def test_source_label_present(self):
        digest, source = get_system_uuid_with_source()
        self.assertEqual(len(digest), 32)
        self.assertTrue(source)


class TestSoulCrypto(unittest.TestCase):
    def test_roundtrip_payload(self):
        crypto = SoulCrypto()
        key, _ = crypto.derive_key(password="pw", hardware_id=b"hw-id")
        crypto.key = key

        payload = {
            "state": "SOVEREIGN_ACTIVE",
            "score": 0.99,
            "memories": ["alpha", "beta"],
        }
        nonce, cipher, tag = crypto.encrypt(payload)
        restored = crypto.decrypt(nonce, cipher, tag)
        self.assertEqual(restored, payload)

    def test_detect_tamper(self):
        crypto = SoulCrypto()
        key, _ = crypto.derive_key(password="pw", hardware_id=b"hw-id")
        crypto.key = key

        nonce, cipher, tag = crypto.encrypt({"ok": True})
        tampered = bytearray(cipher)
        tampered[0] ^= 0x01

        with self.assertRaises(ValueError):
            crypto.decrypt(nonce, bytes(tampered), tag)

    def test_derive_key_deterministic_with_same_salt(self):
        crypto = SoulCrypto()
        salt = b"1234567890abcdef"

        k1, s1 = crypto.derive_key(password="pw", hardware_id=b"hw-id", salt=salt)
        k2, s2 = crypto.derive_key(password="pw", hardware_id=b"hw-id", salt=salt)

        self.assertEqual(s1, s2)
        self.assertEqual(k1, k2)


if __name__ == "__main__":
    unittest.main()
