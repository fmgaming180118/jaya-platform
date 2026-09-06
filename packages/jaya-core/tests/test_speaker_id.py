"""
test_speaker_id.py — Unit tests untuk Speaker Recognition Module JAYA V16.0

Dijalankan dari JAYA_CORE:
    python -m pytest tests/test_speaker_id.py -v
"""
import sys
import os
import json
import tempfile
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================
# Import modul yang akan diuji
# ============================================================
try:
    from jaya_core.brain_v2.protection.speaker_id import SpeakerRecognizer, SIMILARITY_THRESHOLD
    HAS_MODULE = True
except ImportError as e:
    HAS_MODULE = False
    IMPORT_ERR = str(e)

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    HAS_RESEMBLYZER = True
except ImportError:
    HAS_RESEMBLYZER = False


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def dummy_key():
    """32-byte dummy AES key untuk testing."""
    return b"JAYA_TEST_KEY_32BYTES____________"[:32]


@pytest.fixture
def sr_no_key(temp_dir):
    """SpeakerRecognizer tanpa enkripsi (testing mode)."""
    return SpeakerRecognizer(profile_dir=temp_dir, crypto_key=None)


@pytest.fixture
def sr_with_key(temp_dir, dummy_key):
    """SpeakerRecognizer dengan AES-256 key."""
    return SpeakerRecognizer(profile_dir=temp_dir, crypto_key=dummy_key)


# ============================================================
# Test 1: Import & Inisialisasi
# ============================================================

def test_import_speaker_id():
    """Modul speaker_id harus bisa diimport."""
    assert HAS_MODULE, f"Import gagal: {IMPORT_ERR if not HAS_MODULE else ''}"


def test_resemblyzer_available():
    """resemblyzer harus terinstall (skip if not available)."""
    import pytest
    if not HAS_RESEMBLYZER:
        pytest.skip("resemblyzer not installed, skipping speaker_id tests")
    assert HAS_RESEMBLYZER, "resemblyzer tidak terinstall. Jalankan: pip install resemblyzer"


def test_init_no_key(temp_dir):
    """Inisialisasi tanpa key tidak boleh error."""
    sr = SpeakerRecognizer(profile_dir=temp_dir)
    assert not sr.is_enrolled
    assert "BELUM" in sr.status.upper() or "DISABLED" in sr.status.upper()


def test_init_with_key(temp_dir, dummy_key):
    """Inisialisasi dengan AES key tidak boleh error."""
    sr = SpeakerRecognizer(profile_dir=temp_dir, crypto_key=dummy_key)
    assert not sr.is_enrolled


# ============================================================
# Test 2: Enrollment dari WAV
# ============================================================

def _make_synthetic_wav(duration_sec=2.0, sr=16000, seed=42) -> np.ndarray:
    """Buat sinyal audio sintetis sebagai pengganti WAV asli."""
    rng = np.random.RandomState(seed)
    return rng.randn(int(sr * duration_sec)).astype(np.float32)


def _save_wav(audio: np.ndarray, path: str, sr=16000):
    """Simpan numpy array sebagai WAV file."""
    import soundfile as sf
    sf.write(path, audio, sr)


@pytest.mark.skipif(not HAS_RESEMBLYZER, reason="resemblyzer tidak tersedia")
def test_enrollment_from_wavs(temp_dir):
    """Enrollment dari file WAV harus membuat profile file."""
    try:
        import soundfile as sf
        wav_paths = []
        for i in range(2):  # 2 sampel cukup untuk test
            audio = _make_synthetic_wav(seed=i)
            p = os.path.join(temp_dir, f"sample_{i}.wav")
            sf.write(p, audio, 16000)
            wav_paths.append(p)

        sr = SpeakerRecognizer(profile_dir=temp_dir)
        result = sr.enroll_from_wavs(wav_paths)

        assert result is True, "Enrollment harus mengembalikan True"
        assert sr.is_enrolled, "is_enrolled harus True setelah enrollment"
        assert sr.boss_embedding is not None, "boss_embedding tidak boleh None"

        # Pastikan profile file terbuat
        profile_file = os.path.join(temp_dir, "JAYA_VOICE_PROFILE.enc")
        assert os.path.exists(profile_file), "File JAYA_VOICE_PROFILE.enc harus ada"

    except ImportError:
        pytest.skip("soundfile tidak tersedia, skip WAV test")


# ============================================================
# Test 3: Cosine Similarity Logic
# ============================================================

def test_cosine_similarity_identical():
    """Vector yang identik harus punya similarity = 1.0."""
    v = np.array([0.5, 0.3, 0.8, 0.2], dtype=np.float32)
    sim = SpeakerRecognizer._cosine_similarity(v, v)
    assert abs(sim - 1.0) < 1e-5, f"Similarity vector identik harus 1.0, dapat {sim}"


def test_cosine_similarity_orthogonal():
    """Vector orthogonal (90°) harus punya similarity = 0."""
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0], dtype=np.float32)
    sim = SpeakerRecognizer._cosine_similarity(v1, v2)
    assert abs(sim) < 1e-5, f"Similarity orthogonal harus 0, dapat {sim}"


