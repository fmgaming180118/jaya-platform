
import os
import importlib.util
import inspect
import logging
from typing import Dict, List, Any
from pathlib import Path
from src.tools.base import BaseTool

logger = logging.getLogger("ToolRegistry")

class ToolRegistry:
    def __init__(self, tools_dir: str = None):
        self.tools: Dict[str, BaseTool] = {}
        if tools_dir:
            self.scan_directory(tools_dir)
        else:
            # Default to current directory's parent (src/tools)
            current_dir = Path(__file__).parent
            self.scan_directory(str(current_dir))

    def scan_directory(self, path: str):
        """
        Recursively scans the directory for python files containing BaseTool subclasses.
        """
        path_obj = Path(path)
        if not path_obj.exists():
            logger.warning(f"Tools directory not found: {path}")
            return

        logger.info(f"Scanning for tools in: {path}")
        
        for file_path in path_obj.rglob("*.py"):
            if file_path.name == "base.py" or file_path.name == "registry.py" or file_path.name.startswith("__"):
                continue
                
            self._load_tool_from_file(file_path)

    def _load_tool_from_file(self, file_path: Path):
        try:
            # Dynamic Import
            module_name = file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find BaseTool subclasses
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                    try:
                        tool_instance = obj()
                        self.register_tool(tool_instance)
                    except Exception as e:
                        logger.error(f"Failed to instantiate tool {name} from {file_path}: {e}")

        except Exception as e:
            logger.error(f"Error loading module {file_path}: {e}")

    def register_tool(self, tool: BaseTool):
        if tool.name in self.tools:
            logger.warning(f"Duplicate tool name detected: {tool.name}. Overwriting.")
        self.tools[tool.name] = tool
        logger.info(f"Registered Tool: {tool.name}")

    def get_tool(self, name: str) -> BaseTool:
        return self.tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [t.to_schema() for t in self.tools.values()]

    def execute(self, tool_name: str, **kwargs) -> Any:
        tool = self.get_tool(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found."
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            return f"Error executing {tool_name}: {str(e)}"
