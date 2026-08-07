"""
JAYA Indonesian Corpus Builder
Fase 1 — Pengumpulan & Pembersihan Teks Bahasa Indonesia

Strategi multi-sumber (tanpa dependensi berat):
  1. Wikipedia Bahasa Indonesia via Wikimedia dumps (bebas, gratis)
  2. Kalimat seed bawaan (bootstrap tanpa internet)
  3. Generator kalimat JAYA-spesifik (perintah + respons asisten)

Output: JAYA_CORE/data/corpus/id_sentences.txt
        (satu kalimat per baris, UTF-8, sudah dibersihkan)
"""
from __future__ import annotations

import gzip
import logging
import re
import sys
import urllib.request
from pathlib import Path
from typing import Generator, List

logger = logging.getLogger("IndonesianCorpus")

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

CORPUS_DIR    = core_config.DATA_DIR / "corpus"
OUT_FILE      = CORPUS_DIR / "id_sentences.txt"
WIKI_CACHE    = CORPUS_DIR / "id_wiki_raw.json.gz"

# Wikipedia Bahasa Indonesia — abstract dump (~150 MB, lebih kecil dari full dump)
WIKI_DUMP_URL = (
    "https://dumps.wikimedia.org/idwiki/latest/"
    "idwiki-latest-abstract.xml.gz"
)


# ────────────────────────────────────────────────────────────────────────────
# Seed sentences — bootstrap ketika tidak ada internet
# Mencakup: perintah JAYA, percakapan sehari-hari, pengetahuan umum
# ────────────────────────────────────────────────────────────────────────────

_SEED_JAYA_COMMANDS = [
    # Salam & identitas
    "Halo JAYA, apa yang bisa kamu lakukan hari ini?",
    "Siapa kamu sebenarnya?",
    "JAYA, ceritakan tentang dirimu.",
    "Apa kemampuan utamamu?",
    "Apakah kamu bisa bekerja tanpa internet?",
    "JAYA, masuk ke mode senyap.",
    "Aktifkan mode hemat daya.",
    "Matikan semua proses latar belakang.",
    "Tampilkan status sistem saat ini.",
    "Berapa penggunaan RAM sekarang?",
    # Memori & pembelajaran
    "JAYA, ingat bahwa rapat saya besok pukul sembilan pagi.",
    "Simpan catatan ini ke memori jangka panjang.",
    "Apa yang kamu ingat dari percakapan kita kemarin?",
    "Lupakan semua data sesi ini.",
    "Catat bahwa saya lebih suka jawaban singkat.",
    # Pertanyaan sains & teknologi
    "Apa itu kecerdasan buatan?",
    "Bagaimana cara kerja jaringan saraf tiruan?",
    "Jelaskan konsep machine learning dengan sederhana.",
    "Apa perbedaan antara AI lemah dan AI kuat?",
    "Bagaimana cara kerja transformer dalam pemrosesan bahasa?",
    "Apa itu model bahasa besar?",
    "Jelaskan konsep distilasi pengetahuan dalam AI.",
    "Apa itu komputasi kuantum?",
    "Bagaimana cara kerja enkripsi AES?",
    "Apa itu sistem terdistribusi?",
    # Perintah sistem
    "Cari informasi tentang teknologi terbaru.",
    "Buat ringkasan dari dokumen ini.",
    "Analisis data ini dan berikan kesimpulan.",
    "Terjemahkan teks ini ke bahasa Inggris.",
    "Urutkan daftar ini berdasarkan prioritas.",
    "Filter hasil pencarian untuk topik AI saja.",
    "Unduh laporan bulanan terbaru.",
    "Kirim notifikasi pengingat setiap satu jam.",
    "Buka aplikasi penelitian.",
    "Tutup semua tab yang tidak diperlukan.",
    # Kehidupan sehari-hari
    "Ingatkan saya minum air setiap dua jam.",
    "Apa jadwal saya hari ini?",
    "Hitung berapa jam lagi hingga tengah malam.",
    "Apa cuaca di Jakarta hari ini?",
    "Berikan rekomendasi buku yang berhubungan dengan AI.",
    "Tolong bantu saya membuat jadwal belajar mingguan.",
    "Apa langkah pertama untuk memulai proyek penelitian?",
    "Bagaimana cara menulis abstrak yang baik?",
    "Jelaskan metodologi penelitian kualitatif.",
    "Apa perbedaan antara hipotesis dan teori?",
    # Respons JAYA
    "Baik, Bos. Saya sudah mencatat permintaan Anda.",
    "Siap melaksanakan perintah Anda.",
    "Maaf, saya tidak memahami maksud Anda. Bisa diulangi?",
    "Perintah Anda sedang diproses.",
    "Selesai. Ada hal lain yang ingin Anda ketahui?",
    "Saya menemukan informasi yang relevan untuk Anda.",
    "Tidak ada hasil yang ditemukan di memori lokal.",
    "Proses berhasil diselesaikan.",
    "Terjadi kesalahan saat memproses permintaan Anda.",
    "Izinkan saya memverifikasi informasi ini terlebih dahulu.",
]

