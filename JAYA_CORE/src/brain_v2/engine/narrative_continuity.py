"""Pillar 31 - Narrative Continuity.

Lightweight autobiographical memory for keeping cross-turn context coherent.
Design goals:
- pure Python, zero external dependencies,
- bounded memory footprint,
- optional JSON persistence when a path is configured.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, cast

logger = logging.getLogger("NarrativeContinuity")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "with", "in", "on", "at",
    "is", "are", "was", "were", "be", "this", "that", "it", "you", "your",
    "yang", "dan", "atau", "ke", "dari", "untuk", "dengan", "di", "ini", "itu",
    "saya", "aku", "kami", "kita", "anda", "kamu", "apa", "bagaimana", "kenapa",
}


def _sanitize_text(value: Any, max_len: int = 320) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _derive_intent(logic_expr: Any) -> str:
    if isinstance(logic_expr, (tuple, list)):
        seq = cast(Sequence[Any], logic_expr)
        if not seq:
            return "UNKNOWN"
        head = str(seq[0]).strip().upper()
        if len(seq) > 1:
            return f"{head}:{str(seq[1]).strip().upper()}"
        return head
    return "UNKNOWN"


def _derive_topic(text: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    kept = [t for t in tokens if t not in _STOPWORDS]
    if not kept:
        return "general"
    return " ".join(kept[:3])


class NarrativeContinuity:
    """Bounded autobiographical trace for JAYA runtime."""

    def __init__(
        self,
        max_events: int = 256,
        summary_window: int = 8,
        persist_path: Optional[str] = None,
    ) -> None:
        self.max_events = max(32, int(max_events))
        self.summary_window = max(3, int(summary_window))
        self.persist_path = persist_path or None

        self._events: List[Dict[str, Any]] = []
        self._summary: str = ""
        self._last_save_ts: float = 0.0

        self._load()

    def remember_turn(
        self,
        user_text: str,
        logic_expr: Any = None,
        runtime_result: Optional[Dict[str, Any]] = None,
        response_text: str = "",
        source: str = "runtime_intent",
    ) -> Dict[str, Any]:
        result = runtime_result or {}
        event: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": "turn",
            "source": _sanitize_text(source, max_len=32),
            "user": _sanitize_text(user_text, max_len=240),
            "response": _sanitize_text(response_text, max_len=260),
            "intent": _derive_intent(logic_expr),
            "topic": _derive_topic(user_text),
            "ok": bool(result.get("ok", True)),
        }
        self._append_event(event)
        return event

    def remember_feedback(
        self,
        task: str,
        score: Optional[float],
        source: str = "twin_feedback",
    ) -> Dict[str, Any]:
        value = None
        if score is not None:
            try:
                value = float(score)
            except (TypeError, ValueError):
                value = None

        event: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": "feedback",
            "source": _sanitize_text(source, max_len=32),
            "task": _sanitize_text(task, max_len=120),
            "score": value,
        }
        self._append_event(event)
        return event

    def snapshot(self, limit: int = 5, max_chars: int = 600) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit), 20))
        safe_chars = max(120, min(int(max_chars), 2000))

        recent = self._events[-safe_limit:]
        context = self._build_context(recent=recent, max_chars=safe_chars)
        return {
            "summary": self._summary,
            "recent": recent,
            "context": context,
            "total_events": len(self._events),
            "persist_path": self.persist_path,
        }

    def status(self) -> Dict[str, Any]:
        turn_count = sum(1 for e in self._events if e.get("kind") == "turn")
        feedback_count = sum(1 for e in self._events if e.get("kind") == "feedback")
        return {
            "max_events": self.max_events,
            "summary_window": self.summary_window,
            "events": len(self._events),
            "turn_events": turn_count,
            "feedback_events": feedback_count,
            "has_persistence": bool(self.persist_path),
            "summary": self._summary,
        }

    def _append_event(self, event: Dict[str, Any]) -> None:
        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]
        self._refresh_summary()
        self._save()

    def _refresh_summary(self) -> None:
        turns = [e for e in self._events if e.get("kind") == "turn"]
        recent_turns = turns[-self.summary_window :]
        if not recent_turns:
            self._summary = ""
            return

        topics: List[str] = []
        intents: List[str] = []
        for item in recent_turns:
            topic = str(item.get("topic") or "general")
            intent = str(item.get("intent") or "UNKNOWN")
            if topic not in topics:
                topics.append(topic)
            if intent not in intents:
                intents.append(intent)

        latest_user = str(recent_turns[-1].get("user") or "")
        topic_str = ", ".join(topics[:3]) if topics else "general"
        intent_str = ", ".join(intents[:3]) if intents else "UNKNOWN"

        self._summary = (
            f"Focus={topic_str}; Intents={intent_str}; "
            f"Latest='{_sanitize_text(latest_user, max_len=90)}'"
        )

    def _build_context(self, recent: List[Dict[str, Any]], max_chars: int) -> str:
        lines: List[str] = []
        if self._summary:
            lines.append(f"Summary: {self._summary}")

        for item in recent:
            kind = str(item.get("kind") or "")
            if kind == "turn":
                lines.append(
                    "Turn: "
                    f"intent={item.get('intent')} "
                    f"topic={item.get('topic')} "
                    f"user={item.get('user')}"
                )
            elif kind == "feedback":
                lines.append(
                    f"Feedback: task={item.get('task')} score={item.get('score')}"
                )

        context = "\n".join(lines).strip()
        if len(context) <= max_chars:
            return context
        return context[: max_chars - 3].rstrip() + "..."

    def _load(self) -> None:
        if not self.persist_path:
            return
        if not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as handle:
                raw_obj = json.load(handle)

            if not isinstance(raw_obj, dict):
                return
            raw: Dict[str, Any] = cast(Dict[str, Any], raw_obj)

            events_raw_obj = raw.get("events")
            if isinstance(events_raw_obj, list):
                events_raw = cast(List[object], events_raw_obj)
                normalized_events: List[Dict[str, Any]] = []
                for raw_item in events_raw:
                    if isinstance(raw_item, dict):
                        item_map = cast(Dict[Any, Any], raw_item)
                        clean_item: Dict[str, Any] = {}
                        for key, value in item_map.items():
                            clean_item[str(key)] = value
                        normalized_events.append(clean_item)
                self._events = normalized_events[-self.max_events :]
            summary = raw.get("summary")
            if isinstance(summary, str):
                self._summary = summary
            else:
                self._refresh_summary()
        except Exception as exc:
            logger.warning("[NarrativeContinuity] load failed: %s", exc)

    def _save(self) -> None:
        if not self.persist_path:
            return
        try:
            directory = os.path.dirname(self.persist_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "events": self._events,
                        "summary": self._summary,
                    },
                    handle,
                    ensure_ascii=True,
                )
            self._last_save_ts = time.time()
        except OSError as exc:
            logger.warning("[NarrativeContinuity] save failed: %s", exc)
