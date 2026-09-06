"""Comprehensive verification tests for Pillar 04 Multimodal Reflex."""

from __future__ import annotations

import base64
import shutil
import struct
import wave
import zlib
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.media_capability import (
    MEDIA_CAPABILITY_ID,
    MediaObservationCapability,
)


def _write_wav(path: Path, sample_rate: int = 8000, frames: int = 800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * frames)


def _make_minimal_png(width: int = 64, height: int = 32) -> bytes:
    """Create a syntactically valid raw PNG byte stream."""
    signature = b"\x89PNG\r\n\x1a\n"
    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc

    # IDAT (empty image data)
    raw_scanlines = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    compressed = zlib.compress(raw_scanlines)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc

    # IEND
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc

    return signature + ihdr + idat + iend


def _make_minimal_bmp(width: int = 50, height: int = 40) -> bytes:
    """Create a syntactically valid BMP byte stream."""
    row_size = ((width * 3 + 3) // 4) * 4
    image_size = row_size * height
    file_size = 54 + image_size
    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    info_header = struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24, 0, image_size, 2835, 2835, 0, 0)
    pixel_data = b"\x7f\x7f\x7f" * (row_size * height // 3)
    return file_header + info_header + pixel_data[:image_size]


def test_p04_audio_observation_and_spans(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = root / "sample.wav"
    database = tmp_path / "media.sqlite3"
    _write_wav(source, sample_rate=16000, frames=16000)  # 1.0s audio

    cap = MediaObservationCapability(root=root, database_path=database)
    res = cap.execute({"action": "observe_file", "path": "sample.wav"})
    data = res.data

    assert data["provider"] == "FFPROBE"
    assert data["modality"] == "AUDIO"
    assert data["truth_class"] == "EXTRACTED_EVIDENCE"
    assert data["confidence"] == 1.0
    assert len(data["evidence_spans"]) >= 1
    assert data["evidence_spans"][0]["modality"] == "AUDIO"
    assert data["evidence_spans"][0]["truth_class"] == "EXTRACTED_EVIDENCE"
    assert "evidence_digest" in data["evidence_spans"][0]

    # Test explicit extract_spans
    spans_res = cap.execute({"action": "extract_spans", "observation_id": data["observation_id"]})
    assert spans_res.data["observation_id"] == data["observation_id"]
    assert len(spans_res.data["evidence_spans"]) == len(data["evidence_spans"])


def test_p04_image_observation_png_and_bmp(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    png_path = root / "image.png"
    png_path.write_bytes(_make_minimal_png(64, 32))
    bmp_path = root / "graphic.bmp"
    bmp_path.write_bytes(_make_minimal_bmp(50, 40))

    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")

    png_obs = cap.execute({"action": "observe_file", "path": "image.png"})
    assert png_obs.data["modality"] == "IMAGE"
    assert png_obs.data["detected_mime"] == "image/png"
    assert png_obs.data["streams"][0]["width"] == 64
    assert png_obs.data["streams"][0]["height"] == 32
    assert png_obs.data["evidence_spans"][0]["modality"] == "IMAGE"

    bmp_obs = cap.execute({"action": "observe_file", "path": "graphic.bmp"})
    assert bmp_obs.data["modality"] == "IMAGE"
    assert bmp_obs.data["detected_mime"] == "image/bmp"
    assert bmp_obs.data["streams"][0]["width"] == 50
    assert bmp_obs.data["streams"][0]["height"] == 40


def test_p04_document_observation_txt_and_pdf(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    doc_path = root / "report.txt"
    doc_path.write_text(
        "JAYA Operating System Multimodal Reflex Architecture.\n"
        "Evidence span extraction verifies source provenance deterministically.\n"
        "P04 integrates directly with Semantic Bridge P26.\n",
        encoding="utf-8",
    )
    pdf_path = root / "document.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF")

    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")

    txt_obs = cap.execute({"action": "observe_file", "path": "report.txt"})
    assert txt_obs.data["modality"] == "DOCUMENT"
    assert txt_obs.data["provider"] == "DOCUMENT_EXTRACTOR"
    assert txt_obs.data["detected_mime"] == "text/plain"
    assert len(txt_obs.data["evidence_spans"]) >= 1
    assert txt_obs.data["evidence_spans"][0]["modality"] == "DOCUMENT"
    assert "start_offset" in txt_obs.data["evidence_spans"][0]

    pdf_obs = cap.execute({"action": "observe_file", "path": "document.pdf"})
    assert pdf_obs.data["modality"] == "DOCUMENT"
    assert pdf_obs.data["detected_mime"] == "application/pdf"


def test_p04_security_magic_bytes_and_mime_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    # File named fake.png containing JPEG bytes
    fake_png = root / "fake.png"
    fake_png.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 30)

    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")

    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "observe_file", "path": "fake.png"})
    assert exc.value.code == "MIME_MISMATCH"

    # Declared MIME mismatch
    real_png = root / "real.png"
    real_png.write_bytes(_make_minimal_png(16, 16))
    with pytest.raises(LocalPillarError) as exc2:
        cap.execute(
            {
                "action": "observe_file",
                "path": "real.png",
                "options": {"declared_mime": "audio/wav"},
            }
        )
    assert exc2.value.code == "MIME_MISMATCH"


