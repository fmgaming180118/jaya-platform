# 🧠 JAYA Research

> **AI-powered academic research assistant** — recursive research, thesis analysis, journal discovery, and defense preparation. Built for students and researchers who want an intelligent partner in their academic journey.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org)
[![NVIDIA NIM](https://img.shields.io/badge/Powered_by-NVIDIA_NIM-76B900.svg)](https://build.nvidia.com)

---

## ✨ What is JAYA Research?

JAYA Research is an agentic AI system that helps you:

- 🔬 **Analyze your thesis** — novelty check, research gap identification, peer-review critique
- 📝 **Revise drafts** — AI-powered editing with multiple revision modes
- 📚 **Find relevant journals** — ArXiv + Semantic Scholar search
- 🛡️ **Prepare for your defense** — simulate tough supervisor questions
- 💬 **Chat with your documents** — ask questions about your thesis via RAG
- 🔄 **Run recursive research** — autonomous multi-step research on any topic

---

## 🚀 Features

| Feature | Description |
|---|---|
| **Thesis Analyzer** | Upload PDF → auto-extract metadata, check novelty vs literature, identify gaps |
| **Academic Editor** | Revise sections with AI: general, formal, citation, or methodology mode |
| **Journal Discovery** | Search ArXiv + Semantic Scholar based on your thesis topic |
| **Defense Simulator** | Generate tough viva voce questions from your topic & abstract |
| **RAG Chat** | Ask questions about your uploaded thesis — answers grounded in your document |
| **Autonomous Research** | Start a research topic → JAYA scrapes papers, synthesizes findings |
| **Knowledge Graph** | Visual graph of research concepts and relationships |
| **Report Export** | Download a complete analysis report as Markdown |

---

## 📋 Requirements

- **Python** 3.10+
- **Node.js** 18+ (for UI)
- **NVIDIA API Key** — free at [build.nvidia.com](https://build.nvidia.com)
- **PyMuPDF** (for PDF extraction): `pip install pymupdf`

> [!NOTE]
> JAYA Research uses **NVIDIA NIM** (cloud inference) as its AI brain. No local GPU required — runs on any machine with internet access.

---

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/jaya-research.git
cd jaya-research/JAYA_RESEARCH
```

### 2. Set Up Python Environment

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your NVIDIA API Key:

```env
NVIDIA_API_KEY=nvapi-your-key-here
```

Get your free key at [build.nvidia.com](https://build.nvidia.com).

### 4. Set Up the UI

```bash
cd ui
npm install
```

---

## ▶️ Running JAYA Research

### Start the Backend API

```bash
# From JAYA_RESEARCH directory
python src/network/research_api.py
```

Backend runs at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Start the UI

```bash
# From JAYA_RESEARCH/ui directory
npm run dev
```

UI runs at `http://localhost:5173`.

---

## 📖 How to Use

### Analyze Your Thesis

1. Open the **Thesis** page in the UI
2. Drag & drop your PDF or click to upload
3. Click **"Mulai Analisis Komprehensif"**
4. JAYA will run 5 analysis steps (2–5 minutes depending on internet speed):
   - Metadata extraction
   - Novelty check vs ArXiv + Semantic Scholar
   - Research gap identification
   - Peer-review critique
   - Defense question generation
5. Switch tabs to **Revisi**, **Jurnal**, **Chat**, or **Ekspor**

### Run Autonomous Research

1. Open the **Research** page
2. Enter a research topic
3. JAYA will autonomously search papers, synthesize findings, and generate a report

### Chat with Documents

Upload any research-related question in the **Chat** page — answers are grounded in your knowledge base.

---

## 🏗️ Architecture

```
JAYA_RESEARCH/
├── src/
│   ├── network/
│   │   └── research_api.py      ← FastAPI backend (main entry point)
│   ├── research/
│   │   ├── academic/
│   │   │   ├── novelty_checker.py  ← Novelty verification
│   │   │   ├── gap_finder.py       ← Citation network analysis
│   │   │   ├── reviewer.py         ← Peer review & defense questions
│   │   │   ├── editor.py           ← Draft revision
│   │   │   ├── literature.py       ← ArXiv + Semantic Scholar clients
│   │   │   └── ...
│   │   ├── agent.py             ← Autonomous research agent
│   │   └── rag_client.py        ← Vector RAG engine
│   └── teacher.py               ← NVIDIA NIM interface
├── ui/
│   └── src/
│       ├── pages/
│       │   ├── ThesisPage.jsx   ← Thesis analysis UI (multi-tab)
│       │   ├── ResearchPage.jsx ← Autonomous research UI
│       │   └── ChatPage.jsx     ← RAG chat UI
│       └── services/
│           └── api.js           ← All API calls
├── .env.example                 ← Environment template (safe to commit)
├── requirements.txt
└── README.md
```

---

## 🔒 Privacy & Data

> [!CAUTION]
> **Your data stays local.** JAYA Research stores all uploaded documents, embeddings, and conversation history on your own machine. Only the text you query is sent to NVIDIA NIM for inference.

Files excluded from GitHub (see [.gitignore](.gitignore)):
- `data/` — your uploaded PDFs and vector stores
- `workspaces/` — per-workspace embeddings
- `logs/` — runtime logs
- `.env` — your API keys

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas we'd love help with:
- Better PDF extraction (equations, figures)
- More language support (English UI)
- Additional analysis modules
- UI improvements
- Tests

---

## 📄 License

[MIT License](LICENSE) — free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- **NVIDIA NIM** — AI inference backbone
- **ArXiv** & **Semantic Scholar** — academic paper sources
- **FastAPI** — Python web framework
- **React** + **Framer Motion** — UI framework

---

*Built for students who want JARVIS in their research journey. 🚀*
