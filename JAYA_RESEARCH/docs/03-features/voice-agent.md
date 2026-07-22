# Voice Agent — NVIDIA Riva + Pipecat

> [!NOTE]
> Voice Agent adalah fitur **opsional dan eksperimental**. Tidak wajib disetup untuk menggunakan fitur utama JAYA Research (Thesis Analyzer, Research Agent, RAG Chat).

---

## Konsep

Voice Agent memungkinkan percakapan suara real-time dengan JAYA menggunakan:

- **NVIDIA Riva** — ASR (Speech-to-Text) + TTS (Text-to-Speech)
- **Pipecat** — orkestrasi audio real-time (WebRTC/WebSocket)
- **NVIDIA NIM (Llama 3)** — LLM untuk memproses percakapan

```
User Speaks  →  Riva ASR  →  Llama 3 (NIM)  →  Riva TTS  →  Audio Response
                                    ↑
                               RAG Context
                          (dokumen workspace)
```

**Keunggulan:**
- Latensi voice-to-voice < 500ms
- Mendukung interupsi (user bisa memotong saat AI berbicara)
- Terintegrasi dengan RAG — jawaban berdasarkan dokumen kamu

---

## Setup (Opsional)

### 1. Install Pipecat

```bash
pip install pipecat-ai
```

### 2. Setup NVIDIA Riva

Riva membutuhkan akun NVIDIA dan konfigurasi:

```env
# .env
NVIDIA_RIVA_URI=wss://riva.api.nvidia.com
```

Daftar akses Riva di [NVIDIA NGC](https://catalog.ngc.nvidia.com).

### 3. Jalankan Voice Agent

```bash
python src/voice/voice_agent.py
```

---

## Arsitektur Teknis (Nimble Pipecat Blueprint)

Blueprint ini dikembangkan NVIDIA + Daily (pengembang Pipecat):

```
User Audio
    │  (WebRTC/WebSocket)
    ▼
Pipecat Pipeline
    ├── Transport Layer (Daily WebRTC)
    ├── ASR: NVIDIA Riva STT  ← transkripsi real-time
    ├── LLM: NVIDIA NIM Llama 3 ← reasoning + RAG
    └── TTS: NVIDIA Riva TTS  ← sintesis suara natural
    │
    ▼
Audio Output
```

**Fitur kunci Pipecat:**
- **Barge-in detection** — deteksi user memotong AI, langsung berhenti
- **Turn-based management** — mengelola giliran bicara secara natural
- **Modular** — bisa ganti model ASR/TTS/LLM dengan provider lain

---

## Sumber & Referensi

- [GitHub: daily-co/nimble-pipecat](https://github.com/daily-co/nimble-pipecat)
- [NVIDIA Riva Documentation](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/)
- [NVIDIA AI Blueprints](https://build.nvidia.com)
