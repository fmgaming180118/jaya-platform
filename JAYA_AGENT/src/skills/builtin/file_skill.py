"""
Built-in File Operations Skill for JAYA_AGENT.
Provides safe file reading, writing, and listing operations.
"""

import os
from pathlib import Path
from typing import Dict, Any
from ..base_skill import Skill, skill_action


class FileOperationsSkill(Skill):
    name = "file_skill"
    description = "Safe file operations skill"

    @skill_action("read_file", "Reads text content of a file", params={"filepath": "str"})
    def read_file(self, filepath: str) -> str:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(5000)  # Max 5000 chars read limit

    @skill_action("write_file", "Writes text content to a file safely", params={"filepath": "str", "content": "str"})
    def write_file(self, filepath: str, content: str) -> str:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} chars to {filepath}"

    @skill_action("list_directory", "Lists contents of a directory", params={"dirpath": "str"})
    def list_directory(self, dirpath: str) -> str:
        path = Path(dirpath)
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {dirpath}")
        items = os.listdir(path)
        return f"Contents of {dirpath}: {', '.join(items[:20])}"
