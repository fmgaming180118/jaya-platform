# 🚀 JAYA Research & AGI Ecosystem

JAYA is an autonomous AGI research ecosystem featuring closed-loop scientific hypothesis discovery, native OS process isolation, self-code mutation with immune system rollback, and autonomous LoRA neural weight fine-tuning.

---

## 💻 System Architecture

```
                               ┌────────────────────────────────┐
                               │     Vite React Dashboard       │
                               │    (http://localhost:5173)     │
                               └───────────────┬────────────────┘
                                               │ REST API / CORS
                               ▼               ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Backend Engine                               │
│                         (http://localhost:8000)                               │
├───────────────────────────────────────┬───────────────────────────────────────┤
│ 1. Autonomous Research Worker         │ 2. Native OS & WASM Isolation Sandbox │
│    - Hypothesis Generator             │    - Windows Job Objects / cgroups    │
│    - Bayesian Confidence Learner      │    - WebAssembly Execution Engine     │
│    - SQLite Patch Injector            │    - Immune System Rollback           │
├───────────────────────────────────────┼───────────────────────────────────────┤
│ 3. Autonomous LoRA Fine-Tuner         │ 4. Memory Manager & Ecosystem Sync    │
│    - Auto SFT Dataset Collector       │    - SQLite WAL Mode & B-Tree Indexes │
│    - PEFT Weight Adaptation (< 30MB)  │    - RAM Cap (< 200MB) Enforcement   │
└───────────────────────────────────────┴───────────────────────────────────────┘
```

---

## 🛠️ Prerequisites & Requirements

- **Operating System**: Windows 10/11, Linux, or macOS
- **Python**: Version `3.10` or higher (Recommended: `Python 3.12`)
- **Node.js**: Version `18.0` or higher (For UI Frontend)
- **NVIDIA NIM API Key** *(Optional for Cloud LLM Acceleration)*

---

## ⚙️ Environment Setup

1. **Clone Repository**:
   ```bash
   git clone <repository_url>
   cd jaya-research
   ```

2. **Python Environment Setup**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r JAYA_RESEARCH/requirements.txt
   ```

3. **Configure Environment Variables (`.env`)**:
   Create a `.env` file in `JAYA_RESEARCH/.env`:
   ```ini
   NVIDIA_API_KEY=your_nvidia_nim_api_key_here
   NVIDIA_MODEL=meta/llama-3.1-70b-instruct
   RESEARCH_REASONING_MODEL=meta/llama-3.1-70b-instruct
   PORT=8000
   ```

4. **Frontend UI Dependencies**:
   ```bash
   cd JAYA_RESEARCH/ui
   npm install
   ```

---

## 🚀 How to Run JAYA

### 1. Launch Backend API Server

Open terminal at project root and execute:

```bash
# Windows (PowerShell)
$env:PYTHONPATH="JAYA_RESEARCH/src"; python JAYA_RESEARCH/src/network/research_api.py

# Linux / macOS
PYTHONPATH="JAYA_RESEARCH/src" python JAYA_RESEARCH/src/network/research_api.py
```
*Backend will start on `http://localhost:8000` with automatic SQLite persistence & Autonomous Worker Loop.*

### 2. Launch React Frontend Dashboard

Open a second terminal window:

```bash
cd JAYA_RESEARCH/ui
npm run dev
```
*Frontend will launch on `http://localhost:5173`.*

---

## 🧪 Key API Endpoints & Features

| Endpoint | Method | Description |
|---|---|---|
| `/evolution/status` | `GET` | Live status of Autonomous Discovery Loop & Digital Twin |
| `/evolution/patches` | `GET` | Retrieve verified research patches from SQLite DB |
| `/evolution/start-autonomous-loop` | `POST` | Start continuous background research loop |
| `/evolution/stop-autonomous-loop` | `POST` | Stop continuous background research loop |
| `/evolution/auto-finetune` | `POST` | Trigger SFT dataset extraction & LoRA weight fine-tuning |
| `/evolution/memory-status` | `GET` | Monitor RAM RSS memory footprint (< 200MB) |
| `/evolution/optimize-memory` | `POST` | Optimize SQLite WAL indexes & trigger RAM garbage collection |

---

## 🔒 Security & Privacy

- **Data Isolation**: All database files (`*.db`), runtime patches (`*.jaypatch`), weight adapters (`*.pt`), and user uploads are strictly excluded from version control via `.gitignore`.
- **Process Sandbox**: Mutations run inside Windows Job Objects or WebAssembly sandboxes without requiring third-party Docker daemons.
