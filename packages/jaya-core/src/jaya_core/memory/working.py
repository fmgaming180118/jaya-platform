"""
working.py — Bounded, session-scoped working memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkingMemoryItem:
    item_id: str
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0  # 5 minutes default


class WorkingMemory:
    """In-memory, session-isolated, bounded working memory."""

    def __init__(self, session_id: str, max_items: int = 50) -> None:
        self.session_id = session_id
        self.max_items = max_items
        self._items: Dict[str, WorkingMemoryItem] = {}

    def set(self, key: str, value: Any, ttl_seconds: float = 300.0) -> None:
        self.cleanup_expired()
        if len(self._items) >= self.max_items and key not in self._items:
            # Evict oldest item
            oldest_key = min(self._items.keys(), key=lambda k: self._items[k].created_at)
            del self._items[oldest_key]

        item_id = f"wm-{key}-{int(time.time()*1000)}"
        self._items[key] = WorkingMemoryItem(
            item_id=item_id,
            key=key,
            value=value,
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )

    def get(self, key: str, default: Any = None) -> Any:
        self.cleanup_expired()
        item = self._items.get(key)
        if item is None:
            return default
        return item.value

    def cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            k for k, item in self._items.items()
            if now - item.created_at > item.ttl_seconds
        ]
        for k in expired:
            del self._items[k]

    def clear(self) -> None:
        self._items.clear()

    def snapshot(self) -> Dict[str, Any]:
        self.cleanup_expired()
        return {k: item.value for k, item in self._items.items()}
