# JAYA Research

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Frontend](https://img.shields.io/badge/UI-React%20%7C%20Vite%20%7C%20Tailwind-blueviolet.svg)](packages/jaya-research/ui/)
[![Backend](https://img.shields.io/badge/API-FastAPI%20%7C%20Uvicorn-emerald.svg)](packages/jaya-research/src/)

**JAYA Research** is an advanced cognitive evolution and scientific research platform. It connects multimodal scientific literature ingestion, citation-grounded Retrieval-Augmented Generation (RAG), dynamic knowledge graph synthesis, and autonomous research loops into a unified, user-friendly ecosystem with an interactive web dashboard.

---

## Key Features

- **Autonomous Research Loop**: Iterative query planning, thesis analysis, gap detection, and structured report synthesis.
- **Multimodal Document Ingestion**: High-fidelity extraction of text, tables, figures, and bibliographic metadata from scientific PDFs and journals.
- **Citation-Grounded RAG**: Hybrid vector search (FAISS / dense embeddings) backed by knowledge graph representations to prevent hallucination.
- **Interactive Research Dashboard**: Modern React + Vite web application for visualizing research progress, exploring knowledge graphs, and interacting with research agents.
- **Voice & Multimodal Interface**: Low-latency voice interaction and real-time reasoning feedback.
- **Modular Monorepo Architecture**: Clean separation of concerns across cognitive core, agent orchestration, OS policies, and research adapters.

---

## Quick Start (Out of the Box)

### Prerequisites
- **Python**: Version 3.11 or higher
- **Node.js**: Version 18 or higher (with `npm`)

### 1. One-Click Launch

#### On Windows:
Double-click `START_JAYA_RESEARCH.bat` or run:
```cmd
START_JAYA_RESEARCH.bat
```

#### On Linux / macOS:
```bash
chmod +x START_JAYA_RESEARCH.sh
./START_JAYA_RESEARCH.sh
```

The launcher will automatically start the FastAPI backend on port 8000 and the React UI on port 5173, then launch your web browser to `http://localhost:5173`.

---

### 2. Manual Installation & Execution

If you prefer to run services manually or develop on specific components:

#### Step 1: Clone Repository
```bash
git clone https://github.com/fmgaming180118/jaya-research.git
cd jaya-research
```

#### Step 2: Install Python Packages
```bash
python -m pip install --upgrade pip
pip install -r packages/jaya-research/requirements.txt
pip install -e packages/jaya-core -e packages/jaya-agent -e packages/jaya-os -e packages/jaya-research
```

#### Step 3: Install Frontend Dependencies
```bash
cd packages/jaya-research/ui
npm install
cd ../../..
```

#### Step 4: Configure Environment (Optional)
Copy the example environment configuration:
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```
*Note: JAYA will run with built-in local heuristic engines even without external API keys. Configure `NVIDIA_API_KEY` or `OPENAI_API_KEY` in `.env` to enable cloud models.*

#### Step 5: Start the Backend API
```bash
# Windows
set PYTHONPATH=packages\jaya-research\src
python -m jaya_research.network.research_api

# Linux / macOS
PYTHONPATH=packages/jaya-research/src python3 -m jaya_research.network.research_api
```
Backend API docs available at: `http://localhost:8000/docs`

#### Step 6: Start the Frontend UI
In a separate terminal:
```bash
cd packages/jaya-research/ui
npm run dev
```
Access the Dashboard at: `http://localhost:5173`

---

## Repository Structure

```text
jaya-research/
├── packages/
│   ├── jaya-research/        # CEL Research Engine (FastAPI backend, React UI, RAG)
│   │   ├── src/              # Backend Python package
│   │   ├── ui/               # Modern React + Vite Dashboard
│   │   ├── benchmarks/       # Research benchmark scripts
│   │   └── tests/            # Test suite for research module
│   ├── jaya-core/            # Cognitive runtime, pure logic, and verification
│   ├── jaya-agent/           # Multi-agent coordination and execution
│   ├── jaya-os/              # Sandboxing and OS interface adapters
│   └── jaya-android/         # Android mobile companion client
├── native/                   # C++20 and Rust high-performance compute kernels
├── configs/                  # Modular configuration templates
├── scripts/                  # Management, verification, and benchmark scripts
├── tests/                    # Monorepo contract and integration tests
├── pyproject.toml            # Unified monorepo project configuration
├── START_JAYA_RESEARCH.bat   # Windows one-click launcher
├── START_JAYA_RESEARCH.sh    # Linux/macOS one-click launcher
└── .env.example              # Environment variables template
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
