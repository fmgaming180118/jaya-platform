# Fase D — Checklist Eksekusi (Checkbox-Ready)

> **Cara pakai:** Per sprint (2 minggu). Centang `[ ]` → `[x]` saat selesai.  
> **Konvensi:** `☐` = belum, `☑` = selesai, `⏳` = in progress, `🚫` = blocked.

---

## Sprint D-S1: Hybrid Router + Distributed Tracing

### D.1 — Hybrid Router (Local ↔ Cloud)

| ID | Task | Assignee | Est. | Status | Notes / Blocker |
|----|------|----------|------|--------|-----------------|
| D.1.1 | Design router policy spec (`docs/architecture/router_policy.md`) | | 0.5d | ☐ | Rule-based + learned |
| D.1.2 | Implement `HybridRouter` class (`JAYA_CORE/src/router/hybrid_router.py`) | | 1.5d | ☐ | Route(query) → local/cloud |
| D.1.3 | Integrate to `JAYA_RESEARCH` `/chat` endpoint with `model=auto` | | 1d | ☐ | Swagger UI toggle |
| D.1.4 | Semantic cache (Redis + FAISS) for cloud query dedup | | 1.5d | ☐ | Hit rate ≥ 30% |
| D.1.5 | Fallback chain: local → cache → cloud → error | | 0.5d | ☐ | Graceful degradation |
| D.1.6 | Router metrics: decision dist, latency, cache hit rate | | 0.5d | ☐ | Prometheus + Grafana |

### D.8.1 — Distributed Tracing (OpenTelemetry)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.8.1.1 | Setup OpenTelemetry SDK di JAYA_CORE + JAYA_RESEARCH | | 1d | ☐ | `src/observability/tracing.py` |
| D.8.1.2 | Instrument router, RAG, NIM client, GGUF backend | | 1d | ☐ | Auto-instrument + manual spans |
| D.8.1.3 | Export ke Jaeger / Tempo (local dev) | | 0.5d | ☐ | Docker compose |
| D.8.1.4 | Verify trace: query → router decision → backend → response | | 0.5d | ☐ | End-to-end visible |

---

## Sprint D-S2: LAN Sync + Evolution UI

### D.2 — LAN Knowledge Sync (Delta Sync)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.2.1 | Design sync protocol spec (`docs/architecture/lan_sync.md`) | | 0.5d | ☐ | Merkle tree / content hash |
| D.2.2 | Implement `SyncAgent` CLI (`JAYA_CORE/src/sync/sync_agent.py`) | | 1.5d | ☐ | `push --peer`, `pull` |
| D.2.3 | Integrate to JAYA_RESEARCH workspace (auto-sync on ingest) | | 1d | ☐ | UI "Sync to Edge" button |
| D.2.4 | Conflict resolution: LWW + manual merge UI | | 1d | ☐ | Test concurrent edit |
| D.2.5 | Security: mTLS / PSK for LAN sync | | 0.5d | ☐ | `gen_sync_certs.sh` |

### D.3 — Evolution UI (Real-time)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.3.1 | React page `/evolution` (table: policy, status, gain, manifest, GGUF size) | | 1d | ☐ | `Evolution.tsx` |
| D.3.2 | WebSocket feed from JAYA_CORE evolution gate | | 1d | ☐ | `ws_feed.py` |
| D.3.3 | One-click "Promote to Edge" → trigger `promote_gguf.py` via API | | 1d | ☐ | Progress bar + toast |
| D.3.4 | Model lineage graph (base → adapter → merged → GGUF) | | 1d | ☐ | Cytoscape.js / react-flow |

---

## Sprint D-S3: Multimodal PDF (nv-ingest)

### D.4 — Multimodal PDF Extraction

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.4.1 | Integrate `nv-ingest` → structured JSON (text, table, image, formula) | | 2d | ☐ | `nv_ingest_wrapper.py` |
| D.4.2 | Table → Markdown/CSV + embedding for RAG | | 1.5d | ☐ | Table QA ≥ 80% |
| D.4.3 | Figure → caption generation (VLM) + embedding | | 1.5d | ☐ | Figure search |
| D.4.4 | Formula → LaTeX extraction (Nougat/custom) + semantic search | | 1.5d | ☐ | Math QA test |
| D.4.5 | Update thesis analyzer → ingest multimodal chunks | | 1d | ☐ | Chat answers "table 3..." |

---

## Sprint D-S4: Voice Agent (Production)

### D.5 — Voice Agent

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.5.1 | Refactor `voice_agent_demo.py` → `VoiceAgent` class (async, no `input()`) | | 1d | ☐ | `voice_agent.py` |
| D.5.2 | STT: faster-whisper (local) + NIM Parakeet (cloud) | | 1.5d | ☐ | Latency < 500ms local |
| D.5.3 | TTS: piper-tts (local) + NIM TTS (cloud) | | 1d | ☐ | Voice clone optional |
| D.5.4 | VAD + turn-taking + barge-in | | 1d | ☐ | Natural flow |
| D.5.5 | Integrate to Hybrid Router (D.1) → voice query route local/cloud | | 0.5d | ☐ | Voice chat offline |
| D.5.6 | React voice UI: push-to-talk, waveform | | 1d | ☐ | `VoiceChat.tsx` |

---

## Sprint D-S5: Citation Graph + Revision Mode

### D.6 — Citation Graph Interactive

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.6.1 | Enhance `citation_graph.py` → export GraphML / Cytoscape JSON | | 1d | ☐ | Nodes: paper, Edges: cites |
| D.6.2 | React Flow viz: zoom, filter by year/cluster, click → detail | | 1.5d | ☐ | `/thesis/{id}/citations` |
| D.6.3 | Gap finder overlay: highlight missing links | | 1d | ☐ | Visual gap detection |