_SEED_GENERAL_ID = [
    # Bahasa sehari-hari
    "Selamat pagi, semoga hari Anda menyenangkan.",
    "Terima kasih atas bantuan Anda.",
    "Saya sedang belajar kecerdasan buatan.",
    "Indonesia memiliki lebih dari 270 juta penduduk.",
    "Bahasa Indonesia adalah bahasa resmi negara Indonesia.",
    "Teknologi berkembang sangat pesat di era digital ini.",
    "Pendidikan adalah investasi terbaik untuk masa depan.",
    "Ilmu pengetahuan dan teknologi saling melengkapi.",
    "Komputer modern dapat memproses miliaran operasi per detik.",
    "Internet menghubungkan miliaran orang di seluruh dunia.",
    # Sains & pengetahuan
    "Bumi mengorbit matahari dalam waktu sekitar 365 hari.",
    "Air terdiri dari dua atom hidrogen dan satu atom oksigen.",
    "Gravitasi adalah gaya tarik-menarik antara dua benda bermassa.",
    "DNA menyimpan informasi genetik dalam setiap sel makhluk hidup.",
    "Cahaya bergerak dengan kecepatan sekitar 300.000 kilometer per detik.",
    "Atom adalah unit terkecil dari materi yang mempertahankan sifat kimianya.",
    "Evolusi adalah proses perubahan bertahap pada makhluk hidup dari generasi ke generasi.",
    "Otak manusia terdiri dari sekitar 86 miliar neuron.",
    "Sistem tata surya kita memiliki delapan planet.",
    "Alam semesta diperkirakan berusia sekitar 13,8 miliar tahun.",
    # Teknologi AI
    "Pembelajaran mesin adalah cabang dari kecerdasan buatan.",
    "Model bahasa besar dilatih menggunakan miliaran kata teks.",
    "Jaringan saraf tiruan terinspirasi dari cara kerja otak manusia.",
    "Pemrosesan bahasa alami memungkinkan komputer memahami teks manusia.",
    "Computer vision memungkinkan mesin untuk melihat dan mengenali objek.",
    "Reinforcement learning mengajarkan AI melalui sistem hadiah dan hukuman.",
    "Transfer learning memungkinkan model AI belajar dari pengetahuan sebelumnya.",
    "Federated learning memungkinkan pelatihan AI tanpa berbagi data mentah.",
    "Kuantisasi model mengurangi ukuran model AI tanpa kehilangan banyak akurasi.",
    "Edge AI memungkinkan kecerdasan buatan berjalan langsung di perangkat pengguna.",
]

_SEED_SENTENCES = _SEED_JAYA_COMMANDS + _SEED_GENERAL_ID


# ────────────────────────────────────────────────────────────────────────────
# Wikipedia parser (abstractdump XML)
# ────────────────────────────────────────────────────────────────────────────

_CLEAN_RE = [
    re.compile(r"<[^>]+>"),          # strip XML tags
    re.compile(r"&[a-z]+;"),         # strip HTML entities
    re.compile(r"\[\[.*?\]\]"),      # strip wiki links
    re.compile(r"{{.*?}}"),          # strip wiki templates
    re.compile(r"\s{2,}"),           # collapse whitespace
]


