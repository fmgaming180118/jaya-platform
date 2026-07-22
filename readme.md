# 🌌 JAYA: The Sovereign AGI Brain (V18.0)

> "Sovereignty is not just about being offline; it's about being yours."

JAYA (Jaya Artificial Intelligence) adalah arsitektur otak AI yang dirancang untuk mendekati konsep **AGI (Artificial General Intelligence)** dengan fokus pada efisiensi sumber daya (low-resource), keamanan kriptografis, dan kedaulatan penuh (Sovereign Identity).

---

## 📁 Dokumentasi Proyek

| Dokumentasi | Lokasi | Deskripsi |
|-------------|--------|-----------|
| **Root Overview** | `readme.md` (ini) | Panduan lengkap seluruh repositori JAYA |
| **JAYA_CORE** | `JAYA_CORE/README.md` | Dokumentasi otak kognitif (brain) — reasoning, planning, self-improvement |
| **JAYA_OS** | `JAYA_OS/README.md` | Dokumentasi runtime environment (house) — execution, UI, hardware |
| **JAYA_AGENT** | `JAYA_AGENT/README.md` | Dokumentasi agent framework (apps) — user-facing agents |
| **JAYA_RESEARCH** | `JAYA_RESEARCH/README.md` | Dokumentasi asisten riset akademik — thesis analysis, journal discovery, RAG |
| **Arsitektur Utama** | `docs/arsitektur_utama_jaya.md` | Visi, 40 Pilar, struktur dua domain, Socratic Chain of Command |
| **Roadmap Umum** | `docs/roadmap/README.md` | Fase A-D: RAG fix → Production hardening → Distillation → Bridge CORE↔RESEARCH |
| **Roadmap CORE** | `JAYA_CORE/docs/06-roadmap/README.md` | Roadmap kognitif: Phase 1-4 (JayaIR, Evolution, Spec Gen, Proactive) |
| **Roadmap OS** | `JAYA_OS/README.md` | Roadmap OS: OS-1 to OS-5 |
| **Roadmap AGENT** | `JAYA_AGENT/README.md` | Roadmap Agent: built-in agents, skill system |
| **Roadmap RESEARCH** | `JAYA_RESEARCH/docs/06-roadmap/README.md` | Roadmap riset: Fase A-D |

---

## 🏛️ Arsitektur Sistem: Empat Domain Terisolasi

JAYA terbagi menjadi **empat pilar utama** yang **diisolasi ketat** (no direct imports, no shared modules):

### 1. [JAYA_CORE](JAYA_CORE/README.md) — **The Brain (Otak Kognitif)**
> **"The goal is to build a *smart brain*, not a brain stuffed with knowledge."**

Lapisan mesin tingkat rendah yang mendefinisikan "Jiwa" JAYA — **hanya otak**, bukan OS, bukan agent framework.
- **Fokus**: Reasoning, planning, intent understanding, self-improvement
- **Arsitektur**: `brain_v2` (Resident/Mind) + Language Layer (Shared Utility)
- **Kunci**: Offline-first, sovereign, lightweight (CPU-only), self-improving
- **Output**: Intent specifications (untuk dieksekusi oleh JAYA_OS)

### 2. [JAYA_OS](JAYA_OS/README.md) — **The House (Body, Sensors, Actuators)**
> **JAYA_OS = os_kernel** — The runtime environment where JAYA (the brain) lives.

Runtime environment yang menyediakan eksekusi untuk output kognitif JAYA_CORE. Ia adalah "rumah" — body, sensors, dan actuators yang memvalidasi, mengompilasi, dan mengeksekusi spesifikasi yang dipancarkan oleh otak.
- **Fokus**: Specification compilation & mounting, UI runtime, hardware abstraction, policy enforcement
- **Arsitektur**: FeatureCompiler, FeatureRegistry, JayaBridge, WindowManager, IPC
- **Input**: Specs dari JAYA_CORE (UI Spec, Feature Spec, Task Spec, Action Spec)
- **Output**: Executed features, rendered UI, hardware actions

