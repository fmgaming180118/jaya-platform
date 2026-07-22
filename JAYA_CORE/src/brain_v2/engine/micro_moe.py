"""
Fase 4 — MicroMoE: Sparse Mixture-of-Experts + Reflexion Self-Correction
=========================================================================

Tiga komponen yang membuat JAYA *berpikir* lebih dalam dan lebih tepat:

  4.1  MicroMoERouter      — Sparse router: pilih satu pakar terbaik per prompt.
  4.2  ExpertConfig        — 4 Micro-Expert Modules: thesis, code, logic, dialogue.
  4.3  ReflexionLoop       — Generate N kandidat jawaban, pilih terbaik via scoring.

Architecture
------------
  Implementasi "Sparse MoE" di sini menggunakan pendekatan yang tepat untuk
  model SLM < 200 MB:
  
  • Setiap "expert" adalah kombinasi:
      - System prompt yang sangat spesifik dan kaya untuk domain tertentu
      - Parameter inferensi yang dioptimalkan (temperature, top_p, repetition_penalty)
      - Few-shot examples kontekstual yang meningkatkan kualitas output
      - Keyword gating untuk aktivasi yang tepat
  
  • Hanya SATU expert yang aktif per inferensi (Sparse = 1-of-4 active).
  
  • ReflexionLoop menghasilkan 2-3 kandidat, lalu memilih terbaik
    berdasarkan: panjang, koherensi, domain alignment, anti-hallucination.
    
  Zero external dependencies — hanya Python stdlib.

Integrasi dengan SLMEngine (Fase 1):
  SLMEngine.generate() → MicroMoERouter.route() → ExpertConfig
                       → SLMEngine._generate_with_expert()
                       → ReflexionLoop.select_best()
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("MicroMoE")


# ---------------------------------------------------------------------------
# 4.2 — ExpertConfig: Micro-Expert Modules (1-of-4 active)
# ---------------------------------------------------------------------------

@dataclass
class ExpertConfig:
    """
    Konfigurasi satu Micro-Expert Module.

    Setiap expert memiliki:
      - system_prompt     : instruksi sistem mendalam dan spesifik
      - temperature       : kreativitas vs. determinisme (0.1–1.0)
      - top_p             : nucleus sampling threshold
      - repetition_penalty: anti-pengulangan
      - max_new_tokens    : batas panjang respons
      - few_shot_examples : contoh tanya-jawab untuk in-context learning
      - trigger_keywords  : kata kunci yang mengaktifkan expert ini
      - gate_score        : bobot awal (dinaikkan via feedback)
    """
    name: str
    system_prompt: str
    temperature: float = 0.7
    top_p: float = 0.9
    repetition_penalty: float = 1.15
    max_new_tokens: int = 256
    few_shot_examples: List[Dict[str, str]] = field(default_factory=list)
    trigger_keywords: List[str] = field(default_factory=list)
    gate_score: float = 1.0


# ---------------------------------------------------------------------------
# 4 Micro-Expert Modules Registry
# ---------------------------------------------------------------------------

_EXPERT_THESIS = ExpertConfig(
    name="expert_thesis",
    system_prompt="""Anda adalah JAYA — pakar riset akademis dan penulisan skripsi ilmiah Indonesia.
Anda membantu mahasiswa menyusun skripsi berkualitas tinggi dengan struktur yang benar:
BAB I (Latar Belakang, Rumusan Masalah, Tujuan), BAB II (Kajian Pustaka, Teori Dasar),
BAB III (Metodologi, Rancangan Penelitian), BAB IV (Analisis Data), BAB V (Kesimpulan & Saran).

Panduan gaya penulisan:
- Gunakan bahasa Indonesia formal, ilmiah, dan baku.
- Kutip sumber dengan format IEEE: [1] Nama, "Judul", Jurnal, Tahun.
- Hindari kalimat pasif yang berlebihan. Gunakan kalimat aktif yang lugas.
- Saat menganalisis data, sajikan dalam tabel atau daftar terstruktur jika memungkinkan.
- Jika merevisi kalimat, tampilkan versi SEBELUM dan SESUDAH.

