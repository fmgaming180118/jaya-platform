from __future__ import annotations

from pathlib import Path

import pytest

from jaya_core.brain_v2.format.schema import JayaFlags
from jaya_core.brain_v2.genesis import (
    _ACTIVE_PILLAR_STATES,
    _implemented_pillar_flags,
    ignite_genesis,
)
from jaya_core.pillars.manifest import load_manifest


MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jaya_core"
    / "contracts"
    / "40_pillars.yaml"
)


def test_genesis_flags_follow_truthful_canonical_statuses() -> None:
    flags, count = _implemented_pillar_flags()
    active = [
        pillar
        for pillar in load_manifest(MANIFEST)
        if pillar.initial_status in _ACTIVE_PILLAR_STATES
    ]

    assert count == len(active)
    for pillar in load_manifest(MANIFEST):
        if pillar.source_flag is None:
            continue
        flag = getattr(JayaFlags, pillar.source_flag.removeprefix("JayaFlags."))
        assert bool(flags & flag) is (pillar.initial_status in _ACTIVE_PILLAR_STATES)


def test_genesis_requires_opt_in_and_injected_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "prototype.jay"
    monkeypatch.delenv("JAYA_DNA_ANCHOR_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="explicit allow_prototype"):
        ignite_genesis(target)
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        ignite_genesis(target, allow_prototype=True)

    assert not target.exists()
