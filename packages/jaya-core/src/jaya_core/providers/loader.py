"""Safe shared-library discovery for optional first-party providers."""

from __future__ import annotations

import ctypes
import os
import platform
from dataclasses import dataclass
from pathlib import Path


class NativeProviderError(RuntimeError):
    """Stable failure raised at a native provider boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LoadedLibrary:
    library: ctypes.CDLL
    path: Path


def _library_names(base_name: str) -> tuple[str, ...]:
    system = platform.system().casefold()
    if system == "windows":
        return (f"{base_name}.dll", f"lib{base_name}.dll")
    if system == "darwin":
        return (f"lib{base_name}.dylib",)
    return (f"lib{base_name}.so",)


def _repository_native_directories() -> tuple[Path, ...]:
    candidates: list[Path] = []
    source = Path(__file__).resolve()
    for parent in source.parents:
        native_root = parent / "native"
        if not (native_root / "CMakeLists.txt").is_file():
            continue
        candidates.extend(
            (
                native_root / "build" / "lib",
                native_root / "build" / "Release",
                native_root / "build" / "Debug",
                native_root / "build-windows" / "lib",
            )
        )
        break
    return tuple(candidates)


def _configured_candidates(base_name: str, specific_env: str) -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured_file = os.getenv(specific_env)
    if configured_file:
        candidates.append(Path(configured_file).expanduser().resolve())
    configured_dir = os.getenv("JAYA_NATIVE_LIBRARY_DIR")
    directories = []
    if configured_dir:
        directories.append(Path(configured_dir).expanduser().resolve())
    directories.extend(_repository_native_directories())
    for directory in directories:
        candidates.extend(directory / name for name in _library_names(base_name))
    return tuple(dict.fromkeys(candidates))


def load_first_party_library(base_name: str, *, specific_env: str) -> LoadedLibrary | None:
    """Load only an explicit file or a library below the repository build tree."""

    for candidate in _configured_candidates(base_name, specific_env):
        if not candidate.is_file():
            continue
        try:
            return LoadedLibrary(ctypes.CDLL(str(candidate)), candidate)
        except OSError:
            continue
    return None
