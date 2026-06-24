# Hierarki Koneksi Jaya AI

Jaya AI dirancang untuk bekerja dalam berbagai kondisi koneksi, dengan prioritas sebagai berikut:

1. **Lokal (Offline-First)**
   - Menggunakan model LLM kecil yang berada di perangkat sendiri (mis. DistilGPT-2 4-bit).
   - Basis pengetahuan terkompresi (FAISS-IVFPQ atau Annoy dengan PQ) untuk pencarian cepat.
   - Tidak memerlukan jaringan, sehingga menjamin privasi maksimal dan latensi nol.

2. **Jaringan Lokal (LAN)**
   - Saat perangkat terdeteksi berada dalam jaringan yang sama (mis. jam tangan dan laptop di rumah melalui Wi-Fi/Bluetooth).
   - Menggunakan mekanisme sinkronisasi delta (hanya mengirim perubahan) untuk basis pengetahuan.
   - Memungkinkan akses ke basis pengetahuan yang lebih besar yang disimpan di perangkat pribadi (laptop) tanpa perlu internet publik.

3. **Internet Publik (Fallback)**
   - Hanya digunakan ketika lokal dan LAN tidak tersedia atau tidak cukup, dan ketika nilai pengguna (soul) mengizinkan.
   - Akses ke layanan publik yang terpercaya (mis. Wikipedia API, DuckDuckGo Instant Answer) dengan filter ketat:
     - Whitelist domain (hanya domain yang disetujui).
     - Sanitasi permintaan keluar untuk mencegah konten berbahaya.
     - Filter respons masuk untuk menghapus konten yang tidak sesuai.
     - Selalu menggunakan enkripsi TLS.

Algoritma pemilihan koneksi:
- Coba lokal terlebih dahulu (selalu diizinkan).
- Jika tidak cukup, coba LAN (jika tersedia dan diizinkan oleh nilai).
- Jika masih tidak cukup dan internet diizinkan, coba internet publik.
- Jika semua gagal, kembalikan respons fallback (maaf, saya tidak dapat menemukan jawaban).

Nilai pengguna (soul) menilai apakah niat pengguna sesuai dengan preferensi pribadi (mis. topik sensitif seperti kesehatan atau keuangan mungkin lebih memilih sumber pribadi).