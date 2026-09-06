"""Quarantined, bounded upload storage for JAYA_RESEARCH."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_CHUNK_BYTES = 1024 * 1024
_INDEX_NAME = ".upload-index.json"
_INDEX_LOCK = threading.RLock()
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf", "application/octet-stream"}),
    ".docx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            "application/octet-stream",
        }
    ),
    ".txt": frozenset({"text/plain", "application/octet-stream"}),
    ".md": frozenset({"text/markdown", "text/plain", "application/octet-stream"}),
    ".csv": frozenset({"text/csv", "text/plain", "application/octet-stream"}),
    ".json": frozenset({"application/json", "text/json", "text/plain"}),
}


class UploadSecurityError(ValueError):
    """A typed, client-actionable upload rejection."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class UploadPolicy:
    """Validated limits and file types for one upload endpoint."""

    allowed_extensions: frozenset[str]
    max_file_bytes: int
    max_directory_bytes: int
    stream_timeout_seconds: float

    def __post_init__(self) -> None:
        if not self.allowed_extensions:
            raise ValueError("allowed_extensions must not be empty")
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        if self.max_directory_bytes < self.max_file_bytes:
            raise ValueError("max_directory_bytes must be >= max_file_bytes")
        if not math.isfinite(self.stream_timeout_seconds):
            raise ValueError("stream_timeout_seconds must be finite")
        if self.stream_timeout_seconds <= 0:
            raise ValueError("stream_timeout_seconds must be positive")


@dataclass(frozen=True)
class UploadReceipt:
    """Receipt for a validated file stored inside the destination boundary."""

    path: Path
    filename: str
    sha256: str
    size_bytes: int
    media_type: str
    duplicate: bool


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be positive")
    return value


def upload_policy(kind: str) -> UploadPolicy:
    """Build a policy from validated environment configuration."""
    normalized_kind = kind.casefold()
    if normalized_kind == "pdf":
        extensions = frozenset({".pdf"})
    elif normalized_kind == "document":
        extensions = frozenset(_MEDIA_TYPES)
    else:
        raise ValueError(f"Unsupported upload policy kind: {kind}")

    max_file_bytes = _positive_int_env(
        "JAYA_UPLOAD_MAX_FILE_BYTES",
        25 * 1024 * 1024,
    )
    max_directory_bytes = _positive_int_env(
        "JAYA_UPLOAD_MAX_WORKSPACE_BYTES",
        1024 * 1024 * 1024,
    )
    timeout_seconds = _positive_int_env("JAYA_UPLOAD_TIMEOUT_SECONDS", 30)
    return UploadPolicy(
        allowed_extensions=extensions,
        max_file_bytes=max_file_bytes,
        max_directory_bytes=max_directory_bytes,
        stream_timeout_seconds=float(timeout_seconds),
    )


def _safe_filename(original_filename: str, policy: UploadPolicy) -> str:
    normalized = unicodedata.normalize("NFKC", str(original_filename or "")).strip()
    if not normalized or len(normalized) > 180:
        raise UploadSecurityError(
            "INVALID_FILENAME",
            "Filename must contain between 1 and 180 characters",
        )
    if (
        Path(normalized).name != normalized
        or "/" in normalized
        or "\\" in normalized
        or any(ord(character) < 32 for character in normalized)
    ):
        raise UploadSecurityError(
            "INVALID_FILENAME",
            "Filename must not contain a path or control characters",
        )
    if normalized.endswith((" ", ".")):
        raise UploadSecurityError(
            "INVALID_FILENAME",
            "Filename must not end with a space or period",
        )
    stem_name = Path(normalized).stem.split(".", maxsplit=1)[0].upper()
    if stem_name in _WINDOWS_RESERVED:
        raise UploadSecurityError(
            "INVALID_FILENAME", "Reserved filename is not allowed"
        )

    extension = Path(normalized).suffix.casefold()
    if extension not in policy.allowed_extensions:
        allowed = ", ".join(sorted(policy.allowed_extensions))
        raise UploadSecurityError(
            "UNSUPPORTED_EXTENSION",
            f"Unsupported extension {extension or '(none)'}; allowed: {allowed}",
            status_code=415,
        )
    return normalized


def _validate_declared_media_type(filename: str, media_type: str) -> str:
    extension = Path(filename).suffix.casefold()
    normalized_media_type = (
        (media_type or "application/octet-stream")
        .split(";", maxsplit=1)[0]
        .strip()
        .casefold()
    )
    if normalized_media_type not in _MEDIA_TYPES[extension]:
        raise UploadSecurityError(
            "MIME_MISMATCH",
            f"Media type {normalized_media_type!r} does not match {extension}",
            status_code=415,
        )
    return normalized_media_type


