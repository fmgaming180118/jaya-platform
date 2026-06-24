"""
JAYA Research — Autorun Launcher with Watchdog
Satu klik, jalan terus. Ctrl+C untuk stop.
- Status bar compact (tidak scroll terus)
- Notifikasi error langsung di CLI
"""
import sys
import os
import subprocess
import threading
import time
import signal
import shutil
from pathlib import Path
from datetime import datetime
from collections import deque

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Paths ───────────────────────────────────────────────
ROOT          = Path(__file__).resolve().parent
VENV_PYTHON   = ROOT / ".venv312" / "Scripts" / "python.exe"
BACKEND_SCRIPT = ROOT / "src" / "network" / "research_api.py"
UI_DIR        = ROOT / "ui"
LOG_DIR       = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ─── ANSI ─────────────────────────────────────────────────
R = "\033[0m"; BOLD = "\033[1m"; CLR = "\033[2K\r"
GREEN  = "\033[92m"; RED   = "\033[91m"
YELLOW = "\033[93m"; CYAN  = "\033[96m"
GRAY   = "\033[90m"; MAG   = "\033[95m"

# ─── State ────────────────────────────────────────────────
_running   = True
_procs     = {}        # name -> Popen
_restarts  = {}        # name -> int
_statuses  = {}        # name -> str  (RUNNING|STOPPED|ERROR)
_errors    = deque(maxlen=5)   # buffer notifikasi error terbaru
_lock      = threading.Lock()

# ─── Helpers ──────────────────────────────────────────────
def _ts():
    return datetime.now().strftime("%H:%M:%S")

def _notify_error(label: str, msg: str):
    """Simpan error ke buffer — ditampilkan di status bar."""
    with _lock:
        _errors.append(f"{_ts()} [{label}] {msg[:80]}")

def _banner():
    w = shutil.get_terminal_size((80, 20)).columns
    line = "─" * w
    print(f"{CYAN}{BOLD}")
    print(line)
    print("  JAYA RESEARCH — AUTORUN LAUNCHER  ".center(w))
    print("  Backend · UI · DigitalTwin Loop  ".center(w))
    print(line)
    print(f"  API : http://localhost:8000       UI : http://localhost:5173")
    print(f"  Docs: http://localhost:8000/docs  Stop: Ctrl+C")
    print(line)
    print(f"{R}")

# ─── Status board elements ─────────────────────────────────
_status_lines = 0   # berapa baris status yang sudah ditulis
_spinner_idx = 0
_spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

def _get_last_thought():
    import json
    path = ROOT / "data" / "evolution_memory.json"
    if not path.exists():
        return "Initializing consciousness...", "curious"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            thoughts = data.get("thoughts", [])
            if thoughts:
                last = thoughts[-1]
                content = last.get("content", "Thinking...")
                mood = last.get("mood", "curious")
                return content, mood
    except Exception:
        pass
    return "Consolidating neural patterns...", "reflective"

def _get_last_logs():
    path = LOG_DIR / "backend.log"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            filtered = []
            for line in reversed(lines):
                line = line.strip()
                if line and not line.startswith("="):
                    # Saring log request HTTP yang berisik agar layar fokus
                    if "GET / " in line or "GET /workspaces " in line:
                        continue
                    filtered.append(line[:100])
                    if len(filtered) == 3:
                        break
            return list(reversed(filtered))
    except Exception:
        pass
    return []

