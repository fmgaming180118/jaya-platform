"""Lifecycle orchestration for confined evolution artifact installation."""

from __future__ import annotations

import copy
import math
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._evolution_install_storage import (
    ConfinedInstallStorage,
    EvolutionInstallError,
    hmac_compare,
    is_linklike,
)
from .evolution_manifest_v1 import (
    ABSENT_RESTORE_DIGEST,
    EvolutionContractError,
    EvolutionManifestVerifier,
    VerifiedEvolutionManifest,
    canonical_json,
    digest_bytes,
    digest_file,
)

CANARY_SCHEMA_VERSION = "jaya-evolution-canary-receipt-v1"

CanaryRunner = Callable[
    [Path, VerifiedEvolutionManifest],
    Mapping[str, Any],
]

__all__ = [
    "EvolutionInstallError",
    "EvolutionInstaller",
    "InstallResult",
    "RollbackResult",
]


@dataclass(frozen=True)
class InstallResult:
    """Outcome of a dry-run or committed install."""

    status: str
    dry_run: bool
    manifest_digest: str
    registry_key: str
    target_path: str
    canary_receipt_path: str | None = None
    canary_receipt_digest: str | None = None


@dataclass(frozen=True)
class RollbackResult:
    """Outcome of a rollback request."""

    status: str
    registry_key: str
    target_path: str
    restored_digest: str
    idempotent: bool


