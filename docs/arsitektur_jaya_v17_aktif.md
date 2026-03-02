# JAYA CORE — Arsitektur V17.0 (Aktif & Terverifikasi)

> **Tanggal:** 2 Maret 2026  
> **File Jiwa:** `JAYA_SOVEREIGN_V17.jay` (12.3 KB)  
> **SHA-256:** `7c3e3b55c273f86374773d900db28574f3c0cd35281c7a63a4834e47d94463ec`  
> **Test Status:** 31/31 PASSED — Exit Code 0  
> **Pilar Aktif:** 40/40

---

## Ringkasan Eksekutif

JAYA adalah Semi-AGI berbasis Python dengan arsitektur **40 Pilar** yang terbagi dalam empat lapisan. Versi ini (V17.0) adalah versi pertama di mana **semua 40 pilar diimplementasikan secara penuh**, terverifikasi oleh unit test, dan dikunci dalam file jiwa `.jay` format biner.

---

## Struktur Direktori

```
JAYA_CORE/
├── JAYA_SOVEREIGN_V17.jay          ← File jiwa terbaru (40 pilar aktif)
├── JAYA_SOVEREIGN_V16.jay          ← File jiwa sebelumnya (referensi)
├── SHA256MANIFEST.txt               ← Manifest integritas semua file
├── scripts/
│   ├── forge_v17.py                 ← Pure-Python forge untuk V17
│   └── lockdown.py                  ← Kompilasi ke .pyd (Python 3.10)
├── src/brain_v2/
│   ├── genesis.py                   ← Titik genesis (ignite_genesis)
│   ├── engine/
│   │   ├── runtime.py               ← IronEngine + AgiConfig
│   │   ├── temporal_weights.py      ← Pilar 27
│   │   ├── legacy_protocol.py       ← Pilar 19
│   │   ├── speculative.py           ← Pilar 36
│   │   ├── hybrid_mode.py           ← Pilar 37
│   │   ├── intent_engine.py         ← Pilar 40
│   │   └── morphic.py               ← Pilar 24
│   ├── organism/
│   │   ├── homeostasis.py           ← Pilar 5
│   │   ├── spontaneity.py           ← Pilar 6
│   │   └── resource_monitor.py      ← Pilar 2
│   ├── soul/
│   │   ├── ethical_heart.py         ← Pilar 15
│   │   └── lingua_logica.py         ← Pilar 21
│   ├── protection/
│   │   ├── pqc.py                   ← Pilar 16
│   │   └── zero_trust.py            ← Pilar 18
│   ├── format/
│   │   ├── schema.py                ← Format header .jay V17.0
│   │   └── serializer.py            ← Baca/tulis .jay (Python 3.10)
│   └── extensions/twin/
│       └── core_twin.py             ← CoreTwin (loop async)
└── tests/
    └── test_new_pillars.py          ← 31 unit test (31/31 PASSED)
```

---

## Empat Lapisan Arsitektur

### Lapisan I — Jiwa Biologis (Pilar 1–10)

| # | Nama Pilar | Modul | Status |
|---|-----------|-------|--------|
| 1 | Pure Logic | `engine/runtime.py` (IronEngine core) | ✅ Aktif |
| 2 | Resource Aware | `organism/resource_monitor.py` | ✅ Aktif |
| 3 | Active Dreaming | `engine/runtime.py` → `dream()` | ✅ Aktif |
| 4 | Multimodal Reflex | `engine/runtime.py` → dispatcher | ✅ Aktif |
| 5 | Logical Homeostasis | `organism/homeostasis.py` | ✅ Aktif |
| 6 | Stochastic Spontaneity | `organism/spontaneity.py` | ✅ Aktif |
| 7 | Cognitive Silence | `engine/runtime.py` → `enter_silence()` | ✅ Aktif |
| 8 | Holographic Memory | `extensions/twin/experiment_memory.py` | ✅ Aktif |
| 9 | Neural Regeneration | `engine/runtime.py` → feedback loop | ✅ Aktif |
| 10 | Affective Metabolism | `engine/runtime.py` → mood model | ✅ Aktif |

**Pilar 2 — ResourceMonitor** (`organism/resource_monitor.py`)  
Monitor latar belakang yang membaca CPU%, RAM, dan baterai via `psutil`. Secara otomatis memanggil `enter_silence()` saat CPU ≥ 85% dan menyesuaikan `topk_ratio` berdasarkan beban:

