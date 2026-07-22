# 📱 JAYA_ANDROID — Sovereign JARVIS Hybrid Mobile Extension

`JAYA_ANDROID` adalah ekstensi mobile pintar dan portabel untuk ekosistem **JAYA**. Dirancang dengan arsitektur **JARVIS Hybrid Connectivity**, JAYA_ANDROID memungkinkan pengguna mengakses seluruh informasi dan daya komputasi besar JAYA di PC Server saat terhubung, sekaligus tetap dapat digunakan secara otonom di lokasi tanpa sinyal (*Space Mode*).

---

## 🌟 Pilar Utama JAYA_ANDROID

### 1. ⚡ JARVIS Hybrid Connectivity Protocol
* **Online Mode (Server Connected via LAN / mTLS Link)**:
  * Terhubung secara aman ke PC Server Utama (JAYA_CORE + JAYA_RESEARCH).
  * Pengguna di HP dapat melihat seluruh project, skripsi, graf pengetahuan, dan memori besar JAYA secara *real-time*.
* **Offline / Space Mode (No Signal)**:
  * Saat tidak ada sinyal internet/LAN, JAYA di HP otomatis beralih ke **Small Local Nano Model (GGUF)** dan memori lokal terenkripsi di perangkat.
  * Pengguna tetap dapat bertanya, mencatat, dan bernalar secara lokal.
* **Auto-Sync On Reconnect**:
  * Saat terhubung kembali ke PC Server, semua catatan, memori baru, dan log interaksi di HP otomatis tersinkronisasi ke server pusat.

### 2. 🗣️ Hands-Free Voice Assistant Service
* Layanan latar belakang (*Foreground Service*) dengan pendeteksi kata kunci (*Wake-Word Detector*) `"Hey Jaya"`.
* Mode mikrofon nirkabel dan respon suara (*Text-to-Speech*) berkualitas tinggi.

### 3. 🛡️ Mobile Zero-Trust Armor
* Penyimpanan memori lokal terenkripsi **AES-256-GCM**.
* Autentikasi biometrik (Fingerprint / Face ID) sebelum mengakses data sensitif project pengguna.

---

## 📁 Struktur Direktori JAYA_ANDROID

```text
JAYA_ANDROID/
├── README.md                           # Dokumen Master JAYA_ANDROID
├── docs/
│   ├── 01-architecture/
│   │   └── JARVIS_HYBRID_CONNECTIVITY.md  # Spesifikasi Konektivitas Hybrid JARVIS
│   └── 02-roadmap/
│       └── DEVELOPMENT_ROADMAP.md      # Roadmap Pengembangan Phase A - D
├── app/                                # Android Application Package (Kotlin)
│   └── src/
│       ├── main/
│       │   ├── java/com/jaya/android/
│       │   │   ├── core/               # Local Nano Engine & Cache
│       │   │   ├── network/            # mTLS & WebSockets Server Sync
│       │   │   ├── service/            # Voice Foreground Service
│       │   │   └── ui/                 # Modern Jetpack Compose UI
│       │   └── res/
└── build.gradle.kts                    # Gradle Build Configuration
```

---

## 🚀 Panduan Membangun (Build Guide)

### Prasyarat:
* Android Studio Ladybug / Jellyfish (2024.1+)
* JDK 17+
* Android SDK 34 (Android 14)
* NDK r26+ (untuk kompilasi C++ Nano GGUF Kernel)

### Perintah Build CLI:
```bash
# Debug Build
./gradlew assembleDebug

# Release APK Build
./gradlew assembleRelease
```

---

## 📖 Dokumentasi Lanjutan
* [JARVIS Hybrid Connectivity Spec](docs/01-architecture/JARVIS_HYBRID_CONNECTIVITY.md)
* [Development Roadmap Phase A - D](docs/02-roadmap/DEVELOPMENT_ROADMAP.md)
