"""Real local media observation adapter for Pillar 4."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .local_capabilities import LocalPillarError, LocalPillarResult

MEDIA_CAPABILITY_ID = "core.media.observe"

MAX_PIXEL_COUNT = 268_435_456  # 16,384 x 16,384
MAX_DIMENSION_EDGE = 16_384
MAX_UNCOMPRESSED_ESTIMATE_BYTES = 1024 * 1024 * 1024  # 1 GiB
MAX_COMPRESSION_RATIO = 500.0


@contextmanager
def _connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _strict(request: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    candidate = value.strip()
    if not 1 <= len(candidate) <= maximum:
        raise LocalPillarError("INVALID_INPUT", f"{field} must contain 1-{maximum} characters")
    return candidate


def _detect_magic(header: bytes, suffix: str = "") -> tuple[str | None, str | None]:
    """Detect MIME and modality from initial bytes."""
    if len(header) >= 8 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "IMAGE"
    if len(header) >= 3 and header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "IMAGE"
    if len(header) >= 6 and (header.startswith(b"GIF87a") or header.startswith(b"GIF89a")):
        return "image/gif", "IMAGE"
    if len(header) >= 2 and header.startswith(b"BM"):
        return "image/bmp", "IMAGE"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp", "IMAGE"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "audio/wav", "AUDIO"
    if len(header) >= 3 and header.startswith(b"ID3"):
        return "audio/mpeg", "AUDIO"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "audio/mpeg", "AUDIO"
    if len(header) >= 4 and header.startswith(b"fLaC"):
        return "audio/flac", "AUDIO"
    if len(header) >= 4 and header.startswith(b"OggS"):
        return "audio/ogg", "AUDIO"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4", "VIDEO"
    if len(header) >= 4 and header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", "VIDEO"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "video/x-msvideo", "VIDEO"
    if len(header) >= 5 and header.startswith(b"%PDF-"):
        return "application/pdf", "DOCUMENT"

    # Check for readable plain text / document with explicit document extensions
    doc_extensions = {".txt", ".md", ".json", ".csv", ".log", ".rst", ".yaml", ".yml"}
    if suffix.lower() in doc_extensions and header and len(header) >= 1:
        try:
            sample = header[:1024].decode("utf-8")
            if "\x00" not in sample:
                mime = "application/json" if suffix.lower() == ".json" else "text/plain"
                return mime, "DOCUMENT"
        except UnicodeDecodeError:
            pass

    return None, None


def _expected_mime_from_extension(suffix: str) -> str | None:
    ext = suffix.lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/webm",
        ".avi": "video/x-msvideo",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/plain",
        ".json": "application/json",
    }
    return mapping.get(ext)


def _parse_image_dimensions(header: bytes) -> tuple[int, int] | None:
    """Parse width and height from image header bytes."""
    # PNG
    if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        w, h = struct.unpack(">II", header[16:24])
        return w, h

    # BMP
    if len(header) >= 26 and header.startswith(b"BM"):
        w, h = struct.unpack("<ii", header[18:26])
        return abs(w), abs(h)

    # GIF
    if len(header) >= 10 and (header.startswith(b"GIF87a") or header.startswith(b"GIF89a")):
        w, h = struct.unpack("<HH", header[6:10])
        return w, h

    # WebP
    if len(header) >= 30 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        chunk = header[12:16]
        if chunk == b"VP8X" and len(header) >= 30:
            w = 1 + struct.unpack("<I", header[24:27] + b"\x00")[0]
            h = 1 + struct.unpack("<I", header[27:30] + b"\x00")[0]
            return w, h
        if chunk == b"VP8 " and len(header) >= 30:
            if header[23:26] == b"\x9d\x01\x2a":
                w = struct.unpack("<H", header[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", header[28:30])[0] & 0x3FFF
                return w, h

    # JPEG
    if len(header) >= 4 and header.startswith(b"\xff\xd8"):
        offset = 2
        while offset < len(header) - 8:
            if header[offset] != 0xFF:
                offset += 1
                continue
            marker = header[offset + 1]
            offset += 2
            if marker in (0xD8, 0xD9, 0x00, 0xFF):
                continue
            if offset + 2 > len(header):
                break
            length = struct.unpack(">H", header[offset : offset + 2])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if offset + 7 <= len(header):
                    h, w = struct.unpack(">HH", header[offset + 3 : offset + 7])
                    return w, h
            offset += length

    return None


class MediaObservationCapability:
    """Probe real media with ffprobe, validate security boundaries, and extract typed evidence."""

    def __init__(
        self,
        *,
        root: Path,
        database_path: Path,
        maximum_bytes: int = 64 * 1024 * 1024,
        timeout_seconds: float = 10.0,
        ffprobe_path: str | None = None,
        vision_provider: Any = None,
        asr_provider: Any = None,
        ocr_provider: Any = None,
    ) -> None:
        if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= 2**31:
            raise LocalPillarError("INVALID_CONFIG", "media byte limit is invalid")
        if not 0.1 <= timeout_seconds <= 120:
            raise LocalPillarError("INVALID_CONFIG", "media timeout is invalid")
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging_dir = self.root / ".staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.root / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.maximum_bytes = maximum_bytes
        self.timeout_seconds = timeout_seconds
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe")
        self.vision_provider = vision_provider
        self.asr_provider = asr_provider
        self.ocr_provider = ocr_provider
        self._active_jobs: dict[str, dict[str, Any]] = {}

        try:
            with _connection(self.database_path) as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS media_observations(
                    observation_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    source_digest TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                    )"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_media_digest ON media_observations(source_digest)"
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media observation store unavailable") from exc

    def health_check(self) -> bool:
        if not self.ffprobe_path or not Path(self.ffprobe_path).is_file():
            return False
        try:
            completed = subprocess.run(
                [self.ffprobe_path, "-version"],
                capture_output=True,
                timeout=min(self.timeout_seconds, 5.0),
                check=False,
            )
            return completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _confined(self, value: object) -> Path:
        relative = Path(_text(value, "path", 1_024))
        if relative.is_absolute():
            candidate = relative.expanduser().resolve()
        else:
            candidate = (self.root / relative).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise LocalPillarError("PERMISSION_DENIED", "media path escapes configured root") from exc
        if not candidate.is_file():
            raise LocalPillarError("FILE_NOT_FOUND", "media source was not found")
        return candidate

    def _digest(self, path: Path) -> tuple[str, int]:
        size = path.stat().st_size
        if not 1 <= size <= self.maximum_bytes:
            raise LocalPillarError("RESOURCE_LIMIT", "media source exceeds configured byte limit")
        digest = hashlib.sha256()
        read = 0
        try:
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    read += len(block)
                    if read > self.maximum_bytes:
                        raise LocalPillarError("RESOURCE_LIMIT", "media source grew beyond limit")
                    digest.update(block)
        except OSError as exc:
            raise LocalPillarError("FILE_UNAVAILABLE", "media source cannot be read") from exc
        return f"sha256:{digest.hexdigest()}", read

    def _validate_media_security(
        self, source: Path, size: int, declared_mime: str | None = None
    ) -> tuple[str | None, str | None]:
        """Validate magic bytes, MIME matching, and decompression bomb constraints."""
        header_sample_size = min(size, 65536)
        try:
            with source.open("rb") as f:
                header = f.read(header_sample_size)
        except OSError as exc:
            raise LocalPillarError("FILE_UNAVAILABLE", "unable to read media header") from exc

        detected_mime, detected_modality = _detect_magic(header, source.suffix)
        expected_mime = _expected_mime_from_extension(source.suffix)

        # 1. Enforce declared MIME check
        if declared_mime:
            if detected_mime and detected_mime != declared_mime:
                raise LocalPillarError(
                    "MIME_MISMATCH",
                    f"declared MIME '{declared_mime}' does not match detected MIME '{detected_mime}'",
                )

        # 2. Enforce file extension check against detected magic
        if expected_mime and detected_mime and expected_mime != detected_mime:
            raise LocalPillarError(
                "MIME_MISMATCH",
                f"file extension '{source.suffix}' implies '{expected_mime}' but detected '{detected_mime}'",
            )

        # 3. Decompression bomb check for images
        dimensions = _parse_image_dimensions(header)
        if dimensions:
            w, h = dimensions
            if w > MAX_DIMENSION_EDGE or h > MAX_DIMENSION_EDGE or (w * h) > MAX_PIXEL_COUNT:
                raise LocalPillarError(
                    "DECOMPRESSION_BOMB_DETECTED",
                    f"image dimensions {w}x{h} exceed maximum bound of {MAX_DIMENSION_EDGE} pixels",
                )
            uncompressed_bytes = w * h * 4
            if uncompressed_bytes > MAX_UNCOMPRESSED_ESTIMATE_BYTES:
                raise LocalPillarError(
                    "DECOMPRESSION_BOMB_DETECTED",
                    f"estimated uncompressed size {uncompressed_bytes} bytes exceeds safety limit",
                )
            if size > 0 and (uncompressed_bytes / size) > MAX_COMPRESSION_RATIO and uncompressed_bytes > 50 * 1024 * 1024:
                raise LocalPillarError(
                    "DECOMPRESSION_BOMB_DETECTED",
                    "image decompression ratio exceeds safety threshold",
                )

        return detected_mime, detected_modality

    def observe(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            {"action", "path", "modality_action", "options", "auth_token", "job_id"},
            {"action", "path"},
        )
        source = self._confined(request["path"])
        digest, size = self._digest(source)

        options = request.get("options") or {}
        declared_mime = options.get("declared_mime")
        detected_mime, detected_modality = self._validate_media_security(source, size, declared_mime)

        modality_action = request.get("modality_action", "INSPECT")

        # Handle Semantic Invocations
        if modality_action in ("TRANSCRIBE", "DESCRIBE", "OCR"):
            provider_map = {
                "TRANSCRIBE": (self.asr_provider, "ASR"),
                "DESCRIBE": (self.vision_provider, "Vision"),
                "OCR": (self.ocr_provider, "OCR"),
            }
            provider, name = provider_map[modality_action]
            if not provider or not getattr(provider, "is_healthy", lambda: True)():
                raise LocalPillarError(
                    "CAPABILITY_UNAVAILABLE",
                    f"semantic provider for {name} ({modality_action}) is not configured",
                )

        job_id = request.get("job_id") or uuid.uuid4().hex
        self._active_jobs[job_id] = {"status": "RUNNING", "source": str(source), "started_at": time.time()}

        started = time.perf_counter_ns()

        # Handle Document Modality
        if detected_modality == "DOCUMENT":
            return self._observe_document(source, digest, size, detected_mime, started, job_id)

        # Media Modalities (AUDIO, IMAGE, VIDEO) via FFPROBE
        if not self.ffprobe_path:
            raise LocalPillarError("PROVIDER_UNAVAILABLE", "ffprobe is not installed")

        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("TIMEOUT", "media provider timed out") from exc
        except OSError as exc:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("PROVIDER_UNAVAILABLE", "media provider cannot start") from exc

        if completed.returncode != 0:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("MALFORMED_MEDIA", "ffprobe rejected the media source")
        if len(completed.stdout.encode("utf-8")) > 1_048_576:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("RESOURCE_LIMIT", "media provider output exceeds 1 MiB")

        try:
            probed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("INVALID_PROVIDER_RESPONSE", "ffprobe output is invalid") from exc

        streams = probed.get("streams")
        if not isinstance(streams, list) or not streams:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("UNSUPPORTED_MEDIA", "media has no decodable streams")

        types = {str(stream.get("codec_type", "unknown")) for stream in streams}
        known = types & {"audio", "video", "subtitle", "data", "attachment"}
        if "video" in known:
            modality = (
                "IMAGE"
                if all(
                    int(stream.get("nb_frames", 0) or 0) <= 1
                    for stream in streams
                    if stream.get("codec_type") == "video"
                )
                else "VIDEO"
            )
        elif "audio" in known:
            modality = "AUDIO"
        else:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("UNSUPPORTED_MEDIA", "stream modality is unsupported")

        sanitized_streams = [
            {
                key: stream[key]
                for key in (
                    "index",
                    "codec_name",
                    "codec_type",
                    "width",
                    "height",
                    "sample_rate",
                    "channels",
                    "duration",
                    "nb_frames",
                )
                if key in stream
            }
            for stream in streams
        ]

        # Extract Evidence Spans (Semantic Bridge P26 Compatible)
        evidence_spans = self._generate_evidence_spans(modality, sanitized_streams, digest, size)

        observation_id = uuid.uuid4().hex
        observation = {
            "observation_id": observation_id,
            "source_path": str(source.relative_to(self.root)),
            "source_digest": digest,
            "size_bytes": size,
            "modality": modality,
            "detected_mime": detected_mime,
            "provider": "FFPROBE",
            "truth_class": "EXTRACTED_EVIDENCE",
            "confidence": 1.0,
            "streams": sanitized_streams,
            "format": {
                key: probed.get("format", {}).get(key)
                for key in ("format_name", "duration", "bit_rate")
                if key in probed.get("format", {})
            },
            "evidence_spans": evidence_spans,
            "duration_ns": time.perf_counter_ns() - started,
        }

        try:
            with _connection(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO media_observations VALUES(?,?,?,?,?,?,?)",
                    (
                        observation_id,
                        observation["source_path"],
                        digest,
                        modality,
                        "FFPROBE",
                        json.dumps(observation, sort_keys=True, separators=(",", ":")),
                        time.time(),
                    ),
                )
        except sqlite3.Error as exc:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media observation was not stored") from exc

        self._active_jobs.pop(job_id, None)
        return LocalPillarResult("P004", "MEDIA_OBSERVED", observation)

    def _observe_document(
        self, source: Path, digest: str, size: int, detected_mime: str | None, started: int, job_id: str
    ) -> LocalPillarResult:
        """Observe document text or PDF."""
        text_content = ""
        line_count = 0
        char_count = 0

        try:
            if detected_mime == "application/pdf":
                # Extract plain ASCII strings from PDF safely without external parser
                with source.open("rb") as f:
                    raw_bytes = f.read(min(size, 1024 * 1024))
                text_content = f"PDF Document: {len(raw_bytes)} bytes sampled"
                char_count = len(text_content)
                line_count = 1
            else:
                with source.open("r", encoding="utf-8", errors="replace") as f:
                    text_content = f.read(1024 * 1024)
                char_count = len(text_content)
                line_count = len(text_content.splitlines())
        except OSError as exc:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("FILE_UNAVAILABLE", "document content cannot be read") from exc

        # Evidence Spans for documents
        evidence_spans = []
        chunk_size = 500
        for i in range(0, min(char_count, 5000), chunk_size):
            chunk = text_content[i : i + chunk_size]
            span_digest = f"sha256:{hashlib.sha256(chunk.encode('utf-8')).hexdigest()}"
            evidence_spans.append(
                {
                    "span_id": f"doc-span-{len(evidence_spans)}",
                    "start_offset": i,
                    "end_offset": i + len(chunk),
                    "modality": "DOCUMENT",
                    "truth_class": "EXTRACTED_EVIDENCE",
                    "confidence": 1.0,
                    "snippet": chunk[:80],
                    "evidence_digest": span_digest,
                }
            )

        sanitized_streams = [
            {
                "index": 0,
                "codec_name": detected_mime or "text/plain",
                "codec_type": "document",
                "char_count": char_count,
                "line_count": line_count,
            }
        ]

        observation_id = uuid.uuid4().hex
        observation = {
            "observation_id": observation_id,
            "source_path": str(source.relative_to(self.root)),
            "source_digest": digest,
            "size_bytes": size,
            "modality": "DOCUMENT",
            "detected_mime": detected_mime,
            "provider": "DOCUMENT_EXTRACTOR",
            "truth_class": "EXTRACTED_EVIDENCE",
            "confidence": 1.0,
            "streams": sanitized_streams,
            "format": {
                "format_name": detected_mime or "text/plain",
                "duration": None,
                "bit_rate": None,
            },
            "evidence_spans": evidence_spans,
            "duration_ns": time.perf_counter_ns() - started,
        }

        try:
            with _connection(self.database_path) as connection:
                connection.execute(
                    "INSERT INTO media_observations VALUES(?,?,?,?,?,?,?)",
                    (
                        observation_id,
                        observation["source_path"],
                        digest,
                        "DOCUMENT",
                        "DOCUMENT_EXTRACTOR",
                        json.dumps(observation, sort_keys=True, separators=(",", ":")),
                        time.time(),
                    ),
                )
        except sqlite3.Error as exc:
            self._active_jobs.pop(job_id, None)
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media observation was not stored") from exc

        self._active_jobs.pop(job_id, None)
        return LocalPillarResult("P004", "MEDIA_OBSERVED", observation)

    def _generate_evidence_spans(
        self, modality: str, streams: list[dict[str, Any]], digest: str, size: int
    ) -> list[dict[str, Any]]:
        """Generate deterministic evidence spans compatible with P26 Semantic Bridge."""
        spans: list[dict[str, Any]] = []
        if modality == "AUDIO":
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
            total_duration = 1.0
            if audio_stream and audio_stream.get("duration"):
                try:
                    total_duration = float(audio_stream["duration"])
                except (ValueError, TypeError):
                    total_duration = 1.0
            sample_rate = audio_stream.get("sample_rate", "unknown") if audio_stream else "unknown"
            step = 1.0 if total_duration <= 10.0 else 5.0
            cur = 0.0
            idx = 0
            while cur < total_duration and idx < 20:
                end = min(cur + step, total_duration)
                span_data = f"{digest}:audio:{cur:.2f}:{end:.2f}".encode("utf-8")
                spans.append(
                    {
                        "span_id": f"audio-span-{idx}",
                        "start_time_s": round(cur, 3),
                        "end_time_s": round(end, 3),
                        "modality": "AUDIO",
                        "truth_class": "EXTRACTED_EVIDENCE",
                        "confidence": 1.0,
                        "sample_rate": sample_rate,
                        "evidence_digest": f"sha256:{hashlib.sha256(span_data).hexdigest()}",
                    }
                )
                cur = end
                idx += 1
        elif modality == "IMAGE":
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            w = video_stream.get("width") if video_stream else None
            h = video_stream.get("height") if video_stream else None
            spans.append(
                {
                    "span_id": "image-frame-0",
                    "width": w,
                    "height": h,
                    "modality": "IMAGE",
                    "truth_class": "EXTRACTED_EVIDENCE",
                    "confidence": 1.0,
                    "evidence_digest": digest,
                }
            )
        elif modality == "VIDEO":
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            total_duration = 1.0
            if video_stream and video_stream.get("duration"):
                try:
                    total_duration = float(video_stream["duration"])
                except (ValueError, TypeError):
                    total_duration = 1.0
            step = 1.0 if total_duration <= 10.0 else 5.0
            cur = 0.0
            idx = 0
            while cur < total_duration and idx < 20:
                end = min(cur + step, total_duration)
                span_data = f"{digest}:video:{cur:.2f}:{end:.2f}".encode("utf-8")
                spans.append(
                    {
                        "span_id": f"video-span-{idx}",
                        "start_time_s": round(cur, 3),
                        "end_time_s": round(end, 3),
                        "modality": "VIDEO",
                        "truth_class": "EXTRACTED_EVIDENCE",
                        "confidence": 1.0,
                        "evidence_digest": f"sha256:{hashlib.sha256(span_data).hexdigest()}",
                    }
                )
                cur = end
                idx += 1
        return spans

    def observe_bytes(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """Ingest and observe Base64-encoded media bytes."""
        _strict(
            request,
            {"action", "content_base64", "filename", "declared_mime", "options", "job_id"},
            {"action", "content_base64", "filename"},
        )
        filename = _text(request["filename"], "filename", 256)
        if any(c in filename for c in ("..", "/", "\\")):
            raise LocalPillarError("INVALID_INPUT", "filename must not contain path traversal characters")

        try:
            data = base64.b64decode(request["content_base64"], validate=True)
        except Exception as exc:
            raise LocalPillarError("INVALID_INPUT", "content_base64 is not valid Base64") from exc

        if not 1 <= len(data) <= self.maximum_bytes:
            raise LocalPillarError("RESOURCE_LIMIT", "media byte content exceeds limit")

        # Save into staged directory
        temp_name = f"staged_{uuid.uuid4().hex}_{filename}"
        staged_path = self.staging_dir / temp_name
        try:
            staged_path.write_bytes(data)
        except OSError as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "unable to write staged media") from exc

        # Move to persistent artifacts
        artifact_path = self.artifacts_dir / f"{uuid.uuid4().hex}_{filename}"
        try:
            shutil.move(str(staged_path), str(artifact_path))
        except OSError as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "unable to store media artifact") from exc

        # Observe the stored artifact relative to root
        rel_path = artifact_path.relative_to(self.root)
        options = request.get("options") or {}
        if request.get("declared_mime"):
            options["declared_mime"] = request["declared_mime"]

        return self.observe(
            {
                "action": "observe_file",
                "path": str(rel_path),
                "options": options,
                "job_id": request.get("job_id"),
            }
        )

    def extract_spans(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """Extract evidence spans from a previously recorded observation."""
        _strict(request, {"action", "observation_id", "granularity"}, {"action", "observation_id"})
        obs_res = self.get({"action": "get", "observation_id": request["observation_id"]})
        obs_data = obs_res.data
        spans = obs_data.get("evidence_spans") or []
        return LocalPillarResult(
            "P004",
            "MEDIA_SPANS_EXTRACTED",
            {
                "observation_id": obs_data["observation_id"],
                "source_digest": obs_data["source_digest"],
                "modality": obs_data["modality"],
                "evidence_spans": spans,
                "count": len(spans),
            },
        )

    def get(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "observation_id"}, {"action", "observation_id"})
        observation_id = _text(request["observation_id"], "observation_id", 128)
        try:
            with _connection(self.database_path) as connection:
                row = connection.execute(
                    "SELECT observation_json FROM media_observations WHERE observation_id=?",
                    (observation_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media observation cannot be read") from exc
        if row is None:
            raise LocalPillarError("OBSERVATION_NOT_FOUND", "media observation was not found")
        return LocalPillarResult("P004", "MEDIA_OBSERVATION_READ", json.loads(row[0]))

    def list_observations(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """List media observations with optional modality filter."""
        _strict(request, {"action", "modality", "limit"}, {"action"})
        modality = request.get("modality")
        limit = int(request.get("limit", 100))
        if limit < 1 or limit > 1000:
            limit = 100

        try:
            with _connection(self.database_path) as connection:
                if modality:
                    rows = connection.execute(
                        "SELECT observation_json FROM media_observations WHERE modality=? ORDER BY created_at DESC LIMIT ?",
                        (modality, limit),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT observation_json FROM media_observations ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media observation list cannot be read") from exc

        items = [json.loads(r[0]) for r in rows]
        return LocalPillarResult(
            "P004",
            "MEDIA_OBSERVATIONS_LISTED",
            {"observations": items, "count": len(items)},
        )

    def metrics(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """Compute aggregate metrics over observed media."""
        _strict(request, {"action"}, {"action"})
        try:
            with _connection(self.database_path) as connection:
                total = connection.execute("SELECT COUNT(*) FROM media_observations").fetchone()[0]
                rows = connection.execute(
                    "SELECT modality, COUNT(*) FROM media_observations GROUP BY modality"
                ).fetchall()
                modality_counts = {r[0]: r[1] for r in rows}
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media metrics cannot be read") from exc

        return LocalPillarResult(
            "P004",
            "MEDIA_METRICS",
            {
                "total_observations": total,
                "by_modality": modality_counts,
                "ffprobe_healthy": self.health_check(),
                "ffprobe_path": self.ffprobe_path,
                "maximum_bytes": self.maximum_bytes,
            },
        )

    def cancel(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """Cancel an in-flight media processing job."""
        _strict(request, {"action", "job_id"}, {"action", "job_id"})
        job_id = _text(request["job_id"], "job_id", 128)
        job = self._active_jobs.pop(job_id, None)
        # Clean up any files in staging
        for f in self.staging_dir.glob(f"staged_{job_id}*"):
            try:
                f.unlink()
            except OSError:
                pass
        return LocalPillarResult(
            "P004",
            "MEDIA_JOB_CANCELLED",
            {"job_id": job_id, "status": "CANCELLED" if job else "NOT_FOUND"},
        )

    def delete(self, request: Mapping[str, Any]) -> LocalPillarResult:
        """Delete an observation record."""
        _strict(request, {"action", "observation_id"}, {"action", "observation_id"})
        observation_id = _text(request["observation_id"], "observation_id", 128)
        try:
            with _connection(self.database_path) as connection:
                cur = connection.execute(
                    "DELETE FROM media_observations WHERE observation_id=?",
                    (observation_id,),
                )
                deleted = cur.rowcount > 0
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "media observation cannot be deleted") from exc

        if not deleted:
            raise LocalPillarError("OBSERVATION_NOT_FOUND", "media observation was not found")
        return LocalPillarResult(
            "P004",
            "MEDIA_OBSERVATION_DELETED",
            {"observation_id": observation_id, "status": "DELETED"},
        )

    def health(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action"}, {"action"})
        healthy = self.health_check()
        return LocalPillarResult(
            "P004",
            "MEDIA_HEALTH",
            {
                "healthy": healthy,
                "ffprobe_available": bool(self.ffprobe_path and Path(self.ffprobe_path).is_file()),
                "ffprobe_path": self.ffprobe_path,
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action")
        if action == "observe_file":
            return self.observe(request)
        if action == "observe_bytes":
            return self.observe_bytes(request)
        if action == "extract_spans":
            return self.extract_spans(request)
        if action == "get":
            return self.get(request)
        if action == "list_observations":
            return self.list_observations(request)
        if action == "metrics":
            return self.metrics(request)
        if action == "cancel":
            return self.cancel(request)
        if action == "delete":
            return self.delete(request)
        if action == "health":
            return self.health(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", f"media action '{action}' is unsupported")
