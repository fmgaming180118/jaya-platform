import pystray
from PIL import Image
import threading
import subprocess
import os
import sys
import time
from pathlib import Path

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
ICON_PATH = PROJECT_ROOT / "logo.ico"
BACKEND_SCRIPT = PROJECT_ROOT / "src" / "network" / "research_api.py"
UI_DIR = PROJECT_ROOT / "ui"

backend_process = None
ui_process = None

def start_backend(icon, item):
    global backend_process
    if backend_process and backend_process.poll() is None:
        print("Backend already running.")
        return

    print("Starting Backend...")
    # Use python from env or system
    python_cmd = sys.executable
    backend_process = subprocess.Popen([python_cmd, str(BACKEND_SCRIPT)], cwd=str(PROJECT_ROOT))
    
    icon.notify("Backend Started", "JAYA Research")

def start_ui(icon, item):
    global ui_process
    if ui_process and ui_process.poll() is None:
        print("UI already running.")
        return

    print("Starting UI...")
    # Using npm run electron:dev for dev mode
    # In production, this would launch the built executable
    cmd = "npm run electron:dev"
    ui_process = subprocess.Popen(cmd, cwd=str(UI_DIR), shell=True)
    
    icon.notify("Dashboard Opened", "JAYA Research")

def stop_all(icon, item):
    global backend_process, ui_process
    
    if backend_process:
        backend_process.terminate()
        backend_process = None
        
    if ui_process:
        # Killing shell process might be tricky on windows, but terminate works for basic handle
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(ui_process.pid)])
        ui_process = None
        
    icon.notify("All Services Stopped", "JAYA Research")

def exit_app(icon, item):
    stop_all(icon, item)
    icon.stop()

def setup(icon):
    icon.visible = True
    icon.notify("Ready to Serve", "JAYA Research Launcher")

def main():
    if not ICON_PATH.exists():
        print(f"Icon not found at {ICON_PATH}")
        return

    image = Image.open(ICON_PATH)
    
    menu = pystray.Menu(
        pystray.MenuItem("Start Backend", start_backend),
        pystray.MenuItem("Open Dashboard", start_ui),
        pystray.MenuItem("Stop All", stop_all),
        pystray.MenuItem("Exit", exit_app)
    )

    icon = pystray.Icon("JAYA Research", image, "JAYA Research", menu)
    icon.run(setup)

if __name__ == "__main__":
    main()
