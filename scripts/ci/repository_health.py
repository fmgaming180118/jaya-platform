#!/usr/bin/env python3
"""Create a redacted, reproducible repository-health inventory receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ERROR_SECRET = "SECRET_OR_USER_DATA_FOUND"
ERROR_DIRTY = "DIRTY_STATE_AMBIGUOUS"
ERROR_PACKAGE = "PACKAGE_LAYOUT_INVALID"
_MINIMUM_STATUS_RECORD_BYTES = 4
_LS_TREE_METADATA_FIELDS = 3
_PACKAGE_OWNER_PARTS = 2

SOURCE_ROOTS = {
    ".devcontainer",
    ".github",
    "benchmarks",
    "configs",
    "docker",
    "docs",
    "examples",
    "native",
    "packages",
    "scripts",
    "tests",
    "tools",
}
GENERATED_PREFIXES = (
    ".pytest_tmp_",
    "native/build/",
    "native/build-",
    "native/trusted/target/",
    "temp_test_acceptance/",
)
RUNTIME_PREFIXES = (
    "artifacts/",
    "data/",
    "identity/",
    "logs/",
    "outputs/",
)
LEGACY_ROOTS = {
    "JAYA_CORE": ("packages/jaya-core", "jaya_core"),
    "JAYA_AGENT": ("packages/jaya-agent", "jaya_agent"),
    "JAYA_OS": ("packages/jaya-os", "jaya_os"),
    "JAYA_RESEARCH": ("packages/jaya-research", "jaya_research"),
    "JAYA_ANDROID": ("packages/jaya-android", None),
    "test_features": ("tests/fixtures/legacy-features", None),
}
TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".cmd",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".md",
    ".ps1",
    ".py",
    ".pyi",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_PATTERNS = {
    "PEM_PRIVATE_KEY": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "OPENAI_TOKEN": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GITHUB_TOKEN": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "GOOGLE_API_KEY": re.compile(rb"\bAIza[0-9A-Za-z_-]{20,}\b"),
    "AWS_ACCESS_KEY": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "SLACK_TOKEN": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
}
SENSITIVE_FILE_NAMES = {
    ".env",
    "credentials.json",
    "private_key.json",
    "service-account.json",
}
TOOLCHAINS = (
    ("git", ("git", "--version")),
    ("uv", ("uv", "--version")),
    ("node", ("node", "--version")),
    ("npm", ("npm", "--version")),
    ("java", ("java", "-version")),
    ("rustc", ("rustc", "--version")),
    ("cargo", ("cargo", "--version")),
    ("cmake", ("cmake", "--version")),
    ("ninja", ("ninja", "--version")),
)


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    status: str
    path: str
    owner_area: str
    size_bytes: int | None
    category: str
    reason: str
    counterpart: str | None = None
    original_path: str | None = None


class GitCommandError(RuntimeError):
    """Raised when a required read-only Git command fails."""

    def __init__(self, arguments: tuple[str, ...], detail: str) -> None:
        super().__init__(f"git {' '.join(arguments)} failed: {detail}")


class GitStatusParseError(RuntimeError):
    """Raised when Git emits an unsupported status record."""

    def __init__(self, reason: str) -> None:
        messages = {
            "SHORT_RECORD": "unexpected short record from git status",
            "MISSING_SOURCE": "rename/copy record is missing its source path",
        }
        super().__init__(messages[reason])


def _run_git(
    root: Path,
    *arguments: str,
    text: bool = True,
    timeout: float = 30.0,
) -> str | bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=text,
        timeout=timeout,
    )
    if completed.returncode != 0:
        error = completed.stderr.strip()
        raise GitCommandError(arguments, error)
    return completed.stdout


def discover_root(start: Path) -> Path:
    output = _run_git(start.resolve(), "rev-parse", "--show-toplevel")
    return Path(str(output).strip()).resolve()


def _status_records(root: Path) -> list[tuple[str, str, str | None]]:
    raw = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        text=False,
    )
    fields = bytes(raw).split(b"\0")
    records: list[tuple[str, str, str | None]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        if len(field) < _MINIMUM_STATUS_RECORD_BYTES:
            raise GitStatusParseError("SHORT_RECORD")
        status = field[:2].decode("ascii", errors="replace")
        path = os.fsdecode(field[3:]).replace("\\", "/")
        original_path: str | None = None
        if "R" in status or "C" in status:
            if index >= len(fields) or not fields[index]:
                raise GitStatusParseError("MISSING_SOURCE")
            original_path = os.fsdecode(fields[index]).replace("\\", "/")
            index += 1
        records.append((status, path, original_path))
    return records


def _head_blob_paths(root: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    raw = _run_git(root, "ls-tree", "-r", "-z", "HEAD", text=False)
    path_to_hash: dict[str, str] = {}
    hash_to_paths: dict[str, list[str]] = defaultdict(list)
    for record in bytes(raw).split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        if not separator:
            continue
        parts = metadata.decode("ascii", errors="replace").split()
        if len(parts) != _LS_TREE_METADATA_FIELDS or parts[1] != "blob":
            continue
        object_hash = parts[2]
        path = os.fsdecode(raw_path).replace("\\", "/")
        path_to_hash[path] = object_hash
        hash_to_paths[object_hash].append(path)
    return path_to_hash, hash_to_paths


def _git_blob_hash(path: Path, algorithm: str) -> str:
    size = path.stat().st_size
    digest = hashlib.new(algorithm)
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _current_blob_paths(
    root: Path,
    records: Iterable[tuple[str, str, str | None]],
) -> dict[str, list[str]]:
    algorithm = str(_run_git(root, "rev-parse", "--show-object-format")).strip()
    if algorithm not in hashlib.algorithms_available:
        return {}
    result: dict[str, list[str]] = defaultdict(list)
    for status, relative, _original in records:
        if status != "??":
            continue
        path = root / relative
        if not path.is_file() or _is_sensitive_filename(path):
            continue
        try:
            result[_git_blob_hash(path, algorithm)].append(relative)
        except OSError:
            continue
    return result


def _counterpart_candidates(relative: str) -> list[str]:  # noqa: PLR0912
    path = PurePosixPath(relative)
    if not path.parts or path.parts[0] not in LEGACY_ROOTS:
        return []
    destination, module = LEGACY_ROOTS[path.parts[0]]
    remainder = PurePosixPath(*path.parts[1:])
    candidates = [str(PurePosixPath(destination) / remainder)]
    if module and remainder.parts:
        if remainder.parts[0] == "src":
            source_rest = PurePosixPath(*remainder.parts[1:])
            if source_rest.parts and source_rest.parts[0] == module:
                candidates.append(str(PurePosixPath(destination) / "src" / source_rest))
            else:
                candidates.append(str(PurePosixPath(destination) / "src" / module / source_rest))
            if len(source_rest.parts) == 1 and source_rest.suffix == ".py":
                candidates.append(
                    str(
                        PurePosixPath(destination)
                        / "src"
                        / module
                        / source_rest.stem
                        / "__init__.py"
                    )
                )
        if remainder.parts[0] == "contracts":
            candidates.append(str(PurePosixPath(destination) / "src" / module / remainder))
    if path.parts[0] == "JAYA_CORE" and remainder.parts:
        first = remainder.parts[0]
        rest = PurePosixPath(*remainder.parts[1:])
        if first == "data":
            candidates.append(
                str(PurePosixPath(destination) / "src" / "jaya_core" / "resources" / rest)
            )
        elif first == "evolution":
            candidates.append(
                str(
                    PurePosixPath(destination)
                    / "src"
                    / "jaya_core"
                    / "resources"
                    / "evolution_registry"
                    / rest
                )
            )
        elif first == "features":
            candidates.append(
                str(PurePosixPath(destination) / "src" / "jaya_core" / "features" / rest)
            )
        elif first == "test_features":
            candidates.append(str(PurePosixPath("tests/fixtures/legacy-features") / rest))
        elif first == "tools":
            candidates.append(str(PurePosixPath(destination) / "scripts" / "tools" / rest))
        elif len(remainder.parts) == 1 and remainder.name.startswith("test_"):
            candidates.append(
                str(PurePosixPath(destination) / "tests" / "legacy_smoke" / remainder.name)
            )
    if path.parts[0] == "JAYA_RESEARCH" and remainder.parts:
        first = remainder.parts[0]
        rest = PurePosixPath(*remainder.parts[1:])
        if first == "configs":
            candidates.append(str(PurePosixPath("configs/research") / rest))
        elif first == "training":
            candidates.append(
                str(PurePosixPath(destination) / "src" / "jaya_research" / "training" / rest)
            )
        elif first == "src" and rest.name.startswith("test_"):
            candidates.append(
                str(PurePosixPath(destination) / "tests" / "legacy_source" / rest.name)
            )
        elif remainder == PurePosixPath("src/.gitignore"):
            candidates.append(".gitignore")
    if path.parts[0] == "test_features":
        candidates.append(
            str(PurePosixPath("packages/jaya-os/tests/fixtures/test_features") / remainder)
        )
    return list(dict.fromkeys(candidates))


def _is_sensitive_filename(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered in SENSITIVE_FILE_NAMES:
        return True
    return lowered.endswith((".key", ".pem", ".p12", ".pfx"))


def _scan_secret_markers(root: Path, relative: str) -> list[str]:
    path = root / relative
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size > 1024 * 1024:
        return []
    try:
        content = path.read_bytes()
    except OSError:
        return []
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(content)]


def _categorize(  # noqa: PLR0911, PLR0912, PLR0913, PLR0917
    root: Path,
    status: str,
    relative: str,
    original_path: str | None,
    head_path_to_hash: dict[str, str],
    current_hash_to_paths: dict[str, list[str]],
) -> tuple[str, str, str | None]:
    legacy_parts = PurePosixPath(relative).parts
    legacy_remainder = "/".join(legacy_parts[1:]) if legacy_parts else relative
    if status != "??" and legacy_remainder.startswith(".pytest_tmp_"):
        return "GENERATED_CACHE", "tracked pytest output removed from source", None
    if status != "??" and (
        relative == "JAYA_CORE/SHA256MANIFEST.txt" or legacy_remainder.startswith("models/")
    ):
        return "RUNTIME_ARTIFACT", "generated/model artifact removed from source", None
    if "U" in status or status in {"AA", "DD"}:
        return "UNKNOWN", "unresolved Git conflict", None
    if "R" in status or "C" in status:
        return "INTENDED_MIGRATION", "Git recorded a rename or copy", original_path
    if "D" in status:
        for candidate in _counterpart_candidates(relative):
            if (root / candidate).exists():
                return (
                    "INTENDED_MIGRATION",
                    "canonical-layout counterpart exists",
                    candidate,
                )
        object_hash = head_path_to_hash.get(relative)
        if object_hash and current_hash_to_paths.get(object_hash):
            counterpart = sorted(current_hash_to_paths[object_hash])[0]
            return (
                "INTENDED_MIGRATION",
                "identical Git blob exists at a current untracked path",
                counterpart,
            )
        return "UNKNOWN", "deleted tracked path has no proven counterpart", None
    if status == "??":
        normalized = relative.lower()
        if _is_sensitive_filename(root / relative):
            return "USER_DATA_OR_SECRET", "sensitive filename is untracked", None
        if normalized.startswith(GENERATED_PREFIXES):
            return "GENERATED_CACHE", "generated/test build prefix", None
        if normalized.startswith(RUNTIME_PREFIXES):
            return "RUNTIME_ARTIFACT", "runtime-owned prefix", None
        top = PurePosixPath(relative).parts[0] if relative else ""
        if top in SOURCE_ROOTS or relative in {".gitattributes", "conftest.py"}:
            return "INTENDED_SOURCE_CHANGE", "path is inside a canonical source area", None
        return "UNKNOWN", "untracked path is outside canonical source areas", None
    if "A" in status or "M" in status:
        return "INTENDED_SOURCE_CHANGE", "tracked source/configuration change", None
    return "UNKNOWN", f"unclassified Git status {status!r}", None


def _owner_area(relative: str) -> str:
    parts = PurePosixPath(relative).parts
    if not parts:
        return "root"
    if len(parts) >= _PACKAGE_OWNER_PARTS and parts[0] == "packages":
        return "/".join(parts[:_PACKAGE_OWNER_PARTS])
    return parts[0]


def _entry_size(root: Path, relative: str) -> int | None:
    path = root / relative
    try:
        return path.stat().st_size if path.is_file() else None
    except OSError:
        return None


def _is_git_ignored(root: Path, relative: str) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    return completed.returncode == 0


def _protected_local_paths(root: Path) -> list[dict[str, object]]:
    protected: list[dict[str, object]] = []
    identity_root = root / "identity"
    if not identity_root.is_dir():
        return protected
    for path in sorted(item for item in identity_root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        protected.append(
            {
                "path": relative,
                "classification": "USER_DATA_OR_SECRET",
                "ignored_by_git": _is_git_ignored(root, relative),
                "size_bytes": path.stat().st_size,
            }
        )
    return protected


def _probe_toolchain(name: str, command: tuple[str, ...]) -> dict[str, object]:
    if shutil.which(command[0]) is None:
        return {"name": name, "status": "DEPENDENCY_UNAVAILABLE", "version": None}
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"name": name, "status": "DEPENDENCY_UNAVAILABLE", "version": None}
    lines = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
    return {
        "name": name,
        "status": "AVAILABLE" if completed.returncode == 0 else "DEPENDENCY_UNAVAILABLE",
        "version": lines[0].strip() if lines else None,
    }


def _package_health(root: Path) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    manifest = root / "pyproject.toml"
    try:
        configuration = tomllib.loads(manifest.read_text(encoding="utf-8"))
        members = configuration["tool"]["uv"]["workspace"]["members"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        return [{"path": "pyproject.toml", "detail": f"workspace manifest invalid: {exc}"}]
    if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
        return [{"path": "pyproject.toml", "detail": "workspace members must be strings"}]
    for member in members:
        member_root = root / member
        package_name = PurePosixPath(member).name.replace("-", "_")
        required = (
            member_root / "pyproject.toml",
            member_root / "src" / package_name / "__init__.py",
            member_root / "tests",
        )
        failures.extend(
            {
                "path": path.relative_to(root).as_posix(),
                "detail": "required workspace path is missing",
            }
            for path in required
            if not path.exists()
        )
    return failures


def _sanitize_remote(url: str) -> str:
    return re.sub(r"(?<=://)[^/@\s]+@", "<redacted>@", url.strip())


def build_receipt(root: Path) -> dict[str, object]:  # noqa: PLR0914
    records = _status_records(root)
    head_path_to_hash, _head_hash_to_paths = _head_blob_paths(root)
    current_hash_to_paths = _current_blob_paths(root, records)
    entries: list[InventoryEntry] = []
    secret_hits: list[dict[str, object]] = []
    for status, relative, original_path in records:
        category, reason, counterpart = _categorize(
            root,
            status,
            relative,
            original_path,
            head_path_to_hash,
            current_hash_to_paths,
        )
        markers = _scan_secret_markers(root, relative) if status != " D" else []
        if markers:
            category = "USER_DATA_OR_SECRET"
            reason = "secret-like marker detected; value omitted"
            secret_hits.append({"path": relative, "markers": sorted(markers)})
        entries.append(
            InventoryEntry(
                status=status,
                path=relative,
                owner_area=_owner_area(relative),
                size_bytes=_entry_size(root, relative),
                category=category,
                reason=reason,
                counterpart=counterpart,
                original_path=original_path,
            )
        )
    protected = _protected_local_paths(root)
    package_failures = _package_health(root)
    errors: list[str] = []
    if secret_hits or any(not item["ignored_by_git"] for item in protected):
        errors.append(ERROR_SECRET)
    if any(entry.category == "UNKNOWN" for entry in entries):
        errors.append(ERROR_DIRTY)
    if package_failures:
        errors.append(ERROR_PACKAGE)
    digest_source = "".join(
        f"{entry.status}\0{entry.path}\0{entry.category}\0{entry.counterpart or ''}\n"
        for entry in sorted(entries, key=lambda item: (item.path, item.status))
    )
    remotes = []
    for name in str(_run_git(root, "remote")).splitlines():
        if not name.strip():
            continue
        url = str(_run_git(root, "remote", "get-url", name.strip())).strip()
        remotes.append({"name": name.strip(), "url": _sanitize_remote(url)})
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "repository_root": str(root),
        "head": str(_run_git(root, "rev-parse", "HEAD")).strip(),
        "branch": str(_run_git(root, "branch", "--show-current")).strip(),
        "remotes": remotes,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "toolchains": [_probe_toolchain(name, command) for name, command in TOOLCHAINS],
        "commands": [
            "git status --porcelain=v1 -z --untracked-files=all",
            "git ls-tree -r -z HEAD",
            "git check-ignore -q -- <path>",
        ],
        "status_counts": dict(sorted(Counter(item.status for item in entries).items())),
        "category_counts": dict(sorted(Counter(item.category for item in entries).items())),
        "path_digest_sha256": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "errors": errors,
        "package_failures": package_failures,
        "secret_scan": {
            "status": "CLEAR" if not secret_hits else ERROR_SECRET,
            "hits": secret_hits,
            "values_included": False,
        },
        "protected_local_paths": protected,
        "entries": [asdict(entry) for entry in entries],
    }


def _write_receipt(path: Path, receipt: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--json-out",
        type=Path,
        help=("Receipt path; defaults to outputs/reports/repository-health/inventory.json"),
    )
    parser.add_argument(
        "--fail-on-risk",
        action="store_true",
        help="Return exit code 2 when a structured repository-health error exists.",
    )
    return parser.parse_args()


def _execute(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    root = discover_root(args.root)
    receipt = build_receipt(root)
    output = args.json_out or Path("outputs/reports/repository-health/inventory.json")
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    _write_receipt(output, receipt)
    return receipt, output


def main() -> int:
    args = _arguments()
    try:
        receipt, output = _execute(args)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        print(
            json.dumps({"status": "FAILED", "code": "REPOSITORY_AUDIT_FAILED", "error": str(exc)}),
            file=sys.stderr,
        )
        return 3
    summary = {
        "status": "PASS" if not receipt["errors"] else "RISK_FOUND",
        "errors": receipt["errors"],
        "status_counts": receipt["status_counts"],
        "category_counts": receipt["category_counts"],
        "path_digest_sha256": receipt["path_digest_sha256"],
        "receipt": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 2 if args.fail_on_risk and receipt["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
