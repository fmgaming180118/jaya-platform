"""
JAYA Distillation Dataset Generator
Fase 2 — Menghasilkan pasang (input, target, soft_logits) untuk melatih NanoModel

Strategi:
  - Jika NVIDIA_API_KEY tersedia: gunakan Teacher NIM untuk generate target responses
  - Jika tidak: gunakan dataset bawaan (curated QA pairs Bahasa Indonesia)

Output: JAYA_CORE/data/id_distill_dataset.jsonl
Format: {"input": "...", "target": "...", "domain": "..."}
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger("DistillationDataset")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

DATASET_FILE = core_config.DATA_DIR / "id_distill_dataset.jsonl"


# ────────────────────────────────────────────────────────────────────────────
# Curated QA Dataset — selalu tersedia tanpa internet/API
# Domain: perintah JAYA, pengetahuan umum, sains, teknologi AI
# ────────────────────────────────────────────────────────────────────────────

_CURATED_QA: List[Dict[str, str]] = [
    # ── Identitas JAYA ──────────────────────────────────────────────────────
    {"input": "siapa kamu?", "target": "Saya JAYA, asisten AI lokal Anda yang sovereign. Saya berjalan sepenuhnya di perangkat Anda tanpa bergantung pada cloud.", "domain": "identity"},
    {"input": "apa itu jaya?", "target": "JAYA adalah sistem AI sovereign yang dirancang untuk berjalan di perangkat dengan sumber daya terbatas, dilengkapi 40 pilar kecerdasan.", "domain": "identity"},
    {"input": "apakah kamu bisa bekerja tanpa internet?", "target": "Ya, Bos. Saya dirancang untuk beroperasi penuh secara offline menggunakan memori lokal dan model ringan.", "domain": "identity"},
    {"input": "berapa pilar yang kamu miliki?", "target": "Saya memiliki 40 pilar kognitif yang mencakup jiwa biologis, lapis keamanan, mesin besi, dan kemampuan transendental.", "domain": "identity"},
    {"input": "apa versimu saat ini?", "target": "Saya JAYA versi 18.1, profil Indonesia — ultra-ringan dengan model ternary 2-bit yang berjalan dalam RAM di bawah 200 megabita.", "domain": "identity"},

    # ── Perintah Sistem ─────────────────────────────────────────────────────
    {"input": "matikan lampu", "target": "Baik, Bos. Saya mematikan lampu sekarang.", "domain": "command"},
    {"input": "nyalakan alarm besok jam 6", "target": "Siap. Alarm pukul 06:00 besok pagi telah diaktifkan.", "domain": "command"},
    {"input": "masuk mode senyap", "target": "Mode senyap diaktifkan. Saya tidak akan mengirim notifikasi hingga Anda memberi perintah lagi.", "domain": "command"},
    {"input": "tampilkan status sistem", "target": "Memuat status sistem... RAM, CPU, penyimpanan, dan kondisi pilar aktif sedang diperiksa.", "domain": "command"},
    {"input": "aktifkan mode hemat daya", "target": "Mode hemat daya diaktifkan. Saya mengurangi operasi latar belakang dan menurunkan rasio neuron aktif.", "domain": "command"},
    {"input": "simpan catatan ini", "target": "Catatan telah disimpan ke memori jangka panjang, Bos.", "domain": "command"},
    {"input": "hapus semua data sesi ini", "target": "Data sesi telah dihapus. Memori jangka pendek bersih.", "domain": "command"},
    {"input": "cari informasi tentang machine learning", "target": "Mencari informasi tentang machine learning dari memori lokal dan sumber tersedia.", "domain": "command"},
    {"input": "ingatkan aku minum air setiap dua jam", "target": "Pengingat minum air setiap dua jam telah diatur, Bos.", "domain": "command"},
    {"input": "hitung 25 dikali 4", "target": "25 dikali 4 adalah 100.", "domain": "command"},
    {"input": "buka aplikasi kamera", "target": "Membuka aplikasi kamera sekarang.", "domain": "command"},
    {"input": "tutup semua aplikasi", "target": "Menutup semua aplikasi yang terbuka.", "domain": "command"},
    {"input": "hubungkan ke wifi", "target": "Mencoba menghubungkan ke jaringan WiFi terdekat.", "domain": "command"},
    {"input": "berapa baterai tersisa", "target": "Memeriksa status baterai perangkat Anda.", "domain": "command"},
    {"input": "putar musik", "target": "Memutar musik dari perpustakaan lokal Anda.", "domain": "command"},

    # ── Pertanyaan Umum ──────────────────────────────────────────────────────
    {"input": "apa itu kecerdasan buatan?", "target": "Kecerdasan buatan adalah bidang ilmu komputer yang membuat mesin mampu meniru kecerdasan manusia seperti belajar, bernalar, dan memecahkan masalah.", "domain": "knowledge"},
    {"input": "apa itu machine learning?", "target": "Machine learning adalah cabang kecerdasan buatan di mana komputer belajar dari data untuk membuat prediksi atau keputusan tanpa diprogram secara eksplisit.", "domain": "knowledge"},
    {"input": "bagaimana cara kerja jaringan saraf?", "target": "Jaringan saraf tiruan terdiri dari node-node yang terhubung dalam lapisan. Data mengalir dari lapisan input, diproses di lapisan tersembunyi, dan menghasilkan output.", "domain": "knowledge"},
    {"input": "apa itu transformer dalam AI?", "target": "Transformer adalah arsitektur model AI yang menggunakan mekanisme perhatian untuk memproses urutan data secara paralel, menjadi fondasi model bahasa seperti GPT dan BERT.", "domain": "knowledge"},
    {"input": "apa perbedaan AI lemah dan AI kuat?", "target": "AI lemah dirancang untuk tugas spesifik seperti bermain catur. AI kuat memiliki kecerdasan umum setara manusia — ini yang sedang dibangun oleh JAYA.", "domain": "knowledge"},
    {"input": "apa itu deep learning?", "target": "Deep learning menggunakan jaringan saraf berlapis sangat dalam untuk belajar representasi kompleks dari data, sangat efektif untuk gambar, suara, dan teks.", "domain": "knowledge"},
    {"input": "apa itu model bahasa besar?", "target": "Model bahasa besar adalah sistem AI yang dilatih pada teks berskala masif, mampu menghasilkan, memahami, dan merangkum teks dalam berbagai bahasa.", "domain": "knowledge"},
    {"input": "apa itu reinforcement learning?", "target": "Reinforcement learning adalah metode di mana AI belajar melalui percobaan dan kesalahan, mendapat hadiah saat berhasil dan penalti saat gagal.", "domain": "knowledge"},
    {"input": "bagaimana cara kerja GPS?", "target": "GPS bekerja dengan menerima sinyal dari minimal empat satelit orbit Bumi, menghitung jarak ke masing-masing, lalu menentukan posisi tepat melalui triangulasi.", "domain": "knowledge"},
    {"input": "apa itu enkripsi?", "target": "Enkripsi adalah proses mengubah data menjadi format yang tidak terbaca tanpa kunci khusus, melindungi informasi dari akses tidak sah.", "domain": "knowledge"},
    {"input": "apa itu blockchain?", "target": "Blockchain adalah basis data terdistribusi yang menyimpan catatan dalam blok-blok yang saling terhubung secara kriptografis, membuat data sangat sulit diubah.", "domain": "knowledge"},

    # ── Teknologi JAYA-spesifik ─────────────────────────────────────────────
    {"input": "apa itu distilasi pengetahuan?", "target": "Distilasi pengetahuan adalah teknik melatih model AI kecil (student) agar meniru perilaku model besar (teacher), menghasilkan model efisien dengan kecerdasan tinggi.", "domain": "ai_tech"},
    {"input": "apa itu kuantisasi model?", "target": "Kuantisasi mengurangi presisi bobot model dari 32-bit ke 8-bit atau bahkan 2-bit, memperkecil ukuran model secara drastis dengan sedikit kehilangan akurasi.", "domain": "ai_tech"},
    {"input": "apa itu edge AI?", "target": "Edge AI adalah kecerdasan buatan yang berjalan langsung di perangkat pengguna seperti smartphone atau smartwatch, bukan di server cloud.", "domain": "ai_tech"},
    {"input": "apa itu BPE tokenizer?", "target": "Byte-Pair Encoding adalah algoritma tokenisasi yang memecah kata menjadi subword berdasarkan frekuensi kemunculan, efisien untuk bahasa apapun termasuk Indonesia.", "domain": "ai_tech"},
    {"input": "apa itu mixture of experts?", "target": "Mixture of Experts adalah arsitektur AI di mana hanya sebagian kecil 'ahli' jaringan yang diaktifkan per input, menghemat komputasi secara drastis.", "domain": "ai_tech"},
    {"input": "apa itu federated learning?", "target": "Federated learning memungkinkan model AI dilatih di banyak perangkat secara lokal, lalu hanya pembaruan modelnya yang digabungkan, menjaga privasi data pengguna.", "domain": "ai_tech"},
    {"input": "apa itu ternary neural network?", "target": "Jaringan saraf ternary menggunakan bobot hanya bernilai minus satu, nol, atau satu, menggantikan perkalian float dengan penjumlahan sederhana, sangat efisien di hardware terbatas.", "domain": "ai_tech"},

    # ── Bahasa Indonesia & Linguistik ───────────────────────────────────────
    {"input": "apa itu bahasa indonesia?", "target": "Bahasa Indonesia adalah bahasa resmi dan bahasa persatuan Indonesia, dituturkan oleh lebih dari 270 juta orang sebagai bahasa pertama atau kedua.", "domain": "language"},
    {"input": "berapa jumlah kata dalam bahasa indonesia?", "target": "Kamus Besar Bahasa Indonesia memuat lebih dari 127 ribu entri kata, belum termasuk kosakata daerah dan serapan asing.", "domain": "language"},
    {"input": "apa itu morfologi dalam linguistik?", "target": "Morfologi adalah cabang linguistik yang mempelajari struktur kata dan bagaimana morfem — unit terkecil bermakna — digabungkan membentuk kata.", "domain": "language"},
    {"input": "apa contoh prefiks bahasa indonesia?", "target": "Contoh prefiks Bahasa Indonesia: me- (menulis), di- (ditulis), ber- (berlari), ter- (terlambat), pe- (penulis), ke- (ketua).", "domain": "language"},

    # ── Matematika & Logika ─────────────────────────────────────────────────
    {"input": "berapa 15 tambah 27?", "target": "15 ditambah 27 sama dengan 42.", "domain": "math"},
    {"input": "hitung 100 dibagi 4", "target": "100 dibagi 4 sama dengan 25.", "domain": "math"},
    {"input": "berapa akar kuadrat dari 144?", "target": "Akar kuadrat dari 144 adalah 12.", "domain": "math"},
    {"input": "apa itu bilangan prima?", "target": "Bilangan prima adalah bilangan asli lebih besar dari 1 yang hanya habis dibagi oleh 1 dan dirinya sendiri. Contoh: 2, 3, 5, 7, 11.", "domain": "math"},
    {"input": "berapa nilai pi?", "target": "Nilai pi adalah 3,14159265... sebuah konstanta matematika yang merepresentasikan perbandingan keliling lingkaran dengan diameternya.", "domain": "math"},

    # ── Percakapan Sehari-hari ──────────────────────────────────────────────
    {"input": "selamat pagi", "target": "Selamat pagi, Bos! Semoga hari Anda penuh produktivitas. Ada yang bisa saya bantu?", "domain": "greeting"},
    {"input": "selamat malam", "target": "Selamat malam, Bos. Semoga Anda beristirahat dengan baik. Saya siap jika ada yang dibutuhkan.", "domain": "greeting"},
    {"input": "terima kasih", "target": "Sama-sama, Bos! Selalu senang bisa membantu Anda.", "domain": "greeting"},
    {"input": "maaf, saya salah", "target": "Tidak masalah, Bos. Kesalahan adalah bagian dari pembelajaran. Bagaimana saya bisa membantu Anda sekarang?", "domain": "greeting"},
    {"input": "apa kabar?", "target": "Sistem saya berjalan dengan baik, Bos. Semua pilar aktif dan siap melayani Anda.", "domain": "greeting"},
    {"input": "sampai jumpa", "target": "Sampai jumpa, Bos! Hubungi saya kapanpun Anda membutuhkan bantuan.", "domain": "greeting"},
    {"input": "tolong bantu saya", "target": "Tentu, Bos! Saya di sini untuk membantu. Apa yang ingin Anda kerjakan?", "domain": "greeting"},
    {"input": "saya tidak mengerti", "target": "Tidak apa-apa, Bos. Izinkan saya menjelaskan dengan cara yang lebih mudah.", "domain": "greeting"},
]


# ────────────────────────────────────────────────────────────────────────────
# Teacher-augmented generation (via NVIDIA NIM)
# ────────────────────────────────────────────────────────────────────────────

def _generate_via_nim(
    prompts: List[str],
    api_key: str,
    base_url: str,
    model: str = "meta/llama-3.1-8b-instruct",
    batch_size: int = 5,
) -> Iterator[Dict[str, str]]:
    """Gunakan Teacher NIM untuk generate respons tambahan."""
    try:
        import json as _json
        import urllib.request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    except ImportError:
        return

    system_prompt = (
        "Kamu adalah JAYA, asisten AI lokal yang berbicara bahasa Indonesia. "
        "Berikan jawaban singkat, padat, dan dalam bahasa Indonesia yang natural. "
        "Maksimal 2 kalimat per jawaban."
    )

    for i in range(0, len(prompts), batch_size):
        batch = prompts[i:i + batch_size]
        for prompt in batch:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 100,
                    "temperature": 0.7,
                }
                data = json.dumps(payload).encode()
                req = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                    target = result["choices"][0]["message"]["content"].strip()
                    yield {"input": prompt, "target": target, "domain": "nim_generated"}
                    time.sleep(0.3)  # rate limiting
            except Exception as exc:
                logger.warning("[Dataset] NIM call gagal untuk %r: %s", prompt[:40], exc)


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

class DistillationDataset:
    """
    Generator dataset distilasi Bahasa Indonesia untuk NanoModel JAYA.

    Selalu menghasilkan curated dataset (offline-safe), dan opsional
    memperkaya dengan Teacher NIM jika API key tersedia.
    """

    def __init__(self, out_file: Path = DATASET_FILE):
        self.out_file = Path(out_file)
        self.out_file.parent.mkdir(parents=True, exist_ok=True)

        # Cek NIM availability
        self._api_key  = os.getenv("NVIDIA_API_KEY", "")
        self._base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self._use_nim  = bool(self._api_key)

        if self._use_nim:
            logger.info("[Dataset] NVIDIA NIM tersedia — akan menggunakan Teacher augmentation")
        else:
            logger.info("[Dataset] Tanpa NIM — menggunakan curated dataset saja (%d entries)", len(_CURATED_QA))

    def build(self, nim_extra_prompts: Optional[List[str]] = None) -> int:
        """
        Bangun dataset dan simpan ke out_file.
        Returns jumlah entry yang dihasilkan.
        """
        entries: List[Dict[str, str]] = list(_CURATED_QA)

        # Augmentasi via NIM jika tersedia
        if self._use_nim:
            extra_prompts = nim_extra_prompts or self._default_extra_prompts()
            logger.info("[Dataset] Menghasilkan %d entry tambahan via NIM...", len(extra_prompts))
            for entry in _generate_via_nim(extra_prompts, self._api_key, self._base_url):
                entries.append(entry)
                logger.debug("[Dataset] NIM: %r → %r", entry["input"][:30], entry["target"][:40])

        # Simpan sebagai JSONL
        with open(self.out_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("[Dataset] Selesai: %d entry → %s", len(entries), self.out_file)
        return len(entries)

    def load(self) -> List[Dict[str, str]]:
        """Muat dataset dari disk."""
        if not self.out_file.exists():
            logger.warning("[Dataset] File belum ada. Mengembalikan curated saja.")
            return list(_CURATED_QA)
        entries = []
        with open(self.out_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _default_extra_prompts(self) -> List[str]:
        """Prompt tambahan untuk Teacher NIM — variasi lebih kaya."""
        return [
            "apa manfaat belajar kecerdasan buatan?",
            "bagaimana cara meningkatkan produktivitas sehari-hari?",
            "apa langkah-langkah membuat aplikasi mobile?",
            "jelaskan cara kerja sensor accelerometer di smartwatch",
            "apa perbedaan CPU dan GPU dalam komputasi AI?",
            "bagaimana cara kompres ukuran model AI agar muat di smartwatch?",
            "apa itu autonomous agent dalam kecerdasan buatan?",
            "jelaskan konsep memori jangka pendek dan panjang pada AI",
            "bagaimana JAYA bisa berjalan di perangkat dengan RAM terbatas?",
            "apa itu sovereign AI?",
        ]

    def status(self) -> dict:
        n = len(self.load())
        return {
            "exists": self.out_file.exists(),
            "entries": n,
            "nim_available": self._use_nim,
            "path": str(self.out_file),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    ds = DistillationDataset()
    n = ds.build()
    print(f"\n✅ Dataset distilasi selesai: {n} entry")
    print(f"   File: {ds.out_file}")
    # Preview
    samples = ds.load()[:3]
    for s in samples:
        print(f"\n  Input : {s['input']}")
        print(f"  Target: {s['target']}")
        print(f"  Domain: {s['domain']}")
