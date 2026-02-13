
import os
import subprocess
import psutil
import platform
from AppOpener import open as app_opener
from AppOpener import close as app_closer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BrainSystem")

class SystemController:
    def __init__(self):
        self.os_type = platform.system()
    
    def run_command(self, command):
        """
        Executes a shell command and returns the output.
        WARNING: High security risk. 
        """
        logger.info(f"Executing System Command: {command}")
        try:
            # Use PowerShell on Windows for better capability
            if self.os_type == "Windows":
                 completed = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, shell=True)
            else:
                 completed = subprocess.run(command, capture_output=True, text=True, shell=True)
            
            if completed.returncode != 0:
                return f"Error: {completed.stderr.strip()}"
            return completed.stdout.strip()
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return f"Execution Failed: {str(e)}"

    def open_app(self, app_name):
        """
        Opens an application using AppOpener.
        """
        logger.info(f"Opening App: {app_name}")
        try:
            # AppOpener is simple but sometimes slow on first run (indexing)
            app_opener(app_name, match_closest=True, output=False)
            return f"Opening {app_name}..."
        except Exception as e:
            return f"Failed to open {app_name}: {e}"

    def close_app(self, app_name):
        """Closes an application."""
        logger.info(f"Closing App: {app_name}")
        try:
            app_closer(app_name, match_closest=True, output=False)
            return f"Closing {app_name}..."
        except Exception as e:
            return f"Failed to close {app_name}: {e}"

    def open_folder(self, path):
        """
        Opens a folder in the file explorer.
        """
        logger.info(f"Opening Folder: {path}")
        try:
            if self.os_type == "Windows":
                os.startfile(path)
            elif self.os_type == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return f"Opened {path}"
        except Exception as e:
            return f"Could not open path: {e}"

    def get_system_status(self):
        """
        Returns a summary of system resources (CPU, RAM, Net).
        "Melihat data yang mengalir"
        """
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            net_io = psutil.net_io_counters()
            
            status = (
                f"CPU Usage: {cpu_usage}%\n"
                f"Memory: {memory.percent}% used ({round(memory.used/1e9, 2)} GB / {round(memory.total/1e9, 2)} GB)\n"
                f"Network Sent: {round(net_io.bytes_sent/1e6, 2)} MB\n"
                f"Network Recv: {round(net_io.bytes_recv/1e6, 2)} MB"
            )
            return status
        except Exception as e:
            return f"Error reading system status: {e}"

    def get_running_apps(self, limit=5):
        """
        Returns top running processes by memory usage.
        "Melihat aplikasi"
        """
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort by memory usage
        processes.sort(key=lambda p: p['memory_percent'] or 0, reverse=True)
        top_apps = processes[:limit]
        
        report = "Top Apps by Memory:\n"
        for p in top_apps:
            report += f"- {p['name']} ({round(p['memory_percent'], 1)}%)\n"
        
        return report

if __name__ == "__main__":
    # Test
    brain = SystemController()
    print(brain.get_system_status())
    print(brain.get_running_apps())
