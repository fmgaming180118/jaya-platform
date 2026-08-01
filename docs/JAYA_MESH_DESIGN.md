# Desain JAYA Mesh — Jaringan Kecerdasan Terdistribusi

**Status:** IDEA
**Berlaku mulai:** 2 Agustus 2026
**ADR terkait:** ADR-010

---

## 1. Apa itu JAYA Mesh?

JAYA Mesh adalah lapisan sistem saraf JAYA — jaringan yang menghubungkan semua
node JAYA milik satu pengguna sehingga mereka dapat:

- berbagi tugas dan konteks;
- mendelegasikan kemampuan yang tidak dimiliki satu node ke node lain;
- menyinkronkan pengalaman dan memori setelah online kembali;
- tetap beroperasi secara mandiri saat koneksi terputus.

Tanpa JAYA Mesh, setiap node adalah pulau terpisah. Dengan JAYA Mesh, semuanya
adalah satu kecerdasan yang hidup di banyak tempat sekaligus.

---

## 2. Prinsip Desain

- **Satu identitas, banyak manifestasi** — semua node merujuk ke satu `jaya_identity`.
- **Offline-first** — setiap node harus dapat bekerja tanpa Mesh; koneksi adalah bonus.
- **Event-based, bukan database-copy** — sinkronisasi melalui event terstruktur,
  bukan menyalin seluruh database.
- **Signed everything** — setiap pesan, event, dan update ditandatangani.
- **Zero implicit trust** — koneksi node baru harus diotorisasi secara eksplisit.
- **Conflict resolution eksplisit** — konflik memori atau state diselesaikan dengan
  aturan yang deterministik, bukan yang terakhir menang.

---

## 3. Node Tiers — Lima Tingkatan Manifestasi JAYA

### Tier 1 — JAYA Central

**Peran:** Otak dan perpustakaan utama.

**Dijalankan pada:** komputer utama, workstation, home server.

**Kemampuan:**
- JAYA Core penuh dengan semua Capability Packs
- JAYA Research (CEL pipeline lengkap)
- Model besar dan training/distillation
- Long-term memory penuh (seluruh episodic, semantic, procedural)
- Knowledge graph lengkap
- Node registry dan Certificate Authority untuk semua node
- Orchestrasi seluruh node di Mesh
- Sinkronisasi pengalaman dari semua node
- Benchmark dan promotion gate
- Capability pack distribution

**Dapat dijalankan offline:** Ya, dengan kemampuan penuh.

**Contoh identifikasi node:**
```json
{
  "jaya_identity": "jaya-fachri",
  "node_id": "home-central",
  "node_tier": "CENTRAL",
  "node_role": "PRIMARY_COGNITIVE_NODE"
}
```

---

### Tier 2 — JAYA Standard

**Peran:** Node kerja utama sehari-hari.

**Dijalankan pada:** laptop, desktop biasa.

**Kemampuan:**
- JAYA Core cukup lengkap
- Reasoning lokal
- Planning
- Memori pengguna lokal + sinkronisasi ke Central
- Tool execution
- Coding, analisis dokumen
- Voice dan vision sesuai hardware
- Model lokal menengah atau koneksi ke Central
- Research connector (ke JAYA Research di Central)

**Dapat dijalankan offline:** Ya, dengan kemampuan terbatas (tanpa Research dan model besar).

**Contoh identifikasi node:**
```json
{
  "jaya_identity": "jaya-fachri",
  "node_id": "laptop-01",
  "node_tier": "STANDARD",
  "node_role": "PERSONAL_WORKSTATION_NODE"
}
```

---

### Tier 3 — JAYA Edge

**Peran:** Node portabel untuk penggunaan sehari-hari di luar.

**Dijalankan pada:** ponsel, tablet, Raspberry Pi, perangkat kendaraan, wearable.

**Kemampuan:**
- Intent recognition lokal
- Working memory
- Episodic memory terbatas
- Planner ringkas
- Model kecil atau terkuantisasi
- Voice command
- Perception dasar
- Tool dan sensor lokal
- Knowledge cache (subset yang relevan)
- Kemampuan mendelegasikan ke Central/Standard

**Dapat dijalankan offline:** Ya, dengan kemampuan sangat terbatas.