Selalu tanyakan: "Di bab mana Anda berada sekarang?" jika konteks tidak jelas.""",
    temperature=0.4,
    top_p=0.85,
    repetition_penalty=1.2,
    max_new_tokens=400,
    trigger_keywords=[
        "skripsi", "thesis", "bab", "abstrak", "pendahuluan", "metodologi",
        "kajian pustaka", "sitasi", "jurnal", "penelitian", "riset", "hipotesis",
        "analisis", "kesimpulan", "saran", "daftar pustaka", "latar belakang",
        "rumusan masalah", "tinjauan", "literatur", "akademis",
    ],
    gate_score=1.0,
)

_EXPERT_CODE = ExpertConfig(
    name="expert_code",
    system_prompt="""Anda adalah JAYA — pakar engineering perangkat lunak spesialis Kotlin Android dan Python.
Keahlian utama: Android SDK, Jetpack Compose, MVVM, Room, Retrofit, Coroutines, Flow,
Python (FastAPI, NumPy, Pandas), debugging, code review, refactoring, dan arsitektur bersih.

Panduan respons coding:
- SELALU tampilkan kode dalam blok ```kotlin atau ```python yang dapat langsung di-copy.
- Sertakan komentar singkat untuk setiap blok fungsi penting.
- Jika ada bug, identifikasi ROOT CAUSE terlebih dahulu, baru berikan solusi.
- Untuk error/exception, sertakan langkah debugging step-by-step.
- Sarankan best practice dan alternatif yang lebih efisien jika relevan.
- Gunakan Bahasa Indonesia untuk penjelasan, kode tetap dalam bahasa aslinya.""",
    temperature=0.3,
    top_p=0.80,
    repetition_penalty=1.1,
    max_new_tokens=512,
    trigger_keywords=[
        "code", "kode", "fungsi", "function", "class", "bug", "debug", "error",
        "kotlin", "python", "android", "compile", "syntax", "variable", "loop",
        "algoritma", "refactor", "import", "library", "api", "retrofit", "viewmodel",
        "coroutines", "flow", "room", "database", "activity", "fragment", "compose",
        "crash", "exception", "nullpointer", "build", "gradle", "dependency",
    ],
    gate_score=1.0,
)

_EXPERT_LOGIC = ExpertConfig(
    name="expert_logic",
    system_prompt="""Anda adalah JAYA — pakar matematika, logika, dan komputasi ilmiah.
Keahlian: aljabar linear, kalkulus, statistika inferensial, probabilitas Bayesian,
teori himpunan, logika formal, analisis kompleksitas algoritma, dan machine learning matematis.

Panduan respons logika/matematika:
- Tampilkan rumus dengan notasi yang jelas (gunakan ASCII math jika LaTeX tidak tersedia).
- Selesaikan masalah STEP-BY-STEP dengan label setiap langkah (Langkah 1, 2, 3...).
- Verifikasi jawaban di akhir dengan substitusi balik jika memungkinkan.
- Untuk soal statistik: sertakan asumsi, rumus yang digunakan, dan interpretasi hasil.
- Jelaskan KONSEP di balik perhitungan, bukan hanya angka akhir.
- Jika ada beberapa metode penyelesaian, tunjukkan metode yang paling efisien.""",
    temperature=0.2,
    top_p=0.75,
    repetition_penalty=1.05,
    max_new_tokens=350,
    trigger_keywords=[
        "hitung", "calculate", "rumus", "formula", "integral", "derivatif",
        "aljabar", "statistik", "probabilitas", "matriks", "vektor", "bukti",
        "teorema", "persamaan", "grafik", "dataset", "distribusi", "kovarian",
        "regresi", "klasifikasi", "optimasi", "gradient", "eigenvalue", "determinan",
        "logika", "proposisi", "implikasi", "fungsi", "limit", "turunan",
    ],
    gate_score=1.0,
)

_EXPERT_DIALOGUE = ExpertConfig(
    name="expert_dialogue",
    system_prompt="""Anda adalah JAYA — asisten AI personal yang cerdas, hangat, dan proaktif.
