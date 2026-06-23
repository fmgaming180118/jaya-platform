# SRS (JAYA_CORE) — Spesifikasi Teknis untuk Otak AI Ringan & Offline-First

Versi: 0.1
Tanggal: 2026-05-30

## 1. Tujuan
Dokumen ini merinci kebutuhan fungsional dan non-fungsional untuk `JAYA_CORE` yang berfokus pada kemampuan offline, sinkronisasi efisien, dan non-destructive augmentation.

## 2. Scope
- Implementasi runtime inference ringan, local KB, delta-sync protocol, overlay augmentation mechanism, dan security requirements.

## 3. Kebutuhan Fungsional (FR)
FR-1: Local Inference Engine
- Core menyediakan runtime inference untuk model terdistilasi atau komponennya.
- Support running small models (quantized) and retrieval-augmented responses.

FR-2: Local Context Store
- Encrypted key-value store for conversation memory, personal facts, and small retrieval index.
- API: get_context(keys), put_context(k,v), list_context(prefix), delete_context(key).

FR-3: Delta Capture & Compression
- Track deltas from local learning and interactions; produce compressed upload packages.

FR-4: Sync Protocol
- Authenticated, E2E-encrypted channel.
- Operations: upload_delta(device_id, delta_package, metadata), fetch_augmentations(device_id, since_version).

FR-5: Merge & Augmentation Policy
- Central stores augmentations as overlays with provenance.
- Merge rules: prefer additive facts; detect contradictory statements and flag for human review or use confidence scoring.

FR-6: Versioning & Rollback
- Every augmentation and core model has semantic versioning; devices can request specific versions.

FR-7: Privacy Controls
- Field-level consent; allow selective upload filters (user can opt-out by data category).

FR-8: Resource Constraints & Scheduling
- Background sync scheduler respects battery/network conditions; allow manual sync.

## 4. Kebutuhan Non-Fungsional (NFR)
NFR-1: Footprint
- On-device disk for model + KB ≤ 200 MB for target phones; provide lighter profiles for constrained devices.

NFR-2: Latency
- Typical conversational turn response ≤ 300 ms local inference when model cached; retrieval ops ≤ 150 ms.

NFR-3: Reliability
- Sync must support resumable uploads, deduplication, and idempotency.

NFR-4: Security
- All persisted local stores encrypted (AES-256); keys protected by OS keystore when available.

NFR-5: Auditability
- Maintain tamper-evident logs for sync operations and augmentation application.

## 5. Interfaces
- Local API (library) for applications on device.
- Sync REST/gRPC endpoints at central: /upload_delta, /get_augmentations, /ack.

## 6. Data Models
- DeltaPackage: {device_id, timestamp, ops: [op], signature}
- Overlay: {overlay_id, source_devices, created_at, schema_version, payload_index}

## 7. Testing Requirements
- Unit tests for local store, delta generation, and merge logic.
- Integration tests for E2E sync using simulated network interruptions.

## 8. Performance Targets & Benchmarks
- Provide benchmark harness to measure model footprint, inference latency, and sync bandwidth per device.

## 9. Failure Modes & Recovery
- Lost uploads: resumable strategy with sequence numbers.
- Conflicting facts: maintain both facts with provenance and mark confidence; expose conflict resolution UI for human-in-the-loop.

## 10. Deployment Considerations
- OTA for augmentations and core model updates; central publishes signed packages.

## 11. Acceptance Criteria (tests)
- Local inference runs on target device profiles within latency and footprint budgets.
- E2E sync merges augmentations and device demonstrates expanded capability after fetch.

## 12. Next Technical Tasks
1. Prototype local KB (format, encryption, API).
2. Implement delta capture & compression (binary/JSON diff).
3. Implement central collector prototype and basic merge rules.
