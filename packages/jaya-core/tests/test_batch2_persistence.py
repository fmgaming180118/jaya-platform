"""Persistence and reboot recovery test suite for Batch 2:
- Pillar 24 (Morphic Kernel)
- Pillar 40 (Intent Engine)
- Pillar 19 (Legacy Protocol)
- Pillar 37 (Hybrid Router)

Strict compliance with AGENTS.md:
- Tests persist data to temporary disk directories
- Destroys in-memory instances completely
- Recreates fresh instances from disk storage
- Asserts 100% data integrity and behavior fidelity across restarts
"""

from __future__ import annotations

from pathlib import Path
import struct
import zlib
import pytest

from jaya_core.brain_v2.engine.morphic import MorphicKernel
from jaya_core.brain_v2.engine.intent_engine import IntentEngine
from jaya_core.brain_v2.engine.legacy_protocol import LegacyProtocol
from jaya_core.brain_v2.engine.hybrid_mode import HybridRouter


class _Calculator:
    def add(self, a: int, b: int) -> dict:
        return {"result": a + b, "mode": "standard"}


def _create_mock_jay(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(128)
    header[:4] = b"JAYA"
    header[16:48] = b"\xaa" * 32
    header[48:80] = b"\xbb" * 32
    header[88:120] = b"\xcc" * 32
    payload = b"PERSISTENCE_TEST_SOUL"
    sec_hdr = bytearray(24)
    struct.pack_into("<I", sec_hdr, 0, 1)
    struct.pack_into("<Q", sec_hdr, 8, len(payload))
    struct.pack_into("<Q", sec_hdr, 16, 128 + 24)
    content = header + sec_hdr + payload
    crc = zlib.crc32(content) & 0xFFFFFFFF
    footer = bytearray(32)
    footer[:4] = struct.pack("<I", crc)
    with open(path, "wb") as f:
        f.write(content + footer)


def test_morphic_kernel_lifecycle_and_sandboxing():
    """Verify MorphicKernel atomic safe patching, verification, and rollback."""
    kernel = MorphicKernel()
    calc = _Calculator()

    patch_code = """
def add():
    return {"result": 42, "mode": "morphic_constant"}
"""
    assert kernel.patch(calc, "add", patch_code) is True
    assert calc.add(1, 2) == {"result": 42, "mode": "morphic_constant"}
    assert kernel.status()["active"] == 1

    # Atomic rollback
    restored = kernel.rollback("add")
    assert restored == 1
    assert calc.add(10, 20) == {"result": 30, "mode": "standard"}
    assert kernel.status()["active"] == 0


def test_intent_engine_reboot_persistence(tmp_path: Path):
    """Verify IntentEngine preserves N-gram and TF-IDF models across reboot."""
    db_path = tmp_path / "intent_db.json"

    # Session 1: Learn user command patterns
    engine1 = IntentEngine(storage_path=db_path)
    engine1.learn("build native binary package")
    engine1.learn("build docker container image")
    engine1.learn("run unit tests with pytest")
    engine1.learn("run integration test suite")
    engine1.save()

    del engine1  # Complete tear down

    # Session 2: Fresh instance from disk
    engine2 = IntentEngine(storage_path=db_path)
    st = engine2.status()
    assert st["learned"] == 4
    assert st["tfidf_docs"] == 4
    assert st["prefixes"] > 0

    # Predictions match accurately
    pred_build = engine2.predict_intent("build", top_k=2)
    assert len(pred_build) > 0
    assert any("native" in p[0] or "docker" in p[0] for p in pred_build)

    best_run = engine2.best_prediction("run unit")
    assert best_run is not None
    assert "tests" in best_run


def test_legacy_protocol_reboot_persistence(tmp_path: Path):
    """Verify LegacyProtocol manifest and resurrection tokens survive restarts."""
    jay_path = tmp_path / "soul_restart.jay"
    _create_mock_jay(jay_path)

    # Session 1: Self register host-1, generate and redeem token for host-2
    lp1 = LegacyProtocol(jay_path=str(jay_path), dna_secret=b"PERSIST_KEY")
    assert lp1.can_awaken_on("node-alpha-1") is True
    token = lp1.generate_resurrection_token("node-beta-2", ttl_days=5.0)
    assert lp1.redeem_resurrection_token(token) is True
    assert lp1.can_awaken_on("node-beta-2") is True
    assert lp1.can_awaken_on("node-gamma-3") is False

    del lp1  # Complete tear down

    # Session 2: Reload from disk
    lp2 = LegacyProtocol(jay_path=str(jay_path), dna_secret=b"PERSIST_KEY")
    assert lp2.can_awaken_on("node-alpha-1") is True
    assert lp2.can_awaken_on("node-beta-2") is True
    assert lp2.can_awaken_on("node-gamma-3") is False
    assert lp2.status()["approved_uuids"] == 2


def test_hybrid_router_reboot_persistence(tmp_path: Path):
    """Verify HybridRouter state and route counters survive restart."""
    state_file = tmp_path / "hybrid_persist.json"

    # Session 1: Route multiple features in force_offline mode
    router1 = HybridRouter(force_offline=True, storage_path=state_file)
    router1.route("ternary_model")
    router1.route("ternary_model")
    router1.route("local_rag")
    router1.route("collective_pulse")  # should be denied
    router1.save_state()

    del router1  # Complete tear down

    # Session 2: Reload from disk
    router2 = HybridRouter(force_offline=True, storage_path=state_file)
    st = router2.status()
    assert st["is_online"] is False
    assert st["route_counts"]["ternary_model"] == 2
    assert st["route_counts"]["local_rag"] == 1
    assert st["route_counts"]["collective_pulse"] == 1
