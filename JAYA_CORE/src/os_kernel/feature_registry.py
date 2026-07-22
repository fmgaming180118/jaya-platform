"""Phase 3A — Feature Registry for Dynamic Feature Management.

This module manages the lifecycle of dynamically compiled features:
- Registration and discovery
- Versioning and dependency resolution
- Mounting/unmounting into the OS shell
- Security sandboxing
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum


class FeatureStatus(str, Enum):
    """Feature lifecycle status."""
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    MOUNTED = "mounted"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNMOUNTED = "unmounted"


class FeaturePermission(str, Enum):
    """Permissions a feature can request."""
    UI_MOUNT = "ui_mount"
    STATE_READ = "state_read"
    STATE_WRITE = "state_write"
    API_CALL = "api_call"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK = "network"
    PROCESS_SPAWN = "process_spawn"
    CLIPBOARD = "clipboard"
    NOTIFICATIONS = "notifications"


@dataclass
class FeatureManifest:
    """Feature manifest parsed from manifest.json."""
    name: str
    id: str
    version: str
    description: str
    protocol_version: str
    entry_point: str
    capabilities: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)  # feature_id -> version
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatureManifest":
        return cls(
            name=data.get("name", ""),
            id=data.get("id", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            protocol_version=data.get("protocol_version", "1.0"),
            entry_point=data.get("entry_point", "run_feature"),
            capabilities=data.get("capabilities", []),
            permissions=data.get("permissions", []),
            dependencies=data.get("dependencies", {}),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FeatureInstance:
    """Runtime instance of a mounted feature."""
    manifest: FeatureManifest
    module: Any = None
    entry_point: Callable = None
    status: FeatureStatus = FeatureStatus.DISCOVERED
    mount_point: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    started_at: float = 0
    stopped_at: float = 0
    process_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "status": self.status.value,
            "mount_point": self.mount_point,
            "config": self.config,
            "state": self.state,
            "error": self.error,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "process_id": self.process_id,
        }


class FeatureRegistry:
    """Central registry for dynamic features."""

    def __init__(self, features_dir: str = None, sandbox_mode: bool = True):
        self.features_dir = Path(features_dir) if features_dir else Path.cwd() / "features"
        self.features_dir.mkdir(parents=True, exist_ok=True)

        self._discovered: Dict[str, FeatureManifest] = {}
        self._instances: Dict[str, FeatureInstance] = {}
        self._mount_points: Dict[str, str] = {}  # mount_point -> feature_id
        self._lock = threading.RLock()
        self._sandbox_mode = sandbox_mode
        self._permission_grants: Dict[str, Set[FeaturePermission]] = {}

        # Built-in permission policies
        self._default_permissions = {
            FeaturePermission.UI_MOUNT: True,
            FeaturePermission.STATE_READ: True,
            FeaturePermission.STATE_WRITE: True,
            FeaturePermission.API_CALL: True,
            FeaturePermission.FILE_READ: False,
            FeaturePermission.FILE_WRITE: False,
            FeaturePermission.NETWORK: False,
            FeaturePermission.PROCESS_SPAWN: False,
            FeaturePermission.CLIPBOARD: True,
            FeaturePermission.NOTIFICATIONS: True,
        }

    def discover_features(self) -> List[FeatureManifest]:
        """Scan features directory for valid feature packages."""
        discovered = []

        for feature_dir in self.features_dir.iterdir():
            if not feature_dir.is_dir():
                continue

            manifest_file = feature_dir / "manifest.json"
            if not manifest_file.exists():
                continue

            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest = FeatureManifest.from_dict(manifest_data)

                # Validate protocol version
                if manifest.protocol_version != "1.0":
                    print(f"Warning: Feature {manifest.name} has unsupported protocol version {manifest.protocol_version}")
                    continue

                # Validate entry point exists
                module_file = feature_dir / f"{feature_dir.name}.py"
                if not module_file.exists():
                    print(f"Warning: Feature {manifest.name} missing module file")
                    continue

                with self._lock:
                    self._discovered[manifest.id] = manifest
                discovered.append(manifest)

            except Exception as e:
                print(f"Error discovering feature in {feature_dir}: {e}")

        return discovered

    def get_manifest(self, feature_id: str) -> Optional[FeatureManifest]:
        """Get manifest by feature ID."""
        with self._lock:
            return self._discovered.get(feature_id)

    def list_discovered(self) -> List[FeatureManifest]:
        """List all discovered features."""
        with self._lock:
            return list(self._discovered.values())

    def validate_permissions(self, manifest: FeatureManifest) -> Dict[FeaturePermission, bool]:
        """Check which requested permissions are granted by default."""
        results = {}
        for perm_str in manifest.permissions:
            try:
                perm = FeaturePermission(perm_str)
                results[perm] = self._default_permissions.get(perm, False)
            except ValueError:
                results[FeaturePermission(perm_str)] = False
        return results

    def grant_permission(self, feature_id: str, permission: FeaturePermission) -> None:
        """Grant a specific permission to a feature."""
        with self._lock:
            if feature_id not in self._permission_grants:
                self._permission_grants[feature_id] = set()
            self._permission_grants[feature_id].add(permission)

    def revoke_permission(self, feature_id: str, permission: FeaturePermission) -> None:
        """Revoke a permission from a feature."""
        with self._lock:
            if feature_id in self._permission_grants:
                self._permission_grants[feature_id].discard(permission)

    def has_permission(self, feature_id: str, permission: FeaturePermission) -> bool:
        """Check if feature has a permission."""
        with self._lock:
            grants = self._permission_grants.get(feature_id, set())
            if permission in grants:
                return True
            return self._default_permissions.get(permission, False)

    def mount_feature(
        self,
        feature_id: str,
        mount_point: str = "body",
        config: Dict[str, Any] = None,
        jaya_bridge: Any = None,
    ) -> FeatureInstance:
        """Mount a feature at the specified mount point."""
        with self._lock:
            manifest = self._discovered.get(feature_id)
            if not manifest:
                raise ValueError(f"Feature not discovered: {feature_id}")

            if mount_point in self._mount_points:
                raise ValueError(f"Mount point already occupied: {mount_point}")

            # Check for existing instance
            if feature_id in self._instances:
                instance = self._instances[feature_id]
                if instance.status in (FeatureStatus.MOUNTED, FeatureStatus.RUNNING):
                    raise ValueError(f"Feature already mounted: {feature_id}")

            # Load module
            feature_dir = self.features_dir / manifest.name.replace(" ", "_").lower()
            module_file = feature_dir / f"{feature_dir.name}.py"

            spec = importlib.util.spec_from_file_location(manifest.name, module_file)
            module = importlib.util.module_from_spec(spec)

            # Inject sandboxed builtins if in sandbox mode
            if self._sandbox_mode:
                module.__dict__["__builtins__"] = self._create_sandboxed_builtins()

            sys.modules[manifest.name] = module
            spec.loader.exec_module(module)

            # Get entry point
            entry_point = getattr(module, manifest.entry_point.split(".")[-1], None)
            if not entry_point:
                raise ValueError(f"Entry point not found: {manifest.entry_point}")

            # Set JAYA bridge if provided
            if jaya_bridge and hasattr(module, "set_jaya_bridge"):
                module.set_jaya_bridge(jaya_bridge)

            # Create instance
            instance = FeatureInstance(
                manifest=manifest,
                module=module,
                entry_point=entry_point,
                status=FeatureStatus.MOUNTED,
                mount_point=mount_point,
                config=config or {},
                started_at=time.time(),
            )

            # Initialize feature runtime by calling run_feature in background
            # The run_feature function will create its own FeatureRuntime and set up dispatch
            try:
                import asyncio
                
                async def init_feature():
                    try:
                        await entry_point(jaya_bridge, config or {})
                    except Exception as e:
                        print(f"Feature initialization error: {e}")
                
                # Schedule the feature to run
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(init_feature())
                    else:
                        loop.run_until_complete(init_feature())
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(init_feature())
            except Exception as e:
                print(f"Feature runtime initialization error: {e}")

            self._instances[feature_id] = instance
            self._mount_points[mount_point] = feature_id

            return instance

    def unmount_feature(self, feature_id: str) -> bool:
        """Unmount a feature."""
        with self._lock:
            instance = self._instances.get(feature_id)
            if not instance:
                return False

            if instance.mount_point in self._mount_points:
                del self._mount_points[instance.mount_point]

            instance.status = FeatureStatus.UNMOUNTED
            instance.stopped_at = time.time()

            # Clean up module
            if instance.manifest.name in sys.modules:
                del sys.modules[instance.manifest.name]

            return True

    def get_instance(self, feature_id: str) -> Optional[FeatureInstance]:
        """Get feature instance by ID."""
        with self._lock:
            return self._instances.get(feature_id)

    def get_instance_at_mount(self, mount_point: str) -> Optional[FeatureInstance]:
        """Get feature instance at mount point."""
        with self._lock:
            feature_id = self._mount_points.get(mount_point)
            if feature_id:
                return self._instances.get(feature_id)
            return None

    def list_mounted(self) -> List[FeatureInstance]:
        """List all mounted features."""
        with self._lock:
            return [inst for inst in self._instances.values()
                    if inst.status in (FeatureStatus.MOUNTED, FeatureStatus.RUNNING)]

    def _create_sandboxed_builtins(self) -> Dict:
        """Create a restricted builtins dict for sandboxing."""
        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "bytearray": bytearray,
            "bytes": bytes,
            "chr": chr,
            "complex": complex,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "frozenset": frozenset,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "oct": oct,
            "ord": ord,
            "pow": pow,
            "print": print,
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "type": type,
            "zip": zip,
            "__import__": __import__,
            "__build_class__": __build_class__,
            "super": super,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "NotImplementedError": NotImplementedError,
            "RuntimeError": RuntimeError,
            "StopIteration": StopIteration,
            "ImportError": ImportError,
            "ModuleNotFoundError": ModuleNotFoundError,
            "NameError": NameError,
            "SyntaxError": SyntaxError,
            "IndentationError": IndentationError,
            "True": True,
            "False": False,
            "None": None,
        }

        # Add safe modules
        import math
        import random
        import datetime
        import json
        import re
        import hashlib
        import base64
        import urllib.parse

        safe_modules = {
            "math": math,
            "random": random,
            "datetime": datetime,
            "json": json,
            "re": re,
            "hashlib": hashlib,
            "base64": base64,
            "urllib.parse": urllib.parse,
        }

        safe_builtins.update(safe_modules)
        return safe_builtins

    def install_feature(self, source_path: str, feature_name: str = None) -> FeatureManifest:
        """Install a feature from a source directory."""
        source = Path(source_path)
        if not source.exists():
            raise ValueError(f"Source path does not exist: {source_path}")

        # Determine feature name
        if feature_name is None:
            feature_name = source.name

        # Target directory
        target_dir = self.features_dir / feature_name.replace(" ", "_").lower()
        if target_dir.exists():
            shutil.rmtree(target_dir)

        # Copy feature
        shutil.copytree(source, target_dir)

        # Verify manifest
        manifest_file = target_dir / "manifest.json"
        if not manifest_file.exists():
            shutil.rmtree(target_dir)
            raise ValueError("Feature missing manifest.json")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = FeatureManifest.from_dict(manifest_data)

        # Verify module file exists
        module_file = target_dir / f"{target_dir.name}.py"
        if not module_file.exists():
            shutil.rmtree(target_dir)
            raise ValueError(f"Feature module not found: {module_file}")

        # Register
        with self._lock:
            self._discovered[manifest.id] = manifest

        return manifest

    def uninstall_feature(self, feature_id: str) -> bool:
        """Uninstall a feature completely."""
        with self._lock:
            manifest = self._discovered.get(feature_id)
            if not manifest:
                return False

            # Unmount if mounted
            if feature_id in self._instances:
                self.unmount_feature(feature_id)

            # Remove directory
            feature_dir = self.features_dir / manifest.name.replace(" ", "_").lower()
            if feature_dir.exists():
                shutil.rmtree(feature_dir)

            del self._discovered[feature_id]
            return True

    def get_registry_status(self) -> Dict[str, Any]:
        """Get overall registry status."""
        with self._lock:
            return {
                "discovered_count": len(self._discovered),
                "mounted_count": len([i for i in self._instances.values()
                                      if i.status in (FeatureStatus.MOUNTED, FeatureStatus.RUNNING)]),
                "mount_points": dict(self._mount_points),
                "features_dir": str(self.features_dir),
                "sandbox_mode": self._sandbox_mode,
            }


# Global registry instance
_global_registry: Optional[FeatureRegistry] = None


def get_feature_registry(features_dir: str = None) -> FeatureRegistry:
    """Get or create the global feature registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = FeatureRegistry(features_dir)
    return _global_registry


def reset_feature_registry() -> None:
    """Reset the global registry (for testing)."""
    global _global_registry
    _global_registry = None