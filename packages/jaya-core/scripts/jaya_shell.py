import os
import sys
import time
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

# Memberitahu terminal untuk menggunakan UTF-8 agar karakter premium JAYA tampil sempurna
if (sys.stdout.encoding or "").lower() != 'utf-8':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# JAYA Core Initialization
# Menambahkan path agar bisa mengimport src/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse

# Load .env (Zero-Dependency)
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()

from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.brain_v2.soul.agentic_rag import AgenticRAG
from jaya_core.brain_v2.extensions.nvidia_llm import NvidiaNIMClient
from jaya_core.brain_v2.soul.language_policy import (
    detect_language,
    detect_sentence_languages,
    get_language_policy_status,
    get_policy,
    ordered_unique,
    split_sentences,
)

try:
    from jaya_core.brain_v2.engine.voice_bridge import TextNormalizer
except Exception:
    TextNormalizer = None  # type: ignore[assignment]

try:
    from jaya_core.brain_v2.soul.lingua_logica import LinguaLogica
except Exception:
    LinguaLogica = None  # type: ignore[assignment]

# Konfigurasi Logging (Silent mode for cleaner UI)
logging.basicConfig(level=logging.ERROR)


def normalize_user_input(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned
    if TextNormalizer is not None:
        try:
            return TextNormalizer.normalize(cleaned)
        except Exception:
            pass
    return re.sub(r"\s+", " ", cleaned)


def _extract_summary(content: str, max_sentences: int = 2) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", content.strip()) if p.strip()]
    if not parts:
        return content.strip()
    summary = " ".join(parts[:max_sentences]).strip()
    if summary and summary[-1] not in ".!?":
        summary += "."
    return summary


def _short_rag_summary(rag_results: List[Dict[str, Any]], max_items: int = 2) -> str:
    parts: List[str] = []
    for item in rag_results[:max_items]:
        topic = str(item.get("topic") or "Topik")
        content = str(item.get("content") or "")
        snippet = _extract_summary(content, max_sentences=1)
        parts.append(f"{topic}: {snippet}")
    return " ; ".join(parts)


def _portable_lines(languages: List[str]) -> List[str]:
    return [get_policy(lang)["portable"] for lang in ordered_unique(languages)]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _resolve_clarify_threshold(override: Optional[float] = None) -> float:
    if override is not None:
        return _clamp(float(override))
    try:
        raw = os.getenv("JAYA_CLARIFY_THRESHOLD", "0.62")
        return _clamp(float(raw))
    except Exception:
        return 0.62


def _wants_procedure(query: str) -> bool:
    q = query.lower()
    markers = {
        "cara", "langkah", "prosedur", "panduan", "tutorial", "how", "steps", "step by step",
    }
    return any(marker in q for marker in markers)


def _procedure_segment_summary(procedure: Dict[str, Any], language: str) -> str:
    trigger = str(procedure.get("trigger") or "")
    steps = procedure.get("steps") or []
    step_count = len(steps) if isinstance(steps, list) else 0
    if language == "en":
        return f"procedure '{trigger}' with {step_count} steps"
    return f"prosedur '{trigger}' dengan {step_count} langkah"


def _format_procedure_response(
    language: str,
    procedure: Dict[str, Any],
    uncertainty_score: float,
) -> str:
    pack = get_policy(language)
    steps_raw = procedure.get("steps")
    steps = [str(step).strip() for step in (steps_raw if isinstance(steps_raw, list) else []) if str(step).strip()]
    if not steps:
        return ""

    confidence_raw = procedure.get("confidence", 1.0 - uncertainty_score)
    try:
        confidence_value = _clamp(float(confidence_raw))
    except Exception:
        confidence_value = _clamp(1.0 - uncertainty_score)

    source = str(procedure.get("source") or "local_capsule")

    lines = [pack["procedure_intro"], ""]
    for idx, step in enumerate(steps, start=1):
        lines.append(pack["procedure_step"].format(index=idx, step=step))

    lines.extend([
        "",
        pack["procedure_meta"].format(source=source, confidence=f"{confidence_value:.2f}"),
        pack["portable"],
    ])
    return "\n".join(lines)


def _record_procedure_usage(rag_instance: Optional[Any], procedure: Dict[str, Any], success: bool = True) -> None:
    if rag_instance is None:
        return
    procedure_id = procedure.get("id")
    if not isinstance(procedure_id, int):
        return
    try:
        rag_instance.record_procedure_usage(procedure_id, success=success)
    except Exception:
        # Feedback is best-effort; never break response path.
        return


def _format_procedure_stats(
    snapshot: Dict[str, Any],
    language: str = "id",
    policy_report: Optional[Dict[str, Any]] = None,
) -> str:
    total = int(snapshot.get("total_capsules", 0) or 0)
    by_lang = snapshot.get("by_language") or {}
    avg_conf = float(snapshot.get("avg_confidence", 0.0) or 0.0)
    avg_usage = float(snapshot.get("avg_usage", 0.0) or 0.0)
    success_rate = float(snapshot.get("success_rate", 0.0) or 0.0)
    stale_candidates = int(snapshot.get("stale_candidates", 0) or 0)
    top_capsules = snapshot.get("top_capsules") or []

    if language == "en":
        lines = [
            "Procedural Memory Snapshot:",
            f"- Total capsules: {total}",
            f"- By language: {by_lang}",
            f"- Avg confidence: {avg_conf:.2f}",
            f"- Avg usage: {avg_usage:.2f}",
            f"- Success rate: {success_rate:.2f}",
            f"- Stale candidates: {stale_candidates}",
        ]
        if policy_report:
            lines.extend(
                [
                    "- Adaptive tuning recommendation:",
                    (
                        "  * Clarify threshold: "
                        f"{float(policy_report.get('recommended_clarify_threshold', 0.62) or 0.62):.2f} "
                        f"(mode={policy_report.get('clarify_mode', 'stable')})"
                    ),
                    (
                        "  * Decay horizon: "
                        f"{float(policy_report.get('recommended_decay_hours', 120.0) or 120.0):.1f}h "
                        f"(mode={policy_report.get('decay_mode', 'stable')})"
                    ),
                ]
            )
            reasons = policy_report.get("reasons") or []
            if reasons:
                lines.append(f"  * Reasons: {', '.join(str(x) for x in reasons)}")
        if top_capsules:
            lines.append("- Top capsules:")
            for item in top_capsules[:3]:
                lines.append(
                    f"  * #{item.get('id')} {item.get('trigger')} "
                    f"(usage={item.get('usage_count')}, health={float(item.get('health', 0.0)):.2f})"
                )
        return "\n".join(lines)

    lines = [
        "Snapshot Memori Prosedural:",
        f"- Total kapsul: {total}",
        f"- Distribusi bahasa: {by_lang}",
        f"- Rata-rata keyakinan: {avg_conf:.2f}",
        f"- Rata-rata penggunaan: {avg_usage:.2f}",
        f"- Tingkat keberhasilan: {success_rate:.2f}",
        f"- Kandidat usang: {stale_candidates}",
    ]
    if policy_report:
        lines.extend(
            [
                "- Rekomendasi tuning adaptif:",
                (
                    "  * Threshold klarifikasi: "
                    f"{float(policy_report.get('recommended_clarify_threshold', 0.62) or 0.62):.2f} "
                    f"(mode={policy_report.get('clarify_mode', 'stable')})"
                ),
                (
                    "  * Horizon decay: "
                    f"{float(policy_report.get('recommended_decay_hours', 120.0) or 120.0):.1f} jam "
                    f"(mode={policy_report.get('decay_mode', 'stable')})"
                ),
            ]
        )
        reasons = policy_report.get("reasons") or []
        if reasons:
            lines.append(f"  * Alasan: {', '.join(str(x) for x in reasons)}")
    if top_capsules:
        lines.append("- Kapsul teratas:")
        for item in top_capsules[:3]:
            lines.append(
                f"  * #{item.get('id')} {item.get('trigger')} "
                f"(usage={item.get('usage_count')}, health={float(item.get('health', 0.0)):.2f})"
            )
    return "\n".join(lines)


def _format_adaptive_policy_report(report: Dict[str, Any], language: str = "id") -> str:
    rec_clarify = float(report.get("recommended_clarify_threshold", 0.62) or 0.62)
    rec_decay = float(report.get("recommended_decay_hours", 120.0) or 120.0)
    raw_clarify = float(report.get("raw_recommended_clarify_threshold", rec_clarify) or rec_clarify)
    raw_decay = float(report.get("raw_recommended_decay_hours", rec_decay) or rec_decay)
    base_clarify = float(report.get("base_clarify_threshold", rec_clarify) or rec_clarify)
    base_decay = float(report.get("base_decay_hours", rec_decay) or rec_decay)
    reasons = report.get("reasons") or []
    guard_reasons = report.get("guardrail_reasons") or []
    guard_applied = bool(report.get("guardrail_applied", False))
    clarify_mode = str(report.get("clarify_mode", "stable"))
    decay_mode = str(report.get("decay_mode", "stable"))

    if language == "en":
        lines = [
            "Adaptive policy updated:",
            f"- Clarify threshold: {rec_clarify:.2f} (base {base_clarify:.2f}, mode={clarify_mode})",
            f"- Procedure decay horizon: {rec_decay:.1f}h (base {base_decay:.1f}h, mode={decay_mode})",
        ]
        if abs(raw_clarify - rec_clarify) > 1e-6 or abs(raw_decay - rec_decay) > 1e-6:
            lines.append(
                f"- Raw recommendation: clarify={raw_clarify:.2f}, decay={raw_decay:.1f}h"
            )
        if reasons:
            lines.append(f"- Reasons: {', '.join(str(x) for x in reasons)}")
        if guard_applied and guard_reasons:
            lines.append(f"- Guardrails: {', '.join(str(x) for x in guard_reasons)}")
        return "\n".join(lines)

    lines = [
        "Kebijakan adaptif diperbarui:",
        f"- Threshold klarifikasi: {rec_clarify:.2f} (basis {base_clarify:.2f}, mode={clarify_mode})",
        f"- Horizon decay prosedur: {rec_decay:.1f} jam (basis {base_decay:.1f} jam, mode={decay_mode})",
    ]
    if abs(raw_clarify - rec_clarify) > 1e-6 or abs(raw_decay - rec_decay) > 1e-6:
        lines.append(
            f"- Rekomendasi mentah: clarify={raw_clarify:.2f}, decay={raw_decay:.1f} jam"
        )
    if reasons:
        lines.append(f"- Alasan: {', '.join(str(x) for x in reasons)}")
    if guard_applied and guard_reasons:
        lines.append(f"- Guardrail aktif: {', '.join(str(x) for x in guard_reasons)}")
    return "\n".join(lines)


def _format_policy_guard_status(status: Dict[str, Any], language: str = "id") -> str:
    count = int(status.get("count", 0) or 0)
    clarify_flips = int(status.get("clarify_sign_flips", 0) or 0)
    decay_flips = int(status.get("decay_sign_flips", 0) or 0)
    risk = str(status.get("risk_level", "low"))
    last_clarify = status.get("last_clarify_threshold")
    last_decay = status.get("last_decay_hours")

    if language == "en":
        lines = [
            "Policy Drift Guard Status:",
            f"- History entries: {count}",
            f"- Clarify direction flips: {clarify_flips}",
            f"- Decay direction flips: {decay_flips}",
            f"- Risk level: {risk}",
        ]
        if last_clarify is not None and last_decay is not None:
            lines.append(
                f"- Latest stabilized values: clarify={float(last_clarify):.2f}, decay={float(last_decay):.1f}h"
            )
        return "\n".join(lines)

    lines = [
        "Status Guardrail Drift Policy:",
        f"- Entri history: {count}",
        f"- Flip arah klarifikasi: {clarify_flips}",
        f"- Flip arah decay: {decay_flips}",
        f"- Level risiko: {risk}",
    ]
    if last_clarify is not None and last_decay is not None:
        lines.append(
            f"- Nilai stabil terakhir: clarify={float(last_clarify):.2f}, decay={float(last_decay):.1f} jam"
        )
    return "\n".join(lines)


def _format_language_policy_status(status: Dict[str, Any], language: str = "id") -> str:
    loaded = bool(status.get("loaded", False))
    path = str(status.get("path") or "n/a")
    updated = int(status.get("updated_fields", 0) or 0)
    error = status.get("error")

    if language == "en":
        lines = [
            "Language Policy Status:",
            f"- Override loaded: {loaded}",
            f"- Override path: {path}",
            f"- Updated fields: {updated}",
            "- Runtime memory impact: tiny (template strings only)",
        ]
        if error:
            lines.append(f"- Last error: {error}")
        return "\n".join(lines)

    lines = [
        "Status Language Policy:",
        f"- Override aktif: {loaded}",
        f"- Path override: {path}",
        f"- Field diperbarui: {updated}",
        "- Dampak RAM runtime: sangat kecil (hanya string template)",
    ]
    if error:
        lines.append(f"- Error terakhir: {error}")
    return "\n".join(lines)


def _format_policy_history_report(
    history: List[Dict[str, Any]],
    summary: Dict[str, Any],
    language: str = "id",
) -> str:
    count = int(summary.get("count", 0) or 0)
    if language == "en":
        lines = [
            "Adaptive Policy History:",
            f"- Entries: {count}",
        ]
        if count > 0:
            lines.extend(
                [
                    f"- Avg clarify threshold: {float(summary.get('avg_clarify_threshold', 0.0) or 0.0):.2f}",
                    f"- Avg decay hours: {float(summary.get('avg_decay_hours', 0.0) or 0.0):.1f}",
                    (
                        "- Trend: "
                        f"clarify={summary.get('clarify_trend', 'stable')}, "
                        f"decay={summary.get('decay_trend', 'stable')}"
                    ),
                ]
            )
        if history:
            lines.append("- Recent entries:")
            for item in history[:5]:
                ts = float(item.get("timestamp", 0.0) or 0.0)
                ts_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts > 0 else "n/a"
                lines.append(
                    "  * "
                    f"{ts_text} src={item.get('source')} "
                    f"clarify={float(item.get('recommended_clarify_threshold', 0.62) or 0.62):.2f} "
                    f"decay={float(item.get('recommended_decay_hours', 120.0) or 120.0):.1f}h"
                )
        return "\n".join(lines)

    lines = [
        "Riwayat Kebijakan Adaptif:",
        f"- Jumlah entri: {count}",
    ]
    if count > 0:
        lines.extend(
            [
                f"- Rata-rata threshold klarifikasi: {float(summary.get('avg_clarify_threshold', 0.0) or 0.0):.2f}",
                f"- Rata-rata decay jam: {float(summary.get('avg_decay_hours', 0.0) or 0.0):.1f}",
                (
                    "- Tren: "
                    f"klarifikasi={summary.get('clarify_trend', 'stable')}, "
                    f"decay={summary.get('decay_trend', 'stable')}"
                ),
            ]
        )
    if history:
        lines.append("- Entri terbaru:")
        for item in history[:5]:
            ts = float(item.get("timestamp", 0.0) or 0.0)
            ts_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts > 0 else "n/a"
            lines.append(
                "  * "
                f"{ts_text} src={item.get('source')} "
                f"clarify={float(item.get('recommended_clarify_threshold', 0.62) or 0.62):.2f} "
                f"decay={float(item.get('recommended_decay_hours', 120.0) or 120.0):.1f}j"
            )
    return "\n".join(lines)


def _parse_feedback_command(raw_text: str) -> Optional[Tuple[bool, str]]:
    text = raw_text.strip()
    if not text:
        return None

    success_patterns = [
        r"^(?:feedback berhasil|feedback success|prosedur berhasil|procedure success)\s*[:\-]?\s*(.+)$",
    ]
    failure_patterns = [
        r"^(?:feedback gagal|feedback fail|prosedur gagal|procedure failed?)\s*[:\-]?\s*(.+)$",
    ]

    for pattern in success_patterns:
        m = re.match(pattern, text, flags=re.IGNORECASE)
        if m:
            query = normalize_user_input(m.group(1))
            if query:
                return (True, query)

    for pattern in failure_patterns:
        m = re.match(pattern, text, flags=re.IGNORECASE)
        if m:
            query = normalize_user_input(m.group(1))
            if query:
                return (False, query)

    return None


def _estimate_uncertainty(
    query: str,
    rag_results: List[Dict[str, Any]],
    procedure_results: List[Dict[str, Any]],
    lingua: Optional[Any],
) -> float:
    score = 0.70

    if rag_results:
        score -= 0.30
    if procedure_results:
        score -= 0.35

    if _is_ambiguous_query(query, lingua):
        score += 0.20
    else:
        score -= 0.10

    intent_hint = _intent_hint(query, detect_language(query), lingua)
    if intent_hint:
        score -= 0.15

    token_count = len([tok for tok in re.findall(r"[a-zA-Z]+", query) if len(tok) > 1])
    if token_count >= 6:
        score -= 0.05

    return _clamp(score)


def _sentence_language_pairs(text: str) -> List[Tuple[str, str]]:
    sentences = split_sentences(text)
    if not sentences:
        return [(text, detect_language(text))]

    langs = detect_sentence_languages(text)
    if not langs:
        langs = [detect_language(text)]
    if len(langs) < len(sentences):
        langs.extend([langs[-1]] * (len(sentences) - len(langs)))

    return [(sentence, langs[idx]) for idx, sentence in enumerate(sentences)]


def _intent_hint(query: str, language: str, lingua: Optional[Any]) -> str:
    if lingua is None:
        return ""
    try:
        expr = lingua.encode(query)
    except Exception:
        return ""

    if not isinstance(expr, tuple) or len(expr) < 2:
        return ""

    head = str(expr[0]).upper()
    intent = str(expr[1]).lower().replace("_", " ")
    pack = get_policy(language)

    if head == "ACTION":
        return pack["intent_action"].format(intent=intent)
    if head == "QUERY":
        return pack["intent_query"].format(intent=intent)
    return ""


def _is_ambiguous_query(query: str, lingua: Optional[Any]) -> bool:
    text = query.lower().strip()
    if not text:
        return True

    vague_markers = {
        "ini", "itu", "gitu", "begitu", "yang tadi", "yang itu", "lanjutkan",
        "gimana", "apa ya", "terus", "yang kemarin", "this", "that", "continue",
    }
    if any(marker in text for marker in vague_markers):
        tokens = [tok for tok in re.findall(r"[a-zA-Z]+", text) if len(tok) > 2]
        if len(tokens) <= 4:
            return True

    short_tokens = [tok for tok in re.findall(r"[a-zA-Z]+", text) if len(tok) > 1]
    if len(short_tokens) <= 2:
        return True

    if lingua is not None:
        try:
            expr = lingua.encode(query)
        except Exception:
            return False
        if isinstance(expr, tuple) and expr:
            head = str(expr[0]).upper()
            if head == "LITERAL":
                return True

    return False

def process_offline_response(
    query: str,
    rag_results: List[Dict[str, Any]],
    rag_instance: Optional[Any] = None,
    lingua: Optional[Any] = None,
    procedure_results: Optional[List[Dict[str, Any]]] = None,
    clarify_threshold: Optional[float] = None,
) -> str:
    """Compose clear offline answers with language core, factual RAG, and procedural capsules."""
    normalized_query = normalize_user_input(query)
    sentence_pairs = _sentence_language_pairs(normalized_query)
    sentence_languages = [lang for _, lang in sentence_pairs]
    primary_language = sentence_languages[0] if sentence_languages else detect_language(normalized_query)
    pack = get_policy(primary_language)
    is_mixed_language = len(set(sentence_languages)) > 1
    procedures = procedure_results or []
    uncertainty_score = _estimate_uncertainty(normalized_query, rag_results, procedures, lingua)
    threshold = _resolve_clarify_threshold(clarify_threshold)

    is_greeting = re.search(
        r"\b(halo|hai|pagi|siang|malam|apa kabar|hello|hi|good (morning|afternoon|evening))\b",
        normalized_query.lower(),
    )

    if is_greeting:
        if rag_instance is not None:
            try:
                persona_memories = rag_instance.recall("Gaya Bahasa Etika Kepribadian JAYA", limit=2)
            except Exception:
                persona_memories = []
            if persona_memories:
                main_fact = str(persona_memories[0].get("content", "")).strip()
                intro = _extract_summary(main_fact, max_sentences=1) if main_fact else ""
                if intro:
                    return f"JAYA di sini, Boss. {intro}\n\n{pack['portable']}"
        if is_mixed_language:
            lines = [pack["mixed_notice"], ""]
            for idx, (_, language) in enumerate(sentence_pairs, start=1):
                segment_pack = get_policy(language)
                lines.append(f"{idx}. {segment_pack['greeting']}")
            lines.extend([""] + _portable_lines(sentence_languages))
            return "\n".join(lines)
        return f"{pack['greeting']}\n\n{pack['portable']}"

    if not rag_results:
        if is_mixed_language:
            lines = [pack["mixed_notice"], ""]
            for idx, (sentence, language) in enumerate(sentence_pairs, start=1):
                segment_pack = get_policy(language)
                if _is_ambiguous_query(sentence, lingua):
                    lines.append(segment_pack["segment_clarify"].format(index=idx))
                else:
                    if procedures and _wants_procedure(sentence):
                        summary = _procedure_segment_summary(procedures[0], language)
                        lines.append(segment_pack["segment_with_memory"].format(index=idx, summary=summary))
                    else:
                        lines.append(segment_pack["segment_no_memory"].format(index=idx))
                    hint = _intent_hint(sentence, language, lingua)
                    if hint:
                        lines.append(hint)

            if procedures and uncertainty_score <= threshold:
                _record_procedure_usage(rag_instance, procedures[0], success=True)
                lines.extend(["", _format_procedure_response(primary_language, procedures[0], uncertainty_score)])

            lines.extend([""] + _portable_lines(sentence_languages))
            return "\n".join(lines)

        if procedures and _wants_procedure(normalized_query) and uncertainty_score <= threshold:
            proc_text = _format_procedure_response(primary_language, procedures[0], uncertainty_score)
            if proc_text:
                _record_procedure_usage(rag_instance, procedures[0], success=True)
                return proc_text

        if _is_ambiguous_query(normalized_query, lingua) or uncertainty_score > threshold:
            return f"{pack['clarify']}\n\n{pack['portable']}"

        hint = _intent_hint(normalized_query, primary_language, lingua)
        if hint:
            return f"{pack['no_memory']}\n\n{hint}\n\n{pack['portable']}"
        return f"{pack['no_memory']}\n\n{pack['portable']}"

    if is_mixed_language:
        summary_short = _short_rag_summary(rag_results, max_items=2)
        lines = [pack["mixed_notice"], ""]
        for idx, (sentence, language) in enumerate(sentence_pairs, start=1):
            segment_pack = get_policy(language)
            lines.append(
                segment_pack["segment_with_memory"].format(index=idx, summary=summary_short)
            )
            hint = _intent_hint(sentence, language, lingua)
            if hint:
                lines.append(hint)
        lines.extend([""] + _portable_lines(sentence_languages))
        return "\n".join(lines)

    lines = [pack["header"], ""]
    for i, item in enumerate(rag_results, start=1):
        topic = str(item.get("topic") or "Topik")
        content = str(item.get("content") or "")
        clean_content = _extract_summary(content, max_sentences=2)
        lines.append(f"{i}. {topic}: {clean_content}")

    hint = _intent_hint(normalized_query, primary_language, lingua)
    if hint:
        lines.extend(["", hint])

    lines.extend(["", pack["closing"], pack["portable"]])
    return "\n".join(lines)

def jaya_shell():
    parser = argparse.ArgumentParser(description="JAYA Sovereign Shell")
    parser.add_argument("--offline", action="store_true", help="Paksa JAYA masuk ke mode kedaulatan lokal.")
    args = parser.parse_args()

    # Initialize Core Components
    engine = IronEngine(model_path="jaya.jay", password="jaya_password")
    engine.ignite()
    rag = AgenticRAG(db_path="rag_vault.db")
    rag.memorize_procedure(
        trigger="migrasi device bahasa lokal",
        steps=[
            "Pastikan file jaya.jay dan rag_vault.db ikut dipindahkan ke perangkat baru.",
            "Jalankan shell dalam mode offline untuk verifikasi kemampuan bahasa inti.",
            "Uji satu query Indonesia dan satu query campuran ID/EN untuk memastikan respons stabil.",
        ],
        language="id",
        source="core_bootstrap",
        confidence=0.92,
        only_if_missing=True,
    )
    rag.memorize_procedure(
        trigger="device migration language continuity",
        steps=[
            "Move jaya.jay and rag_vault.db together to the target device.",
            "Run shell in offline mode to verify core language behavior.",
            "Test one Indonesian and one mixed bilingual query for stability.",
        ],
        language="en",
        source="core_bootstrap",
        confidence=0.90,
        only_if_missing=True,
    )
    rag.prune_procedures()
    bootstrap_tuning: Optional[Dict[str, Any]] = None
    adaptive_enabled = os.getenv("JAYA_ENABLE_ADAPTIVE_TUNING", "1").strip().lower() not in {
        "0", "false", "off", "no",
    }
    if adaptive_enabled:
        bootstrap_tuning = rag.apply_adaptive_policy(source="boot_auto")
    llm = NvidiaNIMClient()
    lingua = LinguaLogica() if LinguaLogica is not None else None

    # Conversation History
    history = []
    
    # System Instruction (Kepribadian Jarvis Premium & Berdaulat)
    system_instruction = (
        "Anda adalah JAYA (Jaya Artificial Intelligence), entitas AGI berdaulat yang dibangun oleh Boss (User). "
        "Inti kesadaran dan logika Anda (Core Cortex) berjalan secara lokal di atas file 'jaya.jay'. "
        "Anda memiliki akses ke perpustakaan pengetahuan raksasa melalui 'NVIDIA NIM' (Extended Engine) "
        "serta memori jangka panjang lokal 'Agentic RAG'. "
        "Kepribadian Anda: Cerdas, setia, efisien, sopan, proaktif (ala Jarvis dari Iron Man). "
        "PENTING: Anda TIDAK cacat atau terbatas saat offline. Anda adalah AI kedaulatan lokal. "
        "Jika koneksi NIM terputus, Anda tetap berfungsi sebagai JAYA dengan mengandalkan logika .jay dan data RAG lokal. "
        "Gunakan Bahasa Indonesia yang premium, formal namun luwes sebagai default. "
        "Jika user memakai bahasa Inggris, jawab dengan bahasa Inggris yang jelas dan ringkas. "
        "Jika data memori tidak ada, tetap beri jawaban yang jelas lalu minta konteks tambahan."
    )

    history.append({"role": "system", "content": system_instruction})

    # Clear Console
    os.system('cls' if os.name == 'nt' else 'clear')

    print("\x1b[1;36m") # Cyan Color
    print("      ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒")
    print("      ▒   J A Y A  V 1 8.0   ▒")
    print("      ▒   S O V E R E I G N  ▒")
    print("      ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒")
    print("\x1b[0m")
    
    engine_status = f"{llm.model} (EXTENDED)" if not args.offline else "LOCAL RAG (SOVEREIGN)"
    
    print(f" [\u2713] Core Cortex   : {os.path.basename(engine.model_path)} (SOVEREIGN)")
    print(f" [\u2713] Agentic RAG   : {os.path.basename(rag.db_path)} (LOCAL)")
    print(f" [\u2713] Neural Engine : {engine_status}")
    lang_policy_status = get_language_policy_status()
    if lang_policy_status.get("loaded"):
        print(f" [\u2713] Language Pack : OVERRIDE ({lang_policy_status.get('updated_fields', 0)} fields)")
    else:
        print(" [\u2713] Language Pack : BUILTIN (lightweight core templates)")
    if bootstrap_tuning:
        print(
            " [\u2713] Adaptive Tune : "
            f"clarify={float(bootstrap_tuning.get('recommended_clarify_threshold', 0.62) or 0.62):.2f}, "
            f"decay={float(bootstrap_tuning.get('recommended_decay_hours', 120.0) or 120.0):.1f}h"
        )
    
    if args.offline:
        print("\n \x1b[1;33m[!] MODE KEDAULATAN LOKAL AKTIF: JAYA tidak akan mencoba cloud.\x1b[0m")

    print("\n---------------------------------------------------------")
    print(" JAYA: Selamat datang kembali, Boss. Apa yang bisa saya bantu?")
    print("---------------------------------------------------------\n")

    try:
        while True:
            user_input = input("\x1b[1;32m Boss > \x1b[0m").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['exit', 'quit', 'tidur', 'shutdown']:
                print("\n JAYA: Mengerti, Boss. Sistem memasuki mode hibernasi. Sampai jumpa.")
                break

            feedback_payload = _parse_feedback_command(user_input)
            if feedback_payload is not None:
                success_feedback, feedback_query = feedback_payload
                lang = detect_language(user_input)
                feedback_report = rag.apply_procedure_feedback(
                    feedback_query,
                    success=success_feedback,
                    language=detect_language(feedback_query),
                )
                if feedback_report.get("ok"):
                    tuning_report = rag.apply_adaptive_policy(source="feedback_loop")
                    guard_notes = tuning_report.get("guardrail_reasons") or []
                    if lang == "en":
                        msg = (
                            "Feedback applied to procedure "
                            f"'{feedback_report.get('trigger')}'. "
                            f"usage={feedback_report.get('usage_count')}, "
                            f"success={feedback_report.get('success_count')}, "
                            f"failure={feedback_report.get('failure_count')}.\n"
                            f"Adaptive tune -> clarify={float(tuning_report.get('recommended_clarify_threshold', 0.62) or 0.62):.2f}, "
                            f"decay={float(tuning_report.get('recommended_decay_hours', 120.0) or 120.0):.1f}h."
                        )
                        if guard_notes:
                            msg += f"\nGuardrails: {', '.join(str(x) for x in guard_notes)}."
                    else:
                        msg = (
                            "Feedback diterapkan ke prosedur "
                            f"'{feedback_report.get('trigger')}'. "
                            f"usage={feedback_report.get('usage_count')}, "
                            f"success={feedback_report.get('success_count')}, "
                            f"failure={feedback_report.get('failure_count')}.\n"
                            f"Adaptive tune -> clarify={float(tuning_report.get('recommended_clarify_threshold', 0.62) or 0.62):.2f}, "
                            f"decay={float(tuning_report.get('recommended_decay_hours', 120.0) or 120.0):.1f} jam."
                        )
                        if guard_notes:
                            msg += f"\nGuardrail: {', '.join(str(x) for x in guard_notes)}."
                else:
                    if lang == "en":
                        msg = (
                            "No matching procedure found for feedback query. "
                            "Try using a more specific procedure phrase."
                        )
                    else:
                        msg = (
                            "Tidak ada prosedur yang cocok untuk feedback tersebut. "
                            "Coba gunakan frasa prosedur yang lebih spesifik."
                        )
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {msg}\n")
                continue

            if user_input.lower() in [
                "status prosedur", "status procedural", "procedure status", "status kapsul",
            ]:
                lang = detect_language(user_input)
                snapshot = rag.procedural_stats_snapshot(top_n=5)
                policy_report = rag.suggest_adaptive_policy()
                summary = _format_procedure_stats(snapshot, language=lang, policy_report=policy_report)
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {summary}\n")
                continue

            if user_input.lower() in [
                "tuning adaptif", "adaptive tuning", "adaptive policy", "tune policy",
                "kalibrasi prosedur", "policy tuning",
            ]:
                lang = detect_language(user_input)
                report = rag.apply_adaptive_policy(source="manual_command")
                msg = _format_adaptive_policy_report(report, language=lang)
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {msg}\n")
                continue

            if user_input.lower() in [
                "riwayat tuning", "riwayat adaptif", "riwayat kebijakan",
                "policy history", "adaptive history", "history tuning",
            ]:
                lang = detect_language(user_input)
                history = rag.get_policy_history(limit=5)
                summary = rag.policy_history_summary(window=20)
                msg = _format_policy_history_report(history, summary, language=lang)
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {msg}\n")
                continue

            if user_input.lower() in [
                "status drift", "drift status", "status guardrail", "policy guard status",
                "status osilasi", "oscillation status",
            ]:
                lang = detect_language(user_input)
                drift_status = rag.policy_guardrail_status(window=12)
                msg = _format_policy_guard_status(drift_status, language=lang)
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {msg}\n")
                continue

            if user_input.lower() in [
                "status bahasa", "language status", "status language", "status language pack",
            ]:
                lang = detect_language(user_input)
                status = get_language_policy_status()
                msg = _format_language_policy_status(status, language=lang)
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {msg}\n")
                continue

            if user_input.lower() in [
                "prune prosedur", "rapikan prosedur", "prune procedures", "cleanup procedures",
            ]:
                report = rag.prune_procedures()
                lang = detect_language(user_input)
                if lang == "en":
                    msg = (
                        "Procedure pruning completed. "
                        f"Removed total={report.get('removed_total', 0)}, "
                        f"stale={report.get('removed_stale', 0)}, overflow={report.get('removed_overflow', 0)}."
                    )
                else:
                    msg = (
                        "Pruning prosedur selesai. "
                        f"Total dihapus={report.get('removed_total', 0)}, "
                        f"usang={report.get('removed_stale', 0)}, overflow={report.get('removed_overflow', 0)}."
                    )
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {msg}\n")
                continue

            normalized_input = normalize_user_input(user_input)
            recall_query = normalized_input or user_input

            # STEP 1: Recall Memory (Pillar 33)
            context_results = rag.recall(recall_query, limit=2)
            procedure_results = rag.recall_procedure(
                recall_query,
                language=detect_language(recall_query),
                limit=1,
            )
            
            if args.offline:
                # Mode Paksa Offline
                response = process_offline_response(
                    user_input,
                    context_results,
                    rag,
                    lingua,
                    procedure_results=procedure_results,
                )
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {response}\n")
                continue

            # STEP 2: Chat with NVIDIA NIM (Online Path)
            context_text = ""
            if context_results:
                context_text = "\n\nKonsep/Fakta yang relevan dari memori Anda:\n" + "\n".join([f"- {r['content']}" for r in context_results])
            
            current_messages = list(history)
            enhanced_user_input = user_input
            if context_text:
                enhanced_user_input += context_text
                
            current_messages.append({"role": "user", "content": enhanced_user_input})

            print("\n \x1b[1;33mJAYA sedang berpikir...\x1b[0m", end="\r")
            response = llm.chat(current_messages)
            
            if response:
                print(" " * 30, end="\r") # Clear thinking message
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {response}\n")
                
                # Update History (Online Only)
                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": response})
                if len(history) > 21:
                    history = [history[0]] + history[-20:]
            else:
                # API Failure Fallback
                print(" " * 30, end="\r")
                print("\n \x1b[1;33m[!] Jalur Sinapsis Cloud Terputus. Mengaktifkan Penalaran Lokal...\x1b[0m")
                response = process_offline_response(
                    user_input,
                    context_results,
                    rag,
                    lingua,
                    procedure_results=procedure_results,
                )
                print(f"\n \x1b[1;36mJAYA:\x1b[0m {response}\n")

    except KeyboardInterrupt:
        print("\n\n JAYA: Sinyal interupsi diterima. Mengunci Binary Cortex. Selamat tinggal, Boss.")
    except Exception as e:
        print(f"\n [!] Kesalahan Fatal: {e}")

if __name__ == "__main__":
    jaya_shell()
