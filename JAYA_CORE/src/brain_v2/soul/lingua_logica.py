"""Pillar 21 — Lingua Logica.

JAYA's internal symbolic dialect: a minimal S-expression language that
bridges natural language (from the user) and ternary tensor operations
(in the model).

Design
------
* Representations use nested tuples / strings — no third-party parser.
* ``encode(text)`` → ``LogicExpr`` — rule-based NL→logic conversion.
* ``decode(expr)`` → ``str`` — logic→NL for user-facing output.
* ``evaluate(expr)`` → evaluates the expression symbolically (stub for
  complex sub-expressions, full evaluation for simple predicates).

Example
-------
    encode("turn off the lights")  →  ("ACTION", "TURN_OFF", "lights")
    encode("what is 2 + 3?")       →  ("QUERY", "ARITH", ("+", 2, 3))
    decode(("ACTION", "GREET", "user"))  →  "greet user"
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("LinguaLogica")

# Type alias for S-expression trees
LogicExpr = Union[str, int, float, Tuple[Any, ...]]


# ---------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------

_ACTION_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    # ── English ──────────────────────────────────────────────────────────
    (re.compile(r"\b(turn|switch)\s+off\b",             re.I), "TURN_OFF"),
    (re.compile(r"\b(turn|switch)\s+on\b",              re.I), "TURN_ON"),
    (re.compile(r"\b(stop|halt|pause|berhenti)\b",      re.I), "STOP"),
    (re.compile(r"\b(start|begin|run|launch|execute)\b",re.I), "START"),
    (re.compile(r"\b(search|find|look|lookup|query)\b", re.I), "SEARCH"),
    (re.compile(r"\b(delete|remove|erase|clear)\b",     re.I), "DELETE"),
    (re.compile(r"\b(open|launch|load)\b",              re.I), "OPEN"),
    (re.compile(r"\b(close|quit|exit|shutdown)\b",      re.I), "CLOSE"),
    (re.compile(r"\b(greet|hello|hi|hey)\b",            re.I), "GREET"),
    (re.compile(r"\b(sleep|rest|idle|standby)\b",       re.I), "SLEEP"),
    (re.compile(r"\b(help|assist|support)\b",           re.I), "HELP"),
    (re.compile(r"\b(save|store|write|export)\b",       re.I), "SAVE"),
    (re.compile(r"\b(load|import|read|fetch)\b",        re.I), "LOAD"),
    (re.compile(r"\b(send|post|submit|upload)\b",       re.I), "SEND"),
    (re.compile(r"\b(create|make|build|generate)\b",    re.I), "CREATE"),
    (re.compile(r"\b(edit|update|change|modify)\b",     re.I), "EDIT"),
    (re.compile(r"\b(show|display|view|print)\b",       re.I), "SHOW"),
    (re.compile(r"\b(hide|minimize|collapse)\b",        re.I), "HIDE"),
    (re.compile(r"\b(copy|duplicate|clone)\b",          re.I), "COPY"),
    (re.compile(r"\b(move|transfer|shift)\b",           re.I), "MOVE"),
    (re.compile(r"\b(reset|restart|reboot|reload)\b",   re.I), "RESET"),
    (re.compile(r"\b(calculate|compute|evaluate)\b",    re.I), "CALCULATE"),
    (re.compile(r"\b(remember|memorize|record)\b",      re.I), "REMEMBER"),
    (re.compile(r"\b(forget|discard|drop)\b",           re.I), "FORGET"),
    (re.compile(r"\b(translate|convert)\b",             re.I), "TRANSLATE"),
    (re.compile(r"\b(analyze|analyse|examine)\b",       re.I), "ANALYZE"),
    (re.compile(r"\b(download|get|pull)\b",             re.I), "DOWNLOAD"),
    (re.compile(r"\b(list|enumerate|show all)\b",       re.I), "LIST"),
    (re.compile(r"\b(sort|order|arrange|rank)\b",       re.I), "SORT"),
    (re.compile(r"\b(filter|select|pick)\b",            re.I), "FILTER"),
    # ── Bahasa Indonesia: kata kerja utama ───────────────────────────────
    (re.compile(r"\b(matikan|padamkan)\b",              re.I), "TURN_OFF"),
    (re.compile(r"\b(nyalakan|hidupkan|aktifkan)\b",    re.I), "TURN_ON"),
    (re.compile(r"\b(hentikan|berhenti|jeda|pause)\b",  re.I), "STOP"),
    (re.compile(r"\b(mulai(kan)?|jalankan|eksekusi)\b", re.I), "START"),
    (re.compile(r"\b(cari(kan)?|temukan|cek)\b",        re.I), "SEARCH"),
    (re.compile(r"\b(hapus(kan)?|buang|singkir)\b",     re.I), "DELETE"),
    (re.compile(r"\b(buka(kan)?|tampilkan|lihat)\b",    re.I), "OPEN"),
    (re.compile(r"\b(tutup|keluar|berhenti)\b",         re.I), "CLOSE"),
    (re.compile(r"\b(halo|hai|salam|selamat)\b",        re.I), "GREET"),
    (re.compile(r"\b(tidur|istirahat|berdiam)\b",       re.I), "SLEEP"),
    (re.compile(r"\b(tolong|bantu(kan)?|bantuan)\b",    re.I), "HELP"),
    (re.compile(r"\b(simpan|rekam|tulis|ekspor)\b",     re.I), "SAVE"),
    (re.compile(r"\b(muat|impor|ambil|baca)\b",         re.I), "LOAD"),
    (re.compile(r"\b(kirim(kan)?|posting|unggah)\b",    re.I), "SEND"),
    (re.compile(r"\b(buat(kan)?|bikin|ciptakan)\b",     re.I), "CREATE"),
    (re.compile(r"\b(ubah|edit|ganti)\b",               re.I), "EDIT"),
    (re.compile(r"\b(tampilkan|tunjukkan|cetak)\b",     re.I), "SHOW"),
    (re.compile(r"\b(sembunyikan|kecilkan)\b",          re.I), "HIDE"),
    (re.compile(r"\b(salin|duplikat|kopi)\b",           re.I), "COPY"),
    (re.compile(r"\b(pindah(kan)?|geser|transfer)\b",   re.I), "MOVE"),
    (re.compile(r"\b(ulang|restart|reset|muat ulang)\b",re.I), "RESET"),
    (re.compile(r"\b(hitung(kan)?|kalkulasi|komputasi)\b", re.I), "CALCULATE"),
    (re.compile(r"\b(ingat|ingat(kan)?|catat)\b",       re.I), "REMEMBER"),
    (re.compile(r"\b(lupa(kan)?|buang ingatan)\b",      re.I), "FORGET"),
    (re.compile(r"\b(terjemahkan|konversi(kan)?)\b",    re.I), "TRANSLATE"),
    (re.compile(r"\b(analisis|analisa|periksa)\b",      re.I), "ANALYZE"),
    (re.compile(r"\b(unduh|download|ambilkan)\b",       re.I), "DOWNLOAD"),
    (re.compile(r"\b(daftar(kan)?|sebutkan|list)\b",    re.I), "LIST"),
    (re.compile(r"\b(urutkan|sortir|susun)\b",          re.I), "SORT"),
    (re.compile(r"\b(saring|filter|pilih(kan)?)\b",     re.I), "FILTER"),
    (re.compile(r"\b(ceritakan|jelaskan|terangkan)\b",  re.I), "EXPLAIN"),
    (re.compile(r"\b(hubungkan|sambungkan|koneksikan)\b",re.I), "CONNECT"),
    (re.compile(r"\b(putuskan|diskoneksikan)\b",        re.I), "DISCONNECT"),
    (re.compile(r"\b(perbarui|update|perbaiki)\b",      re.I), "UPDATE"),
    (re.compile(r"\b(verifikasi|cek ulang|konfirmasi)\b",re.I), "VERIFY"),
    # ── Bahasa Indonesia: informal/slang ─────────────────────────────────
    (re.compile(r"\b(yuk|ayo|mari)\b",                  re.I), "START"),
    (re.compile(r"\b(dong|donk)\b",                     re.I), "HELP"),
    (re.compile(r"\b(mau|pengen|ingin)\s+(\w+)",        re.I), "START"),
    (re.compile(r"\b(gak bisa|nggak bisa|tidak bisa)\b",re.I), "HELP"),
    (re.compile(r"\b(kasih tahu|kasih tau|beritahu)\b", re.I), "EXPLAIN"),
    (re.compile(r"\b(boleh|bisa|izin)\b",               re.I), "HELP"),
]

_QUERY_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    # ── English ──────────────────────────────────────────────────────────
    (re.compile(r"\b(what\s+is|what's|define)\b",       re.I), "QUERY_DEF"),
    (re.compile(r"\b(how\s+(do|to|can|does|did))\b",    re.I), "QUERY_HOW"),
    (re.compile(r"\b(why|reason\s+for|cause\s+of)\b",   re.I), "QUERY_WHY"),
    (re.compile(r"\b(when|what\s+time|at\s+what\s+time)\b", re.I), "QUERY_WHEN"),
    (re.compile(r"\b(where|location\s+of|place\s+of)\b",re.I), "QUERY_WHERE"),
    (re.compile(r"\b(who|whose|whom)\b",                 re.I), "QUERY_WHO"),
    (re.compile(r"\b(which|what\s+kind|what\s+type)\b",  re.I), "QUERY_WHICH"),
    (re.compile(r"\b(can\s+you|could\s+you|please)\b",   re.I), "QUERY_HOW"),
    (re.compile(r"\b(explain|describe|tell\s+me\s+about)\b", re.I), "QUERY_DEF"),
    (re.compile(r"\b(difference|compare|versus|vs)\b",   re.I), "QUERY_DIFF"),
    (re.compile(r"\b(example|sample|instance|show\s+me)\b", re.I), "QUERY_EXAMPLE"),
    # ── Bahasa Indonesia: pertanyaan ─────────────────────────────────────
    (re.compile(r"\b(apa\s+itu|apa\s+yang\s+dimaksud|definisi)\b", re.I), "QUERY_DEF"),
    (re.compile(r"\b(bagaimana|gimana|caranya|cara)\b",  re.I), "QUERY_HOW"),
    (re.compile(r"\b(kenapa|mengapa|sebab|alasan)\b",    re.I), "QUERY_WHY"),
    (re.compile(r"\b(kapan|tanggal|waktu)\b",             re.I), "QUERY_WHEN"),
    (re.compile(r"\b(dimana|di\s+mana|lokasinya)\b",     re.I), "QUERY_WHERE"),
    (re.compile(r"\b(siapa|orang|tokoh)\b",               re.I), "QUERY_WHO"),
    (re.compile(r"\b(yang\s+mana|jenis\s+apa|tipe\s+apa)\b", re.I), "QUERY_WHICH"),
    (re.compile(r"\b(maksudnya|artinya|arti)\b",          re.I), "QUERY_DEF"),
    (re.compile(r"\b(bedanya|perbedaan|banding)\b",       re.I), "QUERY_DIFF"),
    (re.compile(r"\b(contoh(nya)?|misalnya|contoh\s+kasus)\b", re.I), "QUERY_EXAMPLE"),
    (re.compile(r"\b(berapa|jumlahnya|beratnya|ukuran)\b", re.I), "QUERY_AMOUNT"),
    (re.compile(r"\b(apakah|apa\s+benar|benarkah|betul)\b", re.I), "QUERY_CONFIRM"),
    (re.compile(r"\b(gimana\s+kalau|bagaimana\s+jika|what\s+if)\b", re.I), "QUERY_HYPOTHETICAL"),
    (re.compile(r"\b(rekomendasi|saran|suggest|recommend)\b", re.I), "QUERY_SUGGEST"),
]

_ARITH_RE = re.compile(
    r"(\d+\.?\d*)\s*([+\-*/])\s*(\d+\.?\d*)"
)


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

def encode(text: str) -> LogicExpr:
    """Convert natural language *text* to a LogicExpr S-expression."""
    text = text.strip()

    # Arithmetic expression?
    m = _ARITH_RE.search(text)
    if m:
        op_map = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
        a = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
        b = float(m.group(3)) if "." in m.group(3) else int(m.group(3))
        op = op_map.get(m.group(2), m.group(2))
        return ("QUERY", "ARITH", (op, a, b))

    # Query?
    for pattern, qtype in _QUERY_KEYWORDS:
        if pattern.search(text):
            subject = _extract_subject(text)
            return ("QUERY", qtype, subject)

    # Action?
    for pattern, action in _ACTION_KEYWORDS:
        if pattern.search(text):
            obj = _extract_object(text, pattern)
            return ("ACTION", action, obj)

    # Fallback — treat as opaque literal
    logger.debug("[LinguaLogica] no rule matched for: %r — using LITERAL", text[:60])
    return ("LITERAL", text)


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------

def decode(expr: LogicExpr) -> str:
    """Convert a LogicExpr back to a natural-language string."""
    if isinstance(expr, str):
        return expr
    if not isinstance(expr, tuple) or not expr:
        return str(expr)

    head = expr[0]
    if head == "LITERAL":
        return str(expr[1]) if len(expr) > 1 else ""

    if head == "ACTION":
        _, verb, obj = expr[0], expr[1], (expr[2] if len(expr) > 2 else "")
        return f"{verb.lower().replace('_', ' ')} {obj}".strip()

    if head == "QUERY":
        _, qtype, subject = expr[0], expr[1], (expr[2] if len(expr) > 2 else "")
        if qtype == "ARITH" and isinstance(subject, tuple):
            op: str = str(subject[0])  # type: ignore[arg-type]
            a: Any = subject[1] if len(subject) > 1 else 0  # type: ignore[arg-type]
            b: Any = subject[2] if len(subject) > 2 else 0  # type: ignore[arg-type]
            return f"compute {a} {op} {b}"
        return f"query about {subject}"

    # Generic tuple → parenthesised S-expression string
    return "(" + " ".join(decode(sub) for sub in expr) + ")"


# ---------------------------------------------------------------------------
# Evaluator (numeric only; symbolic evaluation is a stub)
# ---------------------------------------------------------------------------

def evaluate(expr: LogicExpr) -> Optional[Any]:
    """Numerically evaluate a LogicExpr if possible; otherwise None."""
    if not isinstance(expr, tuple):
        return None
    if len(expr) == 3 and expr[0] == "QUERY" and expr[1] == "ARITH":
        op_expr = expr[2]
        if isinstance(op_expr, tuple) and len(op_expr) == 3:  # type: ignore[arg-type]
            op_sym: str = str(op_expr[0])  # type: ignore[arg-type]
            a_val: Any = op_expr[1]  # type: ignore[index]
            b_val: Any = op_expr[2]  # type: ignore[index]
            try:
                ops: Dict[str, Any] = {
                    "ADD": lambda x, y: x + y,  # type: ignore[operator]
                    "SUB": lambda x, y: x - y,  # type: ignore[operator]
                    "MUL": lambda x, y: x * y,  # type: ignore[operator]
                    "DIV": lambda x, y: x / y if y != 0 else float("inf"),  # type: ignore[operator]
                }
                if op_sym in ops:
                    return ops[op_sym](a_val, b_val)  # type: ignore[no-any-return]
            except (TypeError, ZeroDivisionError):
                pass
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_subject(text: str) -> str:
    """Heuristic: extract the noun phrase after a query keyword."""
    text = re.sub(r"^(what\s+is|what's|how\s+(do|to|can)\s+(i|you|we)|why|when|where|who)\s*", "",
                  text.strip(), flags=re.I)
    return text.strip(" ?") or "unknown"


def _extract_object(text: str, action_pattern: re.Pattern[str]) -> str:
    """Heuristic: extract the object noun phrase after the action keyword."""
    remainder = action_pattern.sub("", text).strip()
    return remainder or "target"


# ---------------------------------------------------------------------------
# LinguaLogica class (stateful wrapper for engine integration)
# ---------------------------------------------------------------------------

class LinguaLogica:
    """Stateful interface for the Lingua Logica symbolic dialect.

    Wraps the module-level functions and provides a translation cache
    to avoid re-encoding identical inputs.
    """

    def __init__(self, cache_size: int = 512):
        self._cache_size = cache_size
        self._cache: Dict[str, LogicExpr] = {}
        self._encode_count = 0
        self._cache_hits   = 0

    def encode(self, text: str) -> LogicExpr:
        if text in self._cache:
            self._cache_hits += 1
            return self._cache[text]
        result = encode(text)
        self._encode_count += 1
        if len(self._cache) >= self._cache_size:
            # Evict oldest entry
            self._cache.pop(next(iter(self._cache)))
        self._cache[text] = result
        return result

    def decode(self, expr: LogicExpr) -> str:
        return decode(expr)

    def evaluate(self, expr: LogicExpr) -> Optional[Any]:
        return evaluate(expr)

    def translate(self, text: str) -> Tuple[LogicExpr, str]:
        """Encode, then immediately decode back — for round-trip testing."""
        expr = self.encode(text)
        return expr, self.decode(expr)

    def status(self) -> Dict[str, Any]:
        return {
            "encodes":    self._encode_count,
            "cache_hits": self._cache_hits,
            "cache_size": len(self._cache),
        }
