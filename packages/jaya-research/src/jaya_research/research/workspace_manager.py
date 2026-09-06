"""Secure lifecycle management for isolated research workspaces."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote

if __package__ and __package__.startswith("src."):
    from ..config import config
else:
    from jaya_research.config import config


logger = logging.getLogger(__name__)

_WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_WINDOWS_RESERVED_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


class WorkspaceSecurityError(ValueError):
    """Raised when a workspace path cannot be proven safe."""


class WorkspaceManager:
    """Manage workspace directories without allowing filesystem escape."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        requested_base = Path(base_dir or config.WORKSPACES_DIR).expanduser()
        requested_base.mkdir(parents=True, exist_ok=True)

        self.base_dir = requested_base.resolve(strict=True)
        if not self.base_dir.is_dir():
            raise WorkspaceSecurityError(
                f"Workspace base is not a directory: {self.base_dir}"
            )

        self.current_workspace = "default"
        self._ensure_workspace(self.current_workspace)

    @staticmethod
    def _decode_path_syntax(value: str) -> str:
        """Decode nested URL encoding so encoded separators cannot bypass checks."""
        decoded = value
        for _ in range(4):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        return decoded

    @classmethod
    def _reject_path_syntax(cls, value: str, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise WorkspaceSecurityError(f"{field_name} must be a string")
        if not value or value != value.strip():
            raise WorkspaceSecurityError(
                f"{field_name} must not be empty or contain surrounding whitespace"
            )
        if "\x00" in value or any(ord(character) < 32 for character in value):
            raise WorkspaceSecurityError(
                f"{field_name} contains forbidden control characters"
            )

        decoded = cls._decode_path_syntax(value)
        windows_path = PureWindowsPath(decoded)
        posix_path = PurePosixPath(decoded)

        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or posix_path.is_absolute()
        ):
            raise WorkspaceSecurityError(f"{field_name} must be a relative identifier")
        if "/" in decoded or "\\" in decoded:
            raise WorkspaceSecurityError(
                f"{field_name} must not contain path separators"
            )
        if ".." in decoded:
            raise WorkspaceSecurityError(
                f"{field_name} must not contain traversal syntax"
            )

        return decoded

    @classmethod
    def _validate_workspace_id(cls, workspace_id: str) -> str:
        decoded = cls._reject_path_syntax(
            workspace_id,
            field_name="workspace_id",
        )
        if not _WORKSPACE_ID_PATTERN.fullmatch(decoded):
            raise WorkspaceSecurityError(
                "workspace_id must contain only ASCII letters, digits, '_' or '-', "
                "start with a letter or digit, and be at most 64 characters"
            )

        normalized = decoded.lower()
        if normalized in _WINDOWS_RESERVED_NAMES:
            raise WorkspaceSecurityError(
                f"workspace_id '{workspace_id}' is reserved by the operating system"
            )
        return normalized

    @classmethod
    def _workspace_id_from_name(cls, name: str) -> str:
        safe_name = cls._reject_path_syntax(name, field_name="workspace name")
        workspace_id = re.sub(r"[^A-Za-z0-9_-]+", "_", safe_name)
        workspace_id = workspace_id.strip("_-").lower()
        if not workspace_id:
            raise WorkspaceSecurityError(
                "workspace name must contain at least one ASCII letter or digit"
            )
        return cls._validate_workspace_id(workspace_id)

    @staticmethod
    def _require_contained(path: Path, container: Path, *, label: str) -> Path:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(container)
        except ValueError as exc:
            raise WorkspaceSecurityError(
                f"{label} resolves outside the allowed workspace root"
            ) from exc
        return resolved

    @staticmethod
    def _is_linklike(path: Path) -> bool:
        """Treat symbolic links and Windows junctions as link-like entries."""
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or bool(is_junction and is_junction()):
            return True
        try:
            file_attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except OSError:
            return False
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(file_attributes & reparse_flag)

    def _reject_escaping_links(self, workspace_path: Path) -> None:
        """Reject any link inside a workspace that resolves outside its root."""
        for directory, directory_names, file_names in os.walk(
            workspace_path,
            topdown=True,
            followlinks=False,
        ):
            directory_path = Path(directory)
            for entry_name in [*directory_names, *file_names]:
                entry_path = directory_path / entry_name
                if not self._is_linklike(entry_path):
                    continue
                self._require_contained(
                    entry_path,
                    workspace_path,
                    label=f"Workspace link '{entry_path.name}'",
                )

            # Be explicit that no link-like directory is traversed.
            directory_names[:] = [
                name
                for name in directory_names
                if not self._is_linklike(directory_path / name)
            ]

    def _workspace_path(
        self,
        workspace_id: str,
        *,
        require_exists: bool = False,
    ) -> Path:
        safe_id = self._validate_workspace_id(workspace_id)
        lexical_path = self.base_dir / safe_id

        if self._is_linklike(lexical_path):
            raise WorkspaceSecurityError(
                f"Workspace root '{safe_id}' must not be a symbolic link"
            )

        workspace_path = self._require_contained(
            lexical_path,
            self.base_dir,
            label=f"Workspace '{safe_id}'",
        )
        if require_exists:
            if not workspace_path.exists():
                raise ValueError(f"Workspace '{safe_id}' not found")
            if not workspace_path.is_dir():
                raise WorkspaceSecurityError(
                    f"Workspace '{safe_id}' is not a directory"
                )
        return workspace_path

    def _child_path(
        self,
        workspace_path: Path,
        child_name: str,
        *,
        require_exists: bool = False,
    ) -> Path:
        child_path = self._require_contained(
            workspace_path / child_name,
            workspace_path,
            label=f"Workspace child '{child_name}'",
        )
        if require_exists and not child_path.exists():
            raise WorkspaceSecurityError(
                f"Required workspace child does not exist: {child_name}"
            )
        return child_path

    def _workspace_paths(self, workspace_path: Path) -> dict[str, str]:
        vector_store = self._child_path(
            workspace_path,
            "vector_store",
            require_exists=True,
        )
        knowledge_graph = self._child_path(workspace_path, "knowledge_graph.json")
        return {
            "root": str(workspace_path),
            "vector_store": str(vector_store),
            "knowledge_graph": str(knowledge_graph),
        }

    def _ensure_workspace(self, workspace_id: str) -> Path:
        """Create one validated workspace and its required storage children."""
        safe_id = self._validate_workspace_id(workspace_id)
        workspace_path = self._workspace_path(safe_id)
        workspace_path.mkdir(parents=False, exist_ok=True)

        # Resolve again after mkdir to detect a path swapped to a symlink.
        workspace_path = self._workspace_path(safe_id, require_exists=True)
        vector_store = self._child_path(workspace_path, "vector_store")
        vector_store.mkdir(parents=False, exist_ok=True)
        self._child_path(
            workspace_path,
            "vector_store",
            require_exists=True,
        )

        metadata_path = self._child_path(workspace_path, "metadata.json")
        if not metadata_path.exists():
            metadata_path.write_text(
                json.dumps(
                    {
                        "id": safe_id,
                        "name": safe_id,
                        "created_at": time.time(),
                        "description": f"Workspace for {safe_id}",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return workspace_path

    def create_workspace(self, name: str, description: str = "") -> dict[str, str]:
        """Create a workspace from a display name after rejecting path syntax."""
        workspace_id = self._workspace_id_from_name(name)
        workspace_path = self._workspace_path(workspace_id)

        if workspace_path.exists():
            return {"status": "error", "message": "Workspace already exists"}

        workspace_path = self._ensure_workspace(workspace_id)
        metadata_path = self._child_path(workspace_path, "metadata.json")
        metadata_path.write_text(
            json.dumps(
                {
                    "id": workspace_id,
                    "name": name,
                    "created_at": time.time(),
                    "description": description,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "status": "success",
            "id": workspace_id,
            "path": str(workspace_path),
        }

    def list_workspaces(self) -> list[dict[str, object]]:
        """List contained workspaces while ignoring unsafe filesystem entries."""
        workspaces: list[dict[str, object]] = []
        for item in self.base_dir.iterdir():
            try:
                workspace_path = self._workspace_path(
                    item.name,
                    require_exists=True,
                )
                metadata_path = self._child_path(
                    workspace_path,
                    "metadata.json",
                    require_exists=True,
                )
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(metadata, dict):
                    workspaces.append(metadata)
            except (
                json.JSONDecodeError,
                OSError,
                WorkspaceSecurityError,
                ValueError,
            ) as exc:
                logger.warning(
                    "Ignoring invalid workspace entry %s: %s",
                    item.name,
                    exc,
                )
        return workspaces

    def get_paths(self, workspace_id: str) -> dict[str, str]:
        """Return canonical paths for an existing, contained workspace."""
        workspace_path = self._workspace_path(
            workspace_id,
            require_exists=True,
        )
        return self._workspace_paths(workspace_path)

    def get_or_create_paths(self, workspace_id: str) -> dict[str, str]:
        """Return canonical workspace paths, creating a validated ID if needed."""
        safe_id = self._validate_workspace_id(workspace_id)
        workspace_path = self._workspace_path(safe_id)
        if not workspace_path.exists():
            logger.info("Creating workspace '%s'", safe_id)
            workspace_path = self._ensure_workspace(safe_id)
        else:
            workspace_path = self._workspace_path(
                safe_id,
                require_exists=True,
            )
        return self._workspace_paths(workspace_path)

    def delete_workspace(self, workspace_id: str) -> dict[str, str]:
        """Delete only a canonical, contained, non-symlink workspace directory."""
        safe_id = self._validate_workspace_id(workspace_id)
        workspace_path = self._workspace_path(safe_id)
        if not workspace_path.exists():
            return {
                "status": "error",
                "message": f"Workspace '{safe_id}' not found",
            }

        workspace_path = self._workspace_path(
            safe_id,
            require_exists=True,
        )
        self._reject_escaping_links(workspace_path)

        # Revalidate immediately before the destructive operation.
        if workspace_path != self._workspace_path(
            safe_id,
            require_exists=True,
        ):
            raise WorkspaceSecurityError(
                f"Workspace '{safe_id}' changed during delete validation"
            )

        shutil.rmtree(workspace_path)
        return {
            "status": "success",
            "message": f"Workspace '{safe_id}' deleted",
        }
