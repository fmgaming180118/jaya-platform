# Desain Internal JAYA Core

**Status:** IDEA → PROTOTYPE (bagian berbeda pada tahap berbeda)
**Berlaku mulai:** 2 Agustus 2026
**ADR terkait:** ADR-009, ADR-010

---

## 1. Posisi JAYA Core dalam Ekosistem

JAYA Core adalah otak kognitif aktif JAYA. Ia bukan aplikasi, bukan model bahasa,
dan bukan kumpulan fitur. JAYA Core adalah sistem eksplisit yang mengelola:

- pemahaman maksud pengguna;
- konteks dan memori aktif;
- penalaran dan pembentukan rencana;
- pengambilan keputusan dan evaluasi risiko;
- pemilihan model dan tool;
- produksi JayaIR sebagai bahasa internal;
- refleksi dan evaluasi hasil;
- penerimaan candidate artifact dari Research;
- rollback dan keamanan kognitif.

Model bahasa adalah salah satu mesin yang digunakan Core untuk berpikir —
bukan keseluruhan Core itu sendiri.

---

## 2. Prinsip Desain

### Portabel dan Berlapis

JAYA Core bukan monolith. Ia terdiri dari dua lapisan:

1. **Cognitive Kernel** — bagian minimum yang dapat berjalan di semua node,
   dari komputer pusat hingga perangkat edge kecil.
2. **Capability Packs** — modul tambahan yang dipasang sesuai kemampuan perangkat.

### Domain-Neutral

Core tidak boleh mengenal domain tertentu (tesis, CAD, robotika, dsb.) secara
langsung. Domain adapter mendaftarkan strateginya ke Core melalui registry terbuka.

### Budget-Aware

Sebelum memulai penalaran, Core memeriksa resource yang tersedia dan memilih
strategi yang sesuai.

### Evidence-Bounded

Core hanya menerima pengetahuan yang sudah dikemas, divalidasi, disetujui, dan
dapat dibatalkan melalui promotion pipeline.

---

## 3. Cognitive Kernel — Bagian Minimum JAYA Core

Cognitive Kernel adalah bagian Core yang **wajib ada di semua node JAYA**, dari
komputer pusat hingga perangkat edge. Ia harus tetap ringan dan tidak bergantung
pada model bahasa besar.

```text
JAYA Cognitive Kernel
├── 3.1  Identity Module
├── 3.2  Intent Contract Engine
├── 3.3  Minimal Context Store
├── 3.4  Permission Policy Enforcer
├── 3.5  Capability Registry
├── 3.6  JayaIR Interpreter
├── 3.7  Memory Interface
├── 3.8  Node Communication Layer
├── 3.9  Safety Rule Engine
├── 3.10 State Synchronization Manager
└── 3.11 Update and Rollback Verifier
```

### 3.1 Identity Module

Menyimpan dan memverifikasi identitas node dan pengguna.

```json
{
  "jaya_identity": "jaya-fachri",
  "node_id": "armor-01",
  "node_role": "MISSION_NODE",
  "node_key_fingerprint": "SHA256:...",
  "registered_by": "home-central",
  "registered_at": "2026-08-02T00:00:00Z"
}
```

Identitas JAYA tetap satu lintas semua node. Node memiliki identitas perangkat
yang berbeda, tetapi merujuk ke satu `jaya_identity`.

### 3.2 Intent Contract Engine

Menerima input dari interface (suara, teks, sensor) dan menghasilkan representasi
terstruktur maksud pengguna sebelum diserahkan ke komponen lain.

Kontrak intent minimum:

```json
{
  "intent_id": "int-20260802-001",
  "raw_input": "buat desain casing PC mini yang punya pendinginan baik",
  "intent_type": "CREATE_ARTIFACT",
  "domain": "cad.3d_design",
  "object": "mini_pc_case",
  "constraints": {
    "thermal": "good_airflow",
    "form_factor": "compact"
  },
  "missing_context": ["motherboard_size", "gpu_dimension", "manufacturing_method"],
  "clarification_required": true,
  "confidence": 0.82
}
```

### 3.3 Minimal Context Store

Working memory lokal yang menyimpan konteks tugas aktif. Dibersihkan setelah
tugas selesai atau setelah timeout yang dikonfigurasi.

Bukan tempat penyimpanan seluruh riwayat atau dokumen mentah.

### 3.4 Permission Policy Enforcer

Setiap tindakan yang akan dieksekusi melewati gate ini sebelum diteruskan ke Agent.