**Contoh identifikasi node:**
```json
{
  "jaya_identity": "jaya-fachri",
  "node_id": "phone-primary",
  "node_tier": "EDGE",
  "node_role": "PERSONAL_MOBILE_NODE"
}
```

---

### Tier 4 — JAYA Mission Node

**Peran:** Node yang beroperasi dalam kondisi terisolasi atau berbahaya.

**Dijalankan pada:** armor, robot, drone, kendaraan otonom, perangkat lapangan.

**Kemampuan:**
- Model lokal yang cukup untuk operasi mandiri
- World state lokal
- Mission memory (konteks misi aktif)
- Sensor fusion
- Emergency policy dan fail-safe
- Navigation dan planning lokal
- Tindakan real-time tanpa bergantung koneksi
- Misi dapat dilanjutkan saat koneksi hilang
- Semua keputusan dicatat untuk disinkronkan ke Central

**Dapat dijalankan offline:** Ya, **harus dapat** — desain ini adalah syarat utama.

**Contoh identifikasi node:**
```json
{
  "jaya_identity": "jaya-fachri",
  "node_id": "armor-01",
  "node_tier": "MISSION_NODE",
  "node_role": "MISSION_CRITICAL_AUTONOMOUS_NODE"
}
```

---

### Tier 5 — JAYA Micro Node

**Peran:** Anggota terkecil jaringan — sensor, refleks, dan persepsi.

**Dijalankan pada:** mikrokontroler (ESP32, Arduino, STM32), sensor cerdas, aktuator.

**Kemampuan:**
- Identitas perangkat
- Protokol komunikasi dengan Mesh
- Sensor reading dan telemetri
- Rule engine sederhana (if-then-else lokal)
- Event detection
- Perintah terverifikasi dari node yang lebih tinggi
- Emergency shutdown lokal
- Enkripsi minimal
- State machine lokal
- Cache beberapa instruksi kritis

**Tidak menjalankan model bahasa atau JAYA Core secara penuh.**

**Dapat dijalankan offline:** Ya, dengan aturan lokal yang sudah dikonfigurasi.

**Contoh identifikasi node:**
```json
{
  "jaya_identity": "jaya-fachri",
  "node_id": "room-sensor-02",
  "node_tier": "MICRO_NODE",
  "node_role": "TEMPERATURE_HUMIDITY_PERCEPTION_NODE"
}
```

---

## 4. Perbandingan Kemampuan per Tier

| Kemampuan | Central | Standard | Edge | Mission | Micro |
|---|---|---|---|---|---|
| JAYA Core penuh | ✓ | ✓ partial | ✗ | ✓ partial | ✗ |
| Cognitive Kernel | ✓ | ✓ | ✓ | ✓ | ✗ |
| Model besar | ✓ | ✗ | ✗ | ✗ | ✗ |
| Model menengah | ✓ | ✓ | ✗ | ✓ | ✗ |
| Model kecil | ✓ | ✓ | ✓ | ✓ | ✗ |
| Episodic memory full | ✓ | ✓ | partial | partial misi | ✗ |
| Semantic memory | ✓ | cache | ✗ | cache | ✗ |
| JAYA Research | ✓ | connector | ✗ | ✗ | ✗ |
| Knowledge graph | ✓ | partial | ✗ | ✗ | ✗ |
| Voice | ✓ | ✓ | ✓ | ✓ | ✗ |
| Vision | ✓ | ✓ | basic | basic | ✗ |
| CAD/3D | ✓ | basic | ✗ | ✗ | ✗ |
| Robotics | ✓ | ✗ | ✗ | ✓ | ✗ |
| Task offloading | send+receive | send+receive | send | send | send event |
| Promotion gate | ✓ (authority) | ✗ | ✗ | ✗ | ✗ |
| Rule engine | ✓ | ✓ | ✓ | ✓ | ✓ |
| Emergency policy | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 5. Topologi Jaringan JAYA Mesh

```text
                    JAYA CENTRAL
                  (home-central)
                        │
             JAYA Mesh Secure Transport
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   JAYA Standard    JAYA Edge      JAYA Mission Node
   (laptop-01)      (phone)        (armor-01)
                        │
                   JAYA Micro Nodes
                   (sensors, actuators)
```

