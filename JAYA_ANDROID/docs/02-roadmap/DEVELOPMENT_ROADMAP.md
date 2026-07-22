# 🗺️ Development Roadmap — JAYA_ANDROID

Roadmap pengembangan **JAYA_ANDROID** dibagi menjadi 4 Fase strategis untuk mewujudkan sistem mobile assistant JARVIS Hybrid yang responsif, cerdas, dan hemat daya.

---

## 📌 Indeks Fase Development

| Fase | Fokus | Key Deliverables | Status |
|---|---|---|---|
| **Fase A** | Foundation & UI Scaffold | Jetpack Compose Architecture, Navigation, JayaApiService, Local Storage Permissions | ✅ Complete (100%) |
| **Fase B** | JARVIS Hybrid Connectivity | NetworkDiscoveryManager (mDNS), SecureTunnelManager, JayaWebSocketClient, AutoSyncManager | ✅ Complete (100%) |
| **Fase C** | On-Device Nano Engine | C++ NDK GGUF Loader, Local Vector Store (Room + SQLite) | 🔄 Planned |
| **Fase D** | Voice Assistant & Production | Foreground Voice Service, "Hey Jaya" Wake-Word, Play Store Packaging | 🔄 Planned |

---

## 🛠️ Rincian Deliverables per Fase

### 🅰️ Fase A: Foundation & UI Scaffold ✅ COMPLETE (100%)
- [x] Inisialisasi Android Studio Project (Kotlin 2.0+, Gradle KTS, Jetpack Compose).
- [x] Implementasi Sistem Tema Dark Notebook & Custom Typography.
- [x] Komponen Navigasi Utama (Dashboard, Chat, Profile, Settings).
- [x] Integrasi `JayaApiService` & Pengaturan Local Storage Permissions untuk RAG.

### 🅱️ Fase B: JARVIS Hybrid Connectivity Protocol ✅ COMPLETE (100%)
- [x] Modul `NetworkDiscoveryManager` (mDNS/NSD untuk mendeteksi PC Server di LAN).
- [x] Modul `SecureTunnelManager` (Session Encryption & State Management).
- [x] Client Streaming `JayaWebSocketClient` untuk respons real-time.
- [x] Engine `AutoSyncManager` (Bi-directional Auto-Sync saat terhubung kembali).

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
