"""Capability-contained file operations for JAYA_AGENT."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from jaya_agent.security.capability_sandbox import require_active_capability
from jaya_agent.skills.base_skill import Skill, skill_action

_MAX_READ_BYTES = 1024 * 1024
_MAX_RETURN_CHARACTERS = 5_000
_MAX_WRITE_BYTES = 1024 * 1024
_MAX_LIST_ITEMS = 20


def _ticket_resource(path: Path) -> str:
    return f"path:{os.path.normcase(str(path.resolve(strict=False)))}"


class FileOperationsSkill(Skill):
    """Read, list, and atomically write only explicitly granted paths."""

    name = "file_skill"
    description = "Capability-contained file operations"

    @skill_action(
        "read_file",
        "Reads bounded UTF-8 text from an explicitly granted file",
        params={"filepath": "str"},
        capability="fs.read",
        resource_param="filepath",
        timeout_seconds=5.0,
    )
    def read_file(self, filepath: str) -> str:
        path = Path(filepath)
        resolved = path.resolve(strict=True)
        require_active_capability("fs.read", (_ticket_resource(resolved),))
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError("Granted resource must be a regular non-symlink file")
        if resolved.stat().st_size > _MAX_READ_BYTES:
            raise ValueError("Granted file exceeds the read size limit")
        with resolved.open("r", encoding="utf-8", errors="strict") as stream:
            return stream.read(_MAX_RETURN_CHARACTERS)

    @skill_action(
        "write_file",
        "Atomically writes bounded UTF-8 text to an explicitly granted file",
        params={"filepath": "str", "content": "str"},
        capability="fs.write",
        resource_param="filepath",
        timeout_seconds=5.0,
    )
    def write_file(self, filepath: str, content: str) -> str:
        path = Path(filepath)
        resolved = path.resolve(strict=False)
        require_active_capability("fs.write", (_ticket_resource(resolved),))
        payload = content.encode("utf-8")
        if len(payload) > _MAX_WRITE_BYTES:
            raise ValueError("Write payload exceeds the configured size limit")
        if resolved.exists() and resolved.is_symlink():
            raise ValueError("Writing through a symlink is not allowed")

        if not resolved.parent.exists() or not resolved.parent.is_dir():
            raise ValueError(
                "Parent directory must already exist and be explicitly managed"
            )
        if path.parent.is_symlink():
            raise ValueError("Writing through a symlink directory is not allowed")
        resolved = resolved.resolve(strict=False)
        require_active_capability("fs.write", (_ticket_resource(resolved),))
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=resolved.parent,
                prefix=f".{resolved.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, resolved)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return f"Wrote {len(payload)} UTF-8 bytes"

    @skill_action(
        "list_directory",
        "Lists a bounded number of entries in an explicitly granted directory",
        params={"dirpath": "str"},
        capability="fs.list",
        resource_param="dirpath",
        timeout_seconds=5.0,
    )
    def list_directory(self, dirpath: str) -> str:
        path = Path(dirpath).resolve(strict=True)
        require_active_capability("fs.list", (_ticket_resource(path),))
        if not path.is_dir() or path.is_symlink():
            raise ValueError("Granted resource must be a non-symlink directory")
        items = sorted(item.name for item in path.iterdir())[:_MAX_LIST_ITEMS]
        return ", ".join(items)
