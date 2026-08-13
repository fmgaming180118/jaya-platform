# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportConstantRedefinition=false

import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Tuple, Optional, cast

try:
    import psutil  # type: ignore[import]
    import pystray  # type: ignore[import]
    from PIL import Image, ImageDraw, ImageFont  # type: ignore[import]
except Exception as e:
    # If tray deps are missing, raise a clear error so user can install requirements.
    raise RuntimeError(
        "tray_launcher: required packages missing (pystray, Pillow, psutil).\n"
        "Install with: pip install -r requirements.txt"
    ) from e

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
UI_DIR = PROJECT_ROOT / "ui"
API_SCRIPT = PROJECT_ROOT / "src" / "network" / "research_api.py"

LOG_DIR.mkdir(parents=True, exist_ok=True)

# Windows-specific flag to hide child console windows
# windows-specific flag to hide child console windows
if sys.platform == "win32":
    CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)
else:
    CREATE_NO_WINDOW: int = 0


def _make_icon_image(
    size: int = 64,
    bg: Tuple[int, int, int] = (18, 48, 76),
    fg: Tuple[int, int, int] = (255, 255, 255),
) -> Any:
    img = Image.new("RGBA", (size, size), bg)
    draw: Any = ImageDraw.Draw(img)
    # simple rounded rectangle + letter 'J'
    r = size // 8
    draw.rounded_rectangle((4, 4, size - 4, size - 4), radius=r, fill=bg)  # type: ignore[attr-defined]
    # draw a large J
    try:
        f = ImageFont.load_default()
        w, h = draw.textsize("J", font=f)  # type: ignore[attr-defined]
        draw.text(cast(Tuple[int, int], ((size - w) / 2, (size - h) / 2 - 6)), "J", font=f, fill=fg)  # type: ignore[attr-defined]
    except Exception:
        draw.text(cast(Tuple[int, int], (size // 3, size // 6)), "J", fill=fg)  # type: ignore[attr-defined]
    return img


class TrayController:
    def __init__(self):
        self.backend_proc = None
        self.ui_proc = None
        # type hints for pystray objects are unavailable
        self.icon: Any = pystray.Icon(
            "jaya_research",
            _make_icon_image(),
            "Jaya Research",
            menu=pystray.Menu(
                pystray.MenuItem("Start Backend", cast(Any, self.start_backend)),
                pystray.MenuItem("Stop Backend", cast(Any, self.stop_backend)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Start UI", cast(Any, self.start_ui)),
                pystray.MenuItem("Stop UI", cast(Any, self.stop_ui)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open UI in browser", cast(Any, self.open_ui)),
                pystray.MenuItem("Open API docs", cast(Any, self.open_api)),
                pystray.MenuItem("Open logs folder", cast(Any, self.open_logs)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", cast(Any, self.exit)),
            ),
        )

    def _log_path(self, name: str) -> Path:
        return LOG_DIR / f"{name}.log"

    def _start_process(self, args: list[str], cwd: Optional[str] = None, log_name: Optional[str] = None) -> Any:
        if log_name:
            logfile = open(self._log_path(log_name), "a", encoding="utf-8", errors="ignore")
        else:
            logfile = open(os.devnull, "w")

        try:
            proc = subprocess.Popen(
                args,
                cwd=cwd or str(PROJECT_ROOT),
                stdout=logfile,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
                shell=False,
            )
        except Exception as exc:
            logfs.write(f"Failed to start: {exc}\n")
            logfile.flush()
            logfile.close()
            raise

        # detach a watcher thread to close the logfile when process exits
        def _watch():
            proc.wait()
            try:
                logfile.close()
            except Exception:
                pass

        threading.Thread(target=_watch, daemon=True).start()
        return proc

    def start_backend(self, _=None) -> None:
        if self.backend_proc and self.backend_proc.poll() is None:
            return
        if not API_SCRIPT.exists():
            self._notify("API script not found: src/network/research_api.py")
            return
        args = [sys.executable, str(API_SCRIPT)]
        self.backend_proc = self._start_process(args, cwd=str(PROJECT_ROOT), log_name="api")
        self._notify("Research API starting (logs/api.log)")

    def stop_backend(self, _=None) -> None:
        if not self.backend_proc:
            return
        try:
            if self.backend_proc.poll() is None:
                self.backend_proc.terminate()
                try:
                    self.backend_proc.wait(timeout=5)
                except Exception:
                    # force-kill process tree
                    try:
                        p = psutil.Process(self.backend_proc.pid)
                        for ch in p.children(recursive=True):
                            ch.kill()
                        p.kill()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.backend_proc = None
            self._notify("Research API stopped")

    def start_ui(self, _=None) -> None:
        if self.ui_proc and self.ui_proc.poll() is None:
            return
        if not (PROJECT_ROOT / "ui").exists():
            self._notify("UI folder not found")
            return
        npm = shutil_which("npm")
        if not npm:
            self._notify("npm not found in PATH — cannot start UI")
            return
        args = [npm, "run", "dev"]
        self.ui_proc = self._start_process(args, cwd=str(UI_DIR), log_name="ui")
        self._notify("UI starting (logs/ui.log)")

    def stop_ui(self, _=None) -> None:
        if not self.ui_proc:
            return
        try:
            if self.ui_proc.poll() is None:
                self.ui_proc.terminate()
                try:
                    self.ui_proc.wait(timeout=5)
                except Exception:
                    try:
                        p = psutil.Process(self.ui_proc.pid)
                        for ch in p.children(recursive=True):
                            ch.kill()
                        p.kill()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.ui_proc = None
            self._notify("UI stopped")

    def open_ui(self, _=None) -> None:
        webbrowser.open("http://localhost:5173")

    def open_api(self, _=None) -> None:
        webbrowser.open("http://localhost:8000/docs")

    def open_logs(self, _=None) -> None:
        try:
            if LOG_DIR.exists():
                os.startfile(str(LOG_DIR))
            else:
                self._notify("No logs folder yet")
        except Exception:
            self._notify("Failed to open logs folder")

    def exit(self, _=None) -> None:
        # stop processes and remove icon
        try:
            self.stop_ui()
            self.stop_backend()
        finally:
            try:
                self.icon.stop()
            except Exception:
                pass

    def _notify(self, text: str) -> None:
        try:
            # pystray supports simple notifications on Windows backends
            self.icon.notify(text)
        except Exception:
            # fallback to writing to api log
            with open(self._log_path("tray"), "a", encoding="utf-8") as wf:
                wf.write(f"{time.asctime()}: {text}\n")

    def run(self) -> None:
        self.icon.run()


def shutil_which(cmd: str):
    # simple wrapper for shutil.which but avoids importing shutil in top-level
    try:
        import shutil

        return shutil.which(cmd)
    except Exception:
        return None


def main() -> None:
    # write startup trace to logs for debugging startup failures
    with open(LOG_DIR / "tray.log", "a", encoding="utf-8") as wf:
        wf.write(f"{time.asctime()}: tray_launcher starting (pid={os.getpid()})\n")

    c = TrayController()
    # optionally auto-start backend/UI on tray launch — keep disabled by default
    # c.start_backend()
    # c.start_ui()
    c.run()


if __name__ == "__main__":
    main()
