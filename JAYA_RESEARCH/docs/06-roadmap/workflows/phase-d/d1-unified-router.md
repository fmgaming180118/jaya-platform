# Workflow D.1 — Unified Chat Router

> **Fase:** [D — Ecosystem Bridge](../../phase-d-ecosystem-bridge.md)  
> **Estimasi:** 1 minggu  
> **Prasyarat:** [C.3 Local Student Integration](../phase-c/c3-local-student-integration.md)  
> **Tujuan:** Router cerdas yang menerapkan hierarki **Lokal → LAN → Internet (NIM)** untuk setiap request inference.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/teacher.py` | NIM cloud |
| `src/inference/local_student.py` | Edge model |
| Baru: `src/inference/inference_router.py` | Routing logic |
| `JAYA_CORE/docs/connection_hierarchy.md` | Spesifikasi hierarki |

---

## Routing Rules (Target)

| Prioritas | Backend | Kondisi |
|-----------|---------|---------|
| 1 | Local student | Query ringan, local healthy, user privacy mode |
| 2 | LAN peer | Device JAYA di jaringan sama (Fase D.2) |
| 3 | NVIDIA NIM | Default untuk query kompleks |
| 4 | Degraded keyword | Semua gagal — RAG only tanpa LLM (opsional) |

---

## Checklist Implementasi

### 1. InferenceRouter Class
- [ ] `select_backend(request_context) -> Backend`
- [ ] Input context: `message`, `workspace_id`, `task_type`, `user_preference`
- [ ] Heuristic kompleksitas: token count, task (`thesis_analyze` → cloud only)
- [ ] Config override per workspace

### 2. Privacy Mode
- [ ] Flag `PRIVACY_MODE=local_only` di `.env` atau per-request header
- [ ] Jika aktif: tidak pernah panggil NIM

### 3. Integrasi Semua LLM Call Sites
- [ ] `POST /chat`
- [ ] Thesis analyze background steps
- [ ] Research agent synthesis
- [ ] Graph triple extraction
- [ ] Audit: grep semua `Teacher(` direct calls

### 4. Observability
- [ ] Log structured: `{backend, latency_ms, tokens, workspace_id}`
- [ ] Metrics counter per backend (in-memory atau file)

### 5. API Response
- [ ] Field `inference: {backend, model_id, latency_ms}` di response chat

---

## Checklist Testing

- [ ] Privacy mode → zero NIM calls (mock verify)
- [ ] Thesis analyze → selalu NIM meski query pendek
- [ ] Simple chat → local jika enabled
- [ ] Router fallback chain teruji (local down → NIM)

---

## Kriteria Selesai Workflow D.1

- [ ] Satu entry point `InferenceRouter.complete()` untuk semua LLM calls utama
- [ ] Hierarki terdokumentasi di `overview.md`
- [ ] 3 skenario E2E lulus (local only, cloud only, fallback)

---

**Fase induk:** [phase-d-ecosystem-bridge.md](../../phase-d-ecosystem-bridge.md) · **Berikutnya:** [D.2 Knowledge Sync](d2-knowledge-sync.md)