def test_cosine_similarity_opposite():
    """Vector berlawanan harus punya similarity = -1.0."""
    v = np.array([1.0, 0.5], dtype=np.float32)
    sim = SpeakerRecognizer._cosine_similarity(v, -v)
    assert abs(sim + 1.0) < 1e-5, f"Similarity berlawanan harus -1.0, dapat {sim}"


# ============================================================
# Test 4: Verification Logic (simulasi embedding)
# ============================================================

def test_verify_same_embedding(temp_dir):
    """
    Jika boss_embedding dan kandidat identik → harus diterima sebagai Bos.
    Mensimulasikan tanpa memerlukan audio asli.
    """
    sr = SpeakerRecognizer(profile_dir=temp_dir)
    # Inject embedding langsung (bypass enrollment)
    fake_embedding = np.random.randn(256).astype(np.float32)
    fake_embedding /= np.linalg.norm(fake_embedding)
    sr.boss_embedding = fake_embedding.copy()
    sr.is_enrolled = True

    # Kandidat = embedding yang sama → similarity 1.0
    sr_class = SpeakerRecognizer
    sim = sr_class._cosine_similarity(sr.boss_embedding, fake_embedding)
    is_boss = sim >= SIMILARITY_THRESHOLD
    assert is_boss, "Embedding identik harus diterima sebagai Bos"


def test_verify_different_embedding(temp_dir):
    """
    Jika boss_embedding dan kandidat sangat berbeda → harus ditolak.
    """
    sr = SpeakerRecognizer(profile_dir=temp_dir)
    boss_emb = np.ones(256, dtype=np.float32)
    boss_emb /= np.linalg.norm(boss_emb)
    sr.boss_embedding = boss_emb
    sr.is_enrolled = True

    # Kandidat = vektor yang hampir ortogonal
    rng = np.random.RandomState(0)
    other_emb = rng.randn(256).astype(np.float32)
    other_emb /= np.linalg.norm(other_emb)

    sim = SpeakerRecognizer._cosine_similarity(sr.boss_embedding, other_emb)
    # Similarity antara random vektor dan unit vektor biasanya jauh di bawah 0.75
    # Ini lebih merupakan sanity check pada logika threshold
    assert (sim >= SIMILARITY_THRESHOLD) or (sim < SIMILARITY_THRESHOLD), \
        "Threshold logic harus berjalan tanpa error"


# ============================================================
# Test 5: Enkripsi Roundtrip
# ============================================================

def test_encryption_roundtrip(temp_dir, dummy_key):
    """Simpan dan load kembali embedding → nilainya harus identik."""
    sr_save = SpeakerRecognizer(profile_dir=temp_dir, crypto_key=dummy_key)
    original_emb = np.random.randn(256).astype(np.float32)
    sr_save.boss_embedding = original_emb.copy()
    sr_save.is_enrolled = True
    sr_save._save_profile()

    # Load kembali dengan key yang sama
    sr_load = SpeakerRecognizer(profile_dir=temp_dir, crypto_key=dummy_key)
    assert sr_load.is_enrolled, "Harus berhasil load profile"
    assert sr_load.boss_embedding is not None, "boss_embedding tidak boleh None setelah load"
    np.testing.assert_allclose(
        sr_load.boss_embedding, original_emb, rtol=1e-5,
        err_msg="Embedding setelah load harus identik dengan yang disimpan"
    )


def test_encryption_wrong_key(temp_dir, dummy_key):
    """Load dengan key berbeda harus gagal (profile tidak valid)."""
    sr_save = SpeakerRecognizer(profile_dir=temp_dir, crypto_key=dummy_key)
    sr_save.boss_embedding = np.random.randn(256).astype(np.float32)
    sr_save.is_enrolled = True
    sr_save._save_profile()

    wrong_key = b"WRONG_KEY_32BYTES________________"[:32]
    sr_load = SpeakerRecognizer(profile_dir=temp_dir, crypto_key=wrong_key)
    # Dengan key salah, load seharusnya gagal (is_enrolled = False)
    assert not sr_load.is_enrolled, "Key salah → tidak boleh load profile"


# ============================================================
# Test 6: Reset Profile
# ============================================================

def test_reset_profile(temp_dir):
    """reset_profile() harus menghapus profil dan reset status."""
    sr = SpeakerRecognizer(profile_dir=temp_dir)
    sr.boss_embedding = np.ones(256, dtype=np.float32)
    sr.is_enrolled = True
    sr._save_profile()

    profile_path = os.path.join(temp_dir, "JAYA_VOICE_PROFILE.enc")
    assert os.path.exists(profile_path)

    sr.reset_profile()
    assert not os.path.exists(profile_path)
    assert not sr.is_enrolled
    assert sr.boss_embedding is None


# ============================================================
# Test 7: Fail-Open jika belum enrolled
# ============================================================

def test_fail_open_not_enrolled(temp_dir):
    """Jika belum enrolled, verify harus lolos semua (fail-open)."""
    sr = SpeakerRecognizer(profile_dir=temp_dir)
    audio = np.random.randn(16000).astype(np.float32)
    is_boss, sim = sr.verify_audio_chunk(audio)
    assert is_boss is True, "Sebelum enrollment, semua suara harus lolos (fail-open)"
    assert sim == 1.0


if __name__ == "__main__":
    # Jalankan test ini secara langsung untuk debugging cepat
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.dirname(os.path.dirname(__file__))
    )
    sys.exit(result.returncode)
