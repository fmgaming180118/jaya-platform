import json
import os
import re
import sys
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path.cwd().resolve()

ROOT_FILE_ALLOWLIST = {
    ".env",
    ".gitignore",
    "readme.md",
    "agents.md",
    "jaya.jay",
    "rag_vault.db",
    "jaya_core_mode.bat",
    "jaya_research_mode.bat",
}

WRITE_TOOL_MARKERS = (
    "apply_patch",
    "create_file",
    "create_directory",
    "edit_notebook_file",
    "mcp_github_create_or_update_file",
    "mcp_github_push_files",
    "mcp_io_github_git_delete_file",
)

PATCH_FILE_HEADER = re.compile(r"^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s+(.+?)\s*$")

CORE_IMPORT_RESEARCH_PATTERN = re.compile(r"^\s*(?:from|import)\s+JAYA_RESEARCH\b|\bJAYA_RESEARCH\.", re.IGNORECASE)
RESEARCH_IMPORT_CORE_PATTERN = re.compile(r"^\s*(?:from|import)\s+JAYA_CORE\b|\bJAYA_CORE\.", re.IGNORECASE)


LOOP_PATTERNS = [
    re.compile(r"(?:^|\s)(?:python(?:3)?\s+)?(?:jaya_research[\\/])?src[\\/]discovery\.py\b[^\n\r]*\s--forever\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?:python(?:3)?\s+)?(?:jaya_research[\\/])?src[\\/]jit_discovery\.py\b[^\n\r]*\s--forever\b", re.IGNORECASE),
]

APPROVAL_PATTERNS = [
    re.compile(r"allow\s+self[- ]mutation", re.IGNORECASE),
    re.compile(r"approve\s+self[- ]mutation", re.IGNORECASE),
    re.compile(r"self[- ]mutation\s+approved", re.IGNORECASE),
    re.compile(r"izinkan\s+self[- ]mutation", re.IGNORECASE),
    re.compile(r"setujui\s+self[- ]mutation", re.IGNORECASE),
    re.compile(r"\[allow\s+self[- ]mutation\]", re.IGNORECASE),
]

STRUCTURE_OVERRIDE_PATTERNS = [
    re.compile(r"allow\s+root\s+write", re.IGNORECASE),
    re.compile(r"allow\s+cross[- ]scope", re.IGNORECASE),
    re.compile(r"override\s+structure", re.IGNORECASE),
    re.compile(r"izinkan\s+root\s+write", re.IGNORECASE),
    re.compile(r"izinkan\s+cross[- ]scope", re.IGNORECASE),
]


def _emit(permission: str, reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission,
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload))


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass
    return {}


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("toolInput")
    if not isinstance(tool_input, dict):
        return {}
    return tool_input


def _tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "tool"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _build_command_text(payload: dict[str, Any]) -> str:
    tool_input = _tool_input(payload)

    command = tool_input.get("command") or payload.get("command") or ""
    args = tool_input.get("args") or payload.get("args") or ""

    if isinstance(args, list):
        args_text = " ".join(str(item) for item in args)
    else:
        args_text = str(args)

    return f"{command} {args_text}".strip()


def _is_loop_command(command_text: str) -> bool:
    if not command_text:
        return False
    return any(pattern.search(command_text) for pattern in LOOP_PATTERNS)


def _has_approval(payload_text: str, command_text: str) -> bool:
    haystack = f"{payload_text}\n{command_text}"
    return any(pattern.search(haystack) for pattern in APPROVAL_PATTERNS)


def _has_structure_override(payload_text: str, command_text: str) -> bool:
    haystack = f"{payload_text}\n{command_text}"
    return any(pattern.search(haystack) for pattern in STRUCTURE_OVERRIDE_PATTERNS)