def _draw_status():
    """Gambar ulang status bar di tempat yang sama (overwrite)."""
    global _status_lines, _spinner_idx
    w = shutil.get_terminal_size((80, 20)).columns
    sp = _spinners[_spinner_idx]
    _spinner_idx = (_spinner_idx + 1) % len(_spinners)

    lines = []
    # ── Header
    lines.append(f"{GRAY}{'─'*w}{R}")

    # ── Per-proses status
    for name in ("BACKEND", "UI"):
        st  = _statuses.get(name, "INIT")
        rs  = _restarts.get(name, 0)
        col = GREEN if st == "RUNNING" else (YELLOW if st == "INIT" else RED)
        icon = "●" if st == "RUNNING" else ("○" if st == "INIT" else "✖")
        lines.append(
            f" {col}{BOLD}{icon} {name:<8}{R}"
            f"  Status: {col}{st:<8}{R}"
            f"  Restarts: {YELLOW}{rs}{R}"
        )

    # ── JAYA'S MIND (DigitalTwin state)
    thought, mood = _get_last_thought()
    mood_colors = {
        "proud": GREEN, "excited": GREEN, "satisfied": GREEN,
        "reflective": CYAN, "curious": CYAN, "focused": CYAN,
        "determined": YELLOW, "concerned": YELLOW, "tired": YELLOW,
        "pained": RED, "frustrated": RED
    }
    m_color = mood_colors.get(mood.lower(), CYAN)
    lines.append(f"{GRAY}{'─'*w}{R}")
    lines.append(f" 🤖 {MAG}{BOLD}JAYA'S CONSCIOUS MIND:{R}")
    lines.append(f"   Mood   : {m_color}{mood.upper()}{R}")
    lines.append(f"   Thought: {thought}")

    # ── Last Logs from Backend
    last_logs = _get_last_logs()
    if last_logs:
        lines.append(f"{GRAY}{'─'*w}{R}")
        lines.append(f" 📋 {CYAN}{BOLD}LATEST BACKEND LOGS:{R}")
        for log in last_logs:
            lines.append(f"   {GRAY}{log}{R}")

    # ── Error buffer (maks 3 baris terakhir)
    with _lock:
        errs = list(_errors)
    if errs:
        lines.append(f"{GRAY}{'─'*w}{R}")
        lines.append(f" {RED}{BOLD}⚠ ERRORS TERBARU:{R}")
        for e in errs[-3:]:
            lines.append(f"   {RED}{e}{R}")

    lines.append(f"{GRAY}{'─'*w}{R}")
    lines.append(f" {GRAY}Log → logs/backend.log · logs/ui.log  ·  {_ts()} {CYAN}{sp}{R}")

    # Hapus baris sebelumnya (naik ke atas lalu overwrite)
    if _status_lines > 0:
        sys.stdout.write(f"\033[{_status_lines}A")
    for line in lines:
        sys.stdout.write(f"\033[2K{line}\n")
    sys.stdout.flush()
    _status_lines = len(lines)

