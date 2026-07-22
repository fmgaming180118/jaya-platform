# Workflow B.2 — Progress Streaming Analisis Background

> **Fase:** [B — Production Readiness](../../phase-b-production-readiness.md)  
> **Estimasi:** 3–4 hari  
> **Prasyarat:** [B.1 Session Persistence](b1-session-persistence.md)  
> **Tujuan:** Frontend menerima update progress real-time saat analisis thesis berjalan (5 langkah).

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/network/research_api.py` | Background task, SSE endpoint |
| `ui/src/pages/ThesisPage.jsx` | Konsumsi progress |
| `ui/src/services/api.js` | Client SSE atau polling upgrade |

---

## Lima Langkah Analisis (Events)

| Step | Event name | Deskripsi |
|------|------------|-----------|
| 1 | `meta_extraction` | Ekstraksi metadata (judul, abstrak) |
| 2 | `novelty_check` | Pencarian literatur & novelty |
| 3 | `gap_analysis` | Identifikasi research gap |
| 4 | `peer_review` | Kritik reviewer |
| 5 | `defense_questions` | Generasi pertanyaan sidang |

---

## Checklist Implementasi Backend

### 1. Progress State di Session Store
- [ ] Tambah kolom `progress_json` atau tabel `thesis_progress`
- [ ] Struktur: `{current_step, steps: [{name, status, started_at, completed_at, message}]}`
- [ ] Status per step: `pending` | `running` | `done` | `error`

### 2. Instrumentasi Background Task
- [ ] Di `analyze_thesis` background: update progress sebelum/sesudah setiap langkah
- [ ] Tangkap exception per langkah — lanjut atau abort (dokumentasikan)
- [ ] Log `[ThesisAPI] Step 2/5 novelty_check started`

### 3. SSE Endpoint
- [ ] `GET /thesis/progress/{session_id}` — `text/event-stream`
- [ ] Event format: `data: {"step": "novelty_check", "status": "running", "index": 2}\n\n`
- [ ] Tutup stream saat `status=done` atau `error`
- [ ] Heartbeat setiap 15 detik jika tidak ada update

### 4. Fallback Polling
- [ ] Perkaya `GET /thesis/status/{id}` dengan field `progress`
- [ ] UI bisa fallback ke polling jika SSE tidak didukung

---

## Checklist Implementasi Frontend

- [ ] `ThesisPage.jsx`: subscribe SSE saat analyze dimulai
- [ ] Progress bar atau step indicator (5 langkah)
- [ ] Tampilkan pesan error per langkah jika gagal
- [ ] Cleanup EventSource saat unmount
- [ ] `api.js`: helper `subscribeThesisProgress(sessionId, onEvent)`

---

## Checklist Testing

- [ ] SSE mengirim ≥5 event untuk analisis sukses
- [ ] UI progress bar bergerak tanpa refresh manual
- [ ] Error di langkah 3 → UI menampilkan step 3 merah
- [ ] Multiple client subscribe session sama — keduanya dapat event

---

## Kriteria Selesai Workflow B.2

- [ ] User melihat progress analisis di UI dalam <2 detik setelah klik Analyze
- [ ] Tidak perlu polling lebih cepat dari 2 detik (SSE utama)
- [ ] Dokumen `thesis-analyzer.md` menjelaskan SSE endpoint

---

## Verifikasi

```bash
curl -N "http://localhost:8000/thesis/progress/{session_id}"
# Expect: stream of JSON events until done
```

---

**Sebelumnya:** [B.1](b1-session-persistence.md) · **Berikutnya:** [B.3 Formal Benchmark](b3-formal-benchmark.md)