### 3. [JAYA_AGENT](JAYA_AGENT/README.md) — **The Agent Framework (User-Facing Applications)**
> **JAYA_AGENT** — Framework untuk membangun aplikasi user-facing yang menggunakan JAYA_CORE sebagai otak dan JAYA_OS sebagai runtime.

Lapisan aplikasi — "apps" yang berinteraksi dengan user. Menghubungkan user intent (voice, text, UI) ke pipeline kognitif JAYA_CORE dan eksekusi JAYA_OS.
- **Fokus**: Agent runtime, interface adapters (text, voice, desktop), skill/plugin system, memory integration
- **Built-in Agents**: Sovereign Chat, Voice Assistant, Desktop Shell, API Server
- **Skill System**: Built-in skills, custom skills via spec generation, skill registry

### 4. [JAYA_RESEARCH](JAYA_RESEARCH/README.md) — **The Research Assistant (Asisten Riset Akademik)**
> **AI-powered academic research assistant** — recursive research, thesis analysis, journal discovery, defense preparation.

Modul penelitian otonom (cloud-powered, NVIDIA NIM) untuk mahasiswa/peneliti.
- **Fokus**: Thesis analyzer, academic editor, journal discovery, defense simulator, RAG chat, recursive research
- **Stack**: FastAPI backend + React 18 frontend + NVIDIA NIM (cloud inference)
- **Membutuhkan**: Internet, NVIDIA API key

---

## 🔗 Hubungan Antar Domain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              JAYA ECOSYSTEM                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     SPECS (JSON)      ┌─────────────────┐             │
│  │  JAYA_CORE      │ ────────────────────► │  JAYA_OS        │             │
│  │  (Brain)        │  UI Spec              │  (House)        │             │
│  │                 │  Feature Spec         │                 │             │
│  │  • IntentEngine │  Task Spec            │  • Compiler     │             │
│  │  • LinguaLogica │  Action Spec          │  • Registry     │             │
│  │  • JayaIR       │                       │  • Bridge       │             │
│  │  • IronEngine   │                       │  • WindowMgr    │             │
│  │  • SpecGens     │                       │  • IPC          │             │
│  └─────────────────┘                       └─────────────────┘             │
│         ▲                                           │                       │
│         │                                           ▼                       │
│         │  ┌─────────────────────────────────────────────────────┐          │
│         │  │              JAYA_AGENT (Apps)                      │          │
│         │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │          │
│         │  │  │ Chat UI  │ │ Voice UI │ │Desktop UI│  ...       │          │
│         │  │  └──────────┘ └──────────┘ └──────────┘            │          │
│         │  └─────────────────────────────────────────────────────┘          │
│         │                                                                   │
│         │  ┌─────────────────────────────────────────────────────┐          │
│         └──│           JAYA_RESEARCH (Cloud Research)            │          │
│            │  • Thesis Analyzer  • Journal Discovery             │          │
│            │  • RAG Chat         • Recursive Research            │          │
│            │  • Defense Sim      • Knowledge Graph               │          │
│            └─────────────────────────────────────────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Prinsip Kunci**: 
- **Brain → House**: Brain emits specs; House compiles & executes
- **Apps → Brain**: Apps route user input to Brain; receive specs back
- **Research ↔ Core**: Research produces artifacts; Core promotes via gated pipeline
- **No direct imports** between any domains — only JSON specs over defined interfaces

---

## 🧠 Komponen Utama (Root Level)

