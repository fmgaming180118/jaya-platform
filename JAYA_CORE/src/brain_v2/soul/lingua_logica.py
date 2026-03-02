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

import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("LinguaLogica")

# Type alias for S-expression trees
LogicExpr = Union[str, int, float, Tuple[Any, ...]]


# ---------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------

_ACTION_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(turn|switch)\s+off\b", re.I), "TURN_OFF"),
    (re.compile(r"\b(turn|switch)\s+on\b",  re.I), "TURN_ON"),
    (re.compile(r"\b(stop|halt|pause)\b",    re.I), "STOP"),
    (re.compile(r"\b(start|begin|run)\b",    re.I), "START"),
    (re.compile(r"\b(search|find|look)\b",   re.I), "SEARCH"),
    (re.compile(r"\b(delete|remove)\b",      re.I), "DELETE"),
    (re.compile(r"\b(open|launch)\b",        re.I), "OPEN"),
    (re.compile(r"\b(close|quit|exit)\b",    re.I), "CLOSE"),
    (re.compile(r"\b(greet|hello|hi)\b",     re.I), "GREET"),
    (re.compile(r"\b(sleep|rest|idle)\b",    re.I), "SLEEP"),
]

_QUERY_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(what\s+is|what's)\b",  re.I), "QUERY_DEF"),
    (re.compile(r"\b(how\s+(do|to|can))\b", re.I), "QUERY_HOW"),
    (re.compile(r"\bwhy\b",                  re.I), "QUERY_WHY"),
    (re.compile(r"\bwhen\b",                 re.I), "QUERY_WHEN"),
    (re.compile(r"\bwhere\b",                re.I), "QUERY_WHERE"),
    (re.compile(r"\bwho\b",                  re.I), "QUERY_WHO"),
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

    def __init__(self, cache_size: int = 256):
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
