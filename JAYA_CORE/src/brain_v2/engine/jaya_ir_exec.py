"""Phase 1 — JayaIR executor with bounded cache and latency metrics."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from src.brain_v2.engine.jaya_ir import (
    JayaIRGraph,
    OpCode,
    ValidationMode,
    validate_graph,
)
from src.brain_v2.engine.jaya_ir_translator import logic_expr_to_ir
from src.brain_v2.soul.lingua_logica import LogicExpr


@dataclass
class _CacheEntry:
    ts: float
    fn: Callable[[], Any]


class JayaIRExecutor:
    def __init__(self, cache_size: int = 256, ttl_s: float = 300.0, mode: ValidationMode = ValidationMode.LENIENT):
        self.cache_size = max(1, int(cache_size))
        self.ttl_s = float(ttl_s)
        self.mode = mode
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._executions = 0
        self._last_latency_ms = 0.0

    def clear_cache(self) -> None:
        self._cache.clear()

    def _evict_if_needed(self) -> None:
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _get_cached(self, key: str, count_miss: bool = True) -> Optional[Callable[[], Any]]:
        entry = self._cache.get(key)
        now = time.time()
        if entry is None:
            if count_miss:
                self._misses += 1
            return None
        if now - entry.ts > self.ttl_s:
            self._cache.pop(key, None)
            if count_miss:
                self._misses += 1
            return None
        self._hits += 1
        self._cache.move_to_end(key)
        return entry.fn

    def _put_cached(self, key: str, fn: Callable[[], Any]) -> None:
        self._cache[key] = _CacheEntry(ts=time.time(), fn=fn)
        self._cache.move_to_end(key)
        self._evict_if_needed()

    def _resolve(self, state: Dict[str, Any], token: Any) -> Any:
        if isinstance(token, str) and token in state:
            return state[token]
        return token

    def _execute_instruction(self, state: Dict[str, Any], ins: Any) -> Tuple[bool, Any]:
        if not getattr(ins, "executable", True):
            return False, None

        opcode = ins.opcode
        if not isinstance(opcode, OpCode):
            opcode = OpCode(str(opcode))

        args = tuple(ins.args)
        target = ins.target

        if opcode == OpCode.NO_OP:
            return False, None

        if opcode == OpCode.LOAD_CONST:
            if target is not None:
                state[target] = args[0] if args else None
            return False, None

        if opcode == OpCode.PASS_LITERAL:
            val = args[0] if args else ""
            if target is not None:
                state[target] = val
            return False, val

        if opcode == OpCode.QUERY_INFO:
            qtype = str(args[0]) if len(args) > 0 else "QUERY"
            subject = self._resolve(state, args[1]) if len(args) > 1 else "unknown"
            out = {"query_type": qtype, "subject": subject}
            if target is not None:
                state[target] = out
            return False, out

        if opcode in (OpCode.ARITH_ADD, OpCode.ARITH_SUB, OpCode.ARITH_MUL, OpCode.ARITH_DIV):
            a = self._resolve(state, args[0]) if len(args) > 0 else 0
            b = self._resolve(state, args[1]) if len(args) > 1 else 0
            if opcode == OpCode.ARITH_ADD:
                out = a + b
            elif opcode == OpCode.ARITH_SUB:
                out = a - b
            elif opcode == OpCode.ARITH_MUL:
                out = a * b
            else:
                out = a / b if b != 0 else float("inf")
            if target is not None:
                state[target] = out
            return False, out

        if opcode.name.startswith("ACTION_"):
            obj = self._resolve(state, args[0]) if args else "target"
            out = {"action": opcode.name.replace("ACTION_", "").lower(), "target": obj}
            if target is not None:
                state[target] = out
            return False, out

        if opcode == OpCode.CALL_STUB:
            out = {
                "stub": True,
                "name": self._resolve(state, args[0]) if args else "stub",
                "args": [self._resolve(state, a) for a in args[1:]],
            }
            if target is not None:
                state[target] = out
            return False, out

        if opcode == OpCode.RETURN:
            if args:
                return True, self._resolve(state, args[0])
            return True, state.get(target)

        return False, None

    def _compile(self, graph: JayaIRGraph) -> Callable[[], Any]:
        def _plan() -> Any:
            state: Dict[str, Any] = {}
            last: Any = None
            for ins in graph.instructions:
                should_return, value = self._execute_instruction(state, ins)
                if value is not None:
                    last = value
                if should_return:
                    return value
            return last

        return _plan

    def execute_graph(self, graph: JayaIRGraph) -> Dict[str, Any]:
        t0 = time.perf_counter()
        # Fast path: if the graph signature already has a compiled callable,
        # execute immediately and skip validation work on hot repeats.
        initial_key = graph.signature
        cached = self._get_cached(initial_key)
        if cached is not None:
            result = cached()
            self._executions += 1
            self._last_latency_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "ok": True,
                "result": result,
                "signature": initial_key,
                "cache_hit": True,
                "latency_ms": round(self._last_latency_ms, 4),
                "issues": [],
            }

        report = validate_graph(graph, mode=self.mode)
        if not report.is_valid:
            return {
                "ok": False,
                "error": "validation_failed",
                "issues": [i.message for i in report.issues],
                "critical": report.has_critical,
            }

        key = graph.signature
        fn = self._get_cached(key, count_miss=False)
        cache_hit = fn is not None
        if fn is None:
            fn = self._compile(graph)
            self._put_cached(key, fn)

        result = fn()
        self._executions += 1
        self._last_latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "ok": True,
            "result": result,
            "signature": key,
            "cache_hit": cache_hit,
            "latency_ms": round(self._last_latency_ms, 4),
            "issues": [i.message for i in report.issues],
        }

    def execute_logic_expr(self, expr: LogicExpr) -> Dict[str, Any]:
        graph = logic_expr_to_ir(expr)
        output = self.execute_graph(graph)
        output["graph"] = graph
        return output

    def status(self) -> Dict[str, Any]:
        total_lookups = self._hits + self._misses
        hit_rate = (self._hits / total_lookups) if total_lookups else 0.0
        return {
            "mode": self.mode.value,
            "cache_size": len(self._cache),
            "cache_capacity": self.cache_size,
            "ttl_s": self.ttl_s,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "executions": self._executions,
            "last_latency_ms": round(self._last_latency_ms, 4),
        }