def test_p04_security_decompression_bomb_detection(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()

    # Image header claiming 20,000 x 20,000 pixels (exceeds 16,384 bound)
    bomb_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">IIBBBBB", 20000, 20000, 8, 6, 0, 0, 0)
    bomb_path = root / "bomb.png"
    bomb_path.write_bytes(bomb_header + b"\x00" * 100)

    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")

    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "observe_file", "path": "bomb.png"})
    assert exc.value.code == "DECOMPRESSION_BOMB_DETECTED"


def test_p04_security_resource_limit_and_confinement(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    _write_wav(outside)

    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3", maximum_bytes=64)

    # Path traversal
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "observe_file", "path": "../outside.wav"})
    assert exc.value.code == "PERMISSION_DENIED"

    # Absolute escape
    with pytest.raises(LocalPillarError) as exc2:
        cap.execute({"action": "observe_file", "path": str(outside)})
    assert exc2.value.code == "PERMISSION_DENIED"

    # Resource limit
    large_wav = root / "oversized.wav"
    _write_wav(large_wav, frames=1000)
    with pytest.raises(LocalPillarError) as exc3:
        cap.execute({"action": "observe_file", "path": "oversized.wav"})
    assert exc3.value.code == "RESOURCE_LIMIT"


def test_p04_observe_bytes_and_artifact_storage(tmp_path: Path) -> None:
    root = tmp_path / "media"
    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")

    png_bytes = _make_minimal_png(32, 32)
    b64_content = base64.b64encode(png_bytes).decode("ascii")

    res = cap.execute(
        {
            "action": "observe_bytes",
            "content_base64": b64_content,
            "filename": "ingested.png",
        }
    )
    assert res.data["modality"] == "IMAGE"
    assert res.data["detected_mime"] == "image/png"
    assert "artifacts" in res.data["source_path"]

    # Security: Reject path traversal in filename
    with pytest.raises(LocalPillarError) as exc:
        cap.execute(
            {
                "action": "observe_bytes",
                "content_base64": b64_content,
                "filename": "../../evil.png",
            }
        )
    assert exc.value.code == "INVALID_INPUT"


def test_p04_semantic_provider_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = root / "speech.wav"
    _write_wav(source)

    cap = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")

    # Modality action requiring semantic ASR provider when none configured
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({"action": "observe_file", "path": "speech.wav", "modality_action": "TRANSCRIBE"})
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"

    # Modality action requiring Vision provider when none configured
    img = root / "view.png"
    img.write_bytes(_make_minimal_png(16, 16))
    with pytest.raises(LocalPillarError) as exc2:
        cap.execute({"action": "observe_file", "path": "view.png", "modality_action": "DESCRIBE"})
    assert exc2.value.code == "CAPABILITY_UNAVAILABLE"


def test_p04_durability_across_restart_and_management(tmp_path: Path) -> None:
    root = tmp_path / "media"
    database = tmp_path / "media.sqlite3"
    wav = root / "tone.wav"
    _write_wav(wav)
    doc = root / "note.txt"
    doc.write_text("Durable test content", encoding="utf-8")

    cap = MediaObservationCapability(root=root, database_path=database)
    obs1 = cap.execute({"action": "observe_file", "path": "tone.wav"})
    obs2 = cap.execute({"action": "observe_file", "path": "note.txt"})

    # Restart capability with fresh instance
    restarted = MediaObservationCapability(root=root, database_path=database)

    # Read by ID
    r1 = restarted.execute({"action": "get", "observation_id": obs1.data["observation_id"]})
    assert r1.data["source_digest"] == obs1.data["source_digest"]

    # List observations
    listed_audio = restarted.execute({"action": "list_observations", "modality": "AUDIO"})
    assert listed_audio.data["count"] == 1
    assert listed_audio.data["observations"][0]["observation_id"] == obs1.data["observation_id"]

    listed_all = restarted.execute({"action": "list_observations"})
    assert listed_all.data["count"] == 2

    # Metrics
    m = restarted.execute({"action": "metrics"})
    assert m.data["total_observations"] == 2
    assert m.data["by_modality"]["AUDIO"] == 1
    assert m.data["by_modality"]["DOCUMENT"] == 1
    assert m.data["ffprobe_healthy"] is True

    # Delete
    del_res = restarted.execute({"action": "delete", "observation_id": obs1.data["observation_id"]})
    assert del_res.data["status"] == "DELETED"
    with pytest.raises(LocalPillarError) as exc:
        restarted.execute({"action": "get", "observation_id": obs1.data["observation_id"]})
    assert exc.value.code == "OBSERVATION_NOT_FOUND"


def test_p04_runtime_integration(tmp_path: Path) -> None:
    root = tmp_path / "authorized-media"
    _write_wav(root / "runtime_sound.wav")
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        local_media_root=root,
    )
    try:
        result = runtime.execute_local_pillar(
            MEDIA_CAPABILITY_ID, {"action": "observe_file", "path": "runtime_sound.wav"}
        )
        assert result.data["modality"] == "AUDIO"
        assert result.data["truth_class"] == "EXTRACTED_EVIDENCE"
        assert len(result.data["evidence_spans"]) >= 1
    finally:
        runtime.close()
