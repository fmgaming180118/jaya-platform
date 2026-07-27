"""Strict JayaIR executor with immutable, integrity-checked cache plans."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from src.brain_v2.engine.jaya_ir import (
    IRFailureCode,
    JayaIRGraph,
    OpCode,
    ValidationIssue,
    ValidationMode,
    validate_graph,
)
from src.brain_v2.engine.jaya_ir_translator import logic_expr_to_ir
from src.brain_v2.soul.lingua_logica import LogicExpr


@dataclass
class _CacheEntry:
    ts: float
    fn: Callable[[], Any]


@dataclass(frozen=True)
class _Step:
    next_pc: int
    value: Any = None
    returned: bool = False


@dataclass(frozen=True)
class _CompiledInstruction:
    opcode: OpCode
    args: tuple[Any, ...]
    target: Optional[str]


class _IRExecutionFailure(RuntimeError):
    def __init__(
        self,
        code: IRFailureCode,
        message: str,
        *,
        instruction_index: int,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.instruction_index = instruction_index
        self.details = dict(details or {})


class JayaIRExecutor:
    def __init__(
        self,
        cache_size: int = 256,
        ttl_s: float = 300.0,
        mode: ValidationMode = ValidationMode.STRICT,
    ) -> None:
        self.cache_size = max(1, int(cache_size))
        self.ttl_s = float(ttl_s)
        self.mode = mode
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._logic_graph_cache: OrderedDict[Any, JayaIRGraph] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._executions = 0
        self._last_latency_ms = 0.0

    def clear_cache(self) -> None:
        self._cache.clear()
        self._logic_graph_cache.clear()

    def _evict_if_needed(self) -> None:
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _get_cached(self, key: str) -> Optional[Callable[[], Any]]:
        entry = self._cache.get(key)
        now = time.time()
        if entry is None:
            self._misses += 1
            return None
        if now - entry.ts > self.ttl_s:
            self._cache.pop(key, None)
            self._misses += 1
            return None
        self._hits += 1
        self._cache.move_to_end(key)
        return entry.fn

    def _put_cached(self, key: str, fn: Callable[[], Any]) -> None:
        self._cache[key] = _CacheEntry(ts=time.time(), fn=fn)
        self._cache.move_to_end(key)
        self._evict_if_needed()

    @staticmethod
    def _resolve(state: Dict[str, Any], token: Any) -> Any:
        if isinstance(token, str) and token in state:
            return state[token]
        return token

    def _execute_instruction(
        self,
        state: Dict[str, Any],
        instruction: _CompiledInstruction,
        index: int,
    ) -> _Step:
        opcode = instruction.opcode
        if not isinstance(opcode, OpCode):
            raise _IRExecutionFailure(
                IRFailureCode.UNKNOWN_OPCODE,
                f"unknown opcode: {opcode}",
                instruction_index=index,
            )

        args = instruction.args
        target = instruction.target
        next_pc = index + 1

        if opcode == OpCode.NO_OP:
            return _Step(next_pc=next_pc)
        if opcode == OpCode.LOAD_CONST:
            state[str(target)] = args[0]
            return _Step(next_pc=next_pc)
        if opcode == OpCode.LOAD_VAR:
            source = str(args[0])
            if source not in state:
                raise _IRExecutionFailure(
                    IRFailureCode.TYPE_MISMATCH,
                    f"variable is not defined: {source}",
                    instruction_index=index,
                    details={"variable": source},
                )
            state[str(target)] = state[source]
            return _Step(next_pc=next_pc)
        if opcode == OpCode.STORE_VAR:
            state[str(target)] = self._resolve(state, args[0])
            return _Step(next_pc=next_pc)
        if opcode == OpCode.PASS_LITERAL:
            value = args[0]
            state[str(target)] = value
            return _Step(next_pc=next_pc, value=value)
        if opcode == OpCode.JUMP:
            return _Step(next_pc=int(args[0]))
        if opcode == OpCode.BRANCH_IF:
            condition = self._resolve(state, args[0])
            if not isinstance(condition, bool):
                raise _IRExecutionFailure(
                    IRFailureCode.TYPE_MISMATCH,
                    "BRANCH_IF condition must resolve to boolean",
                    instruction_index=index,
                )
            return _Step(
                next_pc=int(args[1] if condition else args[2])
            )
        if opcode == OpCode.QUERY_INFO:
            query_type = str(args[0])
            subject = self._resolve(state, args[1])
            output = {
                "query_type": query_type,
                "subject": subject,
            }
            if target is not None:
                state[target] = output
            return _Step(next_pc=next_pc, value=output)
        if opcode in {
            OpCode.ARITH_ADD,
            OpCode.ARITH_SUB,
            OpCode.ARITH_MUL,
            OpCode.ARITH_DIV,
        }:
            left = self._resolve(state, args[0])
            right = self._resolve(state, args[1])
            if (
                isinstance(left, bool)
                or isinstance(right, bool)
                or not isinstance(left, (int, float))
                or not isinstance(right, (int, float))
            ):
                raise _IRExecutionFailure(
                    IRFailureCode.TYPE_MISMATCH,
                    "arithmetic operands must resolve to numbers",
                    instruction_index=index,
                )
            if opcode == OpCode.ARITH_DIV and right == 0:
                raise _IRExecutionFailure(
                    IRFailureCode.DIVIDE_BY_ZERO,
                    "division by zero is forbidden",
                    instruction_index=index,
                )
            try:
                if opcode == OpCode.ARITH_ADD:
                    output = left + right
                elif opcode == OpCode.ARITH_SUB:
                    output = left - right
                elif opcode == OpCode.ARITH_MUL:
                    output = left * right
                else:
                    output = left / right
            except (ArithmeticError, OverflowError, TypeError) as exc:
                raise _IRExecutionFailure(
                    IRFailureCode.EXECUTION_ERROR,
                    f"arithmetic execution failed: {exc}",
                    instruction_index=index,
                ) from exc
            if target is not None:
                state[target] = output
            return _Step(next_pc=next_pc, value=output)
        if opcode.name.startswith("ACTION_"):
            object_value = self._resolve(state, args[0])
            output = {
                "action": opcode.name.replace("ACTION_", "").lower(),
                "target": object_value,
            }
            if target is not None:
                state[target] = output
            return _Step(next_pc=next_pc, value=output)
        if opcode == OpCode.RETURN:
            value = (
                self._resolve(state, args[0])
                if args
                else state.get(str(target))
            )
            return _Step(next_pc=next_pc, value=value, returned=True)

        raise _IRExecutionFailure(
            IRFailureCode.UNSUPPORTED_OPCODE,
            f"opcode has no executable contract: {opcode.value}",
            instruction_index=index,
            details={"opcode": opcode.value},
        )

    def _compile(self, graph: JayaIRGraph) -> Callable[[], Any]:
        program = tuple(
            _CompiledInstruction(
                opcode=instruction.opcode,
                args=tuple(instruction.args),
                target=instruction.target,
            )
            for instruction in graph.instructions
            if isinstance(instruction.opcode, OpCode)
        )
        if len(program) != len(graph.instructions):
            raise _IRExecutionFailure(
                IRFailureCode.UNKNOWN_OPCODE,
                "validated graph contains non-enum opcode",
                instruction_index=-1,
            )
        max_steps = max(1, len(program) + 1)

        def _plan() -> Any:
            state: Dict[str, Any] = {}
            pc = 0
            steps = 0
            while True:
                if steps >= max_steps:
                    raise _IRExecutionFailure(
                        IRFailureCode.EXECUTION_LIMIT,
                        "JayaIR execution exceeded bounded step count",
                        instruction_index=pc,
                    )
                if pc < 0 or pc >= len(program):
                    raise _IRExecutionFailure(
                        IRFailureCode.INVALID_CFG,
                        f"program counter escaped graph: {pc}",
                        instruction_index=pc,
                    )
                step = self._execute_instruction(state, program[pc], pc)
                steps += 1
                if step.returned:
                    return step.value
                pc = step.next_pc

        return _plan

    def execute_graph(self, graph: JayaIRGraph) -> Dict[str, Any]:
        started = time.perf_counter()
        was_sealed = graph.is_sealed
        initial_key = graph.signature
        key = initial_key
        # Cache entries contain detached immutable instructions. A stale or
        # force-mutated graph can therefore only select the already-validated
        # plan identified by its old digest; its mutation is never executed.
        function = self._get_cached(key) if was_sealed else None
        cache_hit = function is not None

        if function is None:
            report = validate_graph(graph, mode=self.mode)
            if not report.is_valid:
                self._last_latency_ms = (
                    time.perf_counter() - started
                ) * 1_000.0
                primary = (
                    report.issues[0]
                    if report.issues
                    else ValidationIssue(
                        index=-1,
                        message="JayaIR validation failed",
                    )
                )
                return self._validation_failure(primary, report.issues)

            key = graph.signature
            if not was_sealed:
                function = self._get_cached(key)
                cache_hit = function is not None
        if function is None:
            function = self._compile(graph)
            self._put_cached(key, function)

        try:
            result = function()
        except _IRExecutionFailure as exc:
            self._last_latency_ms = (time.perf_counter() - started) * 1_000.0
            return {
                "ok": False,
                "error": exc.code.value,
                "failure": {
                    "code": exc.code.value,
                    "message": str(exc),
                    "instruction_index": exc.instruction_index,
                    "details": dict(exc.details),
                },
                "signature": key,
                "cache_hit": cache_hit,
                "latency_ms": round(self._last_latency_ms, 4),
                "issues": [],
            }
        except Exception as exc:
            self._last_latency_ms = (time.perf_counter() - started) * 1_000.0
            return {
                "ok": False,
                "error": IRFailureCode.EXECUTION_ERROR.value,
                "failure": {
                    "code": IRFailureCode.EXECUTION_ERROR.value,
                    "message": f"{type(exc).__name__}: {exc}",
                    "instruction_index": -1,
                    "details": {},
                },
                "signature": key,
                "cache_hit": cache_hit,
                "latency_ms": round(self._last_latency_ms, 4),
                "issues": [],
            }

        self._executions += 1
        self._last_latency_ms = (time.perf_counter() - started) * 1_000.0
        return {
            "ok": True,
            "result": result,
            "signature": key,
            "cache_hit": cache_hit,
            "latency_ms": round(self._last_latency_ms, 4),
            "issues": [],
        }

    def _validation_failure(
        self,
        primary: ValidationIssue,
        issues: Sequence[ValidationIssue],
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": primary.code.value,
            "failure": {
                "code": primary.code.value,
                "message": primary.message,
                "instruction_index": primary.index,
                "details": dict(primary.details),
            },
            "issues": [issue.message for issue in issues],
            "issue_details": [
                {
                    "code": issue.code.value,
                    "message": issue.message,
                    "instruction_index": issue.index,
                    "details": dict(issue.details),
                }
                for issue in issues
            ],
            "critical": True,
            "latency_ms": round(self._last_latency_ms, 4),
        }

    def execute_logic_expr(self, expr: LogicExpr) -> Dict[str, Any]:
        try:
            hash(expr)
            expression_key: Any = expr
        except TypeError:
            expression_key = repr(expr)
        graph = self._logic_graph_cache.get(expression_key)
        if graph is None:
            graph = logic_expr_to_ir(expr)
        else:
            self._logic_graph_cache.move_to_end(expression_key)
        output = self.execute_graph(graph)
        if output.get("ok") and graph.is_sealed:
            self._logic_graph_cache[expression_key] = graph
            self._logic_graph_cache.move_to_end(expression_key)
            while len(self._logic_graph_cache) > self.cache_size:
                self._logic_graph_cache.popitem(last=False)
        output["graph"] = graph
        return output

    def status(self) -> Dict[str, Any]:
        total_lookups = self._hits + self._misses
        hit_rate = (
            self._hits / total_lookups
            if total_lookups
            else 0.0
        )
        return {
            "mode": self.mode.value,
            "cache_size": len(self._cache),
            "cache_capacity": self.cache_size,
            "logic_graph_cache_size": len(self._logic_graph_cache),
            "ttl_s": self.ttl_s,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "executions": self._executions,
            "last_latency_ms": round(self._last_latency_ms, 4),
        }
