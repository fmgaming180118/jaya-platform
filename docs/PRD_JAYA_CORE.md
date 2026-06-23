# PRD (JAYA_CORE) — Otak AI Ringan, Offline-First, Sinkronisasi Terpusat

Versi: 0.1
Tanggal: 2026-05-30

## 1. Tujuan
Membangun `JAYA_CORE` sebagai "otak" AI yang:
- Sangat pintar namun ringan — dapat berjalan pada device kecil (HP, embedded).
- Offline-first: mampu berinteraksi dan memahami konteks lokal tanpa koneksi pusat.
- Sinkronisasi aman dan efisien dengan pusat saat terkoneksi, menggabungkan pengetahuan lokal tanpa merusak identitas inti model.

## 2. Stakeholders
- Product Owner, Core Maintainers, Research Leads, DevOps, Security, End users (personal agents)

## 3. Use Case Prioritas
- UC1 (Offline Assistant): Ponsel menjalankan JAYA untuk percakapan, pengingat, dan konteks lokal.
- UC2 (Sync & Merge): Saat tersambung ke laptop/server pusat, hasil pembelajaran lokal dikirim, diolah, dan ditambahkan ke pusat.
- UC3 (Augmented Core): Pusat menggabungkan informasi dari banyak device menjadi model yang lebih kaya; perangkat yang kembali online mendapatkan pembaruan tanpa kehilangan personalisasi lokal.

## 4. MVP Fitur untuk JAYA_CORE
1. Lightweight inference engine (sub-models, distillation, retrieval-augmented local store).
2. Local context store: encrypted on-device knowledge base (KB) dan conversation memory.
3. Efficient sync protocol: delta-based uploads, authenticated & end-to-end encrypted transfer.
4. Merge policy: additive knowledge store model (augment pusat), conflict resolution rules, and versioning.
5. Model & config versioning with rollback support.

## 5. Success Metrics
- On-device model footprint ≤ 200 MB (target; can be tuned per device class).
- Inference latency on phone ≤ 300 ms (cold/hot varies) for basic conversational turns.
- Battery impact: background sync ≤ 2%/hour on idle schedule.
- Sync bandwidth per device avg ≤ 1 MB/day for normal usage (delta compressed uploads).

## 6. Constraints & Assumptions
- Devices have intermittent connectivity.
- Central server has higher compute & storage for aggregation and retraining.
- Privacy-first: user data default-private; uploads require consent and selective fields.

## 7. Security & Privacy
- All local stores encrypted at rest.
- Sync uses mutual TLS + token-based auth.
- Personal identifiers pseudonymized before central aggregation unless user consents.

## 8. Data Flow (high-level)
1. Device collects interactions -> updates local KB and learning deltas.
2. When connected & allowed, device uploads compressed deltas to central collector.
3. Central validates, aggregates from devices, and updates global knowledge/artifacts.
4. Central publishes augmentations (not necessarily replacing core identity) as versioned updates.

## 9. Promotion & Non-destructive Updates
- Core identity = canonical model weights + core policies; augmentations stored as overlay layers (metadata + retrieval indexes).
- On-device, overlays merged at inference time via retrieval; global retraining may incorporate aggregated device signals but only after gated evaluation.

## 10. Roadmap (High-level)
- Sprint 0 (2 wks): Define device classes, storage formats, and sync protocol draft.
- Phase 1 (6–8 wks): Implement lightweight inference + local KB + basic sync pipeline (delta upload + central collector).
- Phase 2 (8–12 wks): Merge policies, overlay system, gated aggregation pipeline, and sample deployments (phone + laptop).

## 11. Acceptance Criteria
- E2E test: phone offline conversation → sync to laptop → central aggregator ingests deltas → laptop receives augmentation and can answer extended queries.
- Security test: encryption and auth enforced; secrets not leaking.

## 12. Next Steps
- Turn each MVP feature into user stories and technical tasks.
- Prototype local KB format and delta diff algorithm.
