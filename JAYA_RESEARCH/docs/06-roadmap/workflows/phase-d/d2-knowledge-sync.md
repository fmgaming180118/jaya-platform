# Workflow D.2 — Sinkronisasi Knowledge CORE ↔ RESEARCH

> **Fase:** [D — Ecosystem Bridge](../../phase-d-ecosystem-bridge.md)  
> **Estimasi:** 1–2 minggu  
> **Prasyarat:** [D.1 Unified Router](d1-unified-router.md), [Fase A](../../phase-a-rag-foundation.md)  
> **Tujuan:** Knowledge base workspace RESEARCH dapat disinkronkan dengan `rag_vault.db` (AgenticRAG) di JAYA_CORE.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `JAYA_RESEARCH/src/research/enhanced_rag.py` | Vector store RESEARCH |
| `JAYA_CORE/` AgenticRAG | SQLite FTS5 + semantic graph |
| Baru: `src/sync/knowledge_bridge.py` | Sync protocol |

---

## Checklist Desain

- [ ] Dokumen format sync delta: `{op: upsert|delete, chunk_id, content, metadata, workspace_id, timestamp}`
- [ ] Tentukan source of truth per skenario (RESEARCH upload → push ke CORE)
- [ ] Conflict resolution: last-write-wins atau manual merge flag

---

## Checklist Implementasi

### 1. Export dari RESEARCH
- [ ] `export_workspace_chunks(workspace_id) -> List[ChunkDelta]`
- [ ] Serialize dari FAISS metadata + content file

### 2. Import ke CORE
- [ ] Script `JAYA_CORE/scripts/import_research_chunks.py`
- [ ] Insert ke `rag_vault.db` dengan tag `origin=jaya_research`
- [ ] Idempotent: re-import tidak duplikat

### 3. LAN Sync (opsional MVP)
- [ ] HTTP endpoint `POST /sync/push` di RESEARCH (auth token)
- [ ] CORE daemon atau cron pull dari LAN IP
- [ ] Dokumentasi di `connection_hierarchy.md`

### 4. UI Trigger
- [ ] Tombol "Sync to JAYA Core" di halaman Documents atau Settings
- [ ] Status: last sync time, chunk count

---

## Checklist Testing

- [ ] Export 100 chunks → import CORE → search CORE menemukan konten
- [ ] Re-sync idempotent
- [ ] Workspace isolation terjaga di kedua sisi

---

## Kriteria Selesai Workflow D.2

- [ ] Satu arah sync RESEARCH → CORE berfungsi
- [ ] Dokumentasi protokol sync di `06-roadmap/` atau `JAYA_CORE/docs/`
- [ ] Manual E2E: upload PDF di RESEARCH → searchable di CORE CLI

---

**Sebelumnya:** [D.1](d1-unified-router.md) · **Berikutnya:** [D.3 Evolution UI](d3-evolution-ui.md)
