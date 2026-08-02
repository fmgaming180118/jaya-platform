"""
compatibility_matrix.py — Device compatibility matrix for JAYA deployment targets.

Defines device profiles and a compatibility checker that verifies whether a
deployment target satisfies JAYA component requirements.

Built-in profiles:
    ANDROID_MID_RANGE   — Android smartphone with ≥ 4 GB RAM, ARM64
    DESKTOP_STANDARD    — Desktop / laptop with ≥ 8 GB RAM, x86_64
    RASPBERRY_PI_4      — Raspberry Pi 4 with ≥ 4 GB RAM, ARM64
    CONSTRAINED_EDGE    — Minimal IoT node with ≥ 512 MB RAM, ARM32

Requirements checked:
    - min_ram_mb        ≥ required_min_ram_mb
    - cpu_arch          in allowed_cpu_archs
    - os_name           in allowed_os_names
    - python_version    >= required_python_major.minor
    - has_gpu           True if required_has_gpu else don't care
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Device Profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceProfile:
    """Physical or virtual deployment target characteristics."""

    device_type: str                # "ANDROID" | "DESKTOP" | "RASPBERRY_PI" | "EDGE_NODE"
    min_ram_mb: int                 # Available RAM in MiB
    cpu_arch: str                   # "ARM64" | "ARM32" | "x86_64" | "x86"
    os_name: str                    # "android" | "linux" | "windows" | "macos"
    python_version: Tuple[int, int] # (major, minor)
    has_gpu: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["python_version"] = list(self.python_version)
        return d


# ---------------------------------------------------------------------------
# Component Requirements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentRequirements:
    """Minimum requirements for a JAYA component to run on a device."""

    component_name: str
    required_min_ram_mb: int
    allowed_cpu_archs: FrozenSet[str]
    allowed_os_names: FrozenSet[str]
    required_python_version: Tuple[int, int]  # minimum (major, minor)
    required_has_gpu: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["allowed_cpu_archs"] = sorted(self.allowed_cpu_archs)
        d["allowed_os_names"] = sorted(self.allowed_os_names)
        d["required_python_version"] = list(self.required_python_version)
        return d


# ---------------------------------------------------------------------------
# Compatibility Result
# ---------------------------------------------------------------------------


@dataclass
class CompatibilityResult:
    device_name: str
    component_name: str
    is_compatible: bool
    pass_checks: List[str] = field(default_factory=list)
    fail_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Built-in Device Profiles
# ---------------------------------------------------------------------------

BUILT_IN_PROFILES: Dict[str, DeviceProfile] = {
    "ANDROID_MID_RANGE": DeviceProfile(
        device_type="ANDROID",
        min_ram_mb=4096,
        cpu_arch="ARM64",
        os_name="android",
        python_version=(3, 10),
        has_gpu=False,
    ),
    "DESKTOP_STANDARD": DeviceProfile(
        device_type="DESKTOP",
        min_ram_mb=8192,
        cpu_arch="x86_64",
        os_name="linux",
        python_version=(3, 12),
        has_gpu=False,
    ),
    "RASPBERRY_PI_4": DeviceProfile(
        device_type="RASPBERRY_PI",
        min_ram_mb=4096,
        cpu_arch="ARM64",
        os_name="linux",
        python_version=(3, 11),
        has_gpu=False,
    ),
    "CONSTRAINED_EDGE": DeviceProfile(
        device_type="EDGE_NODE",
        min_ram_mb=512,
        cpu_arch="ARM32",
        os_name="linux",
        python_version=(3, 9),
        has_gpu=False,
    ),
    "DESKTOP_GPU": DeviceProfile(
        device_type="DESKTOP",
        min_ram_mb=16384,
        cpu_arch="x86_64",
        os_name="linux",
        python_version=(3, 12),
        has_gpu=True,
    ),
}

# ---------------------------------------------------------------------------
# Built-in Component Requirements
# ---------------------------------------------------------------------------

BUILT_IN_REQUIREMENTS: Dict[str, ComponentRequirements] = {
    "JAYA_CORE_RUNTIME": ComponentRequirements(
        component_name="JAYA_CORE_RUNTIME",
        required_min_ram_mb=256,
        allowed_cpu_archs=frozenset({"ARM64", "x86_64"}),
        allowed_os_names=frozenset({"android", "linux", "windows", "macos"}),
        required_python_version=(3, 10),
    ),
    "JAYA_AGENT": ComponentRequirements(
        component_name="JAYA_AGENT",
        required_min_ram_mb=128,
        allowed_cpu_archs=frozenset({"ARM64", "ARM32", "x86_64", "x86"}),
        allowed_os_names=frozenset({"android", "linux", "windows", "macos"}),
        required_python_version=(3, 9),
    ),
    "JAYA_OS_SANDBOX": ComponentRequirements(
        component_name="JAYA_OS_SANDBOX",
        required_min_ram_mb=64,
        allowed_cpu_archs=frozenset({"ARM64", "ARM32", "x86_64", "x86"}),
        allowed_os_names=frozenset({"android", "linux", "windows", "macos"}),
        required_python_version=(3, 9),
    ),
    "EDGE_MODEL_GGUF_Q4": ComponentRequirements(
        component_name="EDGE_MODEL_GGUF_Q4",
        required_min_ram_mb=512,
        allowed_cpu_archs=frozenset({"ARM64", "x86_64"}),
        allowed_os_names=frozenset({"android", "linux", "windows", "macos"}),
        required_python_version=(3, 10),
    ),
    "JAYA_RESEARCH_FULL": ComponentRequirements(
        component_name="JAYA_RESEARCH_FULL",
        required_min_ram_mb=2048,
        allowed_cpu_archs=frozenset({"x86_64"}),
        allowed_os_names=frozenset({"linux", "windows", "macos"}),
        required_python_version=(3, 11),
    ),
}


# ---------------------------------------------------------------------------
# Compatibility Matrix
# ---------------------------------------------------------------------------


class CompatibilityMatrix:
    """
    Registry and checker for device–component compatibility.

    Profiles and requirements can be registered at runtime; the built-in
    sets are loaded automatically.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, DeviceProfile] = dict(BUILT_IN_PROFILES)
        self._requirements: Dict[str, ComponentRequirements] = dict(BUILT_IN_REQUIREMENTS)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_profile(self, name: str, profile: DeviceProfile) -> None:
        """Register or replace a device profile."""
        if not name or not isinstance(profile, DeviceProfile):
            raise ValueError("name must be non-empty and profile must be a DeviceProfile")
        self._profiles[name] = profile

    def register_requirements(self, name: str, req: ComponentRequirements) -> None:
        """Register or replace component requirements."""
        if not name or not isinstance(req, ComponentRequirements):
            raise ValueError(
                "name must be non-empty and req must be ComponentRequirements"
            )
        self._requirements[name] = req

    # ------------------------------------------------------------------
    # Compatibility check
    # ------------------------------------------------------------------

    def is_compatible(
        self,
        device_name: str,
        component_name: str,
    ) -> CompatibilityResult:
        """
        Check whether a named device profile satisfies a component's requirements.

        Args:
            device_name     : Key in the profile registry.
            component_name  : Key in the requirements registry.

        Returns:
            CompatibilityResult with pass_checks and fail_reasons lists.
        """
        if device_name not in self._profiles:
            raise KeyError(
                f"Device profile '{device_name}' not registered; "
                f"available: {sorted(self._profiles)}"
            )
        if component_name not in self._requirements:
            raise KeyError(
                f"Component requirements '{component_name}' not registered; "
                f"available: {sorted(self._requirements)}"
            )

        profile = self._profiles[device_name]
        req = self._requirements[component_name]
        pass_checks: List[str] = []
        fail_reasons: List[str] = []

        # 1. RAM
        if profile.min_ram_mb >= req.required_min_ram_mb:
            pass_checks.append(
                f"RAM: {profile.min_ram_mb} MB ≥ required {req.required_min_ram_mb} MB"
            )
        else:
            fail_reasons.append(
                f"RAM: {profile.min_ram_mb} MB < required {req.required_min_ram_mb} MB"
            )

        # 2. CPU arch
        if profile.cpu_arch in req.allowed_cpu_archs:
            pass_checks.append(f"CPU arch: '{profile.cpu_arch}' is allowed")
        else:
            fail_reasons.append(
                f"CPU arch: '{profile.cpu_arch}' not in {sorted(req.allowed_cpu_archs)}"
            )

        # 3. OS name
        if profile.os_name in req.allowed_os_names:
            pass_checks.append(f"OS: '{profile.os_name}' is allowed")
        else:
            fail_reasons.append(
                f"OS: '{profile.os_name}' not in {sorted(req.allowed_os_names)}"
            )

        # 4. Python version
        if profile.python_version >= req.required_python_version:
            pass_checks.append(
                f"Python: {profile.python_version} ≥ required {req.required_python_version}"
            )
        else:
            fail_reasons.append(
                f"Python: {profile.python_version} < required {req.required_python_version}"
            )

        # 5. GPU (only checked if required)
        if req.required_has_gpu:
            if profile.has_gpu:
                pass_checks.append("GPU: present (required)")
            else:
                fail_reasons.append("GPU: required but not available on this profile")
        else:
            pass_checks.append("GPU: not required")

        return CompatibilityResult(
            device_name=device_name,
            component_name=component_name,
            is_compatible=len(fail_reasons) == 0,
            pass_checks=pass_checks,
            fail_reasons=fail_reasons,
        )

    def check_all_components(self, device_name: str) -> Dict[str, CompatibilityResult]:
        """Check a device profile against every registered component requirement."""
        return {
            comp_name: self.is_compatible(device_name, comp_name)
            for comp_name in self._requirements
        }

    def list_compatible_devices(self, component_name: str) -> List[str]:
        """Return names of all device profiles compatible with a component."""
        return [
            dev_name
            for dev_name in self._profiles
            if self.is_compatible(dev_name, component_name).is_compatible
        ]

    @property
    def profile_names(self) -> List[str]:
        return sorted(self._profiles)

    @property
    def requirement_names(self) -> List[str]:
        return sorted(self._requirements)
