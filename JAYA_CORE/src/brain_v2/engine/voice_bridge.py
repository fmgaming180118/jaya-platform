"""
voice_bridge.py — Voice I/O Bridge for Iron Engine V2.0

Phase 11: The Voice of God.

Connects IronEngine output to JayaMouth (TTS) and ears (STT).
V2.0: Speaker recognition gate + Text normalization (informal Indonesian)
"""

import logging
import re
from enum import IntEnum
from typing import Optional

logger = logging.getLogger("VoiceBridge")

# Speaker Recognition (Pillar 14 Extension V2.0)
try:
    from src.brain_v2.protection.speaker_id import SpeakerRecognizer
    HAS_SPEAKER_ID = True
except ImportError:
    HAS_SPEAKER_ID = False
    logger.warning("[Voice] SpeakerRecognizer not available. Speaker ID disabled.")


# ============================================================
# Text Normalizer — Bahasa Tidak Baku & Logat Indonesia
# ============================================================
SLANG_MAP = {
    # Kata ganti
    "gw": "saya", "gue": "saya", "aku": "saya",
    "lo": "kamu", "lu": "kamu", "elo": "kamu",
    "dia": "dia", "mereka": "mereka",
    # Kata kerja tidak baku
    "nyalain": "nyalakan", "matiin": "matikan", "tampilin": "tampilkan",
    "cariin": "carikan", "bukain": "bukakan", "tutup": "tutup",
    "cari": "cari", "buka": "buka", "kasih": "berikan",
    "blok": "blokir", "hapus": "hapus",
    # Kata sifat / adverbia
    "cepet": "cepat", "bentar": "sebentar", "banyak": "banyak",
    "gede": "besar", "kecil": "kecil", "bagus": "bagus",
    "jelek": "buruk", "susah": "sulit", "gampang": "mudah",
    # Kata penghubung
    "udah": "sudah", "belom": "belum",
    "engga": "tidak", "enggak": "tidak", "nggak": "tidak",
    "gak": "tidak", "ga": "tidak", "ndak": "tidak",
    # Kata konfirmasi / perintah
    "oke": "baik", "ok": "baik", "sip": "baik", "siap": "siap",
    "yo": "ayo", "yuk": "ayo", "hayuk": "ayo",
    # Sapaan ke JAYA (semua disamakan)
    "jay": "jaya", "hey jaya": "jaya", "hei jaya": "jaya",
    "eh jaya": "jaya",
    # Kata tanya informal
    "gimana": "bagaimana", "kenapa": "mengapa", "ngapain": "untuk apa",
    "apaan": "apa", "siapa": "siapa", "dimana": "di mana",
    # Kata benda informal
    "hape": "hp", "henpon": "hp", "laptop": "laptop",
    "komputer": "komputer", "internet": "internet",
    # Logat
    "wes": "sudah", "opo": "apa", "ngono": "begitu",  # Jawa
    "apo": "apa", "mano": "mana",  # Sumatera
    "kumaha": "bagaimana", "atuh": "",  # Sunda
}