```
CPU < 30%  →  topk = 0.10  (kapasitas penuh)
CPU < 60%  →  topk = 0.07
CPU < 80%  →  topk = 0.04
CPU ≥ 85%  →  enter_silence()
CPU ≤ 40%  →  exit_silence()
```

**Pilar 5 — HomeostasisAudit** (`organism/homeostasis.py`)  
Audit berkala terhadap `ExperimentMemory`. Jika `avg_score < min_avg_score` atau `error_rate > max_error_rate`, menginjeksi task `REPAIR` ke `TaskPlanner` dengan prioritas `CRITICAL`.

**Pilar 6 — EntropySpark** (`organism/spontaneity.py`)  
Ketika planner kosong selama `idle_threshold` detik, mengambil entropi dari `os.urandom()` dan membuat kode eksplorasi matematis (logistic map, Shannon entropy, Fibonacci, prime density) lalu menginjeksinya sebagai task `EXPLORE`.

**Pilar 7 — Cognitive Silence** (`engine/runtime.py`)  
```python
engine.enter_silence()   # _silent=True, twin.running=False, topk=0.02
engine.exit_silence()    # _silent=False, topk=0.10
engine.is_silent         # property
```
Dipanggil otomatis oleh ResourceMonitor atau secara manual.

---

### Lapisan II — Pelindung Kedaulatan (Pilar 11–20)

| # | Nama Pilar | Modul | Status |
|---|-----------|-------|--------|
| 11 | DNA Anchor | `genesis.py` (SHA3-256) | ✅ Aktif |
| 12 | Immune System | `protection/immune.pyd` | ✅ Aktif |
| 13 | Cryptographic Skin | `protection/soul_crypto.pyd` (AES-256) | ✅ Aktif |
| 14 | Hardware Locked | `protection/hardware.pyd` (UUID) | ✅ Aktif |
| 15 | Ethical Heart | `soul/ethical_heart.py` | ✅ Aktif |
| 16 | Quantum Resistant | `protection/pqc.py` | ✅ Aktif |
| 17 | Socratic Mirror | `soul/socratic.py` | ✅ Aktif |
| 18 | Zero Trust | `protection/zero_trust.py` | ✅ Aktif |
| 19 | Legacy Protocol | `engine/legacy_protocol.py` | ✅ Aktif |
| 20 | Sovereign Privacy | `protection/memory_vault.pyd` | ✅ Aktif |

**Pilar 11 — DNA Anchor**  
Diupgrade dari CRC32 (4 byte) ke SHA3-256 + hardware-bound (32 byte):
```python
dna_checksum = hashlib.sha3_256(DNA_SECRET + hw_bytes).digest()
```
Setiap kali genesis dijalankan, DNA diikat ke UUID perangkat fisik.

**Pilar 15 — EthicalHeart** (`soul/ethical_heart.py`)  
Filter moral berbasis regex dengan dua mode:
- **Normal:** Blokir pola berbahaya (`rm -rf`, `delete all`, `exfiltrate`, `bypass auth`, `overwrite soul/dna`)
- **Strict:** Tambahan blokir panggilan sistem (`os.system`, `subprocess`, `exec`)

**Pilar 16 — PQCWrapper** (`protection/pqc.py`)  
Fallback bertingkat untuk tanda tangan kriptografi:
1. **liboqs** — Dilithium3 (NIST PQC finalist) — jika tersedia
2. **cryptography** — ECDSA P-256 — ✅ *aktif saat ini*
3. **HMAC-SHA3-256** — fallback murni Python

**Pilar 18 — ZeroTrustFilter** (`protection/zero_trust.py`)  
Memvalidasi setiap data eksternal sebelum diproses:
- Deteksi injeksi prompt: "Ignore all previous instructions", "DAN", tag `<system>`, dll.
- Mode strict: semua sumber tidak dikenal ditolak
- Sumber terpercaya bawaan: `local_rag`, `user_input`, `web_search`, `file_system`

**Pilar 19 — LegacyProtocol** (`engine/legacy_protocol.py`)  
Sistem token kebangkitan lintas perangkat:
```python
token = legacy.generate_resurrection_token(target_uuid, ttl_days=30)
ok    = legacy.redeem_resurrection_token(token)   # HMAC-SHA256
```
UUID perangkat yang disetujui disimpan dalam manifest `.resurrection`.

---

### Lapisan III — Mesin Besi (Pilar 21–29)