# ─── Watchdog ─────────────────────────────────────────────
def _watchdog(name: str, args: list, cwd: str, log_name: str, env=None):
    global _running
    log_path = LOG_DIR / log_name
    _restarts[name] = 0
    _statuses[name] = "INIT"

    while _running:
        _statuses[name] = "RUNNING" if _restarts[name] == 0 else "RESTARTING"

        try:
            with open(log_path, "a", encoding="utf-8", errors="ignore") as lf:
                lf.write(f"\n{'='*60}\n[{datetime.now()}] SESSION START (restart #{_restarts[name]})\n{'='*60}\n")
                lf.flush()

                proc = subprocess.Popen(
                    args, cwd=cwd,
                    stdout=lf, stderr=subprocess.STDOUT,
                    env=env or os.environ.copy(),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                _procs[name] = proc
                _statuses[name] = "RUNNING"

        except FileNotFoundError as e:
            _statuses[name] = "ERROR"
            _notify_error(name, f"Perintah tidak ditemukan: {e}")
            time.sleep(10)
            continue
        except Exception as e:
            _statuses[name] = "ERROR"
            _notify_error(name, f"Gagal start: {e}")
            time.sleep(5)
            continue

        exit_code = proc.wait()
        if not _running:
            break

        _restarts[name] += 1
        _statuses[name] = "STOPPED"

        # Cek penyebab crash dari log (10 baris terakhir)
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                tail = lf.readlines()[-10:]
            for line in reversed(tail):
                line = line.strip()
                if line and not line.startswith("=") and not line.startswith("[20"):
                    _notify_error(name, f"crash[{exit_code}]: {line[:70]}")
                    break
        except Exception:
            _notify_error(name, f"Proses berhenti (exit={exit_code})")

        delay = min(5 * _restarts[name], 30)
        time.sleep(delay)

    _statuses[name] = "STOPPED"

# ─── Stop ─────────────────────────────────────────────────
def _stop_all(sig=None, frame=None):
    global _running
    if not _running:
        return
    _running = False

    # Bersihkan status bar dulu
    if _status_lines > 0:
        sys.stdout.write(f"\033[{_status_lines}A\033[J")
    print(f"\n{YELLOW}{BOLD}[JAYA] Menghentikan semua proses...{R}")

    for name, proc in _procs.items():
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            print(f"  {RED}✖{R} {name} dihentikan")
        except Exception:
            pass

    print(f"\n{GREEN}{BOLD}[JAYA] Semua layanan berhenti. Sampai jumpa!{R}\n")

# ─── Main ─────────────────────────────────────────────────
def main():
    global _running

    # Enable ANSI di Windows
    os.system("")

    _banner()

    signal.signal(signal.SIGINT,  _stop_all)
    signal.signal(signal.SIGTERM, _stop_all)

    if not VENV_PYTHON.exists():
        print(f"{RED}[ERROR] .venv312 tidak ditemukan!{R}")
        print(f"  Buat dengan: python -m venv .venv312")
        sys.exit(1)

    env = os.environ.copy()
    env["PYTHONPATH"]       = str(ROOT / "src") + os.pathsep + str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"

    # ── Bersihkan proses lama yang masih hold port ──────────
    def _free_port(port: int, label: str):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return  # port bebas, tidak perlu apa-apa

        print(f"{YELLOW}[JAYA] Port {port} masih dipakai. Membersihkan...{R}")
        try:
            # Gunakan netstat + parsing Python (tanpa shell batch)
            r = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5
            )
            pids = set()
            for line in r.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pids.add(parts[-1])

            for pid in pids:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True, timeout=3
                )

            time.sleep(1)
            # Cek ulang
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                if s2.connect_ex(("127.0.0.1", port)) == 0:
                    _notify_error(label, f"Port {port} masih sibuk! Coba tutup manual.")
                else:
                    print(f"{GREEN}[JAYA] Port {port} berhasil dibebaskan.{R}")
        except Exception as e:
            _notify_error(label, f"Tidak bisa bebaskan port {port}: {e}")

    _free_port(8000, "BACKEND")
    for p in range(5173, 5179):
        _free_port(p, "UI")

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        _notify_error("UI", "npm tidak ditemukan — UI tidak akan jalan")

    # Inisialisasi state awal
    for name in ("BACKEND", "UI"):
        _statuses[name] = "INIT"
        _restarts[name] = 0

    # Gambar status awal
    _draw_status()

    # ── Mulai threads
    t_back = threading.Thread(
        target=_watchdog, daemon=True,
        args=("BACKEND",
              [str(VENV_PYTHON), str(BACKEND_SCRIPT)],
              str(ROOT), "backend.log", env)
    )
    t_back.start()
    time.sleep(2)

    if npm:
        t_ui = threading.Thread(
            target=_watchdog, daemon=True,
            args=("UI",
                  [npm, "run", "dev"],
                  str(UI_DIR), "ui.log", None)
        )
        t_ui.start()

    # ── Loop status (update in-place tiap 1.5 detik)
    try:
        while _running:
            _draw_status()
            time.sleep(1.5)
    except KeyboardInterrupt:
        _stop_all()

    t_back.join(timeout=8)

if __name__ == "__main__":
    main()
