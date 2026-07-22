# 🗺️ Development Roadmap — JAYA_ANDROID

Roadmap pengembangan **JAYA_ANDROID** dibagi menjadi 4 Fase strategis untuk mewujudkan sistem mobile assistant JARVIS Hybrid yang responsif, cerdas, dan hemat daya.

---

## 📌 Indeks Fase Development

| Fase | Fokus | Key Deliverables | Status |
|---|---|---|---|
| **Fase A** | Foundation & UI Scaffold | Jetpack Compose Architecture, Navigation, Material 3 Theme | 🔄 Planned |
| **Fase B** | JARVIS Hybrid Connectivity | mDNS Auto-Discovery, mTLS Handshake, WebSocket Streaming | 🔄 Planned |
| **Fase C** | On-Device Nano Engine | C++ NDK GGUF Loader, Local Vector Store (Room + SQLite) | 🔄 Planned |
| **Fase D** | Voice Assistant & Production | Foreground Voice Service, "Hey Jaya" Wake-Word, Play Store Packaging | 🔄 Planned |

---

## 🛠️ Rincian Deliverables per Fase

### 🅰️ Fase A: Foundation & UI Scaffold
- [ ] Inisialisasi Android Studio Project (Kotlin 2.0+, Gradle KTS, Jetpack Compose).
- [ ] Implementasi Sistem Tema Dark Notebook & Custom Typography.
- [ ] Komponen Navigasi Utama (Dashboard, Remote Workspace, Local Brain, Settings).

### 🅱️ Fase B: JARVIS Hybrid Connectivity Protocol
- [ ] Modul `NetworkDiscoveryManager` (mDNS/NSD untuk mendeteksi PC Server di LAN).
- [ ] Modul `SecureTunnelManager` (Handshake mTLS & Enkripsi Kunci Sesi).
- [ ] Client Streaming WebSocket untuk merespons prompt dari PC Server secara real-time.
- [ ] Pengujian Alur Sinkronisasi Otomatis (*Auto-Sync Protocol*) saat terhubung kembali.

### 🅲️ Fase C: On-Device Nano Engine (Space Mode)
- [ ] Integrasi C++ NDK dengan `llama.cpp` Android Bindings.
- [ ] Pemuatan Model Kuantisasi Ringan (GGUF 1.5B / 3B) di CPU/NPU HP.
- [ ] DB Lokal Terenkripsi (Room DB + SQLCipher AES-256) untuk cache memori offline.
- [ ] Pengujian Batas RAM HP (< 300 MB footprint saat offline).

### 🅹️ Fase D: Voice Assistant & Production Packaging
- [ ] Foreground Service `JayaVoiceService` untuk mendengarkan perintah suara di latar belakang.
- [ ] Integration Wake-Word Detector `"Hey Jaya"`.
- [ ] Fitur Tanggapan Suara (*Text-to-Speech*) dengan kontrol nada dinamis.
- [ ] Pengujian Rilis APK & Bundling Produksi.
