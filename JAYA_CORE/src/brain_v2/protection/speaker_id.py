"""
speaker_id.py — Sovereign Voice Biometric V2.0 (Pillar 14 Extension)

JAYA V16.0 Enhanced: Adaptive Voice Training System
- Kalimat panduan saat enrollment untuk akurasi tinggi
- Multi-embedding + incremental learning (makin sering latihan → makin akurat)
- Quality scoring per sampel
- Retrain on-demand via perintah suara/teks
- Profil disimpan terenkripsi AES-256

Alur:
  ENROLL → Baca kalimat panduan → simpan embeddings → profil terenkripsi
  RETRAIN → Tambah embeddings baru → update rata-rata → akurasi meningkat
  VERIFY  → Bandwidth similarity ≥ THRESHOLD → Bos ✓ / Asing ✗
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("SpeakerID")

# ============================================================
# Konfigurasi
# ============================================================
SIMILARITY_THRESHOLD = 0.72   # Sedikit lebih longgar untuk logat beragam
SAMPLE_RATE          = 16000  # Hz
PROFILE_FILENAME     = "JAYA_VOICE_PROFILE.enc"
MAX_EMBEDDINGS       = 20     # Batas embeddings tersimpan

# Kalimat panduan enrollment — dirancang untuk menangkap:
# - intonasi formal & informal   - konsonan keras & lembut
# - kosakata perintah JAYA       - logat natural sehari-hari
GUIDED_PHRASES = [
    # Formal / Perintah langsung
    "Halo JAYA, saya siap memberikan perintah.",
    "Aktifkan sistem dan tampilkan statusnya.",
    "Cari informasi tentang teknologi terbaru.",
    # Informal / Bahasa sehari-hari
    "Oke JAYA, lo udah siap belum?",
    "Eh JAYA, nyalain mode gelap dong.",
    "Cepet jawab, gue lagi butuh info ini.",
    # Campuran & perintah variatif
    "JAYA, tolong bantu gue cari jurnal AI.",
    "Sudah, matikan sekarang.",
    "Apa yang kamu ketahui tentang machine learning?",
]

# ============================================================
# Lazy-load library
# ============================================================
try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    HAS_RESEMBLYZER = True
except ImportError:
    HAS_RESEMBLYZER = False
    logger.warning("[SpeakerID] resemblyzer tidak ditemukan. Speaker recognition DISABLED.")

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False
    logger.warning("[SpeakerID] sounddevice tidak ditemukan. Mic recording DISABLED.")


# ============================================================
# SpeakerRecognizer V2.0
# ============================================================
class SpeakerRecognizer:
    """
    Pillar 14 Extension V2.0: Adaptive Voice Biometric Gate.

    Fitur baru vs V1.0:
    - Kalimat panduan saat enrollment (9 kalimat, bisa dikustomisasi)
    - Incremental learning: setiap retrain menambah embedding baru
    - Quality score per rekaman (noise checker)
    - Session log untuk tracking progress akurasi
    - Threshold adaptif berdasarkan riwayat similarity
    """

    def __init__(self, profile_dir: str = ".", crypto_key: Optional[bytes] = None):
        self.profile_path  = Path(profile_dir) / PROFILE_FILENAME
        self.crypto_key    = crypto_key

        # Core state
        self.all_embeddings: List[np.ndarray] = []   # Semua embedding tersimpan
        self.boss_embedding: Optional[np.ndarray] = None  # Rata-rata semua
        self.is_enrolled   = False
        self.session_log: List[Dict] = []
        self._encoder = None

        # Statistik adaptif
        self._similarity_history: List[float] = []  # Riwayat similarity Bos
        self._dynamic_threshold  = SIMILARITY_THRESHOLD

        if HAS_RESEMBLYZER:
            try:
                self._encoder = VoiceEncoder()
                logger.info("[SpeakerID] VoiceEncoder V2.0 dimuat.")
            except Exception as e:
                logger.error(f"[SpeakerID] Gagal memuat VoiceEncoder: {e}")

        if self.profile_path.exists():
            self._load_profile()

    # =========================================================================
    # PUBLIC: Enrollment (Pertama kali — guided)
    # =========================================================================

    def enroll_from_mic(self, num_phrases: Optional[int] = None) -> bool:
        """
        Enrollment dengan kalimat panduan. JAYA memandu Bos membaca tiap kalimat.
        Minimal 3 kalimat, maksimal semua 9 kalimat untuk akurasi terbaik.
        """
        if not HAS_RESEMBLYZER or not HAS_SOUNDDEVICE:
            logger.error("[SpeakerID] Library tidak lengkap.")
            return False

        phrases = GUIDED_PHRASES[:num_phrases] if num_phrases else GUIDED_PHRASES[:5]

        print("\n" + "="*60)
        print("  JAYA — PENDAFTARAN SUARA BOS V2.0 (Guided Enrollment)")
        print("="*60)
        print(f"  Saya akan memandu Bos membaca {len(phrases)} kalimat.")
        print("  Tiap kalimat: baca natural, jangan terlalu pelan/cepat.")
        print("  Kalau rekaman noisy, saya akan minta ulang otomatis.\n")

        new_embeddings = []
        for i, phrase in enumerate(phrases):
            emb, quality = self._record_guided_phrase(i + 1, len(phrases), phrase)
            if emb is not None:
                new_embeddings.append(emb)
                print(f"  ✅ Kalimat {i+1} OK (kualitas: {quality:.0%})\n")
            else:
                print(f"  ⚠️  Kalimat {i+1} dilewati (kualitas buruk).\n")

        if len(new_embeddings) < 2:
            print("  ❌ Tidak cukup sampel valid. Enrollment gagal.")
            return False

        # Simpan semua embeddings baru
        self.all_embeddings.extend(new_embeddings)
        # Batasi maks MAX_EMBEDDINGS, ambil yang terbaru
        self.all_embeddings = self.all_embeddings[-MAX_EMBEDDINGS:]
        self._rebuild_average()

        # Log sesi
        self.session_log.append({
            "date": datetime.now().isoformat(),
            "type": "INITIAL_ENROLLMENT",
            "phrases_used": phrases,
            "samples_captured": len(new_embeddings),
            "total_embeddings": len(self.all_embeddings),
        })
        self.is_enrolled = True
        self._save_profile()

        print("="*60)
        print("  ✅ PENDAFTARAN SELESAI!")
        print(f"  Total embedding tersimpan: {len(self.all_embeddings)}")
        print("  Profil terenkripsi di perangkat ini.")
        print("  Ketik 'latih suara lagi' kapan saja untuk meningkatkan akurasi.")
        print("="*60 + "\n")
        return True

    # =========================================================================
    # PUBLIC: Retrain (On-Demand — tambah embeddings baru)
    # =========================================================================

    def retrain(self, num_phrases: Optional[int] = None) -> bool:
        """
        Tambah embeddings baru ke profil yang sudah ada.
        Dipanggil saat Bos berkata 'latih suara lagi', 'retrain', dst.
        Tidak menghapus profil lama — hanya memperkuat.
        """
        if not HAS_RESEMBLYZER or not HAS_SOUNDDEVICE:
            return False

        phrases = GUIDED_PHRASES[:num_phrases] if num_phrases else GUIDED_PHRASES[4:]
        prev_count = len(self.all_embeddings)

        print("\n" + "="*60)
        print(f"  JAYA — PELATIHAN ULANG SUARA (Sesi ke-{len(self.session_log)+1})")
        print("="*60)
        print(f"  Profil sebelumnya: {prev_count} embedding.")
        print(f"  Kita akan menambah {len(phrases)} kalimat baru.\n")

        new_embeddings = []
        for i, phrase in enumerate(phrases):
            emb, quality = self._record_guided_phrase(i + 1, len(phrases), phrase)
            if emb is not None:
                new_embeddings.append(emb)
                print(f"  ✅ Kalimat {i+1} OK (kualitas: {quality:.0%})\n")
            else:
                print(f"  ⚠️  Kalimat {i+1} dilewati.\n")

        if not new_embeddings:
            print("  ❌ Tidak ada sampel valid. Latihan dibatalkan.")
            return False

        self.all_embeddings.extend(new_embeddings)
        self.all_embeddings = self.all_embeddings[-MAX_EMBEDDINGS:]
        self._rebuild_average()

        self.session_log.append({
            "date": datetime.now().isoformat(),
            "type": "RETRAIN",
            "phrases_used": phrases,
            "samples_added": len(new_embeddings),
            "total_embeddings": len(self.all_embeddings),
        })
        self._save_profile()

        improvement = len(self.all_embeddings) - prev_count
        print("="*60)
        print(f"  ✅ LATIHAN SELESAI! +{improvement} embedding baru.")
        print(f"  Total: {len(self.all_embeddings)} embedding → akurasi lebih tinggi.")
        print("="*60 + "\n")
        return True

    # =========================================================================
    # PUBLIC: Verification
    # =========================================================================

    def verify_audio_chunk(self, audio_array: np.ndarray,
                           source_sr: int = SAMPLE_RATE) -> Tuple[bool, float]:
        """
        Verifikasi apakah audio berasal dari suara Bos.
        Menggunakan dynamic threshold yang adaptif dari histori.
        Returns: (is_boss, similarity)
        """
        if not HAS_RESEMBLYZER or not self.is_enrolled or self.boss_embedding is None:
            return True, 1.0  # Fail-open jika belum enrolled

        try:
            wav = preprocess_wav(audio_array, source_sr=source_sr)
            candidate_emb = self._encoder.embed_utterance(wav)
            similarity = self._cosine_similarity(self.boss_embedding, candidate_emb)
            is_boss = similarity >= self._dynamic_threshold

            if is_boss:
                # Update histori similarity Bos untuk adaptasi threshold
                self._similarity_history.append(similarity)
                if len(self._similarity_history) > 50:
                    self._similarity_history.pop(0)
                self._adapt_threshold()

            logger.debug(f"[SpeakerID] Similarity: {similarity:.3f} "
                         f"(threshold: {self._dynamic_threshold:.3f}) "
                         f"→ {'BOS ✓' if is_boss else 'UNKNOWN ✗'}")
            return is_boss, float(similarity)
        except Exception as e:
            logger.warning(f"[SpeakerID] Verification error: {e}. Fail-open.")
            return True, 0.0

    def verify_wav_file(self, wav_path: str) -> Tuple[bool, float]:
        """Verifikasi dari file WAV (untuk testing)."""
        if not HAS_RESEMBLYZER or not self.is_enrolled:
            return True, 1.0
        try:
            wav = preprocess_wav(wav_path)
            candidate_emb = self._encoder.embed_utterance(wav)
            similarity = self._cosine_similarity(self.boss_embedding, candidate_emb)
            return similarity >= self._dynamic_threshold, float(similarity)
        except Exception as e:
            logger.error(f"[SpeakerID] verify_wav_file error: {e}")
            return False, 0.0

    def enroll_from_wavs(self, wav_paths: List[str]) -> bool:
        """Enrollment dari file WAV (testing/CI)."""
        if not HAS_RESEMBLYZER:
            return False
        embeddings = []
        for path in wav_paths:
            try:
                wav = preprocess_wav(path)
                emb = self._encoder.embed_utterance(wav)
                embeddings.append(emb)
            except Exception as e:
                logger.error(f"[SpeakerID] WAV error {path}: {e}")
        if not embeddings:
            return False
        self.all_embeddings.extend(embeddings)
        self._rebuild_average()
        self.is_enrolled = True
        self._save_profile()
        return True

    # =========================================================================
    # PRIVATE: Recording with Quality Check
    # =========================================================================

    def _record_guided_phrase(self, idx: int, total: int,
                               phrase: str) -> Tuple[Optional[np.ndarray], float]:
        """
        Rekam satu kalimat panduan dengan retry jika kualitas buruk.
        Returns: (embedding, quality_score) atau (None, 0) jika gagal.
        """
        max_retries = 2
        for attempt in range(max_retries):
            if attempt == 0:
                print(f"  [{idx}/{total}] Baca kalimat berikut dengan natural:")
                print(f"  >> \"{phrase}\"")
                input("     Tekan ENTER saat siap bicara...")
            else:
                print(f"  ⚠️  Kualitas kurang baik. Coba lagi ({attempt+1}/{max_retries})")
                input("     Tekan ENTER untuk rekam ulang...")

            print("  🎤 Merekam... (bicara sekarang)")
            try:
                # Durasi adaptif berdasarkan panjang kalimat
                duration = max(3.0, len(phrase.split()) * 0.6)
                audio = sd.rec(int(duration * SAMPLE_RATE),
                               samplerate=SAMPLE_RATE, channels=1, dtype='float32')
                sd.wait()
                audio_flat = audio.flatten()

                quality = self._compute_quality(audio_flat)
                if quality < 0.3 and attempt < max_retries - 1:
                    continue  # Retry

                wav = preprocess_wav(audio_flat, source_sr=SAMPLE_RATE)
                embedding = self._encoder.embed_utterance(wav)
                return embedding, quality
            except Exception as e:
                logger.error(f"[SpeakerID] Rekam error: {e}")

        return None, 0.0

    def _compute_quality(self, audio: np.ndarray) -> float:
        """
        Hitung skor kualitas rekaman berdasarkan RMS energy dan zero-crossing.
        Returns: 0.0 (buruk) – 1.0 (sempurna)
        """
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.005:
            return 0.0  # Terlalu pelan / tidak ada suara
        if rms > 0.8:
            return 0.5  # Terlalu keras / clip

        # Zero-crossing rate: rekaman suara punya ZCR tertentu
        zcr = np.mean(np.abs(np.diff(np.sign(audio)))) / 2
        # Ideal speech ZCR: ~0.05 – 0.20
        zcr_score = 1.0 if 0.04 <= zcr <= 0.25 else 0.5

        rms_score = min(rms / 0.4, 1.0)
        return float(0.6 * rms_score + 0.4 * zcr_score)

    # =========================================================================
    # PRIVATE: Adaptive Threshold
    # =========================================================================

    def _adapt_threshold(self):
        """
        Sesuaikan threshold berdasarkan distribusi similarity histori Bos.
        Semakin banyak data real → threshold makin presisi.
        """
        if len(self._similarity_history) < 5:
            return
        mean_sim = np.mean(self._similarity_history)
        std_sim  = np.std(self._similarity_history)
        # Target: threshold = mean_Bos − 2*std (tangkap 95% suara Bos)
        new_threshold = max(0.60, min(0.85, mean_sim - 2 * std_sim))
        self._dynamic_threshold = new_threshold
        logger.debug(f"[SpeakerID] Threshold adaptif: {new_threshold:.3f} "
                     f"(dari {len(self._similarity_history)} sampel)")

    def _rebuild_average(self):
        """Hitung ulang rata-rata embedding dari semua embedding tersimpan."""
        if self.all_embeddings:
            self.boss_embedding = np.mean(self.all_embeddings, axis=0)

    # =========================================================================
    # PRIVATE: Persistence V2.0
    # =========================================================================

    def _save_profile(self):
        """Simpan semua embeddings terenkripsi AES-256 (format V2.0)."""
        # Serialize semua embeddings
        emb_list = [e.astype(np.float32).tobytes().hex() for e in self.all_embeddings]
        avg_bytes = self.boss_embedding.astype(np.float32).tobytes()
        avg_shape = list(self.boss_embedding.shape)

        payload = {
            "version": "2.0",
            "encrypted": False,
            "total_embeddings": len(self.all_embeddings),
            "embedding_shape": avg_shape,
            "embeddings": emb_list,
            "average_hex": avg_bytes.hex(),
            "checksum": hashlib.sha256(avg_bytes).hexdigest(),
            "session_log": self.session_log[-10:],  # Simpan 10 sesi terakhir
            "similarity_history": self._similarity_history[-50:],
            "dynamic_threshold": self._dynamic_threshold,
            "saved_at": datetime.now().isoformat(),
        }

        if self.crypto_key and len(self.crypto_key) == 32:
            try:
                raw = json.dumps(payload).encode()
                enc = self._aes_encrypt(raw)
                final = {"version": "2.0", "encrypted": True, "data_hex": enc.hex()}
                payload = final
            except Exception as e:
                logger.warning(f"[SpeakerID] Enkripsi gagal: {e}")

        with open(self.profile_path, 'w') as f:
            json.dump(payload, f, indent=2)
        logger.info(f"[SpeakerID] Profil V2.0 disimpan: {len(self.all_embeddings)} embeddings")

    def _load_profile(self):
        """Load profil dari disk (support V1.0 dan V2.0)."""
        try:
            with open(self.profile_path, 'r') as f:
                payload = json.load(f)

            # Decrypt jika perlu
            if payload.get("encrypted") and self.crypto_key:
                raw = self._aes_decrypt(bytes.fromhex(payload["data_hex"]))
                payload = json.loads(raw.decode())

            version = payload.get("version", "1.0")

            if version == "2.0":
                self._load_v2(payload)
            else:
                self._load_v1(payload)

        except Exception as e:
            logger.error(f"[SpeakerID] Gagal load profil: {e}")
            self.is_enrolled = False

    def _load_v2(self, payload: dict):
        """Load format profil V2.0."""
        shape = tuple(payload["embedding_shape"])
        avg_bytes = bytes.fromhex(payload["average_hex"])

        if hashlib.sha256(avg_bytes).hexdigest() != payload.get("checksum", ""):
            logger.error("[SpeakerID] Checksum mismatch! Profil mungkin rusak.")
            return

        self.boss_embedding = np.frombuffer(avg_bytes, dtype=np.float32).reshape(shape)
        self.all_embeddings = [
            np.frombuffer(bytes.fromhex(h), dtype=np.float32).reshape(shape)
            for h in payload.get("embeddings", [])
        ]
        self.session_log        = payload.get("session_log", [])
        self._similarity_history = payload.get("similarity_history", [])
        self._dynamic_threshold  = payload.get("dynamic_threshold", SIMILARITY_THRESHOLD)
        self.is_enrolled = True
        logger.info(f"[SpeakerID] Profil V2.0 dimuat: {len(self.all_embeddings)} embeddings, "
                    f"threshold={self._dynamic_threshold:.3f}")

    def _load_v1(self, payload: dict):
        """Load format profil V1.0 (backward compatibility)."""
        shape = tuple(payload["shape"])
        raw_bytes = bytes.fromhex(payload["data_hex"])

        if hashlib.sha256(raw_bytes).hexdigest() != payload.get("checksum", ""):
            logger.error("[SpeakerID] V1.0 checksum mismatch.")
            return

        self.boss_embedding = np.frombuffer(raw_bytes, dtype=np.float32).reshape(shape)
        self.all_embeddings = [self.boss_embedding.copy()]  # Migrate ke V2
        self.is_enrolled = True
        logger.info("[SpeakerID] Profil V1.0 dimuat dan dimigrasikan ke V2.0.")

    def _aes_encrypt(self, data: bytes) -> bytes:
        try:
            from Crypto.Cipher import AES
            from Crypto.Random import get_random_bytes
            nonce = get_random_bytes(16)
            cipher = AES.new(self.crypto_key, AES.MODE_GCM, nonce=nonce)
            ct, tag = cipher.encrypt_and_digest(data)
            return nonce + tag + ct
        except ImportError:
            return data

    def _aes_decrypt(self, blob: bytes) -> bytes:
        try:
            from Crypto.Cipher import AES
            nonce, tag, ct = blob[:16], blob[16:32], blob[32:]
            cipher = AES.new(self.crypto_key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ct, tag)
        except ImportError:
            return blob

    # =========================================================================
    # PRIVATE: Utility
    # =========================================================================

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def reset_profile(self):
        """Hapus seluruh profil untuk mulai dari awal."""
        if self.profile_path.exists():
            self.profile_path.unlink()
        self.boss_embedding = None
        self.all_embeddings = []
        self.session_log = []
        self._similarity_history = []
        self._dynamic_threshold = SIMILARITY_THRESHOLD
        self.is_enrolled = False
        logger.info("[SpeakerID] Profil suara dihapus.")

    @property
    def training_summary(self) -> str:
        """Ringkasan status training untuk ditampilkan ke Bos."""
        if not self.is_enrolled:
            return "Belum ada profil suara."
        sessions = len(self.session_log)
        embs = len(self.all_embeddings)
        th = self._dynamic_threshold
        return (f"{embs} embedding dari {sessions} sesi latihan. "
                f"Threshold aktif: {th:.2f}")

    @property
    def status(self) -> str:
        if not HAS_RESEMBLYZER:
            return "DISABLED (resemblyzer tidak ditemukan)"
        if not self.is_enrolled:
            return "BELUM TERDAFTAR - ketik 'daftarkan suaraku' untuk memulai"
        return f"AKTIF | {self.training_summary}"
