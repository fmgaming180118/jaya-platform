"""
Pillar 21 — Lingua Logica: Indonesian-First Response Generator

Mengubah LogicExpr hasil encode() menjadi kalimat Bahasa Indonesia yang natural.
Ini adalah lapisan "suara" JAYA yang berbicara kepada Bos.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("IndonesianResponder")

# Type alias — harus sama dengan LogicExpr di lingua_logica
LogicExpr = Union[str, int, float, Tuple[Any, ...]]


# ---------------------------------------------------------------------------
# Template respons Bahasa Indonesia per jenis aksi & query
# ---------------------------------------------------------------------------

_ACTION_TEMPLATES: Dict[str, str] = {
    "TURN_OFF":    "Baik, Bos. Saya akan mematikan {obj}.",
    "TURN_ON":     "Siap, Bos. Saya akan menyalakan {obj}.",
    "STOP":        "Baik, saya menghentikan {obj} sekarang.",
    "START":       "Saya memulai {obj} untuk Anda, Bos.",
    "SEARCH":      "Baik, saya akan mencari {obj}.",
    "DELETE":      "Menghapus {obj}. Mohon konfirmasi jika ini bukan yang Anda maksud.",
    "OPEN":        "Membuka {obj} sekarang, Bos.",
    "CLOSE":       "Menutup {obj}.",
    "GREET":       "Halo, Bos! Ada yang bisa saya bantu hari ini?",
    "SLEEP":       "Baik, saya masuk ke mode istirahat. Hubungi saya kapanpun.",
    "HELP":        "Tentu, saya siap membantu. Apa yang ingin Anda ketahui?",
    "SAVE":        "Menyimpan {obj}.",
    "LOAD":        "Memuat {obj} ke dalam memori.",
    "SEND":        "Mengirim {obj}.",
    "CREATE":      "Membuat {obj} sekarang, Bos.",
    "EDIT":        "Mengubah {obj} sesuai instruksi Anda.",
    "SHOW":        "Menampilkan {obj}.",
    "HIDE":        "Menyembunyikan {obj}.",
    "COPY":        "Menyalin {obj}.",
    "MOVE":        "Memindahkan {obj} ke lokasi baru.",
    "RESET":       "Mengatur ulang {obj} ke kondisi awal.",
    "CALCULATE":   "Menghitung {obj} untuk Anda.",
    "REMEMBER":    "Baik, saya akan mengingat: {obj}.",
    "FORGET":      "Saya menghapus {obj} dari memori.",
    "TRANSLATE":   "Menerjemahkan {obj}.",
    "ANALYZE":     "Menganalisis {obj}. Mohon tunggu sebentar.",
    "DOWNLOAD":    "Mengunduh {obj}.",
    "LIST":        "Berikut adalah daftar {obj}:",
    "SORT":        "Mengurutkan {obj}.",
    "FILTER":      "Menyaring {obj} berdasarkan kriteria Anda.",
    "EXPLAIN":     "Baik, saya akan menjelaskan mengenai {obj}.",
    "CONNECT":     "Menghubungkan ke {obj}.",
    "DISCONNECT":  "Memutus koneksi dari {obj}.",
    "UPDATE":      "Memperbarui {obj}.",
    "VERIFY":      "Memverifikasi {obj}.",
}

_QUERY_TEMPLATES: Dict[str, str] = {
    "QUERY_DEF":          "Baik Bos, saya akan mencari penjelasan mengenai '{subj}' dari memori lokal saya.",
    "QUERY_HOW":          "Untuk cara melakukan '{subj}', saya akan membantu Anda langkah demi langkah.",
    "QUERY_WHY":          "Pertanyaan bagus, Bos. Saya akan mencari alasan mengapa '{subj}'.",
    "QUERY_WHEN":         "Mencari informasi waktu mengenai '{subj}' dari memori lokal.",
    "QUERY_WHERE":        "Mencari lokasi atau tempat yang berkaitan dengan '{subj}'.",
    "QUERY_WHO":          "Mencari informasi tentang siapa '{subj}'.",
    "QUERY_WHICH":        "Untuk menentukan pilihan terbaik mengenai '{subj}', izinkan saya menganalisisnya.",
    "QUERY_DIFF":         "Saya akan membandingkan dan menjelaskan perbedaan pada '{subj}'.",
    "QUERY_EXAMPLE":      "Berikut adalah contoh yang berkaitan dengan '{subj}':",
    "QUERY_AMOUNT":       "Untuk mengetahui jumlah atau ukuran '{subj}', saya akan mencarinya.",
    "QUERY_CONFIRM":      "Izinkan saya memverifikasi pertanyaan Anda mengenai '{subj}'.",
    "QUERY_HYPOTHETICAL": "Skenario '{subj}' sangat menarik, Bos. Mari kita analisis bersama.",
    "QUERY_SUGGEST":      "Berdasarkan memori saya, berikut rekomendasi saya untuk '{subj}':",
}

_ARITH_TEMPLATE = "Hasil perhitungan {a} {op} {b} = {result}."

_ARITH_OP_NAMES: Dict[str, str] = {
    "ADD": "+",
    "SUB": "-",
    "MUL": "×",
    "DIV": "÷",
}

_LITERAL_TEMPLATE = (
    "Saya menerima perintah Anda: \"{text}\". "
    "Saya akan memproses ini sesuai kemampuan terbaik saya."
)

_UNKNOWN_TEMPLATE = (
    "Maaf, Bos. Saya belum memahami perintah tersebut sepenuhnya. "
    "Bisa Anda jelaskan lebih lanjut apa yang ingin Anda lakukan?"
)

_FACTFUL_QUERY_TYPES = {"QUERY_DEF", "QUERY_WHY", "QUERY_DIFF", "QUERY_EXAMPLE", "QUERY_SUGGEST"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_response(expr: LogicExpr, fallback_text: str = "") -> str:
    """
    Mengubah LogicExpr menjadi kalimat Bahasa Indonesia yang natural.

    Args:
        expr: Hasil dari LinguaLogica.encode()
        fallback_text: Teks asli dari user (digunakan untuk LITERAL fallback)

    Returns:
        Kalimat natural dalam Bahasa Indonesia.
    """
    if not isinstance(expr, tuple) or not expr:
        return _UNKNOWN_TEMPLATE

    head = expr[0]

    # ── LITERAL ───────────────────────────────────────────────────────
    if head == "LITERAL":
        text = str(expr[1]) if len(expr) > 1 else fallback_text
        if not text.strip():
            return _UNKNOWN_TEMPLATE
        return _LITERAL_TEMPLATE.format(text=text)

    # ── ACTION ────────────────────────────────────────────────────────
    if head == "ACTION":
        action = str(expr[1]) if len(expr) > 1 else ""
        obj = str(expr[2]) if len(expr) > 2 else ""
        obj = _clean_object(obj)

        template = _ACTION_TEMPLATES.get(action)
        if template:
            return template.format(obj=obj or "itu")
        return f"Baik, saya akan {action.lower().replace('_', ' ')} {obj}.".strip()

    # ── QUERY ─────────────────────────────────────────────────────────
    if head == "QUERY":
        qtype = str(expr[1]) if len(expr) > 1 else ""
        subject = expr[2] if len(expr) > 2 else ""

        # Arithmetic
        if qtype == "ARITH" and isinstance(subject, tuple):
            return _handle_arith(subject)

        subj_str = _clean_object(str(subject) if not isinstance(subject, str) else subject)
        template = _QUERY_TEMPLATES.get(qtype)
        if template:
            return template.format(subj=subj_str or "topik tersebut")
        return f"Saya akan mencari informasi tentang '{subj_str}' untuk Anda."

    return _UNKNOWN_TEMPLATE


def _handle_arith(op_expr: Tuple[Any, ...]) -> str:
    """Evaluasi ekspresi aritmatika dan kembalikan kalimat Indonesia."""
    try:
        op_sym = str(op_expr[0])
        a = float(op_expr[1])
        b = float(op_expr[2])
        ops = {"ADD": a + b, "SUB": a - b, "MUL": a * b, "DIV": a / b if b != 0 else float("inf")}
        result = ops.get(op_sym)

        a_fmt = int(a) if a == int(a) else a
        b_fmt = int(b) if b == int(b) else b

        if result is not None:
            result_fmt = int(result) if isinstance(result, float) and result == int(result) else result
            op_display = _ARITH_OP_NAMES.get(op_sym, op_sym)
            return _ARITH_TEMPLATE.format(a=a_fmt, op=op_display, b=b_fmt, result=result_fmt)
    except Exception:
        pass
    return "Saya tidak dapat menghitung ekspresi tersebut."


def _clean_object(text: str) -> str:
    """Bersihkan teks objek dari noise regex."""
    text = re.sub(r"\s+", " ", text).strip()
    # Buang leading/trailing common conjunctions
    text = re.sub(r"^(the|a|an|untuk|ke|dari|di|pada|dengan)\s+", "", text, flags=re.I)
    return text[:120]  # batasi panjang


# ---------------------------------------------------------------------------
# IndonesianResponder class — untuk diintegrasikan ke IronEngine
# ---------------------------------------------------------------------------

class IndonesianResponder:
    """
    Lapisan natural-language output JAYA dalam Bahasa Indonesia.

    Terintegrasi dengan LinguaLogica (encode) dan LanguagePolicy.
    Digunakan oleh IronEngine.chat() untuk menghasilkan respons user-facing.
    """

    def __init__(self):
        self._response_count = 0
        try:
            from jaya_core.brain_v2.soul.language_policy import get_policy
            self._policy = get_policy("id")
        except ImportError:
            self._policy = {}
        logger.info("[Pillar 21] IndonesianResponder ready")

    def respond(
        self,
        expr: LogicExpr,
        raw_text: str = "",
        rag_facts: Optional[List[Dict[str, Any]]] = None,
        agentic_hint: Optional[Dict[str, Any]] = None,
        control_policy: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Hasilkan respons Bahasa Indonesia lengkap dari LogicExpr + konteks RAG.

        Args:
            expr: LogicExpr dari LinguaLogica.encode()
            raw_text: Teks asli dari user
            rag_facts: Fakta dari AgenticRAG (opsional)
            agentic_hint: Prosedur hint dari AgenticRAG (opsional)
            control_policy: State kontrol Pillar 10; tidak boleh mengubah fakta
        """
        self._response_count += 1

        # 1. Base response dari LogicExpr atau RAG facts
        if rag_facts and isinstance(expr, tuple) and expr[0] == "QUERY":
            factual_answer = self._compose_factual_answer(expr, rag_facts)
            base = factual_answer or generate_response(expr, fallback_text=raw_text)
        else:
            base = generate_response(expr, fallback_text=raw_text)

        parts = [base]

        safe_control = control_policy if isinstance(control_policy, dict) else {}
        if bool(safe_control.get("confirmation_recommended")):
            parts.insert(
                0,
                "Kontrol kehati-hatian aktif; konfirmasi disarankan sebelum tindakan.",
            )
        if bool(safe_control.get("escalation_recommended")):
            parts.insert(
                0,
                "Kontrol eskalasi aktif; keputusan perlu diteruskan ke pihak berwenang.",
            )

        # 2. Tambahkan langkah prosedur jika ada
        if agentic_hint and isinstance(agentic_hint, dict):
            steps = agentic_hint.get("steps", [])
            if steps:
                policy = self._policy
                intro = policy.get("procedure_intro", "Berikut langkah-langkahnya:")
                parts.append(intro)
                for i, step in enumerate(steps[:5], 1):
                    step_tmpl = policy.get("procedure_step", "Langkah {index}: {step}")
                    parts.append(step_tmpl.format(index=i, step=step))

        # 3. Tambahkan fakta relevan jika query dan ada data
        if rag_facts and isinstance(expr, tuple) and expr[0] == "QUERY":
            primary_fact = str(rag_facts[0].get("content", "")).strip() if rag_facts else ""
            for fact in rag_facts[:2]:
                content = str(fact.get("content", "")).strip()
                if not content or content == primary_fact:
                    continue
                fact_line = f"Fakta terkait: {content[:200]}"
                if fact_line not in parts:
                    parts.append(fact_line)

        # 4. Penutup
        closing = self._policy.get("closing", "Silakan lanjutkan jika ada pertanyaan lain, Bos.")
        if len(parts) > 1 and safe_control.get("interaction_mode") != "concise":
            parts.append(closing)

        return "\n".join(p for p in parts if p.strip())

    def _compose_factual_answer(
        self,
        expr: LogicExpr,
        rag_facts: List[Dict[str, Any]],
    ) -> str:
        if not isinstance(expr, tuple) or len(expr) < 3:
            return ""

        qtype = str(expr[1] or "")
        if qtype not in _FACTFUL_QUERY_TYPES:
            return ""

        subject_raw = expr[2]
        subject = _clean_object(str(subject_raw) if not isinstance(subject_raw, str) else subject_raw)
        subject = re.sub(r"^(apa itu|apakah|jelaskan|tolong jelaskan)\s+", "", subject, flags=re.I).strip()

        snippets: List[str] = []
        seen: set[str] = set()
        for fact in rag_facts[:2]:
            content = str(fact.get("content", "")).strip()
            if not content:
                continue
            normalized = content.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            snippets.append(content)

        if not snippets:
            return ""

        first = snippets[0]
        if qtype == "QUERY_DEF" and subject:
            lowered_subject = subject.lower()
            lowered_first = first.lower()
            if lowered_first.startswith(lowered_subject + " adalah"):
                opening = first
            else:
                opening = f"{subject.capitalize()} adalah {first[0].lower() + first[1:] if first else first}"
        else:
            opening = first

        if len(snippets) == 1:
            return opening

        return f"{opening} {' '.join(snippets[1:])}".strip()

    def greet(self) -> str:
        return self._policy.get(
            "greeting",
            "Halo Bos, saya JAYA. Siap membantu Anda.",
        )

    def clarify(self) -> str:
        return self._policy.get(
            "clarify",
            "Maaf, saya belum memahami perintah Anda. Bisa diulang dengan lebih jelas?",
        )

    def status(self) -> Dict[str, Any]:
        return {"responses_generated": self._response_count}