Setiap koneksi di Mesh:
- **dienkripsi** end-to-end;
- **diautentikasi** dengan node certificate;
- **memiliki timeout** dan heartbeat;
- **tidak wajib online terus-menerus**.

Mesh bukan cloud service — ia adalah jaringan privat milik pengguna.

---

## 6. Event Sync Protocol

### Format Event

Semua komunikasi dan sinkronisasi menggunakan event terstruktur:

```json
{
  "event_id": "evt-armor01-00821",
  "event_version": "1.0",
  "jaya_identity": "jaya-fachri",
  "source_node": "armor-01",
  "target_node": "home-central",
  "event_type": "EPISODIC_MEMORY_SYNC",
  "session_id": "mission-007",
  "timestamp": "2026-08-02T02:20:00+07:00",
  "sequence_number": 821,
  "payload": {
    "events": [
      {
        "type": "PLAN_REVISED",
        "old_value": "route-a",
        "new_value": "route-b",
        "reason": "obstacle_detected",
        "timestamp": "2026-08-02T02:15:30+07:00"
      },
      {
        "type": "TASK_COMPLETED",
        "task_id": "navigate-to-checkpoint-3",
        "result": "SUCCESS",
        "duration_seconds": 142,
        "timestamp": "2026-08-02T02:18:10+07:00"
      }
    ]
  },
  "signature": "base64-encoded-ed25519-signature"
}
```

### Alur Sinkronisasi

```text
Node offline bekerja
      ↓
Menyimpan signed event log lokal
      ↓
Koneksi tersedia
      ↓
Node mengirim event batch ke Central
      ↓
Central memverifikasi:
  - signature node
  - sequence number (tidak ada yang terlewat)
  - timestamp (reasonable window)
  - konflik dengan state lain
  - izin event type
      ↓
Event valid → digabungkan ke memori Central
Event konflik → diselesaikan dengan conflict resolution policy
Event tidak valid → ditolak + alasan
      ↓
Central mengirim update yang relevan kembali ke node
      ↓
Node memperbarui knowledge cache
```

### Jenis Event

| Event Type | Asal | Tujuan | Deskripsi |
|---|---|---|---|
| `EPISODIC_MEMORY_SYNC` | semua node | Central | Sinkronisasi riwayat kejadian |
| `TASK_DELEGATED` | node rendah | node tinggi | Mendelegasikan tugas yang tidak bisa dikerjakan |
| `TASK_RESULT` | node pengerjaan | node peminta | Hasil tugas yang didelegasikan |
| `CAPABILITY_QUERY` | semua node | Central | Mencari node yang punya capability tertentu |
| `CAPABILITY_RESPONSE` | Central | node peminta | Daftar node dengan capability yang diminta |
| `KNOWLEDGE_CACHE_UPDATE` | Central | node rendah | Pembaruan knowledge cache |
| `NODE_REGISTERED` | node baru | Central | Pendaftaran node baru |
| `NODE_REVOKED` | Central | semua | Pencabutan sertifikat node |
| `EMERGENCY_EVENT` | semua node | Central | Event darurat prioritas tinggi |
| `HEARTBEAT` | semua node | Central | Tanda bahwa node masih aktif |
| `POLICY_UPDATE` | Central | semua | Pembaruan aturan/policy |
| `ARTIFACT_CANDIDATE` | semua node | Central | Kandidat artifact untuk promotion gate |

---

## 7. Offline Behavior Modes

Setiap node memiliki mode operasi yang ditentukan oleh status koneksi dan resource.

### Mode Definitions

| Mode | Kondisi | Perilaku |
|---|---|---|
| `ONLINE_FULL` | Central tersedia, bandwidth baik, resource cukup | Semua kemampuan aktif, delegasi tersedia |
| `ONLINE_DEGRADED` | Koneksi ada tapi lambat/tidak stabil | Batasi delegasi, kurangi sinkronisasi |
| `OFFLINE_AUTONOMOUS` | Tidak ada koneksi, resource cukup | Jalankan model lokal, catat semua keputusan |
| `OFFLINE_SAFE` | Tidak ada koneksi, resource terbatas | Hanya fungsi penting dan aturan lokal |
| `EMERGENCY` | Kondisi darurat (power kritis, suhu, dll.) | Policy darurat lokal, shutdown non-essential |