```text
Tindakan masuk
     ↓
Klasifikasi risiko
     ↓
┌────────────────────────────────────┐
│ SAFE_INTERNAL    → lanjutkan       │
│ SAFE_WITH_LOG    → lanjutkan + log │
│ REQUIRES_CONFIRM → tanya pengguna  │
│ RESTRICTED       → tolak + alasan  │
│ FORBIDDEN        → blokir + audit  │
└────────────────────────────────────┘
```

### 3.5 Capability Registry

Daftar kemampuan yang tersedia di node saat ini, diperbarui secara dinamis.

```json
{
  "node_id": "laptop-01",
  "capabilities": {
    "reasoning.lite": { "available": true, "version": "1.2" },
    "reasoning.full": { "available": true, "version": "2.0" },
    "voice.recognition": { "available": true, "version": "1.0" },
    "vision.basic": { "available": false, "reason": "no_camera" },
    "cad.parametric": { "available": false, "reason": "pack_not_installed" }
  },
  "updated_at": "2026-08-02T02:00:00Z"
}
```

Ketika capability tidak tersedia, Core dapat:
- meminta pengguna mengaktifkan pack;
- mendelegasikan tugas ke node lain melalui Mesh; atau
- memberitahu pengguna bahwa kemampuan tidak tersedia di perangkat ini.

### 3.6 JayaIR Interpreter

Memproses dan menghasilkan representasi internal terstruktur (JayaIR) yang
menjadi bahasa komunikasi antara Core, Agent, dan node lain.

Lihat Section 7 untuk spesifikasi JayaIR.

### 3.7 Memory Interface

Abstraksi akses memori. Komponen lain tidak boleh mengakses memori secara langsung.
Interface ini menentukan:

- jenis memori yang diakses (working, episodic, semantic, procedural);
- izin baca/tulis per operasi;
- quota dan TTL;
- sinkronisasi dengan node lain.

### 3.8 Node Communication Layer

Mengelola komunikasi antarnode melalui JAYA Mesh. Mengenkripsi, menandatangani,
dan memverifikasi setiap pesan antarnode.

### 3.9 Safety Rule Engine

Aturan keamanan dasar yang tidak dapat dinonaktifkan oleh kemampuan apapun:

- tidak boleh menghapus data tanpa konfirmasi eksplisit;
- tidak boleh memodifikasi file system tanpa izin;
- tidak boleh mengaktifkan kemampuan baru tanpa promotion gate;
- tidak boleh meneruskan data sensitif ke node yang tidak terotorisasi.

### 3.10 State Synchronization Manager

Mengelola sinkronisasi state antara node. Menyimpan event log lokal yang
ditandatangani untuk dikirim ke node lain saat koneksi tersedia.

### 3.11 Update and Rollback Verifier

Setiap update yang masuk ke node harus diverifikasi:

- signature dari node yang berwenang;
- hash payload;
- kompatibilitas versi;
- ketersediaan rollback point.

---

## 4. Capability Packs — Modul Tambahan

Capability packs dipasang terpisah dari Cognitive Kernel. Setiap pack memiliki:

- manifest dengan dependency dan resource minimum;
- rollback point;
- izin yang diperlukan.

### Daftar Capability Packs yang Direncanakan

| Pack | Komponen | Node minimum | Status |
|---|---|---|---|
| `reasoning.lite` | Penalaran ringkas, aturan lokal | Edge | PROTOTYPE |
| `reasoning.full` | Penalaran mendalam, beberapa kandidat | Standard | IMPLEMENTED |
| `voice.recognition` | Speech-to-text lokal | Edge | PROTOTYPE |
| `voice.synthesis` | Text-to-speech lokal | Edge | PROTOTYPE |
| `vision.basic` | Deteksi objek dasar | Edge | IDEA |
| `vision.advanced` | Pemahaman scene dan konteks visual | Standard | IDEA |
| `coding.assistant` | Analisis dan penulisan kode | Standard | IDEA |
| `cad.basic` | Geometri primitif, konsep 3D | Standard | IDEA |
| `cad.parametric` | Desain parametrik, assembly | Central | IDEA |
| `cad.simulation` | Simulasi aliran udara, struktural | Central | IDEA |
| `robotics.navigation` | Navigasi dan path planning | Mission Node | IDEA |
| `robotics.control` | Kontrol aktuator | Mission Node | IDEA |
| `home.automation` | Protokol smart home | Edge | IDEA |
| `research.connector` | Koneksi ke JAYA Research Central | Standard | PROTOTYPE |
| `spatial.ar` | Pemrosesan konteks ruang untuk AR | Standard | IDEA |
| `model.router` | Routing permintaan ke model yang tepat | semua | IMPLEMENTED (partial) |

