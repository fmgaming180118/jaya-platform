"""Regression tests for the quarantined legacy migration prototype.

Strict compliance checks according to AGENTS.md:
- Pure-Python .jay soul header validation and hardware UUID authorization
- HMAC-signed resurrection token lifecycle (issuance, redemption, expiry, rejection)
- Migration and hardware re-binding
- Production runtime keeps the incomplete importer unavailable
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import time
import zlib
import pytest

from jaya_core.brain_v2.engine.legacy_protocol import LegacyProtocol
from jaya_core.brain_v2.engine.runtime import IronEngine


def _create_mock_jay_file(target_path: Path) -> None:
    """Create a minimal valid 128-byte header .jay soul archive for testing."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(128)
    header[:4] = b"JAYA"  # Magic
    # Hardware hash offset 16..48, DNA hash 48..80, Salt 88..120
    header[16:48] = b"\x01" * 32
    header[48:80] = b"\x02" * 32
    header[88:120] = b"\x03" * 32

    # Section payload
    payload = b"TEST_SOUL_PAYLOAD"
    sec_hdr = bytearray(24)
    struct.pack_into("<I", sec_hdr, 0, 1)  # Section type 1 = SOUL_KEY
    struct.pack_into("<Q", sec_hdr, 8, len(payload))
    struct.pack_into("<Q", sec_hdr, 16, 128 + 24)

    # Footer (32 bytes: 4 bytes CRC32 + 28 bytes SHA tag)
    content = header + sec_hdr + payload
    crc = zlib.crc32(content) & 0xFFFFFFFF
    footer = bytearray(32)
    footer[:4] = struct.pack("<I", crc)

    with open(target_path, "wb") as f:
        f.write(content + footer)


def test_legacy_protocol_first_boot_and_authorization(tmp_path: Path):
    jay_path = tmp_path / "test.jay"
    _create_mock_jay_file(jay_path)

    lp = LegacyProtocol(jay_path=str(jay_path), dna_secret=b"MY_DNA_SECRET")

    # First boot: self registers
    hw_1 = "node-alpha-1234"
    assert lp.can_awaken_on(hw_1) is True

    # Same hardware awakens successfully
    assert lp.can_awaken_on(hw_1) is True

    # Unknown hardware is rejected
    hw_2 = "node-beta-5678"
    assert lp.can_awaken_on(hw_2) is False


def test_legacy_protocol_resurrection_tokens(tmp_path: Path):
    jay_path = tmp_path / "test.jay"
    _create_mock_jay_file(jay_path)

    lp = LegacyProtocol(jay_path=str(jay_path), dna_secret=b"MY_DNA_SECRET")
    lp.can_awaken_on("node-alpha-1234")

    # Generate token for node-beta
    token = lp.generate_resurrection_token("node-beta-5678", ttl_days=1.0)
    assert isinstance(token, str)

    # Before redemption, node-beta is rejected
    assert lp.can_awaken_on("node-beta-5678") is False

    # Redeem token
    redeemed = lp.redeem_resurrection_token(token)
    assert redeemed is True

    # Now node-beta is authorized
    assert lp.can_awaken_on("node-beta-5678") is True

    # Invalid token rejection
    bad_token = token.replace("node-beta", "node-gamma")
    assert lp.redeem_resurrection_token(bad_token) is False

    # Expired token rejection
    expired_token = lp.generate_resurrection_token("node-gamma-9999", ttl_days=-1.0)
    assert lp.redeem_resurrection_token(expired_token) is False


def test_legacy_protocol_migration(tmp_path: Path):
    src_jay = tmp_path / "src.jay"
    dst_jay = tmp_path / "dst.jay"
    _create_mock_jay_file(src_jay)

    lp = LegacyProtocol(jay_path=str(src_jay), dna_secret=b"MY_DNA_SECRET")
    lp.can_awaken_on("node-alpha-1234")

    # Migrate with rebinding to node-gamma
    ok = lp.migrate(str(dst_jay), dst_hw_uuid="node-gamma-7777")
    assert ok is True
    assert dst_jay.exists()
    assert (tmp_path / "dst.jay.resurrection").exists()

    # Destination manifest should have node-gamma approved
    lp_dst = LegacyProtocol(jay_path=str(dst_jay), dna_secret=b"MY_DNA_SECRET")
    assert lp_dst.can_awaken_on("node-gamma-7777") is True


def test_legacy_protocol_is_quarantined_from_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    jay_path = tmp_path / "engine_soul.jay"
    _create_mock_jay_file(jay_path)
    monkeypatch.setenv("JAYA_SOUL_PATH", str(jay_path))

    engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
    engine.ignite()

    assert engine.can_awaken_on("host-hw-001") is False
    assert engine.generate_resurrection_token("host-hw-002") is None
    assert engine.redeem_resurrection_token("untrusted-token") is False

    dst_path = tmp_path / "migrated_soul.jay"
    migrated = engine.migrate_soul(str(dst_path), dst_hw_uuid="host-hw-003")
    assert migrated is False
    assert not dst_path.exists()

    st = engine.status()
    assert st["legacy_protocol"] is None