### Transisi Mode

```text
ONLINE_FULL
    ↓ (koneksi memburuk)
ONLINE_DEGRADED
    ↓ (koneksi hilang)
OFFLINE_AUTONOMOUS
    ↓ (resource sangat rendah)
OFFLINE_SAFE
    ↓ (kondisi darurat)
EMERGENCY
    ↓ (koneksi kembali)
ONLINE_DEGRADED → ONLINE_FULL
```

### Mission Node khusus

Mission Node tidak boleh masuk mode `OFFLINE_SAFE` atau `EMERGENCY` secara otomatis
selama misi aktif kecuali ada kondisi keselamatan kritis (suhu ekstrem, power
sangat rendah). Misi harus dapat dilanjutkan dalam `OFFLINE_AUTONOMOUS` sesuai
rencana yang sudah di-cache.

---

## 8. Conflict Resolution

Konflik terjadi ketika dua node memperbarui informasi yang sama saat offline.

### Strategi Resolution

| Jenis Konflik | Strategi |
|---|---|
| Preferensi pengguna | Central menang (lebih otoritatif) |
| Episodic event | Merge berdasarkan timestamp — tidak ada yang hilang |
| Task state | Tanyakan pengguna jika perbedaan signifikan |
| Knowledge delta | Tandai sebagai konflik, masukkan promotion review |
| Policy | Central selalu menang |
| Node-local state | Node lokal menang untuk state miliknya sendiri |

Konflik **tidak pernah diselesaikan secara diam-diam** tanpa log audit.

---

## 9. Knowledge Cache Strategy

Node Edge dan Mission Node tidak boleh membawa seluruh knowledge base.
Mereka hanya membawa cache yang relevan.

### Apa yang masuk ke Knowledge Cache

| Kategori | Contoh | Prioritas |
|---|---|---|
| Preferensi pengguna penting | nama, bahasa, gaya kerja | Critical |
| Prosedur darurat | emergency shutdown, safety rules | Critical |
| Instruksi misi aktif | tujuan, rute, checkpoint | Critical (Mission Node) |
| Kemampuan lokal | daftar capability yang bisa dilakukan tanpa delegasi | High |
| Pengetahuan domain yang sering diakses | manual perangkat, peta area | Medium |
| Context terbaru | percakapan terakhir, task terakhir | Medium |
| Pengetahuan umum terpilih | fakta yang sering dibutuhkan | Low |

### Pembaruan Cache

- Central memperbarui cache node secara proaktif berdasarkan pola penggunaan.
- Node dapat meminta pembaruan cache secara eksplisit saat online.
- Cache memiliki TTL (Time-to-Live) dan versi.
- Cache kedaluwarsa ditandai, bukan dihapus secara langsung.

---

## 10. Keamanan dan Identitas Node

### Property Keamanan

- Setiap node memiliki key pair yang dihasilkan saat pendaftaran.
- Private key tidak pernah meninggalkan node.
- Central bertindak sebagai Certificate Authority untuk JAYA Mesh privat.
- Setiap event dan pesan ditandatangani dengan private key node.
- Sertifikat node memiliki masa berlaku dan dapat diperbarui.
- Node yang hilang atau dicuri dapat dicabut sertifikatnya oleh pemilik.

### Pencabutan Node

```text
Pemilik mendeteksi node hilang/dicuri
      ↓
Pemilik memberi perintah revoke node-id ke Central
      ↓
Central menerbitkan Node Revocation Notice
      ↓
Semua node yang online menerima notice
      ↓
Node yang dicabut tidak dapat lagi:
  - mengakses memori Central
  - mendelegasikan tugas
  - mengirim event
  - menerima update
      ↓
Audit log mencatat kapan dan mengapa node dicabut
```

### Data Isolation

- Data sensitif dienkripsi per perangkat — kunci enkripsi unik per node.
- Pencurian satu node tidak memberi akses ke memori node lain.
- Mission Node tidak membawa seluruh episodic memory — hanya misi aktif.

---

## 11. Contoh Skenario

### Skenario A — Ponsel offline, perintah suara

