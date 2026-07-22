# 🌐 JARVIS Hybrid Connectivity Specification — JAYA_ANDROID

Dokumen ini mendefinisikan arsitektur konektivitas **JARVIS Hybrid** antara `JAYA_ANDROID` (HP/Client Portabel) dan PC Server Utama (`JAYA_CORE` + `JAYA_RESEARCH`).

---

## 🏛️ Arsitektur Sistem Dual-State

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       STATE 1: ONLINE / SERVER CONNECTED                    │
│                                                                             │
│ ┌───────────────────────────┐     mTLS / WebSocket      ┌─────────────────┐ │
│ │  JAYA_ANDROID (HP Client) │ <=======================> │ PC Server Utama │ │
│ │ • Jetpack Compose UI      │    Secure Peer Tunnel     │ • JAYA_CORE     │ │
│ │ • Streaming Remote Prompt │                           │ • JAYA_RESEARCH │ │
│ └───────────────────────────┘                           └─────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       STATE 2: OFFLINE / SPACE MODE                         │
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      JAYA_ANDROID (HP Standalone)                        │ │
│ │ • Local GGUF Nano LLM (1.5B/3B)                                          │ │
│ │ • Encrypted SQLite/Room Cache                                            │ │
│ │ • Offline Voice Assistant                                               │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📡 1. Online Mode (Full Server Synchronization)

Saat HP berada di jaringan WiFi/LAN yang sama dengan PC Server atau terhubung melalui secure VPN / WebRTC tunnel:

1. **Auto-Discovery**:
   * `JAYA_ANDROID` mendeteksi PC Server Utama di jaringan menggunakan **mDNS / NSD (Network Service Discovery)**.
2. **mTLS Handshake & Authentication**:
   * Sertifikat keamanan kriptografi dipasangkan (*Pairing*) antara HP dan PC Server.
3. **Full Access Capabilities**:
   * Menampilkan seluruh project pengguna, dokumen skripsi, laporan riset terbaru, dan memori jangka panjang JAYA dari server pusat.
   * Eksekusi model LLM skala besar (7B/14B/70B) dilakukan oleh PC Server, lalu hasilnya di-*stream* ke HP dengan latensi sangat rendah via WebSockets.

---

## 🛰️ 2. Offline Mode (Space Mode / Standalone)

Saat HP tidak terhubung ke sinyal internet/LAN (misal di luar angkasa, pesawat, atau area tanpa sinyal):

1. **Seamless Fallback**:
   * Tanpa *crash* atau pesan error, sistem secara otomatis beralih ke **Local Nano Engine** di HP.
2. **On-Device Inference**:
   * Menggunakan model kuantisasi ringan (GGUF 1.5B / 3B) yang berjalan murni di CPU/NPU smartphone.
3. **Local Encrypted Cache**:
   * Semua query, ide, dan pesan baru disimpan di **Room Database AES-256-GCM** lokal HP.

---

## 🔄 3. Synchronization Protocol (Auto-Sync on Reconnect)

Saat HP kembali mendapatkan koneksi ke PC Server Utama:

1. **Delta Transaction Log Check**:
   * HP dan PC Server saling mencocokkan `last_synced_timestamp`.
2. **Bi-directional Sync**:
   * **Pesan/Memori Baru HP ➔ Server**: Catatan yang dibuat saat offline diunggah ke memori pusat PC Server.
   * **Update Riset Server ➔ HP**: Pembaruan otak `auto_research_patch` terbaru dari `JAYA_RESEARCH` didownload ke HP.
