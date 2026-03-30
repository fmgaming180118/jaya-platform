"""Phase 1 — JayaIR schema and validation.

JayaIR is a typed intermediate representation used to execute common
intent plans with stable signatures and cache-friendly behavior.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

Primitive = Union[str, int, float, bool, None]

JAYA_IR_VERSION = "0.1"
JAYA_IR_PHASE_STATE = "phase1_frozen"


class ValidationMode(str, Enum):
    STRICT = "strict"
    LENIENT = "lenient"


class OpCode(str, Enum):
    # Core control flow
    NO_OP = "NO_OP"
    LOAD_CONST = "LOAD_CONST"
    LOAD_VAR = "LOAD_VAR"
    STORE_VAR = "STORE_VAR"
    BRANCH_IF = "BRANCH_IF"
    JUMP = "JUMP"
    RETURN = "RETURN"

    # Action/System operations
    ACTION_OPEN = "ACTION_OPEN"
    ACTION_CLOSE = "ACTION_CLOSE"
    ACTION_START = "ACTION_START"
    ACTION_STOP = "ACTION_STOP"
    ACTION_CREATE = "ACTION_CREATE"
    ACTION_EDIT = "ACTION_EDIT"
    ACTION_DELETE = "ACTION_DELETE"
    ACTION_SHOW = "ACTION_SHOW"
    ACTION_HIDE = "ACTION_HIDE"
    ACTION_MOVE = "ACTION_MOVE"
    ACTION_COPY = "ACTION_COPY"
    ACTION_RESET = "ACTION_RESET"
    ACTION_HELP = "ACTION_HELP"
    ACTION_SEARCH = "ACTION_SEARCH"
    ACTION_LIST = "ACTION_LIST"
    ACTION_TRANSLATE = "ACTION_TRANSLATE"

    # Arithmetic/Query operations
    QUERY_INFO = "QUERY_INFO"
    ARITH_ADD = "ARITH_ADD"
    ARITH_SUB = "ARITH_SUB"
    ARITH_MUL = "ARITH_MUL"
    ARITH_DIV = "ARITH_DIV"

    # Memory/Cache/interop operations
    CACHE_GET = "CACHE_GET"
    CACHE_PUT = "CACHE_PUT"
    MEMORY_TAG = "MEMORY_TAG"
    CALL_STUB = "CALL_STUB"
    PASS_LITERAL = "PASS_LITERAL"


@dataclass
class IRInstruction:
    opcode: Union[OpCode, str]
    args: Tuple[Primitive, ...] = ()
    target: Optional[str] = None
    executable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> Dict[str, Any]:
        opcode = self.opcode.value if isinstance(self.opcode, OpCode) else str(self.opcode)
        return {
            "opcode": opcode,
            "args": list(self.args),
            "target": self.target,
            "executable": self.executable,
            "metadata": self.metadata,
        }


@dataclass
class JayaIRGraph:
    instructions: List[IRInstruction]
    source: str = "unknown"
    version: str = JAYA_IR_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature: str = field(init=False)

    def __post_init__(self) -> None:
        self.signature = self.compute_signature()

    def compute_signature(self) -> str:
        payload = {
            "version": self.version,
            "source": self.source,
            "instructions": [ins.canonical() for ins in self.instructions],
            "metadata": self.metadata,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def refresh_signature(self) -> str:
        self.signature = self.compute_signature()
        return self.signature


@dataclass
class ValidationIssue:
    index: int
    message: str
    critical: bool = False


@dataclass
class ValidationReport:
    is_valid: bool
    has_critical: bool
    valid_instructions: int
    invalid_instructions: int
    issues: List[ValidationIssue] = field(default_factory=list)


def _looks_like_arith(opcode: OpCode) -> bool:
    return opcode in {
        OpCode.ARITH_ADD,
        OpCode.ARITH_SUB,
        OpCode.ARITH_MUL,
        OpCode.ARITH_DIV,
    }


def _validate_instruction(ins: IRInstruction, index: int) -> Optional[ValidationIssue]:
    if not isinstance(ins.args, tuple):
        return ValidationIssue(index=index, message="args must be tuple", critical=True)

    if isinstance(ins.opcode, OpCode):
        opcode = ins.opcode
    else:
        try:
            opcode = OpCode(str(ins.opcode))
        except ValueError:
            return ValidationIssue(index=index, message=f"unknown opcode: {ins.opcode}", critical=False)

    if _looks_like_arith(opcode):
        if len(ins.args) < 2:
            return ValidationIssue(index=index, message="arith opcode requires two operands", critical=True)
        if not all(isinstance(v, (int, float)) for v in ins.args[:2]):
            return ValidationIssue(index=index, message="arith operands must be numeric", critical=True)

    if opcode == OpCode.LOAD_CONST and ins.target is None:
        return ValidationIssue(index=index, message="LOAD_CONST requires target", critical=True)

    return None


def validate_graph(
    graph: JayaIRGraph,
    mode: ValidationMode = ValidationMode.STRICT,
) -> ValidationReport:
    issues: List[ValidationIssue] = []
    valid_count = 0

    if not graph.instructions:
        issues.append(ValidationIssue(index=-1, message="graph has no instructions", critical=True))

    for idx, ins in enumerate(graph.instructions):
        issue = _validate_instruction(ins, idx)
        if issue is None:
            if isinstance(ins.opcode, str) and not isinstance(ins.opcode, OpCode):
                try:
                    ins.opcode = OpCode(ins.opcode)
                except ValueError:
                    pass
            valid_count += 1
            continue

        issues.append(issue)
        if mode == ValidationMode.LENIENT and not issue.critical:
            ins.executable = False
            ins.metadata["validation_error"] = issue.message
            continue

    has_critical = any(i.critical for i in issues)
    if mode == ValidationMode.STRICT:
        is_valid = len(issues) == 0
    else:
        is_valid = not has_critical

    graph.refresh_signature()
    return ValidationReport(
        is_valid=is_valid,
        has_critical=has_critical,
        valid_instructions=valid_count,
        invalid_instructions=max(0, len(graph.instructions) - valid_count),
        issues=issues,
    )


def supported_opcodes() -> Sequence[str]:
    return [op.value for op in OpCode]


def contract_metadata() -> Dict[str, Any]:
    """Expose stable contract info for tests and governance docs."""
    return {
        "version": JAYA_IR_VERSION,
        "phase_state": JAYA_IR_PHASE_STATE,
        "opcode_count": len(list(OpCode)),
        "opcodes": supported_opcodes(),
    }
