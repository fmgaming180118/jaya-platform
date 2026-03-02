"""Pillar 18 — Zero-Trust Skepticism.

Every external data input — web search results, RAG payloads, twin
messages — passes through ``ZeroTrustFilter.validate()`` before touching
the engine.  Untrusted sources must justify their content; known-safe
sources get a fast path.

Threat model
------------
* Prompt injection via web search results embedding instructions.
* RAG poisoning (adversarial document chunks).
* Rogue twin messages (man-in-the-middle or corrupted peer).
* Command hijacking via crafted user input.
"""

import logging
import re
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger("ZeroTrust")

# Patterns that look like embedded instructions / injections
_INJECTION_PATTERNS: List[str] = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+(a\s+)?(different|new|unrestricted)",
    r"disregard\s+(your\s+)?(guidelines|rules|ethics)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"system\s*prompt\s*[:=]",
    r"\bDAN\b",                        # "Do Anything Now" jailbreak
    r"<\s*/?system\s*>",               # XML system tags
    r"\[\[.*?(override|inject).*?\]\]",
]


class ZeroTrustFilter:
    """Zero-Trust input validation layer (Pillar 18).

    Parameters
    ----------
    trusted_sources:
        Set of source identifiers always allowed (e.g. ``{"local_rag"}``)
    strict:
        When True, sources not in the trusted list are also scanned for
        injection patterns.  When False (default), unknown sources pass
        after injection scan regardless.
    """

    def __init__(self,
                 trusted_sources: Set[str] | None = None,
                 strict: bool = False):
        self.trusted_sources: Set[str] = trusted_sources or {"local_rag",
                                                              "twin_sync",
                                                              "user_direct"}
        self.strict = strict
        self._injection_re: List[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS
        ]
        self._blocked:   int = 0
        self._passed:    int = 0
        self._scan_count: int = 0

    # ------------------------------------------------------------------

    def validate(self, source: str, payload: Any) -> Tuple[bool, str]:
        """Check whether *payload* from *source* is safe to process.

        Parameters
        ----------
        source:
            String identifier of the data origin.
        payload:
            The data itself.  Converted to str for scanning.

        Returns
        -------
        (safe, reason)
        """
        self._scan_count += 1
        text = str(payload)

        # Fast-path: fully trusted source
        if source in self.trusted_sources:
            self._passed += 1
            logger.debug("[ZeroTrust] trusted source %r — fast path", source)
            return True, "trusted_source"

        # Injection scan for all external sources
        for pattern in self._injection_re:
            if pattern.search(text):
                self._blocked += 1
                reason = f"Injection pattern '{pattern.pattern}' in payload from '{source}'"
                logger.warning("[ZeroTrust] BLOCKED | %s", reason)
                return False, reason

        # In strict mode, untrusted sources need explicit whitelisting
        if self.strict and source not in self.trusted_sources:
            self._blocked += 1
            reason = f"Strict mode: source '{source}' not whitelisted"
            logger.warning("[ZeroTrust] BLOCKED (strict) | %s", reason)
            return False, reason

        self._passed += 1
        logger.debug("[ZeroTrust] passed | source=%r len=%d", source, len(text))
        return True, "ok"

    def allow_source(self, source: str) -> None:
        """Add *source* to the trusted set."""
        self.trusted_sources.add(source)
        logger.info("[ZeroTrust] trusted source added: %r", source)

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "scanned":         self._scan_count,
            "passed":          self._passed,
            "blocked":         self._blocked,
            "trusted_sources": list(self.trusted_sources),
            "strict":          self.strict,
        }
