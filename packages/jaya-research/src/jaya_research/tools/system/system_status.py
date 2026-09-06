
import psutil
from pydantic import BaseModel
from jaya_research.tools.base import BaseTool

class SystemStatusInput(BaseModel):
    pass # No input needed

class SystemStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "system_get_status"

    @property
    def description(self) -> str:
        return "Returns current CPU, Memory, and Network usage statistics."

    @property
    def parameters(self):
        return SystemStatusInput

    def execute(self) -> str:
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            net_io = psutil.net_io_counters()
            
            return (
                f"CPU Usage: {cpu_usage}%\n"
                f"Memory: {memory.percent}% used ({round(memory.used/1e9, 2)} GB / {round(memory.total/1e9, 2)} GB)\n"
                f"Network Sent: {round(net_io.bytes_sent/1e6, 2)} MB\n"
                f"Network Recv: {round(net_io.bytes_recv/1e6, 2)} MB"
            )
        except Exception as e:
            return f"Error reading system status: {e}"