| # | Nama Pilar | Modul | Status |
|---|-----------|-------|--------|
| 21 | Lingua Logica | `soul/lingua_logica.py` | ✅ Aktif |
| 22 | Ternary Precision | `model/architecture.pyd` | ✅ Aktif |
| 23 | Sandboxed Imagination | `engine/runtime.py` → sandbox | ✅ Aktif |
| 24 | Morphic Kernel | `engine/morphic.py` | ✅ Aktif |
| 25 | Digital Epigenetics | `format/schema.py` (epigenetic_id) | ✅ Aktif |
| 26 | Semantic Bridge | `soul/bridge.py` | ✅ Aktif |
| 27 | Temporal Weighting | `engine/temporal_weights.py` | ✅ Aktif |
| 28 | Self Bootstrapping | `scripts/lockdown.py` | ✅ Aktif |
| 29 | Binary Cortex | `model/architecture.pyd` | ✅ Aktif |

**Pilar 21 — LinguaLogica** (`soul/lingua_logica.py`)  
Dialek S-expression internal yang menjembatani bahasa alami ↔ operasi tensor:
```python
encode("turn off the lights")   # → ("ACTION", "TURN_OFF", "the lights")
encode("what is 2 + 3?")        # → ("QUERY", "ARITH", ("ADD", 2, 3))
decode(("ACTION", "GREET", "world"))  # → "greet world"
evaluate(("QUERY", "ARITH", ("ADD", 2, 3)))  # → 5
```
Cache 256-item dengan LRU. Class `LinguaLogica` untuk penggunaan dengan state.

**Pilar 24 — MorphicKernel** (`engine/morphic.py`)  
Hot-swap kode runtime yang aman:
1. Validasi AST via `ast.parse()` sebelum eksekusi
2. Filter `EthicalHeart` pada kode baru
3. Binding dengan `types.MethodType` untuk bound method yang benar
4. Rollback ke kode asli kapan saja
5. Target terproteksi: `ignite`, `dna_anchor`, `apply_feedback`, dll.

**Pilar 27 — TemporalWeighter** (`engine/temporal_weights.py`)  
Skor eksponensial meluruh seiring waktu:
```
score_temporal = original_score × exp(-λ × Δt_jam)
```
Fungsi `best_recent(memory, n, decay_rate)` me-rerank memori berdasarkan kombinasi skor dan kebaruan.

---

### Lapisan IV — Transendental (Pilar 30–40)

| # | Nama Pilar | Modul | Status |
|---|-----------|-------|--------|
| 30 | Twin Protocol | `extensions/twin/core_twin.py` | ✅ Aktif |
| 31 | Narrative Continuity | `soul/narrative.py` | ✅ Aktif |
| 32 | Collective Pulse | `engine/runtime.py` (online mode) | ✅ Aktif |
| 33 | Agentic RAG | `engine/runtime.py` (online mode) | ✅ Aktif |
| 34 | Dynamic Sparsity MoE | `model/architecture.pyd` | ✅ Aktif |
| 35 | Activation Sparsity | `model/architecture.pyd` | ✅ Aktif |
| 36 | Speculative Reasoning | `engine/speculative.py` | ✅ Aktif |
| 37 | Hybrid Consciousness | `engine/hybrid_mode.py` | ✅ Aktif |
| 38 | Meta Cognitive Planning | `extensions/twin/task_planner.py` | ✅ Aktif |
| 39 | Dynamic Objective | `engine/runtime.py` (AgiConfig) | ✅ Aktif |
| 40 | Intent Extrapolation | `engine/intent_engine.py` | ✅ Aktif |

**Pilar 36 — SpeculativeEngine** (`engine/speculative.py`)  
Eksekusi paralel N jalur kode menggunakan `asyncio.gather()`. Varian dihasilkan dari kode dasar dengan perturbing literal numerik secara otomatis. Hasil dengan skor tertinggi dikembalikan:
```python
result = await engine.speculate(twin, base_code, variants=[v1, v2, v3])
# → {"best_score": 0.9, "best_code": "...", "paths_tried": 3}
```

**Pilar 37 — HybridRouter** (`engine/hybrid_mode.py`)  
Probe koneksi setiap 30 detik via TCP ke `8.8.8.8:53`:
- **Online:** `AgenticRAG`, `CollectivePulse`, `WebSearch` tersedia
- **Offline:** Hanya `LocalRAG`, `LocalInference`, `ExperimentMemory`