class TextNormalizer:
    """
    Normalisasi teks hasil STT dari bahasa tidak baku / logat → formal.
    JAYA memahami cara bicara Bos yang natural, bukan hanya bahasa baku.
    """
    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return text
        result = text.lower().strip()

        # Terapkan pemetaan slang (multi-kata dulu, baru satu kata)
        sorted_keys = sorted(SLANG_MAP.keys(), key=len, reverse=True)
        for slang, formal in [(k, SLANG_MAP[k]) for k in sorted_keys]:
            if formal:  # Jangan ganti jika pemetaan kosong (kata filler)
                result = re.sub(r'\b' + re.escape(slang) + r'\b', formal, result)
            else:
                result = re.sub(r'\b' + re.escape(slang) + r'\b', '', result)

        # Bersihkan spasi berlebih
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    @staticmethod
    def detect_retrain_command(text: str) -> bool:
        """Deteksi apakah teks adalah perintah retrain suara."""
        keywords = [
            "latih suara", "retrain suara", "perbaiki pendengaran",
            "latih pendengaran", "daftarkan suara", "training ulang",
            "belajar suara", "kenali suaraku", "latih lagi",
            "voice training", "speaker training", "akurasi suara",
            "aku mau ngajarin", "ajarin lo suara",
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    @staticmethod
    def detect_enrollment_command(text: str) -> bool:
        """Deteksi perintah enrollment pertama kali."""
        keywords = [
            "daftarkan suaraku", "kenali suara saya", "simpan suaraku",
            "enroll suara", "buat profil suara",
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)


class SpeechPriority(IntEnum):
    """Priority levels for speech queue."""
    LOW = 0       # Status updates
    NORMAL = 1    # Regular responses
    URGENT = 2    # Dissent, warnings, blocks


class VoiceBridge:
    """
    Bridges IronEngine ↔ Voice I/O.

    Usage:
        voice = VoiceBridge()
        voice.speak("Selamat pagi, Bos!")
        voice.speak_dissent("Waduh, itu berbahaya!")
        text = voice.listen()  # STT input
    """

    def __init__(self, enable_tts: bool = True, enable_stt: bool = False,
                 profile_dir: str = ".", crypto_key: bytes = None):
        self.tts_enabled = enable_tts
        self.stt_enabled = enable_stt
        self.mouth = None
        self.ear = None

        # Speaker Recognition Gate (Pillar 14)
        self.speaker_id: Optional['SpeakerRecognizer'] = None
        if HAS_SPEAKER_ID:
            self.speaker_id = SpeakerRecognizer(
                profile_dir=profile_dir,
                crypto_key=crypto_key
            )
            logger.info(f"[Voice] Speaker ID: {self.speaker_id.status}")

        if enable_tts:
            self._init_tts()
        if enable_stt:
            self._init_stt()

    def _init_tts(self):
        """Initialize JayaMouth (TTS engine)."""
        try:
            from src.voice_agent.tts import JayaMouth
            self.mouth = JayaMouth()
            self.mouth.start()
            logger.info("[Voice] TTS Engine (JayaMouth) initialized.")
        except ImportError:
            logger.warning("[Voice] JayaMouth not available. TTS disabled.")
            self.tts_enabled = False
        except Exception as e:
            logger.error(f"[Voice] TTS init failed: {e}")
            self.tts_enabled = False

    def _init_stt(self):
        """Initialize speech recognition (STT)."""
        try:
            import speech_recognition as sr
            self.ear = sr.Recognizer()
            logger.info("[Voice] STT Engine initialized.")
        except ImportError:
            logger.warning("[Voice] speech_recognition not available. STT disabled.")
            self.stt_enabled = False

    def speak(self, text: str, priority: SpeechPriority = SpeechPriority.NORMAL):
        """
        Speak text via TTS.
        Falls back to print if TTS unavailable.
        """
        if self.mouth and self.tts_enabled:
            self.mouth.speak(text)
        else:
            # Console fallback
            prefix = {
                SpeechPriority.LOW: "[📢]",
                SpeechPriority.NORMAL: "[🗣️]",
                SpeechPriority.URGENT: "[⚠️🗣️]",
            }.get(priority, "[🗣️]")
            print(f"{prefix} {text}")

    def speak_dissent(self, dissent: str):
        """
        Speak Socratic dissent with URGENT priority.
        Prefixed with attention tone.
        """
        self.speak(f"Bos, saya perlu ngomong. {dissent}", SpeechPriority.URGENT)

    def speak_block(self, reason: str):
        """Announce immune system block."""
        self.speak(f"Aksi diblok. {reason}", SpeechPriority.URGENT)

    def speak_status(self, status: str):
        """Low-priority status announcement."""
        self.speak(status, SpeechPriority.LOW)

    def enroll_boss(self) -> bool:
        """Enrollment pertama kali — JAYA memandu Bos membaca kalimat."""
        if self.speaker_id is None:
            logger.warning("[Voice] Speaker ID module tidak tersedia.")
            return False
        return self.speaker_id.enroll_from_mic()

    def retrain_boss(self) -> bool:
        """
        Retrain on-demand — tambah embeddings baru ke profil yang ada.
        Dipanggil saat Bos berkata 'latih suara lagi', 'retrain', dst.
        """
        if self.speaker_id is None:
            logger.warning("[Voice] Speaker ID tidak tersedia.")
            return False
        if not self.speaker_id.is_enrolled:
            self.speak("Saya belum kenal suara Bos. Mari mulai pendaftaran dulu.")
            return self.speaker_id.enroll_from_mic()
        self.speak("Siap Bos! Mari kita latih pendengaran saya lagi. Ikuti panduan di layar.")
        return self.speaker_id.retrain()

    def voice_status(self) -> str:
        """Kembalikan status speaker ID untuk ditampilkan ke Bos."""
        if self.speaker_id is None:
            return "Speaker ID tidak aktif."
        return self.speaker_id.status

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """
        Listen for voice input via microphone.
        V2.0: Speaker verification gate + text normalization bahasa tidak baku.
        Returns normalized transcribed text or None.
        """
        if not self.stt_enabled or not self.ear:
            return None

        try:
            import numpy as np
            import speech_recognition as sr

            with sr.Microphone() as source:
                logger.info("[Voice] Listening...")
                self.ear.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.ear.listen(source, timeout=timeout)

            # --- SPEAKER VERIFICATION GATE (Pillar 14) ---
            if self.speaker_id and self.speaker_id.is_enrolled:
                try:
                    raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    audio_np = (
                        np.frombuffer(raw_data, dtype=np.int16)
                        .astype(np.float32) / 32768.0
                    )
                    is_boss, similarity = self.speaker_id.verify_audio_chunk(audio_np)
                    if not is_boss:
                        logger.warning(
                            f"[Voice] Suara tidak dikenal (sim={similarity:.2f}). Diabaikan."
                        )
                        return None
                    logger.info(f"[Voice] Bos diverifikasi (sim={similarity:.2f}) ✓")
                except Exception as e:
                    logger.warning(f"[Voice] Verification error: {e}. Melanjutkan.")
            # --- END GATE ---

            # --- STT dengan fallback bahasa ---
            text = None
            # Coba formal Indonesian dulu
            try:
                text = self.ear.recognize_google(audio, language="id-ID")
            except sr.UnknownValueError:
                pass
            except Exception:
                pass

            # Fallback: generic Indonesian (lebih toleran informal)
            if not text:
                try:
                    text = self.ear.recognize_google(audio, language="id")
                except Exception:
                    pass

            if not text:
                return None

            # --- TEXT NORMALIZATION (Bahasa Tidak Baku) ---
            normalized = TextNormalizer.normalize(text)
            if normalized != text:
                logger.info(f"[Voice] Normalized: '{text}' → '{normalized}'")
            else:
                logger.info(f"[Voice] Heard: {text}")

            # --- RETRAIN COMMAND DETECTION ---
            if TextNormalizer.detect_retrain_command(normalized):
                logger.info("[Voice] Retrain command terdeteksi!")
                self.retrain_boss()
                return None  # Retrain ditangani di sini, bukan dikirim ke engine

            return normalized

        except Exception as e:
            logger.debug(f"[Voice] Listen error: {e}")
            return None

    def stop(self):
        """Shutdown voice systems."""
        if self.mouth:
            self.mouth.stop()
            logger.info("[Voice] TTS stopped.")