Status:
- **IDEA** — dikonsepkan, belum ada implementasi
- **PROTOTYPE** — ada implementasi awal, belum diuji sepenuhnya
- **IMPLEMENTED** — ada implementasi, diuji lokal
- **VERIFIED** — diuji pada perangkat nyata dengan benchmark

---

## 5. Model Router — Memilih Model Berdasarkan Resource

Core tidak boleh selalu menggunakan model terbesar atau terbaik. Sebelum
memilih model, Core memeriksa:

```text
Permintaan masuk
      ↓
Analisis: kompleksitas, privasi, latensi, koneksi
      ↓
Cek resource: RAM, CPU/GPU, baterai, suhu, bandwidth
      ↓
┌─────────────────────────────────────────────────────┐
│ Model lokal sangat kecil  (< 500 MB, < 512 MB RAM)  │
│ Model lokal ringan        (< 2 GB, < 2 GB RAM)      │
│ Model lokal utama         (< 8 GB, < 8 GB RAM)      │
│ Model Central             (diteruskan ke node pusat)│
│ Provider cloud (opsional) (dengan izin eksplisit)   │
└─────────────────────────────────────────────────────┘
      ↓
Pilih model yang memenuhi kebutuhan dan resource
```

Aturan routing:

| Kondisi | Strategi |
|---|---|
| Baterai < 20% | Hanya model lokal sangat kecil |
| Offline | Hanya model lokal yang tersedia |
| Suhu > threshold | Turunkan kelas model |
| Privasi tinggi | Tolak cloud, gunakan lokal saja |
| Latency kritis | Model lokal tercepat |
| Kompleksitas tinggi + resource cukup | Model utama atau Central |

Model bukan identitas JAYA. Mengganti model tidak mengganti kepribadian atau
memori JAYA.

---

## 6. Budget-Aware Reasoning

Sebelum memulai sesi penalaran, Core memeriksa budget yang tersedia:

```python
# Pseudocode — bukan implementasi aktual
resource_budget = {
    "ram_available_mb": query_available_ram(),
    "cpu_usage_pct": query_cpu_load(),
    "gpu_available_mb": query_available_vram(),
    "battery_pct": query_battery(),
    "temperature_c": query_cpu_temp(),
    "bandwidth_kbps": query_network_bandwidth(),
    "storage_mb": query_storage(),
    "task_urgency": intent.urgency,  # LOW, NORMAL, HIGH, CRITICAL
}

strategy = reasoning_strategy_selector(resource_budget)
# Hasilnya: DEEP, STANDARD, LITE, RULE_ONLY, atau OFFLOAD
```

Strategi penalaran berdasarkan resource:

| Strategi | Kondisi | Perilaku |
|---|---|---|
| `DEEP` | Resource penuh, urgensi rendah-normal | Beberapa kandidat, evaluasi mendalam |
| `STANDARD` | Resource cukup | Satu kandidat, evaluasi standar |
| `LITE` | Resource terbatas | Penalaran singkat, aturan eksplisit |
| `RULE_ONLY` | Resource sangat terbatas | Hanya aturan lokal, tidak ada model |
| `OFFLOAD` | Resource tidak cukup tapi koneksi ada | Delegasikan ke node yang lebih kuat |

---

## 7. JayaIR — Bahasa Internal Terstruktur

JayaIR (JAYA Internal Representation) adalah format terstruktur yang digunakan
Core untuk mengekspresikan rencana, tujuan, dan instruksi secara eksplisit.
Agent menginterpretasikan JayaIR untuk menentukan tindakan yang akan diambil.

Dengan JayaIR, Core tidak bergantung pada satu aplikasi atau tool. Rencana yang
sama dapat dieksekusi melalui berbagai tool selama ada adapter yang mendukung.

### Contoh JayaIR lengkap — Desain 3D

