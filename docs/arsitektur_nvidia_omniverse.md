# Arsitektur NVIDIA Omniverse Digital Twin

Dokumen ini menjelaskan arsitektur sistem Digital Twin berbasis NVIDIA Omniverse, sebagaimana digambarkan dalam diagram arsitektur yang disediakan.

## Ringkasan Arsitektur
Sistem ini dirancang untuk memfasilitasi kolaborasi real-time, simulasi fisik yang akurat, dan integrasi AI dalam pembuatan Digital Twin. Arsitektur ini menghubungkan berbagai pemangku kepentingan (engineer, reviewer, admin) dengan alat simulasi dan data melalui platform terpusat.

## Komponen Utama

### 1. World State Controller (Inti Sistem)
Ini adalah pusat orkestrasi simulasi.
- **Kit App Streaming**: Menangani streaming aplikasi Omniverse ke pengguna.
- **Simulation Data Delegate**: Mengelola delegasi data simulasi.
- **NVIDIA Warp**: Framework untuk simulasi fisik kinerja tinggi.
- **Flow**: Simulasi fluida/gas (jika relevan dengan konteks).
- **Index**: Pengindeksan data aset.

### 2. Application Hosting
Infrastruktur hosting untuk menjalankan aplikasi Omniverse.
- Bisa berupa **On-Premises** (lokal) atau **Cloud**.
- Mendukung Omniverse App Streaming untuk akses jarak jauh.

### 3. Asset Pipeline (Alur Kerja Aset)
- **OEM Assets**: Aset dari produsen asli, dikonversi ke USD.
- **3D Assets**: Dibuat oleh Design Engineer menggunakan aplikasi DCC/CAD (ISV Application).
- **USD Database**: Penyimpanan pusat untuk semua aset dalam format Universal Scene Description (USD).
- **USD Simulation Schema**: Skema definisi untuk simulasi.

### 4. Surrogate Model NIM (NVIDIA Inference Microservices)
Layanan mikro untuk inferensi AI cepat.
- **PhysicsNemo Inference**: Model AI untuk memprediksi fisika.
- **USD Search**: Pencarian cerdas dalam database USD.
- **Edify 3D**: Generasi konten 3D generative.

### 5. AI Model Training
Siklus pelatihan model AI menggunakan data simulasi.
- **Simulation Data** & **Scene Data**: Data mentah dari simulasi dan scene.
- **PhysicsNemo Training**: Pelatihan model fisika.
- **Simulation Foundation Model**: Model dasar yang dihasilkan.
- Akses oleh **AI Engineer** melalui **AI Training ISV Application**.

## Peran Pengguna (Roles)

1.  **Reviewers**: Mengakses hasil simulasi melalui Omniverse App Streaming.
2.  **Design Engineer**: Membuat aset 3D (CAD/DCC) dan mengunggahnya ke database.
3.  **Network Admin**: Mengelola infrastruktur (NVIDIA Air).
4.  **Mechanical & Electrical Engineers**: Menggunakan aplikasi ISV untuk kontribusi data simulasi dan scene.
5.  **AI Engineer**: Melatih model AI dan mengelola pipeline inferensi.

## Alur Data (Data Flow)

- **USD (Universal Scene Description)**: Standar utama pertukaran data antar semua komponen. Semua aset dikonversi dan disimpan dalam format ini.
- **API**: Menghubungkan World State Controller dengan Surrogate Model NIM.
- **Stream**: Aplikasi di-stream dari server hosting ke perangkat pengguna (Reviewers).
- **ISV Data**: Data spesifik aplikasi industri dikonversi dan diintegrasikan.

---
*Dokumen ini dibuat berdasarkan analisis diagram arsitektur NVIDIA Omniverse Digital Twin.*
