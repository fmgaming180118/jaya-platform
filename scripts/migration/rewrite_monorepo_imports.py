#!/usr/bin/env python3
"""Rewrite legacy JAYA imports after the src-layout monorepo migration.

This migration is intentionally narrow: it only rewrites Python import syntax
and import statements embedded in command strings. It does not rename domain
labels, environment variables, persisted producer names, or user-facing text.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Scope:
    root: Path
    legacy_src_owner: str | None


DOMAIN_IMPORTS = {
    "JAYA_CORE.src": "jaya_core",
    "JAYA_AGENT.src": "jaya_agent",
    "JAYA_OS.src.jaya_os": "jaya_os",
    "JAYA_OS.src": "jaya_os",
    "JAYA_RESEARCH.src": "jaya_research",
}

AGENT_LOCAL_IMPORTS = (
    "contracts",
    "interfaces",
    "memory",
    "multiagent",
    "runtime",
    "security",
    "skills",
)

RESEARCH_LOCAL_IMPORTS = (
    "academic",
    "agentic_research",
    "auto_finetune",
    "benchmark",
    "brain",
    "config",
    "discovery",
    "digital_twin",
    "edge",
    "engine",
    "evolution",
    "graphrag",
    "immune_system",
    "integrity",
    "introspection",
    "jit",
    "memory",
    "network",
    "optimizer",
    "provider",
    "research",
    "safeguard",
    "sandbox",
    "synthesize",
    "teacher",
    "tokenizer",
    "tools",
    "training",
    "voice_agent",
)

IGNORED_PARTS = {
    ".git",
    ".venv-research",
    "__pycache__",
    "build",
    "data",
    "dist",
    "llama.cpp",
    "node_modules",
    "outputs",
}


def _replace_import_prefix(text: str, old: str, new: str) -> str:
    pattern = re.compile(
        rf"(?m)^(?P<indent>\s*)(?P<verb>from|import)\s+{re.escape(old)}(?=\.|\s|$)"
    )
    rewritten = pattern.sub(
        lambda match: (
            f"{match.group('indent')}{match.group('verb')} {new}"
        ),
        text,
    )
    for quote in ('"', "'"):
        rewritten = rewritten.replace(
            f"{quote}from {old}.",
            f"{quote}from {new}.",
        )
        rewritten = rewritten.replace(
            f"{quote}import {old}.",
            f"{quote}import {new}.",
        )
    return rewritten


def rewrite_file(path: Path, legacy_src_owner: str | None) -> bool:
    original_bytes = path.read_bytes()
    try:
        text = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return False

    rewritten = text
    for old, new in DOMAIN_IMPORTS.items():
        rewritten = _replace_import_prefix(rewritten, old, new)
    if legacy_src_owner is not None:
        rewritten = _replace_import_prefix(rewritten, "src", legacy_src_owner)

    normalized = path.as_posix()
    if "/packages/jaya-agent/" in normalized:
        for module in AGENT_LOCAL_IMPORTS:
            rewritten = _replace_import_prefix(
                rewritten, module, f"jaya_agent.{module}"
            )
    if "/packages/jaya-research/" in normalized:
        for module in RESEARCH_LOCAL_IMPORTS:
            rewritten = _replace_import_prefix(
                rewritten, module, f"jaya_research.{module}"
            )
    if "/packages/jaya-core/" in normalized and any(
        part in path.parts for part in ("scripts", "tests")
    ):
        rewritten = rewritten.replace(
            "Path(__file__).resolve().parent.parent.parent",
            "Path(__file__).resolve().parents[3]",
        )
        rewritten = rewritten.replace(
            'repo_root / "JAYA_CORE"',
            'repo_root / "packages" / "jaya-core" / "src"',
        )
    if "/packages/jaya-research/" in normalized and any(
        part in path.parts for part in ("scripts", "tests")
    ):
        rewritten = rewritten.replace(
            "Path(__file__).resolve().parent.parent.parent",
            "Path(__file__).resolve().parents[3]",
        )
        rewritten = rewritten.replace(
            'repo_root / "JAYA_RESEARCH"',
            'repo_root / "packages" / "jaya-research" / "src"',
        )

    rewritten_bytes = rewritten.encode("utf-8")
    if rewritten_bytes == original_bytes:
        return False
    path.write_bytes(rewritten_bytes)
    return True


def iter_python_files(scope: Scope) -> list[Path]:
    if not scope.root.exists():
        return []
    return sorted(
        path
        for path in scope.root.rglob("*.py")
        if not any(part in IGNORED_PARTS for part in path.parts)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    scopes = (
        Scope(root / "packages" / "jaya-core", "jaya_core"),
        Scope(root / "packages" / "jaya-agent", None),
        Scope(root / "packages" / "jaya-os", None),
        Scope(root / "packages" / "jaya-research", "jaya_research"),
        Scope(root / "scripts", "jaya_core"),
        Scope(root / "tests", None),
    )

    changed: list[Path] = []
    for scope in scopes:
        for path in iter_python_files(scope):
            owner = scope.legacy_src_owner
            if "packages" in path.parts and "jaya-os" in path.parts:
                owner = "jaya_core"
            if rewrite_file(path, owner):
                changed.append(path.relative_to(root))

    print(f"rewritten_files={len(changed)}")
    for path in changed:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