```json
{
  "jaya_ir_version": "0.3",
  "goal_id": "goal-20260802-001",
  "intent": "CREATE_3D_MODEL",
  "domain": "cad.parametric_modeling",
  "object": {
    "type": "mini_pc_case",
    "label": "Casing Mini PC Berpendingin Baik"
  },
  "constraints": {
    "max_width_mm": 180,
    "max_depth_mm": 220,
    "max_height_mm": 80,
    "airflow": "front_to_back",
    "manufacturing": "3d_printing",
    "material": "PLA_or_PETG"
  },
  "missing_context": [
    { "field": "motherboard_size", "ask_user": true },
    { "field": "gpu_model", "ask_user": true },
    { "field": "cooling_type", "ask_user": true }
  ],
  "plan": [
    {
      "step": 1,
      "action": "collect_component_dimensions",
      "requires_user_input": true,
      "inputs_needed": ["motherboard_size", "gpu_model", "cooling_type"]
    },
    {
      "step": 2,
      "action": "calculate_airflow_requirements",
      "capability": "cad.thermal_analysis",
      "inputs": ["component_dimensions", "cooling_type"]
    },
    {
      "step": 3,
      "action": "generate_parametric_geometry",
      "capability": "cad.parametric_modeling",
      "inputs": ["component_dimensions", "airflow_requirements", "constraints"],
      "output": "geometry_v1"
    },
    {
      "step": 4,
      "action": "validate_clearance",
      "capability": "cad.collision_check",
      "inputs": ["geometry_v1"],
      "output": "clearance_report"
    },
    {
      "step": 5,
      "action": "simulate_airflow",
      "capability": "cad.simulation",
      "inputs": ["geometry_v1"],
      "output": "airflow_report"
    },
    {
      "step": 6,
      "action": "present_preview",
      "capability": "interface.3d_viewer",
      "inputs": ["geometry_v1", "clearance_report", "airflow_report"],
      "requires_user_approval": true
    },
    {
      "step": 7,
      "action": "export_model",
      "capability": "cad.export",
      "formats": ["STL", "STEP", "OBJ"],
      "requires_user_approval_before": true,
      "outputs": ["export_file"]
    }
  ],
  "approval_required_before": ["export_model"],
  "rollback_available": true,
  "estimated_resource": {
    "ram_mb": 2048,
    "gpu_mb": 512,
    "duration_estimate_min": 5
  }
}
```

### JayaIR untuk perintah sederhana

```json
{
  "jaya_ir_version": "0.3",
  "goal_id": "goal-20260802-002",
  "intent": "SET_REMINDER",
  "domain": "personal.scheduler",
  "object": {
    "type": "reminder",
    "message": "Cek progres eksperimen"
  },
  "constraints": {
    "delay_minutes": 30
  },
  "plan": [
    {
      "step": 1,
      "action": "schedule_notification",
      "capability": "os.scheduler",
      "inputs": ["message", "delay_minutes"]
    }
  ],
  "approval_required_before": [],
  "rollback_available": true
}
```

JayaIR versi 0.x masih dalam tahap desain. Schema akan dibekukan sebelum Fase B.

---

## 8. Memory Architecture per Node

Setiap node membawa himpunan memori yang berbeda sesuai perannya.

### 8.1 Jenis Memori

| Jenis | Deskripsi | Di mana disimpan |
|---|---|---|
| Working Memory | Konteks tugas aktif saat ini | Node aktif (RAM) |
| Episodic Memory | Riwayat kejadian dan interaksi | Node lokal + Central |
| Semantic Memory | Fakta dan konsep terverifikasi | Central (di-cache di Edge) |
| Procedural Memory | Cara melakukan pekerjaan tertentu | Central + node yang relevan |
| User Model | Preferensi, kebiasaan, perangkat | Central + cache lokal |
| World State | State aplikasi, file, perangkat, lingkungan | Node aktif |
| Mission Memory | Memori spesifik misi saat ini | Mission Node |
| Knowledge Cache | Subset pengetahuan penting untuk node | Edge + Mission Node |

### 8.2 Distribusi Memori per Node

| Node | Working | Episodic | Semantic | User Model | Knowledge Cache |
|---|---|---|---|---|---|
| Central | ✓ full | ✓ full | ✓ full | ✓ full | — |
| Standard | ✓ full | ✓ lokal + sync | ✓ subset | ✓ cache | ✓ relevan |
| Edge | ✓ terbatas | ✓ terbatas | — | ✓ cache kecil | ✓ kritis |
| Mission | ✓ misi | ✓ misi | — | ✓ cache kecil | ✓ misi |
| Micro | — | — | — | — | ✓ minimal |

### 8.3 Aturan Memori

