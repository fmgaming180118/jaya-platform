# Fase D — Ecosystem Bridge

> **Estimasi:** Berkelanjutan (ongoing)  
> **Prasyarat:** [Fase C selesai](phase-c-distillation-edge.md) (minimal C.3 untuk D.1)  
> **Tujuan:** Menyatukan JAYA_RESEARCH (cloud lab) dan JAYA_CORE (offline runtime) menjadi ekosistem terpadu dengan fitur lanjutan multimodal dan voice.

---

## Konteks Masalah

| Area | Kondisi saat ini | Target Fase D |
|------|------------------|---------------|
| CORE ↔ RESEARCH | Terpisah, artefak manual | Router & sync otomatis |
| Evolution UI | Halaman ada, data statis | Live registry + manifest |
| PDF ingest | Teks saja | Tabel & gambar (multimodal) |
| Voice agent | Eksperimental, terisolasi | Terintegrasi UI utama |
| Hierarki konektivitas | Dokumentasi CORE saja | Diterapkan di RESEARCH runtime |

---

## Workflow Anak

| ID | Nama | Dokumen | Bergantung pada | Prioritas |
|----|------|---------|-----------------|-----------|
| **D.1** | Unified Chat Router | [d1-unified-router.md](workflows/phase-d/d1-unified-router.md) | Fase C.3 | Tinggi |
| **D.2** | Knowledge Sync | [d2-knowledge-sync.md](workflows/phase-d/d2-knowledge-sync.md) | D.1, Fase A | Tinggi |
| **D.3** | Evolution UI | [d3-evolution-ui.md](workflows/phase-d/d3-evolution-ui.md) | Fase C | Sedang |
| **D.4** | Multimodal PDF | [d4-multimodal-pdf.md](workflows/phase-d/d4-multimodal-pdf.md) | Fase A | Sedang |
| **D.5** | Voice Integration | [d5-voice-integration.md](workflows/phase-d/d5-voice-integration.md) | D.1 | Rendah |

**Catatan:** Fase D bersifat iteratif. Workflow bisa dikerjakan paralel setelah dependensi terpenuhi. Tidak wajib menyelesaikan semua untuk menutup milestone awal Fase D — lihat **Milestone D.0** di bawah.

---

## Milestone Fase D

### Milestone D.0 (Minimum Viable Bridge)
Selesai jika D.1 + D.3 checklist selesai.

### Milestone D.1 (Full Ecosystem)
Selesai jika **semua** workflow D.1–D.5 selesai.

---

## Master Checklist Fase D

### D.1 — Unified Chat Router
- [ ] Semua item di [d1-unified-router.md](workflows/phase-d/d1-unified-router.md) selesai

### D.2 — Knowledge Sync
- [ ] Semua item di [d2-knowledge-sync.md](workflows/phase-d/d2-knowledge-sync.md) selesai

### D.3 — Evolution UI
- [ ] Semua item di [d3-evolution-ui.md](workflows/phase-d/d3-evolution-ui.md) selesai

### D.4 — Multimodal PDF
- [ ] Semua item di [d4-multimodal-pdf.md](workflows/phase-d/d4-multimodal-pdf.md) selesai

### D.5 — Voice Integration
- [ ] Semua item di [d5-voice-integration.md](workflows/phase-d/d5-voice-integration.md) selesai

### Verifikasi Integrasi Fase (Milestone D.1)
- [ ] Query ringan dijawab student lokal; query kompleks ke NIM — tanpa konfigurasi manual per request
- [ ] Halaman Evolution menampilkan policy aktif dari `registry.json`
- [ ] PDF berisi tabel bisa di-query via RAG
- [ ] Voice chat dari UI memanggil backend terpadu
- [ ] Dokumen arsitektur `overview.md` mencerminkan hierarki Lokal → LAN → Internet

---

## Kriteria Selesai Fase D

**Milestone D.0 selesai** jika D.1 + D.3 terpenuhi.

**Fase D penuh selesai** jika:

1. **Router** otomatis memilih local/cloud berdasarkan kompleksitas & ketersediaan.
2. **Knowledge** bisa disinkronkan antara workspace RESEARCH dan `rag_vault.db` CORE.
3. **Evolution UI** live — deploy status, manifest signature, rollback.
4. **Multimodal** ingest untuk minimal tabel PDF.
5. **Voice** terhubung ke chat router (bukan pipeline terpisah).

---

## File Utama yang Terdampak

```
JAYA_RESEARCH/src/teacher.py
JAYA_RESEARCH/src/network/research_api.py
JAYA_RESEARCH/ui/src/pages/EvolutionPage.jsx
JAYA_RESEARCH/ui/src/pages/ChatPage.jsx
JAYA_RESEARCH/src/voice_agent/
JAYA_CORE/src/ (AgenticRAG, evolution_gate)
JAYA_CORE/data/policies/registry.json
```

---

**Sebelumnya:** [Fase C](phase-c-distillation-edge.md)