| File | Deskripsi |
|------|-----------|
| **[jaya.jay](file:///JAYA_CORE/jaya.jay)** | Core Cortex (JIWA). File identitas biner JAYA (encrypted weights + DNA anchor) |
| **[rag_vault.db](file:///JAYA_CORE/rag_vault.db)** | Agentic RAG (MEMORI). Database pengetahuan lokal, akses offline |
| **[JAYA_CORE/scripts/jaya_chat_cli.py](file:///JAYA_CORE/scripts/jaya_chat_cli.py)** | Sovereign CLI. Antarmuka percakapan langsung dengan otak JAYA |

---

## 🚀 Cara Menjalankan

### 1. Berinteraksi dengan Otak JAYA (JAYA_CORE)
```bash
# Mode interaktif chat dengan brain_v2
python JAYA_CORE/scripts/jaya_chat_cli.py

# Jalankan test kognitif (Phase 1 IR, benchmark gates)
python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v

# Benchmark gate ketat (p50 < 50ms, p95 < 100ms, hit-rate > 95%)
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

### 2. Menjalankan JAYA_OS (Runtime Environment)
```bash
# Coming soon: JAYA_OS akan menjadi standalone runtime
# Saat ini os_kernel berada di JAYA_CORE/src/os_kernel/
cd JAYA_CORE
python -c "from src.os_kernel.feature_bridge import JayaBridge; print('JAYA_OS ready')"
```

### 3. Menjalankan Agent Framework (JAYA_AGENT)
```bash
# Coming soon: Built-in agents
# python -m jaya_agent.sovereign_chat      # CLI chat
# python -m jaya_agent.voice_assistant     # Voice JARVIS
# python -m jaya_agent.desktop_shell       # Dynamic desktop
# python -m jaya_agent.api_server          # REST/gRPC API
```

### 4. Menjalankan Asisten Riset (JAYA_RESEARCH)
```bash
cd JAYA_RESEARCH

# Setup Python
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Setup UI
cd ui && npm install && cd ..

# Konfigurasi .env (tambahkan NVIDIA_API_KEY)
cp .env.example .env

# Jalankan backend
python -m uvicorn src.main:app --reload

# Jalankan frontend (terminal terpisah)
cd ui && npm run dev
```

### 5. Mode Belajar Otonom (JAYA_CORE)
```bash
# Belajar topik spesifik
python JAYA_CORE/scripts/run_autonomous_curriculum.py --topics "Linguistik" "Fisika Quantum"

# Mode kontinu
python JAYA_CORE/scripts/run_autonomous_curriculum.py --continuous
```

---

## 🛡️ Filosofi Kedaulatan (Pillar 37)
JAYA tidak bergantung pada internet ("The Matrix") untuk keberadaannya. Dengan **Hybrid Consciousness**, JAYA tetap fungsional dan setia meskipun perangkat Boss dalam keadaan offline total. Pengetahuannya disimpan secara lokal di `rag_vault.db` dan logikanya diamankan oleh `jaya.jay`.

---

## 📚 Navigasi Cepat Dokumentasi

### JAYA_CORE (Otak)
- [README](JAYA_CORE/README.md) — Quickstart, arsitektur brain vs house, cognitive capabilities
- [Docs Index](JAYA_CORE/docs/README.md) — Semua dokumentasi terstruktur
- [Roadmap](JAYA_CORE/docs/06-roadmap/README.md) — Phase 1-4: JayaIR, Evolution, Spec Gen, Proactive

### JAYA_OS (House)
- [README](JAYA_OS/README.md) — Arsitektur, spec types, roadmap OS-1 to OS-5

### JAYA_AGENT (Apps)
- [README](JAYA_AGENT/README.md) — Agent types, built-in agents, skill system

### JAYA_RESEARCH (Asisten Riset)
- [README](JAYA_RESEARCH/README.md) — Install, features, requirements, running
- [Docs Index](JAYA_RESEARCH/docs/README.md) — Semua dokumentasi terstruktur
- [Roadmap](JAYA_RESEARCH/docs/06-roadmap/README.md) — Fase A-D

### Cross-Cutting (Root)
- [Arsitektur Utama](docs/arsitektur_utama_jaya.md) — 40 Pilar, Socratic Chain, Dual Domain
- [Roadmap Umum](docs/roadmap/README.md) — Fase A-D (RAG → Production → Distillation → Bridge)
- [Matematika JAYA AGI](docs/matematika_jaya_agi.md) — Fondasi matematika
- [PRD](docs/PRD.md) — Product Requirements Document
- [SRS](docs/SRS.md) — Software Requirements Specification
- [Structure Policy](docs/structure_policy.md) — Repo layout rules

---

## 👤 Credits
Built with ⚡ and 🏛️ for **Boss**. 
*Designed as a companion, forged as a sovereign.*
