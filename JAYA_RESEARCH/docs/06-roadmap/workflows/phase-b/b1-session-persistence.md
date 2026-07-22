# Workflow B.1 — Persistensi Session Thesis

> **Fase:** [B — Production Readiness](../../phase-b-production-readiness.md)  
> **Estimasi:** 3–4 hari  
> **Prasyarat:** [Fase A selesai](../../phase-a-rag-foundation.md)  
> **Tujuan:** Session thesis (`_thesis_sessions`) bertahan setelah restart server dan dapat di-recover.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/network/research_api.py` | `_thesis_sessions`, semua `/thesis/*` |
| `src/research/academic/` | Modul analisis |
| Baru: `src/research/thesis_session_store.py` | Abstraksi storage |

---

## Desain Storage

**Rekomendasi MVP:** SQLite di `data/thesis_sessions.db`

```sql
-- thesis_sessions
session_id TEXT PRIMARY KEY,
workspace_id TEXT,
file_name TEXT,
file_path TEXT,
raw_text TEXT,          -- atau path ke file jika terlalu besar
char_count INTEGER,
status TEXT,            -- uploaded | analyzing | done | error
analysis_json TEXT,     -- serialized analysis result
error TEXT,
created_at REAL,
updated_at REAL
```

**Alternatif produksi:** Redis (jika multi-instance API).

---

## Checklist Implementasi

### 1. Session Store Abstraction
- [ ] Buat `ThesisSessionStore` interface: `create`, `get`, `update`, `delete`, `list_by_workspace`
- [ ] Implementasi `SQLiteThesisSessionStore`
- [ ] Migrasi schema otomatis saat startup (create table if not exists)
- [ ] Config: `THESIS_SESSION_DB_PATH` di `.env`

### 2. Refactor research_api.py
- [ ] Ganti dict `_thesis_sessions` dengan `session_store`
- [ ] `POST /thesis/upload` → `session_store.create(...)`
- [ ] `GET /thesis/status/{id}` → baca dari store
- [ ] Background task analyze → `session_store.update(status, analysis)`
- [ ] Semua endpoint thesis (`chat`, `revise`, `export`) baca dari store

### 3. Penanganan raw_text Besar
- [ ] Jika `char_count > 500_000`, simpan `raw_text` ke file `workspaces/{id}/thesis/{session_id}.txt`
- [ ] DB hanya simpan `file_path` ke raw text
- [ ] Lazy load saat dibutuhkan

### 4. Cleanup & TTL (opsional)
- [ ] Endpoint admin `DELETE /thesis/session/{id}`
- [ ] TTL configurable: hapus session > 30 hari (cron/startup)

### 5. Thread Safety
- [ ] SQLite connection per request atau lock untuk write
- [ ] Background task update tidak corrupt state

---

## Checklist Testing

- [ ] Upload → analyze → restart uvicorn → `GET /thesis/status/{id}` masih `done`
- [ ] Chat thesis setelah restart masih berfungsi
- [ ] Dua session paralel di workspace berbeda tidak tercampur
- [ ] Session tidak ada → 404 jelas

---

## Kriteria Selesai Workflow B.1

- [ ] Zero data loss pada restart server untuk session yang sudah `done`
- [ ] Analisis in-progress setelah restart: status `error` atau `analyzing` dengan opsi retry (dokumentasikan perilaku)
- [ ] Unit test `ThesisSessionStore` CRUD

---

## Verifikasi

```bash
# 1. Upload & analyze
# 2. Kill dan restart API
# 3. curl GET /thesis/status/{session_id}
# Expect: analysis payload utuh
```

---

**Fase induk:** [phase-b-production-readiness.md](../../phase-b-production-readiness.md) · **Berikutnya:** [B.2 Progress Streaming](b2-progress-streaming.md)