class EvolutionInstaller:
    """Verify, install, canary, register, and restore evolution artifacts."""

    def __init__(
        self,
        *,
        verifier: EvolutionManifestVerifier,
        registry_root: str | Path,
        data_root: str | Path,
        canary_runner: CanaryRunner,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.verifier = verifier
        self._storage = ConfinedInstallStorage(
            registry_root=registry_root,
            data_root=data_root,
        )
        self.registry_root = self._storage.registry_root
        self.data_root = self._storage.data_root
        if not callable(canary_runner):
            raise EvolutionInstallError(
                "CANARY_CONFIGURATION_INVALID",
                "A callable canary runner is required",
            )
        self.canary_runner = canary_runner
        self._clock = clock
        self._lock = threading.RLock()

    def install(
        self,
        manifest: Mapping[str, Any],
        *,
        artifact_source: str | Path,
        verified_receipt_digests: Iterable[str],
        dry_run: bool = False,
        now: float | None = None,
    ) -> InstallResult:
        """Verify, plan, atomically publish, canary, and register one artifact."""
        verified = self.verifier.verify(
            manifest,
            verified_receipt_digests=verified_receipt_digests,
            now=now,
        )
        source = self._storage.source_file(artifact_source)
        if source.stat().st_size != verified.artifact_size_bytes or not hmac_compare(
            digest_file(source), verified.artifact_digest
        ):
            raise EvolutionInstallError(
                "ARTIFACT_DIGEST_MISMATCH",
                "Artifact source does not match the signed manifest",
            )

        with self._lock:
            self._storage.assert_root_integrity()
            target = self._storage.data_path(verified.target_path)
            if target == source:
                raise EvolutionInstallError(
                    "SOURCE_OVERWRITE_REJECTED",
                    "Install target must not overwrite its artifact source",
                )
            registry = self._storage.load_registry()
            if verified.manifest_digest in registry["consumed_manifests"]:
                raise EvolutionInstallError(
                    "MANIFEST_REPLAY",
                    "This signed manifest has already been consumed",
                )
            previous_exists, restore_digest = self._storage.check_preinstall_state(
                target,
                verified.expected_restore_digest,
            )
            if dry_run:
                return InstallResult(
                    status="planned",
                    dry_run=True,
                    manifest_digest=verified.manifest_digest,
                    registry_key=verified.registry_key,
                    target_path=verified.target_path,
                )

            transaction = self._prepare_transaction_paths(verified)
            backup_path = transaction["backup_path"]
            receipt_path = transaction["receipt_path"]
            published = False
            receipt_written = False
            try:
                if previous_exists:
                    self._storage.atomic_publish_copy(
                        target,
                        backup_path,
                        expected_digest=restore_digest,
                    )
                self._storage.atomic_publish_copy(
                    source,
                    target,
                    expected_digest=verified.artifact_digest,
                    expected_size=verified.artifact_size_bytes,
                )
                published = True
                canary_payload = self._run_canary(target, verified)
                observed_digest = digest_file(target)
                if not hmac_compare(observed_digest, verified.artifact_digest):
                    raise EvolutionInstallError(
                        "CANARY_MUTATED_ARTIFACT",
                        "Canary execution changed the installed artifact",
                    )
                receipt = self._canary_receipt(
                    verified,
                    canary_payload=canary_payload,
                    observed_digest=observed_digest,
                    now=now,
                )
                self._storage.atomic_json_write(receipt_path, receipt)
                receipt_written = True
                registry["installations"][verified.registry_key] = self._registry_entry(
                    verified,
                    previous_exists=previous_exists,
                    restore_digest=restore_digest,
                    backup_relative=transaction["backup_relative"],
                    receipt_relative=transaction["receipt_relative"],
                    receipt_digest=receipt["receipt_digest"],
                    now=now,
                )
                registry["consumed_manifests"][verified.manifest_digest] = (
                    verified.registry_key
                )
                self._storage.atomic_json_write(
                    self._storage.registry_path,
                    registry,
                )
            except Exception as exc:
                if published:
                    self._restore_after_failed_install(
                        target=target,
                        previous_exists=previous_exists,
                        restore_digest=restore_digest,
                        backup_path=backup_path,
                    )
                if receipt_written:
                    receipt_path.unlink(missing_ok=True)
                backup_path.unlink(missing_ok=True)
                if isinstance(exc, (EvolutionInstallError, EvolutionContractError)):
                    raise
                raise EvolutionInstallError(
                    "INSTALL_FAILED",
                    "Evolution artifact installation failed",
                ) from exc

            return InstallResult(
                status="installed",
                dry_run=False,
                manifest_digest=verified.manifest_digest,
                registry_key=verified.registry_key,
                target_path=verified.target_path,
                canary_receipt_path=transaction["receipt_relative"],
                canary_receipt_digest=receipt["receipt_digest"],
            )

    def _prepare_transaction_paths(
        self,
        verified: VerifiedEvolutionManifest,
    ) -> dict[str, Any]:
        self._storage.ensure_data_parent(verified.target_path)
        manifest_hex = verified.manifest_digest.removeprefix("sha256:")
        backup_relative = (
            f".evolution-rollback/{manifest_hex}/{verified.artifact_name}.previous"
        )
        receipt_relative = f".evolution-receipts/{manifest_hex}.json"
        self._storage.ensure_data_parent(backup_relative)
        self._storage.ensure_data_parent(receipt_relative)
        backup_path = self._storage.data_path(backup_relative)
        receipt_path = self._storage.data_path(receipt_relative)
        if os.path.lexists(backup_path) or os.path.lexists(receipt_path):
            raise EvolutionInstallError(
                "STALE_TRANSACTION_STATE",
                "Installer transaction paths already exist",
            )
        return {
            "backup_relative": backup_relative,
            "receipt_relative": receipt_relative,
            "backup_path": backup_path,
            "receipt_path": receipt_path,
        }

    def _run_canary(
        self,
        target: Path,
        verified: VerifiedEvolutionManifest,
    ) -> dict[str, Any]:
        try:
            raw_result = self.canary_runner(target, verified)
        except Exception as exc:
            raise EvolutionInstallError(
                "CANARY_FAILED",
                "Post-install canary raised an exception",
            ) from exc
        if not isinstance(raw_result, Mapping) or raw_result.get("passed") is not True:
            raise EvolutionInstallError(
                "CANARY_FAILED",
                "Post-install canary did not pass",
            )
        result = copy.deepcopy(dict(raw_result))
        if len(canonical_json(result)) > 64 * 1024:
            raise EvolutionInstallError(
                "CANARY_INVALID",
                "Post-install canary result is too large",
            )
        return result

    def _canary_receipt(
        self,
        verified: VerifiedEvolutionManifest,
        *,
        canary_payload: Mapping[str, Any],
        observed_digest: str,
        now: float | None,
    ) -> dict[str, Any]:
        body = {
            "schema_version": CANARY_SCHEMA_VERSION,
            "manifest_digest": verified.manifest_digest,
            "candidate_id": verified.candidate_id,
            "registry_key": verified.registry_key,
            "check_id": verified.canary_check_id,
            "passed": True,
            "observed_artifact_digest": observed_digest,
            "created_at": self._now(now),
            "result": copy.deepcopy(dict(canary_payload)),
        }
        return {
            **body,
            "receipt_digest": digest_bytes(canonical_json(body)),
        }

    def _registry_entry(
        self,
        verified: VerifiedEvolutionManifest,
        *,
        previous_exists: bool,
        restore_digest: str,
        backup_relative: str,
        receipt_relative: str,
        receipt_digest: str,
        now: float | None,
    ) -> dict[str, Any]:
        return {
            "state": "active",
            "manifest_id": verified.manifest_id,
            "manifest_digest": verified.manifest_digest,
            "candidate_id": verified.candidate_id,
            "approval_id": verified.approval_id,
            "target_path": verified.target_path,
            "artifact_digest": verified.artifact_digest,
            "previous_existed": previous_exists,
            "restore_digest": restore_digest,
            "backup_path": backup_relative if previous_exists else None,
            "canary_receipt_path": receipt_relative,
            "canary_receipt_digest": receipt_digest,
            "installed_at": self._now(now),
        }

    def _restore_after_failed_install(
        self,
        *,
        target: Path,
        previous_exists: bool,
        restore_digest: str,
        backup_path: Path,
    ) -> None:
        if previous_exists:
            self._storage.validate_existing_regular(
                backup_path,
                code="ROLLBACK_BACKUP_INVALID",
            )
            if not hmac_compare(digest_file(backup_path), restore_digest):
                raise EvolutionInstallError(
                    "ROLLBACK_BACKUP_INVALID",
                    "Rollback backup digest does not match",
                )
            self._storage.atomic_publish_copy(
                backup_path,
                target,
                expected_digest=restore_digest,
            )
            return
        if os.path.lexists(target):
            self._storage.validate_existing_regular(
                target,
                code="ROLLBACK_TARGET_CHANGED",
            )
            target.unlink()
            self._storage.fsync_directory(target.parent)

    def rollback(
        self,
        registry_key: str,
        *,
        now: float | None = None,
    ) -> RollbackResult:
        """Restore the exact pre-install digest; repeated calls are idempotent."""
        if not isinstance(registry_key, str) or not registry_key:
            raise EvolutionInstallError(
                "REGISTRY_KEY_INVALID",
                "Rollback registry key is invalid",
            )
        with self._lock:
            self._storage.assert_root_integrity()
            registry = self._storage.load_registry()
            entry = registry["installations"].get(registry_key)
            if not isinstance(entry, dict):
                raise EvolutionInstallError(
                    "INSTALLATION_NOT_FOUND",
                    "No installation exists for this registry key",
                )
            target_relative = entry.get("target_path")
            if not isinstance(target_relative, str):
                raise EvolutionInstallError(
                    "REGISTRY_INVALID",
                    "Installation target is missing from the registry",
                )
            target = self._storage.data_path(target_relative)
            restore_digest = entry.get("restore_digest")
            installed_digest = entry.get("artifact_digest")
            previous_existed = entry.get("previous_existed") is True
            if not isinstance(installed_digest, str) or not isinstance(
                restore_digest,
                str,
            ):
                raise EvolutionInstallError(
                    "REGISTRY_INVALID",
                    "Installation digests are invalid",
                )

            state = entry.get("state")
            if state == "rolled_back":
                self._verify_restored_state(
                    target,
                    previous_existed=previous_existed,
                    restore_digest=restore_digest,
                )
                return self._rollback_result(
                    registry_key,
                    target_relative,
                    restore_digest,
                    idempotent=True,
                )
            if state not in {"active", "rollback_pending"}:
                raise EvolutionInstallError(
                    "ROLLBACK_STATE_INVALID",
                    "Installation is not in a rollback-capable state",
                )
            if state == "active":
                self._storage.validate_existing_regular(
                    target,
                    code="ROLLBACK_TARGET_CHANGED",
                )
                if not hmac_compare(digest_file(target), installed_digest):
                    raise EvolutionInstallError(
                        "ROLLBACK_TARGET_CHANGED",
                        "Installed target changed after the canary",
                    )
                entry["state"] = "rollback_pending"
                self._storage.atomic_json_write(
                    self._storage.registry_path,
                    registry,
                )

            self._complete_rollback(
                target,
                entry=entry,
                previous_existed=previous_existed,
                restore_digest=restore_digest,
                installed_digest=installed_digest,
            )
            entry["state"] = "rolled_back"
            entry["rolled_back_at"] = self._now(now)
            entry["restored_digest"] = restore_digest
            self._storage.atomic_json_write(self._storage.registry_path, registry)
            return self._rollback_result(
                registry_key,
                target_relative,
                restore_digest,
                idempotent=False,
            )

    @staticmethod
    def _rollback_result(
        registry_key: str,
        target_path: str,
        restored_digest: str,
        *,
        idempotent: bool,
    ) -> RollbackResult:
        return RollbackResult(
            status="rolled_back",
            registry_key=registry_key,
            target_path=target_path,
            restored_digest=restored_digest,
            idempotent=idempotent,
        )

    def _complete_rollback(
        self,
        target: Path,
        *,
        entry: Mapping[str, Any],
        previous_existed: bool,
        restore_digest: str,
        installed_digest: str,
    ) -> None:
        if previous_existed:
            if target.is_file() and not is_linklike(target):
                current_digest = digest_file(target)
                if hmac_compare(current_digest, restore_digest):
                    return
                if not hmac_compare(current_digest, installed_digest):
                    raise EvolutionInstallError(
                        "ROLLBACK_TARGET_CHANGED",
                        "Rollback refuses to overwrite an external target change",
                    )
            backup_relative = entry.get("backup_path")
            if not isinstance(backup_relative, str):
                raise EvolutionInstallError(
                    "ROLLBACK_BACKUP_INVALID",
                    "Rollback backup path is missing",
                )
            backup = self._storage.data_path(backup_relative)
            self._storage.validate_existing_regular(
                backup,
                code="ROLLBACK_BACKUP_INVALID",
            )
            if not hmac_compare(digest_file(backup), restore_digest):
                raise EvolutionInstallError(
                    "ROLLBACK_BACKUP_INVALID",
                    "Rollback backup digest does not match",
                )
            self._storage.atomic_publish_copy(
                backup,
                target,
                expected_digest=restore_digest,
            )
            self._verify_restored_state(
                target,
                previous_existed=True,
                restore_digest=restore_digest,
            )
            return

        if not os.path.lexists(target):
            return
        self._storage.validate_existing_regular(
            target,
            code="ROLLBACK_TARGET_CHANGED",
        )
        if not hmac_compare(digest_file(target), installed_digest):
            raise EvolutionInstallError(
                "ROLLBACK_TARGET_CHANGED",
                "Rollback refuses to remove an external target change",
            )
        target.unlink()
        self._storage.fsync_directory(target.parent)
        self._verify_restored_state(
            target,
            previous_existed=False,
            restore_digest=ABSENT_RESTORE_DIGEST,
        )

    def _verify_restored_state(
        self,
        target: Path,
        *,
        previous_existed: bool,
        restore_digest: str,
    ) -> None:
        if previous_existed:
            self._storage.validate_existing_regular(
                target,
                code="ROLLBACK_RESTORE_MISMATCH",
            )
            if not hmac_compare(digest_file(target), restore_digest):
                raise EvolutionInstallError(
                    "ROLLBACK_RESTORE_MISMATCH",
                    "Rollback did not restore the recorded digest",
                )
            return
        if os.path.lexists(target):
            raise EvolutionInstallError(
                "ROLLBACK_RESTORE_MISMATCH",
                "Rollback did not restore the absent target state",
            )

    def _now(self, supplied: float | None) -> float:
        value = float(supplied if supplied is not None else self._clock())
        if not math.isfinite(value) or value <= 0:
            raise EvolutionInstallError(
                "CLOCK_INVALID",
                "Installer clock is invalid",
            )
        return value