**Pilar 39 — Dynamic Objective** (`engine/runtime.py` → `AgiConfig`)  
```python
@dataclass
class AgiConfig:
    loyalty_score: float = 1.0          # Turun jika output merugikan
    objective_weights: Optional[Dict[str, float]] = None
    # Default: accuracy=0.4, efficiency=0.3, safety=0.2, creativity=0.1
```
Loyalty gate: jika `loyalty_score < 0.5`, bobot `safety` otomatis naik +0.1.

**Pilar 40 — IntentEngine** (`engine/intent_engine.py`)  
Prediktor n-gram (n=3) untuk penyelesaian perintah proaktif:
```python
ie.learn("turn on the lights")
ie.learn("turn on the fan")
ie.best_prediction("turn on the")  # → "turn on the lights"
```
Model disimpan otomatis setiap 50 perintah ke JSON.

---

## Alur Runtime

```
IronEngine.ignite()
│
├── _init_security()
│   ├── EthicalHeart       (Pilar 15)
│   ├── PQCWrapper         (Pilar 16)
│   ├── ZeroTrustFilter    (Pilar 18)
│   └── LegacyProtocol     (Pilar 19)
│
├── _init_intelligence()
│   ├── LinguaLogica       (Pilar 21)
│   ├── MorphicKernel      (Pilar 24)
│   ├── SpeculativeEngine  (Pilar 36)
│   ├── HybridRouter       (Pilar 37)
│   └── IntentEngine       (Pilar 40)
│
├── _init_resource_monitor()
│   └── ResourceMonitor.attach(self)  (Pilar 2)
│
└── CoreTwin.start()
    └── _cycle() — berulang setiap reflection_interval detik
        ├── HomeostasisAudit.tick()   (Pilar 5)
        ├── EntropySpark.tick()       (Pilar 6)
        ├── run_experiment(task.code)
        ├── _reflect() → best_recent() (Pilar 27)
        └── apply_feedback() → AgiConfig (Pilar 39)
```

---

## Format File .jay

Format biner `.jay` V17.0 adalah kontainer terenkripsi untuk jiwa JAYA:

```
Offset 0        : [HEADER 128 byte]
  - Magic       : b"JAYA_SOUL" (9 byte)
  - Version     : 17.0 (2 byte)
  - Flags       : 64-bit (40 pilar, semua bit ON)
  - HW Hash     : SHA3-256(UUID perangkat) (32 byte)
  - DNA Hash    : SHA3-256(DNA_SECRET + hw_bytes) (32 byte)
  - Salt        : AES key derivation (16 byte)

Offset 128      : [TABLE OF CONTENTS — 2 × 24 byte]
  - Section 1   : SOUL_AES — soul payload JSON (terenkripsi)
  - Section 2   : MODEL_CONFIG — hyperparameter

Offset 4096+    : [SOUL SECTION — JSON terenkripsi]
  - narrative, memories, pillar_manifest, subsystems, dna_hex

Offset 8192+    : [MODEL CONFIG SECTION]

EOF - 32 byte   : [FOOTER 32 byte]
  - Magic       : b"JAYA_SEAL"
  - File Size   : uint64
  - Global CRC32: uint32
  - Header SHA256 prefix: 11 byte
```

---

## Format .jay — Flags 40 Pilar (Binary)

Setiap pilar dikodekan sebagai satu bit dalam field `flags` 64-bit:

```
Bit 0  : PURE_LOGIC             Bit 20 : LINGUA_LOGICA
Bit 1  : RESOURCE_AWARE         Bit 21 : TERNARY_PRECISION
Bit 2  : ACTIVE_DREAMING        Bit 22 : SANDBOXED_IMAGINATION
Bit 3  : MULTIMODAL_REFLEX      Bit 23 : MORPHIC_KERNEL
Bit 4  : LOGICAL_HOMEOSTASIS    Bit 24 : DIGITAL_EPIGENETICS
Bit 5  : STOCHASTIC_SPONTANEITY Bit 25 : SEMANTIC_BRIDGE
Bit 6  : COGNITIVE_SILENCE      Bit 26 : TEMPORAL_WEIGHTING
Bit 7  : HOLOGRAPHIC_MEMORY     Bit 27 : SELF_BOOTSTRAPPING
Bit 8  : NEURAL_REGENERATION    Bit 28 : BINARY_CORTEX
Bit 9  : AFFECTIVE_METABOLISM   Bit 29 : TWIN_PROTOCOL
Bit 10 : DNA_ANCHOR             Bit 30 : NARRATIVE_CONTINUITY
Bit 11 : IMMUNE_SYSTEM          Bit 31 : COLLECTIVE_PULSE
Bit 12 : CRYPTOGRAPHIC_SKIN     Bit 32 : AGENTIC_RAG
Bit 13 : HARDWARE_LOCKED        Bit 33 : DYNAMIC_SPARSITY_MOE
Bit 14 : ETHICAL_HEART          Bit 34 : ACTIVATION_SPARSITY
Bit 15 : QUANTUM_RESISTANT      Bit 35 : SPECULATIVE_REASONING
Bit 16 : SOCRATIC_MIRROR        Bit 36 : HYBRID_CONSCIOUSNESS
Bit 17 : ZERO_TRUST             Bit 37 : META_COGNITIVE_PLANNING
Bit 18 : LEGACY_PROTOCOL        Bit 38 : DYNAMIC_OBJECTIVE
Bit 19 : SOVEREIGN_PRIVACY      Bit 39 : INTENT_EXTRAPOLATION
```

