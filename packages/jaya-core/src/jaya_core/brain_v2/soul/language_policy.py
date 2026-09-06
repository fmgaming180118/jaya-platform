"""Lightweight language policy pack for portable offline dialogue.

This module keeps language behavior separate from runtime orchestration,
so style tuning can be done without changing engine logic.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, cast

LANGUAGE_CORE: Dict[str, Dict[str, str]] = {
    "id": {
        "greeting": (
            "Halo, saya JAYA, asisten lokal Anda. "
            "Silakan sampaikan apa yang ingin Anda lakukan hari ini."
        ),
        "no_memory": (
            "Untuk topik ini, fakta lokal belum tersedia. "
            "Namun saya tetap bisa membantu dengan arah umum dan klarifikasi."
        ),
        "portable": (
            "Bahasa ini tertanam di core lokal, jadi JAYA tetap bisa berkomunikasi "
            "meski memori tambahan belum lengkap."
        ),
        "header": "Pertanyaan Anda:",
        "closing": "Silakan lanjutkan jika Anda ingin penjelasan tambahan.",
        "intent_action": "Saya akan {intent} untuk Anda.",
        "intent_query": "Bagaimana saya bisa membantu Anda {intent}?",
        "mixed_notice": "Saya mendeteksi campuran bahasa. Jawaban akan dibuat per bagian.",
        "clarify": (
            "Maaf, maksudnya belum jelas. Tolong jelaskan tujuan, objek, dan hasil yang Anda inginkan."
        ),
        "segment_no_memory": "Bagian {index}: belum ada memori yang sesuai.",
        "segment_clarify": "Bagian {index}: maksudnya masih kurang jelas. Mohon perjelas.",
        "segment_with_memory": "Bagian {index}: konteks tersedia, ringkasannya {summary}",
        "procedure_intro": "Saya menemukan prosedur lokal yang relevan. Ikuti langkah berikut:",
        "procedure_step": "Langkah {index}: {step}",
        "procedure_meta": "Sumber: {source}, kepercayaan: {confidence}",
    },
    "en": {
        "greeting": (
            "JAYA online, Boss. Local sovereign mode is active. "
            "Share your request and I will answer clearly."
        ),
        "no_memory": (
            "Boss, local factual memory for this topic is not available yet. "
            "The core language module is still active and ready to converse."
        ),
        "portable": (
            "This language ability is embedded in the local core, so JAYA can still speak "
            "after device migration, even with a minimal RAG state."
        ),
        "header": "Boss, I searched local memory. Summary:",
        "closing": "If needed, I can continue with a deeper explanation.",
        "intent_action": "I read your intent as an action: {intent}.",
        "intent_query": "I read your intent as a question: {intent}.",
        "mixed_notice": "I detected mixed language input. I will answer sentence by sentence.",
        "clarify": (
            "Your request is still ambiguous. Please clarify the goal, target object, and expected output "
            "so I can execute it accurately."
        ),
        "segment_no_memory": (
            "Sentence {index}: factual memory is not available, but the core language module remains active."
        ),
        "segment_clarify": (
            "Sentence {index}: the intent is ambiguous. Please clarify the context or target object."
        ),
        "segment_with_memory": "Sentence {index}: local context is available, summary {summary}",
        "procedure_intro": "I found a relevant local procedure. Follow these steps:",
        "procedure_step": "{index}. {step}",
        "procedure_meta": "Source: {source} | confidence: {confidence}",
    },
}

_OVERRIDE_STATUS: Dict[str, Any] = {
    "loaded": False,
    "path": None,
    "updated_fields": 0,
    "error": None,
}

_REQUIRED_PLACEHOLDERS: Dict[str, tuple[str, ...]] = {
    "intent_action": ("{intent}",),
    "intent_query": ("{intent}",),
    "segment_no_memory": ("{index}",),
    "segment_clarify": ("{index}",),
    "segment_with_memory": ("{index}", "{summary}"),
    "procedure_step": ("{index}", "{step}"),
    "procedure_meta": ("{source}", "{confidence}"),
}

_PLACEHOLDER_PATTERN = re.compile(r"\{[a-z_]+\}")


_EN_HINTS = {
    "what", "how", "why", "where", "when", "who", "please", "help", "open",
    "close", "search", "find", "create", "delete", "update", "explain", "translate",
}

_ID_HINTS = {
    "apa", "bagaimana", "kenapa", "mengapa", "siapa", "kapan", "dimana", "di", "tolong",
    "buka", "tutup", "cari", "buat", "hapus", "ubah", "jelaskan", "terjemahkan",
    "saya", "kamu", "anda", "kami", "kita", "mau", "bisa", "ya",
}


def get_policy(language: str) -> Dict[str, str]:
    return LANGUAGE_CORE.get(language, LANGUAGE_CORE["id"])


def split_sentences(text: str) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+|[;\n]+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return "id"

    en_score = sum(1 for word in words if word in _EN_HINTS)
    id_score = sum(1 for word in words if word in _ID_HINTS)

    if en_score > (id_score + 1):
        return "en"
    return "id"


def detect_sentence_languages(text: str) -> List[str]:
    sentences = split_sentences(text)
    if not sentences:
        return [detect_language(text)]
    return [detect_language(sentence) for sentence in sentences]


def ordered_unique(items: List[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def get_language_policy_status() -> Dict[str, Any]:
    return dict(_OVERRIDE_STATUS)


def _default_override_path() -> Path:
    # language_policy.py -> soul -> brain_v2 -> src -> JAYA_CORE
    core_root = Path(__file__).resolve().parents[3]
    return core_root / "docs" / "language_policy_overrides.json"


def _build_merged_language_core(
    base: Dict[str, Dict[str, str]],
    overrides: Dict[str, Any],
) -> tuple[Dict[str, Dict[str, str]], int]:
    merged: Dict[str, Dict[str, str]] = {
        lang: dict(entries) for lang, entries in base.items()
    }
    updated_fields = 0

    for lang, lang_overrides in overrides.items():
        if lang not in merged:
            continue
        if not isinstance(lang_overrides, dict):
            continue

        lang_map = cast(Dict[str, Any], lang_overrides)
        for key, value in lang_map.items():
            key_name = str(key)
            if key_name not in merged[lang]:
                continue
            if not isinstance(value, str):
                continue

            clean_value = re.sub(r"\s+", " ", value.strip())
            if not clean_value:
                continue

            # Keep policy compact for low-RAM deployments.
            if len(clean_value) > 420:
                clean_value = clean_value[:420].rstrip() + "..."

            required_tokens = _REQUIRED_PLACEHOLDERS.get(key_name)
            if required_tokens and not all(token in clean_value for token in required_tokens):
                # Skip malformed template overrides to preserve runtime formatting behavior.
                continue

            found_tokens = set(_PLACEHOLDER_PATTERN.findall(clean_value))
            allowed_tokens = set(required_tokens or ())
            if found_tokens - allowed_tokens:
                # Skip unresolved or unsupported placeholders.
                continue

            if merged[lang][key_name] != clean_value:
                merged[lang][key_name] = clean_value
                updated_fields += 1

    return merged, updated_fields


def load_language_policy_overrides(path: str | None = None) -> bool:
    candidate_path = Path(path).resolve() if path else _default_override_path()

    _OVERRIDE_STATUS["loaded"] = False
    _OVERRIDE_STATUS["path"] = str(candidate_path)
    _OVERRIDE_STATUS["updated_fields"] = 0
    _OVERRIDE_STATUS["error"] = None

    if not candidate_path.exists():
        return False

    try:
        raw = candidate_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            _OVERRIDE_STATUS["error"] = "invalid_payload_type"
            return False

        payload_map = cast(Dict[str, Any], payload)
        merged, updated_fields = _build_merged_language_core(LANGUAGE_CORE, payload_map)
        for lang, lang_values in merged.items():
            LANGUAGE_CORE[lang].update(lang_values)

        _OVERRIDE_STATUS["loaded"] = updated_fields > 0
        _OVERRIDE_STATUS["updated_fields"] = updated_fields
        return _OVERRIDE_STATUS["loaded"]
    except Exception as exc:
        _OVERRIDE_STATUS["error"] = str(exc)
        return False


_ = load_language_policy_overrides(os.getenv("JAYA_LANGUAGE_POLICY_PATH"))