def _normalize_path(raw_path: str) -> str:
    path = raw_path.strip().strip('"').strip("'")
    if not path:
        return ""

    path = path.replace("\\", "/")

    if path.startswith("file://"):
        path = path[7:]

    as_path = Path(path)
    if as_path.is_absolute():
        try:
            rel = as_path.resolve().relative_to(WORKSPACE_ROOT)
            path = str(rel)
        except Exception:
            try:
                path = os.path.relpath(str(as_path), str(WORKSPACE_ROOT))
            except Exception:
                pass

    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _extract_paths_from_patch(patch_text: str) -> set[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        match = PATCH_FILE_HEADER.match(line.strip())
        if match:
            normalized = _normalize_path(match.group(1))
            if normalized:
                paths.add(normalized)
    return paths


def _extract_paths(payload: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    tool_input = _tool_input(payload)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_l = str(key).lower()
                if isinstance(value, str):
                    if "path" in key_l:
                        normalized = _normalize_path(value)
                        if normalized:
                            paths.add(normalized)
                    if key_l in {"input", "patch"} and "*** Begin Patch" in value:
                        paths.update(_extract_paths_from_patch(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tool_input)

    return {path for path in paths if path}


def _is_write_tool(payload: dict[str, Any], payload_text: str) -> bool:
    tool_name_l = _tool_name(payload).lower()
    if any(marker in tool_name_l for marker in WRITE_TOOL_MARKERS):
        return True
    return "*** Begin Patch" in payload_text


def _check_path_policy(paths: set[str]) -> str | None:
    for rel_path in sorted(paths):
        lower = rel_path.lower()

        if lower.startswith("../"):
            return f"Writing outside workspace is blocked: {rel_path}"

        if lower.startswith("tests/"):
            return "Root tests/ is blocked. Put tests in JAYA_CORE/tests or JAYA_RESEARCH/tests."

        if "/" not in rel_path:
            if lower not in ROOT_FILE_ALLOWLIST:
                return (
                    f"Root file write blocked for {rel_path}. "
                    "Place files inside JAYA_CORE/, JAYA_RESEARCH/, docs/, or .github/."
                )

        if lower.endswith(".md"):
            if "/" not in rel_path and lower not in {"readme.md", "agents.md"}:
                return f"Root markdown write blocked for {rel_path}. Use docs/ for cross-cutting docs."

            if lower.startswith("jaya_core/") and lower != "jaya_core/readme.md" and not lower.startswith("jaya_core/docs/"):
                return f"Core markdown must be in JAYA_CORE/docs/: {rel_path}"

            if lower.startswith("jaya_research/") and lower != "jaya_research/readme.md" and not lower.startswith("jaya_research/docs/"):
                return f"Research markdown must be in JAYA_RESEARCH/docs/: {rel_path}"

    return None


def _extract_python_updates(payload: dict[str, Any]) -> list[tuple[str, str]]:
    updates: list[tuple[str, str]] = []
    tool_input = _tool_input(payload)

    patch_text = tool_input.get("input")
    if isinstance(patch_text, str) and "*** Begin Patch" in patch_text:
        current_path = ""
        for line in patch_text.splitlines():
            header = PATCH_FILE_HEADER.match(line.strip())
            if header:
                current_path = _normalize_path(header.group(1))
                continue

            if line.startswith("*** End Patch"):
                current_path = ""
                continue

            if not current_path.lower().endswith(".py"):
                continue

            if line.startswith("+") and not line.startswith("+++"):
                updates.append((current_path, line[1:]))

    file_path_raw = tool_input.get("filePath") or tool_input.get("filepath") or tool_input.get("path")
    content = tool_input.get("content")
    if isinstance(file_path_raw, str) and isinstance(content, str):
        file_path = _normalize_path(file_path_raw)
        if file_path.lower().endswith(".py"):
            for line in content.splitlines():
                updates.append((file_path, line))

    return updates


def _check_cross_scope_imports(python_updates: list[tuple[str, str]]) -> str | None:
    for rel_path, line in python_updates:
        lower_path = rel_path.lower()
        if lower_path.startswith("jaya_core/") and CORE_IMPORT_RESEARCH_PATTERN.search(line):
            return (
                f"Cross-domain import blocked in {rel_path}: "
                "JAYA_CORE must not import JAYA_RESEARCH directly."
            )
        if lower_path.startswith("jaya_research/") and RESEARCH_IMPORT_CORE_PATTERN.search(line):
            return (
                f"Cross-domain import blocked in {rel_path}: "
                "JAYA_RESEARCH must not import JAYA_CORE directly."
            )
    return None


def main() -> None:
    payload = _read_stdin_json()
    command_text = _build_command_text(payload)

    payload_text = ""
    if payload:
        payload_text = json.dumps(payload, ensure_ascii=False)

    is_target = _is_loop_command(command_text)
    approved = _has_approval(payload_text, command_text)

    if is_target and not approved:
        _emit(
            "deny",
            "Blocked long-running self-mutation loop. Add explicit approval text in prompt, for example: ALLOW SELF-MUTATION.",
        )
        return

    if _is_write_tool(payload, payload_text):
        structure_override = _has_structure_override(payload_text, command_text)

        paths = _extract_paths(payload)
        path_violation = _check_path_policy(paths)
        if path_violation and not structure_override:
            _emit("deny", path_violation)
            return

        python_updates = _extract_python_updates(payload)
        import_violation = _check_cross_scope_imports(python_updates)
        if import_violation and not structure_override:
            _emit("deny", import_violation)
            return

    _emit("allow", "ok")


if __name__ == "__main__":
    main()