def _clean_wiki_text(text: str) -> str:
    for pat in _CLEAN_RE:
        text = pat.sub(" ", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    """Pisahkan paragraf menjadi kalimat-kalimat individual."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    result = []
    for part in parts:
        s = part.strip()
        if 10 <= len(s) <= 500 and not s.startswith("http"):
            result.append(s)
    return result


def _parse_wiki_abstract_xml(raw_gz: bytes) -> Generator[str, None, None]:
    """Parse Wikipedia abstract XML dump dan yield kalimat bersih."""
    try:
        import xml.etree.ElementTree as ET
        xml_bytes = gzip.decompress(raw_gz)
        root = ET.fromstring(xml_bytes)
        for doc in root.findall(".//abstract"):
            if doc.text:
                cleaned = _clean_wiki_text(doc.text)
                for sent in _split_sentences(cleaned):
                    yield sent
    except Exception as exc:
        logger.warning("Wiki XML parse error: %s", exc)


def _download_wiki(url: str, cache_path: Path) -> bytes:
    """Download Wikipedia dump dengan progress, simpan ke cache."""
    if cache_path.exists():
        logger.info("[Corpus] Using cached wiki dump: %s", cache_path)
        return cache_path.read_bytes()

    logger.info("[Corpus] Downloading Wikipedia ID dump (ini mungkin memakan waktu)...")
    logger.info("[Corpus] URL: %s", url)

    def _reporthook(count: int, block_size: int, total_size: int) -> None:
        pct = int(count * block_size * 100 / max(total_size, 1))
        if count % 500 == 0:
            logger.info("[Corpus]   %.1f MB  (%d%%)",
                        count * block_size / 1_000_000, min(pct, 100))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, str(cache_path), reporthook=_reporthook)
        return cache_path.read_bytes()
    except Exception as exc:
        logger.warning("[Corpus] Download gagal: %s. Menggunakan seed saja.", exc)
        return b""


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

class IndonesianCorpus:
    """
    Pengumpul dan pembersih corpus Bahasa Indonesia untuk melatih tokenizer
    dan dataset distilasi NanoModel JAYA.

    Urutan sumber:
      1. Seed sentences bawaan (selalu tersedia)
      2. Wikipedia Bahasa Indonesia (jika ada internet / cache)
    """

    def __init__(
        self,
        out_file: Path = OUT_FILE,
        use_wiki: bool = True,
        max_sentences: int = 500_000,
    ):
        self.out_file     = Path(out_file)
        self.use_wiki     = use_wiki
        self.max_sentences = max_sentences
        self.out_file.parent.mkdir(parents=True, exist_ok=True)

    def build(self) -> int:
        """
        Bangun corpus dan simpan ke out_file.
        Mengembalikan jumlah kalimat yang berhasil dikumpulkan.
        """
        sentences: List[str] = []

        # 1. Seed
        logger.info("[Corpus] Memuat %d seed sentences...", len(_SEED_SENTENCES))
        sentences.extend(_SEED_SENTENCES)

        # 2. Wikipedia (opsional)
        if self.use_wiki and len(sentences) < self.max_sentences:
            raw = _download_wiki(WIKI_DUMP_URL, WIKI_CACHE)
            if raw:
                wiki_count = 0
                for sent in _parse_wiki_abstract_xml(raw):
                    sentences.append(sent)
                    wiki_count += 1
                    if len(sentences) >= self.max_sentences:
                        break
                logger.info("[Corpus] Wikipedia: %d kalimat ditambahkan.", wiki_count)

        # Deduplikasi & simpan
        seen: set = set()
        unique = []
        for s in sentences:
            key = s.lower().strip()
            if key not in seen and len(key) >= 5:
                seen.add(key)
                unique.append(s)

        self.out_fs.write_text("\n".join(unique), encoding="utf-8")
        logger.info("[Corpus] Selesai: %d kalimat unik → %s", len(unique), self.out_file)
        return len(unique)

    def load(self) -> List[str]:
        """Muat corpus yang sudah ada dari file."""
        if not self.out_file.exists():
            logger.warning("[Corpus] %s belum ada. Jalankan build() terlebih dahulu.", self.out_file)
            return list(_SEED_SENTENCES)
        lines = self.out_fs.read_text(encoding="utf-8").splitlines()
        return [l for l in lines if l.strip()]

    def status(self) -> dict:
        if self.out_file.exists():
            count = len(self.out_fs.read_text(encoding="utf-8").splitlines())
            size  = self.out_file.stat().st_size
            return {"exists": True, "sentences": count, "size_bytes": size, "path": str(self.out_file)}
        return {"exists": False, "sentences": len(_SEED_SENTENCES), "path": str(self.out_file)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    corpus = IndonesianCorpus(use_wiki="--no-wiki" not in sys.argv)
    n = corpus.build()
    print(f"\n✅ Corpus selesai: {n:,} kalimat")
    print(f"   Tersimpan di: {corpus.out_file}")
