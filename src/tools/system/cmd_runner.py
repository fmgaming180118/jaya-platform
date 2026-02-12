
import subprocess
import platform
import logging
from pydantic import BaseModel, Field
from src.tools.base import BaseTool

logger = logging.getLogger("Tool:CmdRunner")

class CommandInput(BaseModel):
    command: str = Field(..., description="The shell command to execute (e.g., 'ping google.com', 'dir').")

class CmdRunnerTool(BaseTool):
    @property
    def name(self) -> str:
        return "system_run_command"

    @property
    def description(self) -> str:
        return "Executes a shell command on the host system (PowerShell on Windows, Bash on Linux). Use with caution."

    @property
    def parameters(self):
        return CommandInput

    def execute(self, command: str) -> str:
        logger.info(f"Executing: {command}")
        try:
            os_type = platform.system()
            if os_type == "Windows":
                 completed = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, shell=True)
            else:
                 completed = subprocess.run(command, capture_output=True, text=True, shell=True)
            
            if completed.returncode != 0:
                return f"Error: {completed.stderr.strip()}"
            return completed.stdout.strip()
        except Exception as e:
            return f"Execution Failed: {str(e)}"
