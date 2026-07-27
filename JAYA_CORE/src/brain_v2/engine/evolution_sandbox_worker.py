"""Isolated worker for evolution experiments.

This module is launched with ``python -I -S`` by :mod:`evolution_sandbox`.
It must remain standard-library only and must never be imported by candidate
code.
"""

from __future__ import annotations

import ast
import json
import math
import os
import sys
from collections.abc import Mapping
from typing import Any

_MAX_INPUT_BYTES = 65_536
_MAX_AST_NODES = 256
_MAX_COLLECTION_ITEMS = 256
_MAX_STRING_CHARS = 4_096
_MAX_RESULT_DEPTH = 6

_SAFE_CALLS: Mapping[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}

_EXPERIMENT_NODES = (
    ast.Module,
    ast.Assign,
    ast.Expr,
    ast.If,
    ast.Pass,
    ast.Name,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Subscript,
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.keyword,
    ast.Load,
    ast.Store,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


class PolicyViolation(ValueError):
    """Raised when candidate AST exceeds the sandbox policy."""


class _ExperimentPolicy(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> Any:
        if not isinstance(node, _EXPERIMENT_NODES):
            raise PolicyViolation(f"AST node is not allowed: {type(node).__name__}")
        return super().visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_"):
            raise PolicyViolation("private and dunder names are forbidden")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not node.targets or not all(
            isinstance(target, ast.Name) for target in node.targets
        ):
            raise PolicyViolation("assignment targets must be simple names")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_CALLS:
            raise PolicyViolation("call target is not in the safe API allowlist")
        self.generic_visit(node)


def _set_posix_resource_limits(memory_limit_mb: int, cpu_time_s: int) -> None:
    try:
        import resource
    except ImportError:
        if os.name == "posix":
            raise PolicyViolation(
                "POSIX resource limits are unavailable; sandbox fails closed"
            )
        return

    memory_bytes = max(32, int(memory_limit_mb)) * 1024 * 1024
    cpu_seconds = max(1, int(cpu_time_s))
    required_limits = (
        (resource.RLIMIT_AS, memory_bytes),
        (resource.RLIMIT_CPU, cpu_seconds),
    )
    optional_limits = (
        (resource.RLIMIT_FSIZE, 0),
        (resource.RLIMIT_NOFILE, 8),
    )
    for resource_id, value in required_limits:
        try:
            resource.setrlimit(resource_id, (value, value))
        except (OSError, ValueError) as exc:
            raise PolicyViolation(
                f"required POSIX resource limit failed: {exc}"
            ) from exc
    for resource_id, value in optional_limits:
        try:
            resource.setrlimit(resource_id, (value, value))
        except (OSError, ValueError):
            continue


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_RESULT_DEPTH:
        raise PolicyViolation("result nesting exceeds sandbox limit")
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > _MAX_STRING_CHARS:
            raise PolicyViolation("result string exceeds sandbox limit")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PolicyViolation("non-finite result values are forbidden")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise PolicyViolation("result collection exceeds sandbox limit")
        return [_sanitize(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise PolicyViolation("result mapping exceeds sandbox limit")
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key.startswith("_"):
                raise PolicyViolation("result keys must be public strings")
            clean[key] = _sanitize(item, depth=depth + 1)
        return clean
    raise PolicyViolation(f"result type is not serializable: {type(value).__name__}")


def _parse(code: str) -> ast.Module:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise PolicyViolation(f"candidate syntax error: {exc.msg}") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise PolicyViolation("candidate AST exceeds node limit")
    return tree


def _run_experiment(code: str) -> dict[str, Any]:
    tree = _parse(code)
    _ExperimentPolicy().visit(tree)
    compiled = compile(tree, "<jaya-evolution-sandbox>", "exec", dont_inherit=True)
    globals_ns = {"__builtins__": dict(_SAFE_CALLS)}
    locals_ns: dict[str, Any] = {}
    exec(compiled, globals_ns, locals_ns)
    outcome = {
        key: _sanitize(value)
        for key, value in locals_ns.items()
        if not key.startswith("_")
    }
    return {"ok": True, "outcome": outcome}


def _literal_default(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError) as exc:
        raise PolicyViolation("function defaults must be literals") from exc


def _validate_morphic(code: str, expected_function: str) -> dict[str, Any]:
    tree = _parse(code)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise PolicyViolation("morphic candidate must define exactly one function")

    function = tree.body[0]
    if function.name != expected_function:
        raise PolicyViolation("morphic function name does not match target")
    if function.decorator_list:
        raise PolicyViolation("morphic decorators are forbidden")
    if function.args.vararg is not None or function.args.kwarg is not None:
        raise PolicyViolation("variadic morphic functions are forbidden")
    for default in [*function.args.defaults, *function.args.kw_defaults]:
        if default is not None:
            _literal_default(default)

    body = list(function.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body.pop(0)
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        raise PolicyViolation(
            "morphic safe API currently supports one literal return only"
        )
    if body[0].value is None:
        return_value = None
    else:
        try:
            return_value = ast.literal_eval(body[0].value)
        except (ValueError, TypeError) as exc:
            raise PolicyViolation(
                "morphic return value must be a JSON-compatible literal"
            ) from exc

    return {
        "ok": True,
        "function_spec": {
            "kind": "constant_return",
            "name": function.name,
            "value": _sanitize(return_value),
        },
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "failure": {
            "code": code,
            "message": message,
        },
    }


def main() -> int:
    raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if len(raw) > _MAX_INPUT_BYTES:
        response = _failure("input_limit", "sandbox request exceeds input limit")
    else:
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise PolicyViolation("sandbox request must be an object")
            _set_posix_resource_limits(
                int(request.get("memory_limit_mb", 128)),
                int(request.get("cpu_time_s", 1)),
            )
            code = request.get("code")
            mode = request.get("mode")
            if not isinstance(code, str):
                raise PolicyViolation("candidate code must be a string")
            if mode == "experiment":
                response = _run_experiment(code)
            elif mode == "morphic":
                expected = request.get("expected_function")
                if not isinstance(expected, str) or not expected.isidentifier():
                    raise PolicyViolation("expected morphic function is invalid")
                response = _validate_morphic(code, expected)
            else:
                raise PolicyViolation("unsupported sandbox mode")
        except PolicyViolation as exc:
            response = _failure("policy_rejected", str(exc))
        except MemoryError:
            response = _failure(
                "resource_limit",
                "candidate exceeded sandbox memory limit",
            )
        except BaseException as exc:
            response = _failure(
                "execution_error",
                f"{type(exc).__name__}: {exc}",
            )

    response["worker_pid"] = os.getpid()
    encoded = json.dumps(
        response,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
