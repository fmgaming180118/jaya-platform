"""Real ffprobe integration and failure tests for P4 Multimodal Reflex."""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.media_capability import MEDIA_CAPABILITY_ID, MediaObservationCapability


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 800)


def test_p004_observes_real_audio_and_persists_provider_output(tmp_path: Path) -> None:
    assert shutil.which("ffprobe") is not None
    root = tmp_path / "media"
    source = root / "sample.wav"
    database = tmp_path / "media.sqlite3"
    _write_wav(source)
    capability = MediaObservationCapability(root=root, database_path=database)

    observed = capability.execute({"action": "observe_file", "path": "sample.wav"})
    restarted = MediaObservationCapability(root=root, database_path=database)
    read = restarted.execute(
        {"action": "get", "observation_id": observed.data["observation_id"]}
    )

    assert observed.data["provider"] == "FFPROBE"
    assert observed.data["modality"] == "AUDIO"
    assert observed.data["streams"][0]["sample_rate"] == "8000"
    assert read.data["source_digest"] == observed.data["source_digest"]
    assert observed.data["duration_ns"] > 0


def test_p004_rejects_malformed_media_escape_and_resource_limit(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    (root / "broken.bin").write_bytes(b"not-media")
    outside = tmp_path / "outside.wav"
    _write_wav(outside)
    capability = MediaObservationCapability(
        root=root,
        database_path=tmp_path / "media.sqlite3",
        maximum_bytes=32,
    )
    with pytest.raises(LocalPillarError) as malformed:
        capability.execute({"action": "observe_file", "path": "broken.bin"})
    assert malformed.value.code == "MALFORMED_MEDIA"
    with pytest.raises(LocalPillarError) as escape:
        capability.execute({"action": "observe_file", "path": str(outside)})
    assert escape.value.code == "PERMISSION_DENIED"
    _write_wav(root / "large.wav")
    with pytest.raises(LocalPillarError) as limit:
        capability.execute({"action": "observe_file", "path": "large.wav"})
    assert limit.value.code == "RESOURCE_LIMIT"


def test_runtime_dispatches_p004_with_configured_media_root(tmp_path: Path) -> None:
    root = tmp_path / "authorized-media"
    _write_wav(root / "runtime.wav")
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        local_media_root=root,
    )
    try:
        result = runtime.execute_local_pillar(
            MEDIA_CAPABILITY_ID, {"action": "observe_file", "path": "runtime.wav"}
        )
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        assert result.data["modality"] == "AUDIO"
        assert health[MEDIA_CAPABILITY_ID] == "HEALTHY"
    finally:
        runtime.close()