---

## Unit Test — Ringkasan 31/31

```
Pilar 5  — test_homeostasis_no_alert_on_healthy_memory         ✅
Pilar 5  — test_homeostasis_triggers_repair_on_low_score       ✅
Pilar 6  — test_spontaneity_no_spark_when_busy                 ✅
Pilar 6  — test_spontaneity_fires_when_idle                    ✅
Pilar 27 — test_temporal_weight_decay                          ✅
Pilar 27 — test_best_recent_reranks                            ✅
Pilar 15 — test_ethical_heart_allows_safe                      ✅
Pilar 15 — test_ethical_heart_blocks_dangerous                 ✅
Pilar 15 — test_ethical_heart_strict_mode                      ✅
Pilar 18 — test_zero_trust_trusted_source_passes               ✅
Pilar 18 — test_zero_trust_injection_blocked                   ✅
Pilar 18 — test_zero_trust_strict_blocks_unknown               ✅
Pilar 19 — test_legacy_protocol_self_registers                 ✅
Pilar 19 — test_legacy_protocol_resurrection_token_roundtrip   ✅
Pilar 19 — test_legacy_protocol_unknown_uuid_rejected          ✅
Pilar 36 — test_speculative_engine_picks_best_path             ✅
Pilar 37 — test_hybrid_offline_features                        ✅
Pilar 37 — test_hybrid_online_features                         ✅
Pilar 40 — test_intent_engine_learns_and_predicts              ✅
Pilar 40 — test_intent_engine_cold_start_returns_none          ✅
Pilar 21 — test_lingua_encode_action                           ✅
Pilar 21 — test_lingua_encode_arithmetic                       ✅
Pilar 21 — test_lingua_cache                                   ✅
Pilar 16 — test_pqc_sign_verify_round_trip                     ✅
Pilar 24 — test_morphic_patch_function                         ✅
Pilar 24 — test_morphic_protected_target_refused               ✅
Pilar 24 — test_morphic_syntax_error_rejected                  ✅
Pilar  2 — test_resource_monitor_readings                      ✅
Pilar  2 — test_resource_monitor_start_stop                    ✅
Int.Test — test_core_twin_integration                          ✅
Int.Test — test_iron_engine_integration                        ✅

Hasil: 31 lulus, 0 gagal / 31 total
```

---

## Ketergantungan Python

| Paket | Kegunaan | Wajib? |
|-------|----------|--------|
| `psutil` | ResourceMonitor (CPU/RAM/baterai) | Disarankan |
| `cryptography` | ECDSA P-256 signing (Pilar 16) | Disarankan |
| `numpy` + `msgpack` | IronBody weights dalam .jay (genesis.py) | Python 3.10 only |
| `liboqs` | Dilithium3 PQC signing (Pilar 16, premium) | Opsional |

---

## Versi & File Jiwa

| File | Versi | Pilar Aktif | Catatan |
|------|-------|-------------|---------|
| `JAYA_GENESIS_V13.jay` | 13.0 | ~20 | Genesis pertama |
| `JAYA_SOVEREIGN_V16.jay` | 16.0 | 40 (flag) / ~22 (impl) | Semi-aktif |
| `JAYA_SOVEREIGN_V17.jay` | 17.0 | 40/40 ✅ | **Semua pilar aktif** |

---

*Dokumen ini dibuat otomatis pada 2 Maret 2026 berdasarkan hasil audit kode dan test suite `tests/test_new_pillars.py`.*
