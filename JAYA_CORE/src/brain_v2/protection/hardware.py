"""Hardware identity helpers for Pillar 14 (Hardware Locked).

This module provides a pure-Python fallback path so runtime can work even
without compiled protection extensions.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple


_STRICT_ENV = "JAYA_STRICT_HARDWARE_LOCK"


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _strict_enabled() -> bool:
    return _is_truthy(os.getenv(_STRICT_ENV, "0"))


def _normalise_uuid(text: str) -> str:
    cleaned = re.sub(r"[^0-9a-fA-F]", "", text)
    return cleaned.lower()


def _run_command(args: list[str], timeout: float = 1.5) -> Optional[str]:
    try:
        out = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=timeout)
    except Exception:
        return None
    value = out.decode("utf-8", errors="ignore").strip()
    return value or None


def _windows_uuid() -> Optional[str]:
    # Prefer CIM on modern Windows, then fall back to wmic for old environments.
    output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID",
        ]
    )
    if not output:
        output = _run_command(["wmic", "csproduct", "get", "uuid"])
    if not output:
        return None

    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower() == "uuid":
            continue
        norm = _normalise_uuid(line)
        if len(norm) >= 16:
            return norm
    return None


def _linux_uuid() -> Optional[str]:
    candidates = [
        Path("/etc/machine-id"),
        Path("/var/lib/dbus/machine-id"),
        Path("/sys/class/dmi/id/product_uuid"),
    ]
    for path in candidates:
        try:
            if not path.exists():
                continue
            value = path.read_text(encoding="utf-8", errors="ignore").strip()
            norm = _normalise_uuid(value)
            if len(norm) >= 16:
                return norm
        except Exception:
            continue
    return None


def _darwin_uuid() -> Optional[str]:
    output = _run_command(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
    if not output:
        return None

    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', output)
    if not match:
        return None

    norm = _normalise_uuid(match.group(1))
    return norm if len(norm) >= 16 else None


def _probe_native_uuid() -> Tuple[Optional[str], Optional[str]]:
    system = platform.system().lower()
    if system == "windows":
        return _windows_uuid(), "windows"
    if system == "linux":
        return _linux_uuid(), "linux"
    if system == "darwin":
        return _darwin_uuid(), "darwin"
    return None, system


def _fallback_fingerprint() -> str:
    # Stable host fingerprint for environments where platform UUID is not accessible.
    parts = [
        platform.system(),
        platform.release(),
        platform.machine(),
        platform.node(),
        socket.gethostname(),
        f"{uuid.getnode():012x}",
    ]
    return "|".join(parts)


def get_system_uuid_with_source() -> Tuple[bytes, str]:
    """Return a 32-byte hardware-bound identity hash and source label.

    The returned bytes are always SHA3-256 digest output.
    """
    raw_uuid, source = _probe_native_uuid()

    if raw_uuid:
        material = raw_uuid.encode("utf-8")
        return hashlib.sha3_256(material).digest(), source or "native"

    if _strict_enabled():
        raise RuntimeError(
            "Hardware UUID unavailable and strict hardware lock is enabled "
            f"({_STRICT_ENV}=1)."
        )

    fallback = _fallback_fingerprint().encode("utf-8")
    return hashlib.sha3_256(fallback).digest(), "fallback"


def get_system_uuid() -> bytes:
    """Compatibility helper used by genesis/runtime code."""
    digest, _ = get_system_uuid_with_source()
    return digest


def get_system_uuid_hex() -> str:
    """Return system UUID digest in hex format."""
    return get_system_uuid().hex()