### D.7 — Structured Revision Mode

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.7.1 | Thesis versioning: snapshot per analysis run (Git-like) | | 1d | ☐ | `versioning.py` |
| D.7.2 | Diff engine: section-level diff (difflib + semantic) | | 1d | ☐ | Side-by-side Markdown |
| D.7.3 | UI: revision timeline, accept/reject per suggestion | | 1d | ☐ | `RevisionView.tsx` |

---

## Sprint D-S6: SRE Hardening

### D.8 — Observability & SRE

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| D.8.2 | SLO/SLI dashboard: latency p95, error rate, availability, router accuracy | | 1.5d | ☐ | Grafana + Alertmanager |
| D.8.3 | Chaos engineering: kill GGUF, kill NIM, network partition | | 1.5d | ☐ | Runbook documented |
| D.8.4 | Backup/restore: rag_vault.db, registry.json, GGUF models | | 1d | ☐ | RTO < 5 min, RPO < 1 min |

---

## Exit Criteria Verification (Per Sprint)

### Sprint D-S1 Gate

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| S1-1 | All D.1 + D.8.1 tasks ☑ | | | ☐ |
| S1-2 | `pytest JAYA_CORE/tests/ JAYA_RESEARCH/tests/ -v` pass | | | ☐ |
| S1-3 | E2E test: query → router decision visible in trace | | | ☐ |
| S1-4 | Cache hit rate ≥ 30% on thesis chat workload | | | ☐ |
| S1-5 | Grafana dashboard shows router metrics | | | ☐ |

### Sprint D-S2 Gate

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| S2-1 | All D.2 + D.3 tasks ☑ | | | ☐ |
| S2-2 | `pytest ...` pass | | | ☐ |
| S2-3 | CLI `jaya-sync push/pull` works between two machines | | | ☐ |
| S2-4 | Evolution UI shows real-time gate status | | | ☐ |
| S2-5 | "Promote to Edge" button triggers deploy successfully | | | ☐ |

### Sprint D-S3 Gate

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| S3-1 | All D.4 tasks ☑ | | | ☐ |
| S3-2 | `pytest ...` pass | | | ☐ |
| S3-3 | Table QA benchmark ≥ 80% accuracy | | | ☐ |
| S3-4 | Thesis chat answers "table 3 shows..." correctly | | | ☐ |

### Sprint D-S4 Gate

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| S4-1 | All D.5 tasks ☑ | | | ☐ |
| S4-2 | `pytest ...` pass | | | ☐ |
| S4-3 | Voice chat works offline (WiFi off) → local STT+TTS+GGUF | | | ☐ |
| S4-4 | Voice chat online → routes to cloud for complex queries | | | ☐ |

### Sprint D-S5 Gate

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| S5-1 | All D.6 + D.7 tasks ☑ | | | ☐ |
| S5-2 | `pytest ...` pass | | | ☐ |
| S5-3 | Citation graph interactive: zoom, filter, click detail works | | | ☐ |
| S5-4 | Revision mode: diff view + accept/reject per suggestion | | | ☐ |

### Sprint D-S6 Gate

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| S6-1 | All D.8.2–D.8.4 tasks ☑ | | | ☐ |
| S6-2 | `pytest ...` pass | | | ☐ |
| S6-3 | SLO dashboard shows all 4 SLIs with alerts | | | ☐ |
| S6-4 | Chaos runbook executed: system recovers < 5 min | | | ☐ |
| S6-5 | Backup/restore drill: RTO < 5 min, RPO < 1 min verified | | | ☐ |

---

## Blocker / Risk Log (Fase D)

| Date | Risk | Sprint | Likelihood | Impact | Mitigation |
|------|------|--------|------------|--------|------------|
| | nv-ingest license / GPU req | D-S3 | Medium | High | Fallback: pdfplumber + custom table detection |
| | faster-whisper model size | D-S4 | Low | Medium | Use tiny/base model, quantize |
| | LAN sync conflict complexity | D-S2 | Medium | Medium | Start simple: LWW, add CRDT later |
| | React Flow performance large graphs | D-S5 | Medium | Low | Virtualize, cluster nodes |

---

## Daily Standup Notes (Append-only per Sprint)

```
## Sprint D-S1
YYYY-MM-DD: 
- Done: 
- Doing: 
- Blockers: 

## Sprint D-S2
YYYY-MM-DD: 
- Done: 
- Doing: 
- Blockers: 

... (repeat per sprint)
```

---

## Changelog Updates (Per Sprint)

| Sprint | CHANGELOG Entry | Date |
|--------|-----------------|------|
| D-S1 | `## [Unreleased] - Phase D Sprint 1: Hybrid Router + Tracing` | |
| D-S2 | `## [Unreleased] - Phase D Sprint 2: LAN Sync + Evolution UI` | |
| D-S3 | `## [Unreleased] - Phase D Sprint 3: Multimodal PDF` | |
| D-S4 | `## [Unreleased] - Phase D Sprint 4: Voice Agent` | |
| D-S5 | `## [Unreleased] - Phase D Sprint 5: Citation Graph + Revision` | |
| D-S6 | `## [Unreleased] - Phase D Sprint 6: SRE Hardening` | |

---

> **Phase D Complete** ketika semua 6 sprint gate ☑.  
> **Next:** Long-term vision items (model scaling, NPU, federated, auto-paper, plugins).