- Core tidak menyimpan dokumen mentah atau PDF. Dokumen mentah berada di Research.
- Pengetahuan hanya masuk ke Semantic Memory setelah melewati promotion gate.
- Working memory dibersihkan setelah tugas selesai.
- Episodic memory lokal disinkronkan ke Central setelah sanitasi dan deduplikasi.
- Knowledge cache diperbarui oleh Central berdasarkan relevansi node.

---

## 9. Node Identity Protocol

Setiap node JAYA memiliki identitas yang unik dan terverifikasi.

### Registrasi Node

```text
Node baru dibuat
      ↓
Generate node key pair
      ↓
Kirim registration request ke Central
      (signed with temporary key)
      ↓
Central verifikasi identitas pemilik
      ↓
Central issue node certificate
      ↓
Node menyimpan certificate
      ↓
Node terdaftar dalam node registry
```

### Security Properties

- Setiap node memiliki key sendiri yang tidak dibagikan ke node lain.
- Setiap event dan pesan ditandatangani dengan node key.
- Central dapat mencabut sertifikat node yang dicuri atau rusak.
- Node yang sertifikatnya dicabut tidak dapat mengakses memori Central.
- Data sensitif dienkripsi per perangkat — pencurian satu node tidak
  memberi akses ke semua data.

---

## 10. Capability Negotiation

Ketika Core membutuhkan capability yang tidak tersedia di node saat ini:

```text
Core: membutuhkan cad.parametric_modeling

Cek Capability Registry lokal
      ↓
Tidak tersedia di node ini
      ↓
Query JAYA Mesh: node mana yang memiliki capability ini?
      ↓
┌────────────────────────────────────┐
│ Central  → tersedia, resource cukup│
│ Laptop   → tersedia, GPU terbatas  │
│ Phone    → tidak tersedia          │
└────────────────────────────────────┘
      ↓
Pilih node terbaik (Central)
      ↓
Buat task delegation request (JayaIR)
      ↓
Kirim ke Central via Mesh
      ↓
Terima hasil dari Central
      ↓
Tampilkan ke pengguna melalui Interface lokal
```

Jika tidak ada node yang memiliki capability dan pengguna online:
→ Tawarkan instalasi capability pack atau upgrade node.

Jika tidak ada node yang memiliki capability dan pengguna offline:
→ Beritahu pengguna bahwa kemampuan ini memerlukan koneksi atau node yang lebih kuat.

---

## 11. Komponen Core yang Sudah Ada

Struktur yang sudah diimplementasikan di `JAYA_CORE/src/brain_v2/`:

```text
brain_v2/
├── soul/
│   ├── agentic_jarvis.py    — planner, proactive engine, knowledge delta builder
│   ├── episodic_memory.py   — UserProfile, EpisodicMemory
│   └── ...
├── engine/
│   ├── runtime.py           — runtime policy dan gate
│   └── ...
├── model/                   — model adapter dan router (partial)
├── organism/                — komponen organisme/integrator
├── protection/              — keamanan dan sandbox
├── education/               — learning interface
├── extensions/              — plugin sistem
├── format/                  — format output
├── network/                 — komunikasi
└── genesis.py               — inisialisasi Core
```

Sebagian besar komponen sudah ada sebagai `IMPLEMENTED` atau `PROTOTYPE`.
Cognitive Kernel yang portabel dan Node Communication Layer adalah komponen
baru yang akan dikembangkan pada Fase B.

---

## 12. Roadmap Pengembangan Core

| Fase | Fokus | Status |
|---|---|---|
| Fase 1 | Intent, context, JayaIR draft, runtime contract | IMPLEMENTED (partial) |
| Fase 2 | Working memory, episodic memory, user model | IMPLEMENTED (partial) |
| Fase 3 | Semantic memory policy, knowledge ingestion | PROTOTYPE |
| Fase 4 | Reasoning engine, problem decomposition | PROTOTYPE |
| Fase 5 | Hierarchical planner, domain-neutral agent interface | IMPLEMENTED (partial) |
| Fase 6 | Cognitive evaluation, reflection, benchmark | PROTOTYPE |
| Fase 7 | Candidate artifact gate, promotion pipeline | PROTOTYPE |
| Fase 8 | Proactive intelligence | IMPLEMENTED (partial) |
| Fase 9 | Multimodal understanding | PROTOTYPE |
| Fase B | Cognitive Kernel portabel, Node Identity, Budget-Aware reasoning | IDEA |
| Fase C | JAYA Mesh integration, multi-node synchronization | IDEA |
| Fase 10 | Advanced capabilities (3D, robotics, coding, AR) | IDEA |
