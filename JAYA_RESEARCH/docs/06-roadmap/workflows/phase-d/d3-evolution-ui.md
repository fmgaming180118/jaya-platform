# Workflow D.3 — Evolution UI & Registry Live

> **Fase:** [D — Ecosystem Bridge](../../phase-d-ecosystem-bridge.md)  
> **Estimasi:** 4–6 hari  
> **Prasyarat:** [Fase C](../../phase-c-distillation-edge.md)  
> **Tujuan:** Halaman Evolution di React menampilkan data live dari `registry.json`, manifest, dan status gate.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `ui/src/pages/EvolutionPage.jsx` | UI utama |
| `src/network/research_api.py` | Endpoint evolution |
| `JAYA_CORE/data/policies/registry.json` | Source of truth |
| `JAYA_CORE/evolution/manifests/` | Signed manifests |

---

## Checklist Backend

### 1. API Endpoints
- [ ] `GET /evolution/policies` — baca registry (path configurable ke JAYA_CORE)
- [ ] `GET /evolution/manifest/{policy_id}` — manifest + signature status
- [ ] `GET /evolution/candidates` — list candidate JSON + decision
- [ ] `GET /evolution/edge-deploy` — GGUF files, size, quant type
- [ ] Error jika JAYA_CORE path tidak ditemukan

### 2. Security
- [ ] Read-only — tidak expose private key HMAC
- [ ] Validate path traversal pada `policy_id`

---

## Checklist Frontend

### 1. EvolutionPage.jsx
- [ ] Tabel policy: id, type, base_model, status, deployed_at
- [ ] Detail panel: metadata (teacher, epochs, VRAM target)
- [ ] Manifest card: version, signature valid/invalid badge
- [ ] Edge deploy card: GGUF filenames + size MB
- [ ] Candidate history: ACCEPT/REJECT dengan reason

### 2. UX
- [ ] Loading & error states
- [ ] Auto-refresh setiap 60 detik (opsional)
- [ ] Link ke dokumentasi QLoRA/distillation

---

## Checklist Testing

- [ ] UI menampilkan 2 policy aktif dari registry saat ini
- [ ] Manifest signature ditampilkan sebagai valid (verify HMAC di backend)
- [ ] Policy baru setelah deploy muncul tanpa ubah kode UI

---

## Kriteria Selesai Workflow D.3

- [ ] Evolution page bukan placeholder — data real dari CORE
- [ ] `api-reference.md` terupdate dengan endpoint evolution

---

**Sebelumnya:** [D.2](d2-knowledge-sync.md) · **Berikutnya:** [D.4 Multimodal PDF](d4-multimodal-pdf.md)
