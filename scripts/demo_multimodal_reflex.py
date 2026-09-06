#!/usr/bin/env python3
"""Interactive demonstration of Pillar 04 Multimodal Reflex."""

from __future__ import annotations

import base64
import json
import shutil
import struct
import sys
import tempfile
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.media_capability import MediaObservationCapability  # noqa: E402


def _write_wav(path: Path, sample_rate: int = 16000, frames: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * frames)


def _make_minimal_png(width: int = 64, height: int = 32) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc

    raw_scanlines = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    compressed = zlib.compress(raw_scanlines)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc

    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    return signature + ihdr + idat + iend


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p04_"))
    media_root = temp_dir / "media_store"
    media_root.mkdir(parents=True, exist_ok=True)
    db_path = media_root / "media_ledger.sqlite3"

    print("=" * 75)
    print(" JAYA COGNITIVE ARCHITECTURE — PILAR 04: MULTIMODAL REFLEX DEMO")
    print("=" * 75)
    print(f"Store Root: {media_root}\n")

    try:
        cap = MediaObservationCapability(root=media_root, database_path=db_path)

        # 1. Health check
        print("[1] Performing capability health check and probing ffprobe binary...")
        healthy = cap.health_check()
        print(f"    ffprobe Path   : {cap.ffprobe_path}")
        print(f"    Health Status  : {'NOMINAL' if healthy else 'DEGRADED'}\n")

        # 2. Audio Ingestion & Span Extraction
        print("[2] Ingesting real Audio file (sample.wav: 16kHz, 1.0s mono)...")
        wav_file = media_root / "sample.wav"
        _write_wav(wav_file, sample_rate=16000, frames=16000)
        audio_obs = cap.execute({"action": "observe_file", "path": "sample.wav"})
        data = audio_obs.data
        print(f"    Observation ID : {data['observation_id']}")
        print(f"    Modality       : {data['modality']}")
        print(f"    MIME Type      : {data['detected_mime']}")
        print(f"    Truth Class    : {data['truth_class']}")
        print(f"    Confidence     : {data['confidence']}")
        print(f"    Stream Codec   : {data['streams'][0].get('codec')}")
        print(f"    Duration       : {data['streams'][0].get('duration_seconds')}s")
        print(f"    Evidence Spans : {len(data['evidence_spans'])} spans generated")
        print(f"    Span 0 Digest  : {data['evidence_spans'][0]['evidence_digest']}\n")

        # 3. Image Ingestion
        print("[3] Ingesting real Image file (diagram.png: 64x32 RGBA)...")
        png_file = media_root / "diagram.png"
        png_file.write_bytes(_make_minimal_png(64, 32))
        img_obs = cap.execute({"action": "observe_file", "path": "diagram.png"})
        print(f"    Observation ID : {img_obs.data['observation_id']}")
        print(f"    Modality       : {img_obs.data['modality']}")
        print(f"    Resolution     : {img_obs.data['streams'][0]['width']}x{img_obs.data['streams'][0]['height']}")
        print(f"    Truth Class    : {img_obs.data['truth_class']}\n")

        # 4. Document Ingestion
        print("[4] Ingesting Document file (system_log.txt)...")
        doc_file = media_root / "system_log.txt"
        doc_file.write_text(
            "Kernel initialized.\nDeterministic evidence anchors established.\nP04 verification active.\n",
            encoding="utf-8",
        )
        doc_obs = cap.execute({"action": "observe_file", "path": "system_log.txt"})
        print(f"    Observation ID : {doc_obs.data['observation_id']}")
        print(f"    Modality       : {doc_obs.data['modality']}")
        print(f"    Paragraphs     : {len(doc_obs.data['evidence_spans'])}\n")

        # 5. Security Boundary Defenses
        print("[5] Testing Security Defenses...")

        # 5a. MIME mismatch
        print("    [5a] Testing Magic Byte MIME Mismatch Detection (spoofed .png)...")
        spoofed = media_root / "spoofed.png"
        spoofed.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
        try:
            cap.execute({"action": "observe_file", "path": "spoofed.png"})
            print("         ERROR: Mismatch was not rejected!")
        except LocalPillarError as exc:
            print(f"         PASSED -> Caught {exc.code}: {exc}")

        # 5b. Decompression Bomb
        print("    [5b] Testing Decompression Bomb Prevention (25,000 x 25,000 px)...")
        bomb = media_root / "bomb.png"
        bomb_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">IIBBBBB", 25000, 25000, 8, 6, 0, 0, 0)
        bomb.write_bytes(bomb_header + b"\x00" * 64)
        try:
            cap.execute({"action": "observe_file", "path": "bomb.png"})
            print("         ERROR: Bomb was not rejected!")
        except LocalPillarError as exc:
            print(f"         PASSED -> Caught {exc.code}: {exc}")

        # 5c. Path Confinement
        print("    [5c] Testing Root Confinement & Path Traversal Defense...")
        try:
            cap.execute({"action": "observe_file", "path": "../../windows/system32/cmd.exe"})
            print("         ERROR: Path traversal was not rejected!")
        except LocalPillarError as exc:
            print(f"         PASSED -> Caught {exc.code}: {exc}\n")

        # 6. Fail-Closed Semantic Dispatch
        print("[6] Testing Fail-Closed Semantic Dispatch (modality_action='TRANSCRIBE')...")
        try:
            cap.execute({"action": "observe_file", "path": "sample.wav", "modality_action": "TRANSCRIBE"})
            print("    ERROR: Semantic action succeeded without configured provider!")
        except LocalPillarError as exc:
            print(f"    PASSED -> Caught {exc.code}: {exc}\n")

        # 7. Durability Across Restart
        print("[7] Testing SQLite Durability Across Restart...")
        restarted = MediaObservationCapability(root=media_root, database_path=db_path)
        metrics = restarted.execute({"action": "metrics"}).data
        print(f"    Total Observations Persisted : {metrics['total_observations']}")
        print(f"    Modality Breakdown           : {json.dumps(metrics['by_modality'])}")

        print("\n" + "=" * 75)
        print(" PILAR 04 MULTIMODAL REFLEX: DEMONSTRATION COMPLETE (STATUS: VERIFIED)")
        print("=" * 75)
        return 0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
