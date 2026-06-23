# Software Requirements Specification (SRS) — JAYA AI Platform

Versi: 0.1
Tanggal: 2026-05-30

## 1. Tujuan Dokumen
Dokumen ini merinci kebutuhan fungsional dan non-fungsional untuk implementasi awal JAYA: pemisahan antara `JAYA_CORE` (production brain) dan `JAYA_RESEARCH` (experiments & recursive prototypes).

## 2. Ruang Lingkup Sistem
- Sistem terbagi menjadi dua subsistem: `JAYA_CORE` (runtime, inference, model management) dan `JAYA_RESEARCH` (eksperimen, dataset, prototipe recursive).

## 3. Definisi, Akronim, dan Singkatan
- JayaIR: intermediate representation untuk runtime
- Core: `JAYA_CORE` runtime
- Research: `JAYA_RESEARCH`

## 4. Gambaran Sistem (High-level)
- `JAYA_CORE` exposes a well-defined API (in-process or via IPC) for model inference, health, and metrics.
- `JAYA_RESEARCH` contains sandboxed experiments, datasets, and tooling to produce artefak yang dapat dievaluasi dan dipromosikan.

## 5. Kebutuhan Fungsional (FR)
FR-1: Core Inference API
- Deskripsi: Core menyediakan endpoint/library untuk inference synchronous.
- Input: model id, input payload
- Output: inference result

FR-2: Model Management
- Deskripsi: Registrasi model, versioning, checksum, metadata.

FR-3: Research Sandbox Management
- Deskripsi: Isolasi environment (requirements, data), runtime limits, and run metadata tracking.

FR-4: Promotion Workflow
- Deskripsi: Research artefacts dapat diajukan ke core dengan PR yang menyertakan kontrak API, tests, dan audit deps.

## 6. Kebutuhan Non-Fungsional (NFR)
NFR-1: Keamanan
- Secrets tidak pernah disimpan di repo.

NFR-2: Performa
- Core inference latency dan throughput harus dipantau; benchmark p50/p95 harus dalam threshold yang disepakati.

NFR-3: Reproducibility
- All experiment runs must record seed, environment, and data snapshot references.

NFR-4: Maintainability
- Code harus modular; core modules harus independen dari research-only dependencies.

## 7. Data Requirements
- Dataset eksperimen disimpan di `JAYA_RESEARCH/data/` (metadata + provenance). Tidak ada data sensitif di repo.

## 8. Interface Requirements
- Internal API between research artefacts and core harus melalui explicit contracts (JSON Schema / OpenAPI minimal) and versioned.

## 9. Architecture & Mapping ke Repos
- `JAYA_CORE/src/` — runtime core, model serving, jayaIR executor
- `JAYA_RESEARCH/src/` — experiment harness, recursive prototypes

## 10. Testing & Validation
- Unit tests, integration tests, benchmark tests.
- Promotion acceptance requires passing integration test suite against a core sandbox.

## 11. Deployment & CI
- CI must run unit tests, secret-scan, and benchmark gate for core changes.

## 12. Traceability Matrix (sample)
- FR-1 -> Unit tests: `JAYA_CORE/tests/test_inference.py`
- FR-4 -> Integration tests: `JAYA_CORE/tests/test_promotion_integration.py` (to be created)

## 13. Risks & Mitigations
- Risk: Research code accidentally imported in core. Mitigation: CI boundary checks, review policies.
- Risk: Performance regressions. Mitigation: benchmark gate + revert plan.

## 14. Acceptance Criteria (SRS)
- All FRs have at least one passing test case.
- NFRs have monitoring & benchmarks defined.

## 15. Next Steps
- Review SRS and PRD; expand FRs into user stories and tasks; create initial test harness for FR-1.
