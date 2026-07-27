"""Confined filesystem and atomic I/O primitives for evolution installs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .evolution_manifest_v1 import (
    ABSENT_RESTORE_DIGEST,
    digest_file,
    validate_relative_install_path,
)

REGISTRY_SCHEMA_VERSION = "jaya-evolution-install-registry-v1"
_COPY_CHUNK_BYTES = 1024 * 1024
_MAX_REGISTRY_BYTES = 16 * 1024 * 1024


class EvolutionInstallError(RuntimeError):
    """Typed, client-safe installer or rollback rejection."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_linklike(path: Path) -> bool:
    """Return whether a path is a symlink or Windows junction."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def is_relative_to(path: Path, root: Path) -> bool:
    """Compatibility helper for strict containment checks."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def hmac_compare(left: str, right: str) -> bool:
    """Compare public digests with constant-time semantics."""
    try:
        left_bytes = left.encode("ascii")
        right_bytes = right.encode("ascii")
    except (AttributeError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(left_bytes, right_bytes)


class ConfinedInstallStorage:
    """All filesystem access allowed to the mutating installer."""

    def __init__(
        self,
        *,
        registry_root: str | Path,
        data_root: str | Path,
    ) -> None:
        self.registry_root = self._canonical_existing_root(
            registry_root,
            field="registry_root",
        )
        self.data_root = self._canonical_existing_root(
            data_root,
            field="data_root",
        )
        if (
            self.registry_root == self.data_root
            or is_relative_to(self.registry_root, self.data_root)
            or is_relative_to(self.data_root, self.registry_root)
        ):
            raise EvolutionInstallError(
                "ROOT_CONFIGURATION_INVALID",
                "Registry and data roots must be separate directory trees",
            )
        self.registry_path = self.registry_root / "evolution-installs-v1.json"

    @staticmethod
    def _canonical_existing_root(path: str | Path, *, field: str) -> Path:
        raw = Path(path)
        if is_linklike(raw):
            raise EvolutionInstallError(
                "ROOT_LINK_REJECTED",
                f"{field} must not be a link or junction",
            )
        try:
            resolved = raw.resolve(strict=True)
        except OSError as exc:
            raise EvolutionInstallError(
                "ROOT_CONFIGURATION_INVALID",
                f"{field} must already exist",
            ) from exc
        if not resolved.is_dir() or is_linklike(resolved):
            raise EvolutionInstallError(
                "ROOT_CONFIGURATION_INVALID",
                f"{field} must be a regular directory",
            )
        return resolved

    def assert_root_integrity(self) -> None:
        """Fail when either injected boundary changes after initialization."""
        for root in (self.registry_root, self.data_root):
            if (
                not root.is_dir()
                or is_linklike(root)
                or root.resolve(strict=True) != root
            ):
                raise EvolutionInstallError(
                    "ROOT_CHANGED",
                    "An injected installer root changed after initialization",
                )

    @staticmethod
    def _reject_link_components(root: Path, relative_path: str) -> None:
        current = root
        for part in PurePosixPath(relative_path).parts:
            current = current / part
            if os.path.lexists(current) and is_linklike(current):
                raise EvolutionInstallError(
                    "SYMLINK_REJECTED",
                    "Installer paths must not contain links or junctions",
                )

    def data_path(self, relative_path: str) -> Path:
        """Resolve one validated path under the data boundary."""
        relative_path = validate_relative_install_path(relative_path)
        self._reject_link_components(self.data_root, relative_path)
        candidate = self.data_root.joinpath(*PurePosixPath(relative_path).parts)
        resolved = candidate.resolve(strict=False)
        if not is_relative_to(resolved, self.data_root):
            raise EvolutionInstallError(
                "PATH_ESCAPE",
                "Installer target escapes the injected data root",
            )
        return resolved

    def ensure_data_parent(self, relative_path: str) -> Path:
        """Create only regular parent directories below the data root."""
        relative_path = validate_relative_install_path(relative_path)
        parts = PurePosixPath(relative_path).parts[:-1]
        current = self.data_root
        for part in parts:
            current = current / part
            if os.path.lexists(current):
                if is_linklike(current) or not current.is_dir():
                    raise EvolutionInstallError(
                        "SYMLINK_REJECTED",
                        "Installer parent is not a regular directory",
                    )
            else:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                if is_linklike(current) or not current.is_dir():
                    raise EvolutionInstallError(
                        "SYMLINK_REJECTED",
                        "Installer parent changed during creation",
                    )
        resolved = current.resolve(strict=True)
        if not is_relative_to(resolved, self.data_root):
            raise EvolutionInstallError(
                "PATH_ESCAPE",
                "Installer parent escapes the injected data root",
            )
        return resolved

    @staticmethod
    def source_file(path: str | Path) -> Path:
        """Open source eligibility without allowing traversal or links."""
        raw = Path(path)
        if ".." in raw.parts or is_linklike(raw):
            raise EvolutionInstallError(
                "SOURCE_PATH_REJECTED",
                "Artifact source must be a direct regular-file path",
            )
        try:
            absolute = raw.absolute()
            resolved = raw.resolve(strict=True)
        except OSError as exc:
            raise EvolutionInstallError(
                "SOURCE_NOT_FOUND",
                "Artifact source does not exist",
            ) from exc
        if absolute != resolved or is_linklike(resolved) or not resolved.is_file():
            raise EvolutionInstallError(
                "SOURCE_PATH_REJECTED",
                "Artifact source must not traverse a link or junction",
            )
        return resolved

    @staticmethod
    def empty_registry() -> dict[str, Any]:
        """Return a new registry document."""
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "consumed_manifests": {},
            "installations": {},
        }

    def load_registry(self) -> dict[str, Any]:
        """Read and minimally validate the confined install registry."""
        path = self.registry_path
        if is_linklike(path):
            raise EvolutionInstallError(
                "REGISTRY_LINK_REJECTED",
                "Install registry must not be a link or junction",
            )
        if not path.exists():
            return self.empty_registry()
        if not path.is_file() or path.stat().st_size > _MAX_REGISTRY_BYTES:
            raise EvolutionInstallError(
                "REGISTRY_INVALID",
                "Install registry is not a bounded regular file",
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvolutionInstallError(
                "REGISTRY_INVALID",
                "Install registry cannot be decoded",
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != REGISTRY_SCHEMA_VERSION
            or not isinstance(payload.get("consumed_manifests"), dict)
            or not isinstance(payload.get("installations"), dict)
        ):
            raise EvolutionInstallError(
                "REGISTRY_INVALID",
                "Install registry schema is invalid",
            )
        return payload

    @staticmethod
    def fsync_directory(path: Path) -> None:
        """Persist directory metadata where the platform supports it."""
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def atomic_json_write(self, path: Path, payload: Mapping[str, Any]) -> None:
        """Publish JSON atomically below either injected root."""
        resolved_parent = path.parent.resolve(strict=True)
        if not is_relative_to(
            resolved_parent,
            self.registry_root,
        ) and not is_relative_to(resolved_parent, self.data_root):
            raise EvolutionInstallError(
                "PATH_ESCAPE",
                "JSON destination escapes injected installer roots",
            )
        if is_linklike(path):
            raise EvolutionInstallError(
                "SYMLINK_REJECTED",
                "JSON destination must not be a link or junction",
            )
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=resolved_parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if is_linklike(path):
                raise EvolutionInstallError(
                    "SYMLINK_REJECTED",
                    "JSON destination changed during publication",
                )
            os.replace(temporary_path, path)
            self.fsync_directory(resolved_parent)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def atomic_publish_copy(
        self,
        source: Path,
        target: Path,
        *,
        expected_digest: str,
        expected_size: int | None = None,
    ) -> None:
        """Copy, verify, fsync, and atomically replace a data-root file."""
        parent = target.parent.resolve(strict=True)
        if not is_relative_to(parent, self.data_root):
            raise EvolutionInstallError(
                "PATH_ESCAPE",
                "Artifact publication escapes the injected data root",
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".installing",
            dir=parent,
        )
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        total_bytes = 0
        try:
            with (
                source.open("rb") as source_handle,
                os.fdopen(
                    descriptor,
                    "wb",
                ) as target_handle,
            ):
                while chunk := source_handle.read(_COPY_CHUNK_BYTES):
                    total_bytes += len(chunk)
                    digest.update(chunk)
                    target_handle.write(chunk)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            copied_digest = f"sha256:{digest.hexdigest()}"
            if not hmac_compare(copied_digest, expected_digest) or (
                expected_size is not None and total_bytes != expected_size
            ):
                raise EvolutionInstallError(
                    "ARTIFACT_DIGEST_MISMATCH",
                    "Copied artifact does not match the signed manifest",
                )
            if is_linklike(target) or not is_relative_to(
                target.parent.resolve(strict=True),
                self.data_root,
            ):
                raise EvolutionInstallError(
                    "SYMLINK_REJECTED",
                    "Artifact target changed during publication",
                )
            os.replace(temporary_path, target)
            self.fsync_directory(parent)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def validate_existing_regular(path: Path, *, code: str) -> None:
        """Reject links, directories, devices, and absent state."""
        if is_linklike(path) or not path.is_file():
            raise EvolutionInstallError(
                code,
                "Installer state is not a regular file",
            )

    def check_preinstall_state(
        self,
        target: Path,
        expected_restore_digest: str,
    ) -> tuple[bool, str]:
        """Bind installation to the signed pre-install restore state."""
        exists = os.path.lexists(target)
        if expected_restore_digest == ABSENT_RESTORE_DIGEST:
            if exists:
                raise EvolutionInstallError(
                    "RESTORE_STATE_MISMATCH",
                    "Install target exists but rollback expects an absent target",
                )
            return False, ABSENT_RESTORE_DIGEST
        if not exists:
            raise EvolutionInstallError(
                "RESTORE_STATE_MISMATCH",
                "Install target is missing but rollback expects prior content",
            )
        self.validate_existing_regular(target, code="RESTORE_STATE_MISMATCH")
        current_digest = digest_file(target)
        if not hmac_compare(current_digest, expected_restore_digest):
            raise EvolutionInstallError(
                "RESTORE_STATE_MISMATCH",
                "Existing target does not match the signed rollback digest",
            )
        return True, current_digest
