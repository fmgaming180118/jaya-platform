# Workflow D.5 — Voice Agent Terintegrasi UI

> **Fase:** [D — Ecosystem Bridge](../../phase-d-ecosystem-bridge.md)  
> **Estimasi:** 2–3 minggu  
> **Prasyarat:** [D.1 Unified Router](d1-unified-router.md)  
> **Tujuan:** Voice chat dari UI utama memakai pipeline terpadu (STT → InferenceRouter → TTS), bukan demo terisolasi.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/voice_agent/` | Pipecat + Riva |
| `docs/03-features/voice-agent.md` | Dokumentasi existing |
| `ui/src/pages/ChatPage.jsx` | Tombol voice |
| `src/inference/inference_router.py` | LLM routing |

---

## Checklist Perbaikan Foundation

### 1. Fix Import Lintas Repo
- [ ] Hapus import `brain_v2` dari JAYA_CORE di demo voice (jika path invalid)
- [ ] Voice agent hanya import dari `JAYA_RESEARCH/src/`

### 2. WebSocket Voice Endpoint
- [ ] `WS /voice/session` — audio stream in/out
- [ ] Auth token atau session id (minimal)
- [ ] Integrasi dengan `workspace_id`

---

## Checklist Pipeline

### 1. STT
- [ ] NVIDIA Riva atau fallback Whisper local
- [ ] Config: `RIVA_URI` di `.env`
- [ ] Graceful degrade jika Riva tidak tersedia

### 2. LLM
- [ ] Transcript → `InferenceRouter.complete()` (bukan hardcode Llama NIM)
- [ ] Konteks RAG dari workspace aktif (opsional)

### 3. TTS
- [ ] Riva TTS atau fallback browser TTS
- [ ] Streaming audio response

---

## Checklist Frontend

- [ ] Tombol mic di ChatPage
- [ ] Indikator listening / speaking
- [ ] Error: "Voice unavailable" jika backend down
- [ ] Mobile-friendly (opsional)

---

## Checklist Testing

- [ ] E2E: bicara → transcript → jawaban → audio balik
- [ ] Router: voice query ringan → local backend (jika configured)
- [ ] Tidak crash jika Riva offline

---

## Kriteria Selesai Workflow D.5

- [ ] Voice terintegrasi ChatPage (bukan script terpisah)
- [ ] `voice-agent.md` terupdate dengan arsitektur baru
- [ ] Marked as **beta** di UI

---

**Fase induk:** [phase-d-ecosystem-bridge.md](../../phase-d-ecosystem-bridge.md)
