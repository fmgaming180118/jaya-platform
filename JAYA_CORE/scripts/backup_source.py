#!/usr/bin/env python3
"""Create and verify a ZIP backup of JAYA_CORE Python source files.

The script never deletes source. All local paths are derived from this checkout;
an optional external mirror must be supplied explicitly through CLI or environment.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = CORE_ROOT / "src" / "brain_v2"
DEFAULT_BACKUP_DIR = CORE_ROOT / "backup"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_contained(
    raw_path: str | os.PathLike[str],
    *,
    root: Path = CORE_ROOT,
    must_exist: bool = False,
    directory: bool = False,
) -> Path:
    """Resolve a user path and require it to remain inside ``root``."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=must_exist)
    if not _is_relative_to(resolved, resolved_root):
        raise ValueError(f"path must stay inside {resolved_root}: {resolved}")
    if must_exist and directory and not resolved.is_dir():
        raise ValueError(f"expected a directory: {resolved}")
    return resolved


def resolve_mirror_dir(raw_path: str | os.PathLike[str], *, source_dir: Path) -> Path:
    """Validate an explicit external mirror destination."""
    mirror = Path(raw_path).expanduser().resolve(strict=False)
    filesystem_root = Path(mirror.anchor).resolve(strict=False)
    if mirror == filesystem_root or mirror == Path.home().resolve(strict=False):
        raise ValueError(
            "mirror directory cannot be a filesystem root or the user home"
        )
    if mirror == source_dir or _is_relative_to(mirror, source_dir):
        raise ValueError("mirror directory cannot be inside the source directory")
    return mirror


def collect_python_files(source_dir: Path) -> list[Path]:
    """Collect regular Python files without following paths outside source."""
    files: list[Path] = []
    for candidate in sorted(source_dir.rglob("*.py")):
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file() or not _is_relative_to(resolved, source_dir):
            continue
        files.append(resolved)
    return files


def create_backup(
    source_dir: Path,
    backup_dir: Path,
    *,
    mirror_dir: Path | None = None,
) -> Path:
    """Create, verify, and optionally mirror a source archive."""
    source_dir = resolve_contained(
        source_dir,
        must_exist=True,
        directory=True,
    )
    backup_dir = resolve_contained(backup_dir)
    if mirror_dir is not None:
        mirror_dir = resolve_mirror_dir(mirror_dir, source_dir=source_dir)
    if _is_relative_to(backup_dir, source_dir):
        raise ValueError("backup directory cannot be inside the source directory")

    files = collect_python_files(source_dir)
    if not files:
        raise RuntimeError(f"no Python files found under {source_dir}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = backup_dir.resolve(strict=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%fZ")
    archive_path = backup_dir / f"brain_v2_source_{timestamp}.zip"

    manifest: dict[str, str] = {}
    with zipfile.ZipFile(
        archive_path,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source_path in files:
            relative_name = source_path.relative_to(source_dir).as_posix()
            manifest[relative_name] = sha256_file(source_path)
            archive.write(source_path, arcname=relative_name)
        manifest_text = "".join(
            f"{digest}  {relative_name}\n"
            for relative_name, digest in sorted(manifest.items())
        )
        archive.writestr("SHA256MANIFEST.txt", manifest_text)

    with zipfile.ZipFile(archive_path, mode="r") as archive:
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise RuntimeError(f"ZIP CRC verification failed for {corrupt_member}")
        for relative_name, expected_digest in manifest.items():
            actual_digest = hashlib.sha256(archive.read(relative_name)).hexdigest()
            if actual_digest != expected_digest:
                raise RuntimeError(f"SHA-256 verification failed for {relative_name}")

    if mirror_dir is not None:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        mirror_target = mirror_dir / archive_path.name
        if mirror_target.exists():
            raise FileExistsError(f"mirror archive already exists: {mirror_target}")
        shutil.copy2(archive_path, mirror_target)
        if sha256_file(mirror_target) != sha256_file(archive_path):
            raise RuntimeError(f"mirrored archive verification failed: {mirror_target}")

    return archive_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a verified backup of JAYA_CORE Python source files."
    )
    parser.add_argument(
        "--source-dir",
        default=os.getenv("JAYA_BACKUP_SOURCE_DIR", str(DEFAULT_SOURCE_DIR)),
        help="source directory inside JAYA_CORE (env: JAYA_BACKUP_SOURCE_DIR)",
    )
    parser.add_argument(
        "--backup-dir",
        default=os.getenv("JAYA_BACKUP_DIR", str(DEFAULT_BACKUP_DIR)),
        help="archive directory inside JAYA_CORE (env: JAYA_BACKUP_DIR)",
    )
    parser.add_argument(
        "--mirror-dir",
        default=os.getenv("JAYA_BACKUP_MIRROR_DIR"),
        help="optional explicit mirror directory (env: JAYA_BACKUP_MIRROR_DIR)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source_dir = resolve_contained(
            args.source_dir,
            must_exist=True,
            directory=True,
        )
        backup_dir = resolve_contained(args.backup_dir)
        mirror_dir = (
            resolve_mirror_dir(args.mirror_dir, source_dir=source_dir)
            if args.mirror_dir
            else None
        )
        archive_path = create_backup(
            source_dir,
            backup_dir,
            mirror_dir=mirror_dir,
        )
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1

    print(f"verified source backup: {archive_path}")
    if mirror_dir is not None:
        print(f"verified mirror: {mirror_dir / archive_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