def _validate_magic(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        header = handle.read(8192)
    if extension == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise UploadSecurityError(
                "MAGIC_MISMATCH",
                "File extension is PDF but the PDF signature is missing",
                status_code=415,
            )
        return
    if extension == ".docx":
        if not header.startswith(b"PK"):
            raise UploadSecurityError(
                "MAGIC_MISMATCH",
                "DOCX ZIP signature is missing",
                status_code=415,
            )
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            raise UploadSecurityError(
                "INVALID_DOCX",
                "DOCX archive is invalid",
                status_code=415,
            ) from exc
        if "[Content_Types].xml" not in names or not any(
            name.startswith("word/") for name in names
        ):
            raise UploadSecurityError(
                "INVALID_DOCX",
                "ZIP file does not contain a Word document",
                status_code=415,
            )
        return

    if b"\x00" in header:
        raise UploadSecurityError(
            "BINARY_TEXT_FILE",
            "Text document contains binary null bytes",
            status_code=415,
        )
    try:
        header.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadSecurityError(
            "INVALID_TEXT_ENCODING",
            "Text document must be UTF-8 encoded",
            status_code=415,
        ) from exc


def _contained(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UploadSecurityError(
            "PATH_ESCAPE",
            "Upload target escapes the configured destination",
        ) from exc
    return resolved


def _directory_usage(root: Path, quarantine: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            path.resolve(strict=False).relative_to(quarantine)
        except ValueError:
            total += path.stat().st_size
    return total


def _load_index(index_path: Path, root: Path) -> dict[str, str]:
    if not index_path.is_file():
        return {}
    try:
        value = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(value, dict):
        return {}

    cleaned: dict[str, str] = {}
    for digest, filename in value.items():
        if isinstance(digest, str) and len(digest) == 64 and isinstance(filename, str):
            try:
                candidate = _contained(root / filename, root)
            except UploadSecurityError:
                continue
            if candidate.is_file():
                cleaned[digest] = filename
    return cleaned


def _write_index(index_path: Path, index: dict[str, str]) -> None:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{index_path.name}.",
        suffix=".tmp",
        dir=index_path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, index_path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def store_upload(
    stream: BinaryIO,
    *,
    original_filename: str,
    media_type: str,
    destination_dir: Path,
    policy: UploadPolicy,
) -> UploadReceipt:
    """Stream into quarantine, validate, deduplicate, and atomically publish."""
    filename = _safe_filename(original_filename, policy)
    normalized_media_type = _validate_declared_media_type(filename, media_type)
    destination = Path(destination_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    quarantine = _contained(destination / ".quarantine", destination)
    quarantine.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".upload.",
        suffix=".part",
        dir=quarantine,
    )
    temporary_path = Path(temporary_name)
    digest = hashlib.sha256()
    total_bytes = 0
    started_at = time.monotonic()
    try:
        with os.fdopen(descriptor, "wb") as handle:
            while True:
                if time.monotonic() - started_at > policy.stream_timeout_seconds:
                    raise UploadSecurityError(
                        "UPLOAD_TIMEOUT",
                        "Upload exceeded the configured streaming timeout",
                        status_code=408,
                    )
                chunk = stream.read(_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise UploadSecurityError(
                        "INVALID_STREAM",
                        "Upload stream must return bytes",
                    )
                total_bytes += len(chunk)
                if total_bytes > policy.max_file_bytes:
                    raise UploadSecurityError(
                        "FILE_TOO_LARGE",
                        "Upload exceeds the configured per-file size limit",
                        status_code=413,
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())

        if total_bytes == 0:
            raise UploadSecurityError("EMPTY_FILE", "Empty uploads are not accepted")
        _validate_magic(temporary_path, Path(filename).suffix.casefold())
        sha256 = digest.hexdigest()

        with _INDEX_LOCK:
            index_path = destination / _INDEX_NAME
            index = _load_index(index_path, destination)
            duplicate_name = index.get(sha256)
            if duplicate_name:
                existing = _contained(destination / duplicate_name, destination)
                if existing.is_file():
                    temporary_path.unlink(missing_ok=True)
                    return UploadReceipt(
                        path=existing,
                        filename=existing.name,
                        sha256=sha256,
                        size_bytes=total_bytes,
                        media_type=normalized_media_type,
                        duplicate=True,
                    )

            if (
                _directory_usage(destination, quarantine) + total_bytes
                > policy.max_directory_bytes
            ):
                raise UploadSecurityError(
                    "WORKSPACE_QUOTA_EXCEEDED",
                    "Upload would exceed the configured workspace quota",
                    status_code=413,
                )

            target = _contained(destination / filename, destination)
            if target.exists():
                target = _contained(
                    destination
                    / f"{target.stem}-{sha256[:12]}{target.suffix.casefold()}",
                    destination,
                )
            os.replace(temporary_path, target)
            index[sha256] = target.name
            _write_index(index_path, index)

        return UploadReceipt(
            path=target,
            filename=target.name,
            sha256=sha256,
            size_bytes=total_bytes,
            media_type=normalized_media_type,
            duplicate=False,
        )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
