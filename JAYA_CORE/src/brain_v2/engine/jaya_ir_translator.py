"""Phase 1 — Translate Lingua Logica expressions into JayaIR graphs."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from src.brain_v2.engine.jaya_ir import IRInstruction, JayaIRGraph, OpCode
from src.brain_v2.soul.lingua_logica import LinguaLogica, LogicExpr

_ACTION_TO_OPCODE: Dict[str, OpCode] = {
    "OPEN": OpCode.ACTION_OPEN,
    "CLOSE": OpCode.ACTION_CLOSE,
    "START": OpCode.ACTION_START,
    "STOP": OpCode.ACTION_STOP,
    "CREATE": OpCode.ACTION_CREATE,
    "EDIT": OpCode.ACTION_EDIT,
    "DELETE": OpCode.ACTION_DELETE,
    "SHOW": OpCode.ACTION_SHOW,
    "HIDE": OpCode.ACTION_HIDE,
    "MOVE": OpCode.ACTION_MOVE,
    "COPY": OpCode.ACTION_COPY,
    "RESET": OpCode.ACTION_RESET,
    "HELP": OpCode.ACTION_HELP,
    "SEARCH": OpCode.ACTION_SEARCH,
    "LIST": OpCode.ACTION_LIST,
    "TRANSLATE": OpCode.ACTION_TRANSLATE,
}

_ARITH_TO_OPCODE: Dict[str, OpCode] = {
    "ADD": OpCode.ARITH_ADD,
    "SUB": OpCode.ARITH_SUB,
    "MUL": OpCode.ARITH_MUL,
    "DIV": OpCode.ARITH_DIV,
}


def _literal(value: Any) -> str:
    return str(value) if value is not None else ""


def logic_expr_to_ir(expr: LogicExpr) -> JayaIRGraph:
    instructions = []

    if not isinstance(expr, tuple) or not expr:
        instructions.append(
            IRInstruction(
                opcode=OpCode.PASS_LITERAL, args=(_literal(expr),), target="out"
            )
        )
        instructions.append(IRInstruction(opcode=OpCode.RETURN, args=("out",)))
        return JayaIRGraph(instructions=instructions, source="lingua")

    head = str(expr[0])

    if head == "ACTION":
        action = str(expr[1]) if len(expr) > 1 else "UNKNOWN"
        obj = _literal(expr[2]) if len(expr) > 2 else "target"
        opcode = _ACTION_TO_OPCODE.get(action)
        if opcode is None:
            capability_id = f"action.{action.casefold()}"
            payload = json.dumps(
                {"action": action, "target": obj},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            instructions.append(
                IRInstruction(
                    opcode=OpCode.CALL_CAPABILITY,
                    args=(capability_id, payload),
                    target="out",
                    metadata={"kind": "external_capability"},
                )
            )
        else:
            instructions.append(IRInstruction(opcode=opcode, args=(obj,), target="out"))
        instructions.append(IRInstruction(opcode=OpCode.RETURN, args=("out",)))
        return JayaIRGraph(instructions=instructions, source="lingua")

    if head == "QUERY":
        qtype = str(expr[1]) if len(expr) > 1 else "QUERY_DEF"
        payload = expr[2] if len(expr) > 2 else "unknown"

        if qtype == "ARITH" and isinstance(payload, tuple) and len(payload) == 3:
            arith_op = str(payload[0])
            left = payload[1]
            right = payload[2]
            op = _ARITH_TO_OPCODE.get(arith_op)
            instructions.append(
                IRInstruction(opcode=OpCode.LOAD_CONST, args=(left,), target="lhs")
            )
            instructions.append(
                IRInstruction(opcode=OpCode.LOAD_CONST, args=(right,), target="rhs")
            )
            if op is None:
                capability_id = f"math.{arith_op.casefold()}"
                capability_payload = json.dumps(
                    {"left": left, "right": right},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                instructions.append(
                    IRInstruction(
                        opcode=OpCode.CALL_CAPABILITY,
                        args=(capability_id, capability_payload),
                        target="out",
                        metadata={"kind": "external_capability"},
                    )
                )
            else:
                instructions.append(
                    IRInstruction(opcode=op, args=(left, right), target="out")
                )
            instructions.append(IRInstruction(opcode=OpCode.RETURN, args=("out",)))
            return JayaIRGraph(instructions=instructions, source="lingua")

        instructions.append(
            IRInstruction(
                opcode=OpCode.QUERY_INFO, args=(qtype, _literal(payload)), target="out"
            )
        )
        instructions.append(IRInstruction(opcode=OpCode.RETURN, args=("out",)))
        return JayaIRGraph(instructions=instructions, source="lingua")

    if head == "LITERAL":
        lit = _literal(expr[1]) if len(expr) > 1 else ""
        instructions.append(
            IRInstruction(opcode=OpCode.PASS_LITERAL, args=(lit,), target="out")
        )
        instructions.append(IRInstruction(opcode=OpCode.RETURN, args=("out",)))
        return JayaIRGraph(instructions=instructions, source="lingua")

    payload = json.dumps(
        {"expression": _literal(expr)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    instructions.append(
        IRInstruction(
            opcode=OpCode.CALL_CAPABILITY,
            args=("lingua.expression", payload),
            target="out",
            metadata={"kind": "external_capability"},
        )
    )
    instructions.append(IRInstruction(opcode=OpCode.RETURN, args=("out",)))
    return JayaIRGraph(instructions=instructions, source="lingua")


def text_to_ir(
    text: str, lingua: LinguaLogica | None = None
) -> Tuple[LogicExpr, JayaIRGraph]:
    adapter = lingua or LinguaLogica()
    expr = adapter.encode(text)
    return expr, logic_expr_to_ir(expr)


def logic_request_to_ir(
    *,
    request_id: str,
    facts: list[str],
    rules: list[dict[str, Any]],
    query: str,
) -> JayaIRGraph:
    """Translate the typed Pure Logic contract into immutable JayaIR."""
    payload = json.dumps(
        {
            "request_id": request_id,
            "facts": facts,
            "rules": rules,
            "query": query,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return JayaIRGraph(
        instructions=[
            IRInstruction(
                opcode=OpCode.CALL_CAPABILITY,
                args=("core.logic.evaluate", payload),
                target="logic_result",
            ),
            IRInstruction(opcode=OpCode.RETURN, args=("logic_result",)),
        ],
        source="lingua-pure-logic",
    )