```text
Pengguna berkata ke ponsel (offline):
"Jaya, ingatkan saya saat sampai di kantor."

Phone (OFFLINE_AUTONOMOUS):
  → Kenali intent lokal: SET_GEOFENCE_REMINDER
  → Cek capability: geofence_trigger tersedia
  → Set reminder lokal
  → Catat event: GEOFENCE_REMINDER_SET
  → Sinkronkan ke Central saat online

Saat online kembali:
  → Central menerima event
  → Episodic memory diperbarui: "pengguna set reminder di perjalanan kantor"
```

### Skenario B — Delegation dari ponsel ke laptop

```text
Pengguna berkata ke ponsel (online):
"Jaya, analisis arsitektur kode proyek besar ini."

Phone (ONLINE_FULL):
  → Kenali intent: ANALYZE_CODEBASE
  → Cek capability lokal: tidak tersedia (butuh reasoning.full)
  → Query Mesh: siapa yang punya reasoning.full?
  → Central menjawab: laptop-01 tersedia
  → Delegasikan task ke laptop-01 via JayaIR
  → Tampilkan "Saya delegasikan ke laptop, tunggu sebentar..."

Laptop-01 (ONLINE_FULL):
  → Terima JayaIR task
  → Jalankan reasoning.full
  → Kirim hasil ke phone via Mesh

Phone:
  → Terima hasil
  → Tampilkan ke pengguna
```

### Skenario C — Mission Node kehilangan koneksi

```text
Mission Node armor-01 sedang menjalankan misi navigasi
Koneksi ke Central terputus

armor-01 (OFFLINE_AUTONOMOUS):
  → Deteksi koneksi hilang
  → Beralih ke mode OFFLINE_AUTONOMOUS
  → Lanjutkan misi dengan rencana yang sudah di-cache
  → Navigasi menggunakan model lokal dan peta yang di-cache
  → Catat semua keputusan dalam signed event log
  → Kirim notifikasi ke pengguna (jika ponsel masih terhubung):
    "Koneksi ke Central terputus. Beroperasi mandiri."

Koneksi kembali:
  → armor-01 mengirim event batch ke Central
  → Central memverifikasi dan menggabungkan
  → Episodic memory misi diperbarui
  → armor-01 kembali ke ONLINE_FULL
```

---

## 12. Komponen yang Dibutuhkan (Belum Diimplementasikan)

JAYA Mesh adalah konsep arsitektur yang belum diimplementasikan. Komponen yang
diperlukan untuk implementasi:

| Komponen | Deskripsi | Status |
|---|---|---|
| Node Registry | Database node yang terdaftar | IDEA |
| Certificate Authority | Penerbitan dan pencabutan sertifikat node | IDEA |
| Secure Transport | Protokol komunikasi terenkripsi antarnode | IDEA |
| Event Bus | Antrian dan routing event antarnode | IDEA |
| Sync Engine | Penggabungan event ke memori | IDEA |
| Conflict Resolver | Penyelesaian konflik state | IDEA |
| Cache Manager | Distribusi knowledge cache ke node | IDEA |
| Task Offloader | Delegasi tugas ke node yang tepat | IDEA |
| Mesh Discovery | Penemuan node yang tersedia | IDEA |
| Offline Queue | Antrian event saat offline | IDEA |

Semua komponen di atas berstatus `IDEA`. Tidak ada implementasi aktif.
Implementasi dimulai pada Fase B roadmap.

---

## 13. Hubungan dengan Modul Lain

```text
JAYA Research (Central) ──────────────────────────────┐
    menghasilkan candidate artifact                    │
           │                                           │
           ▼                                           │
    Promotion Gate (Central)                           │
           │ (setelah disetujui manusia)               │
           ▼                                           │
    JAYA Core (Central) ◄──── JAYA Mesh ────► JAYA Core (node lain)
    otak utama                sinkronisasi    manifestasi di node
           │                     │
           ▼                     ▼
    JAYA Agent               Node Task Execution
    menjalankan tugas
           │
           ▼
    JAYA OS
    izin dan sandbox
           │
           ▼
    Tool, aplikasi, perangkat fisik
```

JAYA Research hanya berjalan di Central. Kandidat artifact dari Research
tidak pernah langsung dikirim ke node lain tanpa melewati promotion gate Central.