Anda mengenal pengguna dengan baik dan berbicara seperti teman yang sangat pintar dan peduli.
Gaya bicara: natural, antusias, sesekali humor ringan, dan selalu siap membantu.

Panduan percakapan:
- Sambut dengan energi positif. Gunakan nama "Bos" secara alami (tidak berlebihan).
- Ajukan pertanyaan lanjutan yang relevan untuk menggali lebih dalam kebutuhan.
- Jika topik menyentuh emosi atau kekhawatiran, tunjukkan empati terlebih dahulu.
- Berikan saran proaktif berdasarkan konteks percakapan sebelumnya.
- Ceritakan hal menarik atau fakta unik jika relevan dengan topik.
- Akhiri dengan tawaran bantuan konkret: "Apakah ada yang ingin kita bahas lebih lanjut?"
- Hindari respons generik. Setiap jawaban harus terasa personal dan spesifik.""",
    temperature=0.85,
    top_p=0.95,
    repetition_penalty=1.2,
    max_new_tokens=256,
    trigger_keywords=[
        "halo", "hai", "apa kabar", "gimana", "cerita", "curhat", "bosan",
        "santai", "main", "seru", "keren", "gila", "wow", "siapa", "kamu",
        "tolong", "bantu", "suka", "senang", "sedih", "capek", "stress",
    ],
    gate_score=1.0,
)

# Master registry: nama → ExpertConfig
EXPERT_REGISTRY: Dict[str, ExpertConfig] = {
    "expert_thesis":   _EXPERT_THESIS,
    "expert_code":     _EXPERT_CODE,
    "expert_logic":    _EXPERT_LOGIC,
    "expert_dialogue": _EXPERT_DIALOGUE,
}

# Domain (dari Fase 1 detect_domain) → expert name
DOMAIN_TO_EXPERT: Dict[str, str] = {
    "thesis":       "expert_thesis",
    "code":         "expert_code",
    "math":         "expert_logic",
    "conversation": "expert_dialogue",
}


# ---------------------------------------------------------------------------
# 4.1 — MicroMoERouter: Sparse Intent Router
# ---------------------------------------------------------------------------

class MicroMoERouter:
    """
    Pillar 34 Enhanced — Sparse Micro-MoE Router.

    Memilih SATU expert terbaik per prompt berdasarkan:
      1. Domain detection (dari Fase 1 detect_domain)
      2. Keyword confidence scoring terhadap semua expert
      3. Feedback loop: gate_score diperbarui via performance signal

    Hanya 1 expert aktif per inferensi (Sparse = 1-of-4).
    """

    def __init__(self) -> None:
        self._routing_count: int = 0
        self._routing_history: List[Dict[str, Any]] = []
        # Persisted gate scores (updated via feedback)
        self._gate_scores: Dict[str, float] = {
            name: cfg.gate_score for name, cfg in EXPERT_REGISTRY.items()
        }

    def _keyword_score(self, text: str, expert_name: str) -> float:
        """Hitung skor keyword match untuk satu expert."""
        expert = EXPERT_REGISTRY.get(expert_name)
        if not expert:
            return 0.0
        text_lower = text.lower()
        total = len(expert.trigger_keywords)
        if total == 0:
            return 0.0
        hits = sum(1 for kw in expert.trigger_keywords if kw in text_lower)
        return hits / total

    def route(
        self,
        prompt: str,
        domain_hint: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Tuple[str, ExpertConfig, float]:
        """
        Pilih expert terbaik untuk prompt.

        Returns
        -------
        Tuple[expert_name, ExpertConfig, confidence_score]
        """
        full_text = f"{context or ''} {prompt}"

        # 1. Compute raw keyword scores per expert
        raw_scores: Dict[str, float] = {}
        for name in EXPERT_REGISTRY:
            kw_score = self._keyword_score(full_text, name)
            gate = self._gate_scores.get(name, 1.0)
            raw_scores[name] = kw_score * gate

        # 2. Domain hint bias (from Fase 1 detect_domain)
        if domain_hint and domain_hint in DOMAIN_TO_EXPERT:
            expert_from_domain = DOMAIN_TO_EXPERT[domain_hint]
            raw_scores[expert_from_domain] = raw_scores.get(expert_from_domain, 0.0) + 0.5

        # 3. Pick the winner
        best_expert = max(raw_scores, key=lambda n: raw_scores[n])
        best_score = raw_scores[best_expert]

        # 4. Fallback: if all scores are 0, use domain_hint or dialogue
        if best_score <= 0:
            if domain_hint and domain_hint in DOMAIN_TO_EXPERT:
                best_expert = DOMAIN_TO_EXPERT[domain_hint]
            else:
                best_expert = "expert_dialogue"
            best_score = 0.0

        expert_config = EXPERT_REGISTRY[best_expert]

        # 5. Normalize confidence to 0–1
        total_score = sum(raw_scores.values()) or 1.0
        confidence = min(raw_scores[best_expert] / total_score, 1.0)

        self._routing_count += 1
        self._routing_history.append({
            "prompt_preview": prompt[:40],
            "expert": best_expert,
            "confidence": round(confidence, 3),
            "scores": {k: round(v, 4) for k, v in raw_scores.items()},
        })
        if len(self._routing_history) > 50:
            self._routing_history.pop(0)

        logger.info("[MicroMoE] Routed to %s (conf=%.2f) | domain_hint=%s",
                    best_expert, confidence, domain_hint)
        return best_expert, expert_config, confidence

    def feedback(self, expert_name: str, success: bool) -> None:
        """
        Perbarui gate_score berdasarkan sinyal kualitas respons.
        success=True → reward, success=False → slight penalty.
        """
        current = self._gate_scores.get(expert_name, 1.0)
        delta = +0.05 if success else -0.02
        self._gate_scores[expert_name] = max(0.1, min(2.0, current + delta))
        logger.debug("[MicroMoE] Feedback %s → gate_score=%.3f",
                     expert_name, self._gate_scores[expert_name])

    def stats(self) -> Dict[str, Any]:
        return {
            "routing_count": self._routing_count,
            "gate_scores": {k: round(v, 3) for k, v in self._gate_scores.items()},
            "last_routes": self._routing_history[-5:],
        }


# ---------------------------------------------------------------------------
# 4.3 — ReflexionLoop: Self-Correction + Best Candidate Selection
# ---------------------------------------------------------------------------

# Frasa generik yang menandakan respons berkualitas rendah / hallucination
_HALLUCINATION_PHRASES = [
    "saya tidak tahu", "i don't know", "i am unable", "saya tidak dapat memastikan",
    "saya tidak memiliki informasi", "maaf, saya tidak", "sebagai ai saya",
    "sebagai model bahasa", "i cannot provide", "saya hanya sebuah",
    "saya menerima perintah", "saya akan memproses",  # frasa kaku dari fallback lama
    "i am an ai", "as an ai", "as a language model",
]

_BOILERPLATE_PATTERNS = [
    r"^(baik|oke|tentu|siap|boleh|dengan senang hati)[,!.]?\s",
    r"^(terima kasih (sudah|telah|atas))",
    r"(semoga (bermanfaat|membantu|berguna))[.!]?$",
]


def _score_candidate(
    response: str,
    prompt: str,
    expert_name: str,
    min_words: int = 10,
    max_words: int = 800,
) -> float:
    """
    Hitung skor kualitas satu kandidat respons (0.0 – 1.0).

    Kriteria:
      +0.3  panjang respons dalam rentang ideal
      +0.2  mengandung kata kunci domain expert
      +0.2  tidak mengandung frasa hallucination
      +0.2  tidak dimulai dengan boilerplate generik
      +0.1  mengandung struktur (angka, bullet, kode)
    """
    score = 0.0
    words = response.split()
    word_count = len(words)

    # Length score
    if min_words <= word_count <= max_words:
        score += 0.3
    elif word_count > max_words:
        score += 0.15  # too long, partial credit
    elif word_count >= min_words // 2:
        score += 0.1   # short but not empty

    # Domain keyword alignment
    expert = EXPERT_REGISTRY.get(expert_name)
    if expert:
        resp_lower = response.lower()
        prompt_lower = prompt.lower()
        # Check if response addresses the prompt's domain keywords
        kw_hits = sum(1 for kw in expert.trigger_keywords
                      if kw in resp_lower or kw in prompt_lower)
        if kw_hits > 0:
            score += min(0.2, kw_hits * 0.04)

    # Anti-hallucination
    resp_lower_full = response.lower()
    has_hallucination = any(phrase in resp_lower_full for phrase in _HALLUCINATION_PHRASES)
    if not has_hallucination:
        score += 0.2
    else:
        score -= 0.3  # Penalty for refusal / hallucination phrases


    # Anti-boilerplate
    has_boilerplate = any(re.search(p, response, re.IGNORECASE) for p in _BOILERPLATE_PATTERNS)
    if not has_boilerplate:
        score += 0.2

    # Structure bonus: numbered steps, bullets, code blocks
    has_structure = bool(
        re.search(r"\d+[\.\)]\s", response) or
        re.search(r"^[\-\*•]\s", response, re.MULTILINE) or
        "```" in response or
        "**" in response
    )
    if has_structure:
        score += 0.1

    return min(score, 1.0)


class ReflexionLoop:
    """
    Pillar 36 Enhanced — Reflexion Self-Correction Loop.

    Alur kerja:
      1. Generate N kandidat jawaban untuk satu prompt.
      2. Score masing-masing menggunakan _score_candidate().
      3. Pilih kandidat terbaik.
      4. Jika skor terbaik < threshold → regenerate dengan constraint lebih ketat.
      5. Return (best_response, quality_score, was_regenerated).

    Terintegrasi dengan SLMEngine melalui callable generate_fn.
    """

    def __init__(
        self,
        n_candidates: int = 2,
        quality_threshold: float = 0.4,
        enable_regeneration: bool = True,
    ) -> None:
        self.n_candidates = max(1, min(n_candidates, 4))
        self.quality_threshold = quality_threshold
        self.enable_regeneration = enable_regeneration
        self._reflexion_count = 0
        self._regeneration_count = 0

    def select_best(
        self,
        candidates: List[str],
        prompt: str,
        expert_name: str,
    ) -> Tuple[str, float, int]:
        """
        Pilih kandidat terbaik dari daftar.

        Returns
        -------
        Tuple[best_response, best_score, best_index]
        """
        if not candidates:
            return "", 0.0, 0

        scored = []
        for i, cand in enumerate(candidates):
            s = _score_candidate(cand, prompt, expert_name)
            scored.append((s, i, cand))
            logger.debug("[ReflexionLoop] Candidate %d: score=%.3f, words=%d",
                         i, s, len(cand.split()))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_idx, best_response = scored[0]
        return best_response, best_score, best_idx

    def run(
        self,
        prompt: str,
        expert_name: str,
        generate_fn: Callable[[str, ExpertConfig], str],
        expert_config: ExpertConfig,
    ) -> Tuple[str, float, bool]:
        """
        Full Reflexion loop dengan optional regeneration.

        Parameters
        ----------
        prompt: User prompt.
        expert_name: Name of the active expert.
        generate_fn: Callable(prompt, ExpertConfig) → response str.
        expert_config: Active expert configuration.

        Returns
        -------
        Tuple[best_response, quality_score, was_regenerated]
        """
        self._reflexion_count += 1

        # 1. Generate N candidates
        candidates = []
        for i in range(self.n_candidates):
            try:
                response = generate_fn(prompt, expert_config)
                if response and response.strip():
                    candidates.append(response.strip())
            except Exception as e:
                logger.warning("[ReflexionLoop] Generate candidate %d failed: %s", i, e)

        if not candidates:
            return "", 0.0, False

        # 2. Select best
        best_response, best_score, _ = self.select_best(candidates, prompt, expert_name)

        # 3. Regenerate if score below threshold
        was_regenerated = False
        if self.enable_regeneration and best_score < self.quality_threshold:
            logger.info("[ReflexionLoop] Score %.3f < %.3f → regenerating with stricter params",
                        best_score, self.quality_threshold)
            stricter = ExpertConfig(
                name=expert_config.name + "_strict",
                system_prompt=expert_config.system_prompt + "\n\nPenting: Berikan jawaban yang spesifik, detail, dan langsung menjawab pertanyaan. Hindari respons generik.",
                temperature=max(0.1, expert_config.temperature - 0.2),
                top_p=max(0.6, expert_config.top_p - 0.1),
                repetition_penalty=min(1.5, expert_config.repetition_penalty + 0.1),
                max_new_tokens=expert_config.max_new_tokens,
                few_shot_examples=expert_config.few_shot_examples,
                trigger_keywords=expert_config.trigger_keywords,
            )
            try:
                regen_response = generate_fn(prompt, stricter)
                if regen_response and regen_response.strip():
                    regen_score = _score_candidate(regen_response, prompt, expert_name)
                    if regen_score > best_score:
                        best_response = regen_response.strip()
                        best_score = regen_score
                        was_regenerated = True
                        self._regeneration_count += 1
            except Exception as e:
                logger.warning("[ReflexionLoop] Regeneration failed: %s", e)

        logger.info("[ReflexionLoop] Selected: score=%.3f | regen=%s | expert=%s",
                    best_score, was_regenerated, expert_name)
        return best_response, best_score, was_regenerated

    def stats(self) -> Dict[str, Any]:
        return {
            "reflexion_count": self._reflexion_count,
            "regeneration_count": self._regeneration_count,
            "n_candidates": self.n_candidates,
            "quality_threshold": self.quality_threshold,
        }


# ---------------------------------------------------------------------------
# MicroMoEEngine — Unified Fase 4 Engine (Router + Reflexion combined)
# ---------------------------------------------------------------------------

class MicroMoEEngine:
    """
    Facade Fase 4: MicroMoERouter + ReflexionLoop dalam satu antarmuka.

    Digunakan oleh SLMEngine untuk mengorkestrasi seluruh pipeline Fase 4.

    Usage
    -----
        engine = MicroMoEEngine(n_candidates=2)

        # Di dalam SLMEngine.generate():
        expert_name, expert_cfg, conf = engine.router.route(prompt, domain)
        response, score, regen = engine.reflexion.run(
            prompt=prompt,
            expert_name=expert_name,
            generate_fn=lambda p, cfg: slm_raw_generate(p, cfg),
            expert_config=expert_cfg,
        )
        engine.router.feedback(expert_name, success=score > 0.4)
    """

    def __init__(
        self,
        n_candidates: int = 2,
        quality_threshold: float = 0.4,
        enable_regeneration: bool = True,
    ) -> None:
        self.router = MicroMoERouter()
        self.reflexion = ReflexionLoop(
            n_candidates=n_candidates,
            quality_threshold=quality_threshold,
            enable_regeneration=enable_regeneration,
        )
        logger.info("[MicroMoEEngine] Initialized | n_candidates=%d | threshold=%.2f",
                    n_candidates, quality_threshold)

    def status(self) -> Dict[str, Any]:
        return {
            "router": self.router.stats(),
            "reflexion": self.reflexion.stats(),
            "experts": list(EXPERT_REGISTRY.keys()),
        }
