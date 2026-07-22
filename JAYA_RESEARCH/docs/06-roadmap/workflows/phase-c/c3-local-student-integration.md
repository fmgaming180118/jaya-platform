# Workflow C.3 — Integrasi Student Model ke JAYA_RESEARCH

> **Fase:** [C — Distillation & Edge](../../phase-c-distillation-edge.md)  
> **Estimasi:** 4–6 hari  
> **Prasyarat:** [C.2 Student Evaluation](c2-student-evaluation.md)  
> **Tujuan:** JAYA_RESEARCH dapat memanggil student model lokal (GGUF/Ollama) sebagai fallback atau untuk query ringan.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `JAYA_RESEARCH/src/teacher.py` | NIM client — tambah router |
| `JAYA_RESEARCH/.env.example` | Config baru |
| `JAYA_CORE/data/edge_deploy/` | Path GGUF |
| Baru: `src/inference/local_student.py` | Wrapper Ollama/llama.cpp |

---

## Checklist Implementasi

### 1. Local Inference Wrapper
- [ ] Class `LocalStudentClient` — interface mirip `Teacher.generate()`
- [ ] Backend opsi: Ollama API (`localhost:11434`) atau llama-cpp-python
- [ ] Load model dari path GGUF di config
- [ ] Streaming support (opsional untuk Fase C)
- [ ] Timeout & error handling

### 2. Environment Config
- [ ] `LOCAL_STUDENT_ENABLED=true|false`
- [ ] `LOCAL_STUDENT_BACKEND=ollama|llamacpp`
- [ ] `LOCAL_STUDENT_MODEL_PATH` atau `OLLAMA_MODEL_NAME`
- [ ] Dokumentasi di `configuration.md`

### 3. Teacher Router (minimal)
- [ ] Fungsi `route_inference(prompt, complexity_hint)`:
  - `LOCAL_STUDENT_ENABLED=false` → NIM only
  - NIM unavailable → fallback local
  - Query panjang/kompleks → NIM (heuristic: token count, keywords)
- [ ] Log setiap request: `backend=nim|local`

### 4. Integrasi Chat Endpoint
- [ ] `POST /chat` memakai router (bukan hardcode NIM)
- [ ] Response metadata: `inference_backend`
- [ ] Mode degraded jelas ke user jika hanya local

### 5. Health Check
- [ ] `GET /health/local-model` — status loaded, latency probe
- [ ] `GET /evolution/status` — sertakan policy aktif dari registry (read-only)

---

## Checklist Testing

- [ ] Chat dengan NIM disabled + local enabled → jawaban terima
- [ ] Chat kompleks (thesis analysis) → tetap NIM jika tersedia
- [ ] Ollama tidak jalan → error message jelas, bukan hang
- [ ] Latency local <5s untuk prompt pendek

---

## Kriteria Selesai Workflow C.3

- [ ] End-to-end: registry GGUF → Ollama → JAYA_RESEARCH chat
- [ ] Fallback otomatis saat `NVIDIA_API_KEY` kosong (jika local enabled)
- [ ] `.env.example` terupdate

---

## Verifikasi

```bash
# Tanpa NVIDIA_API_KEY
LOCAL_STUDENT_ENABLED=true ollama serve &
curl -X POST http://localhost:8000/chat \
  -d '{"message": "Apa itu machine learning?", "workspace_id": "default"}'
# Expect: inference_backend=local
```

---

**Fase induk:** [phase-c-distillation-edge.md](../../phase-c-distillation-edge.md)
