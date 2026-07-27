"""Phase 1 — strict, immutable JayaIR schema and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

Primitive = Union[str, int, float, bool, None]

JAYA_IR_VERSION = "0.1"
JAYA_IR_PHASE_STATE = "phase1_frozen"


class ValidationMode(str, Enum):
    STRICT = "strict"
    LENIENT = "lenient"


class IRFailureCode(str, Enum):
    VALIDATION_FAILED = "validation_failed"
    UNKNOWN_OPCODE = "unknown_opcode"
    UNSUPPORTED_OPCODE = "unsupported_opcode"
    INVALID_ARGUMENTS = "invalid_arguments"
    INVALID_CFG = "invalid_cfg"
    DIVIDE_BY_ZERO = "divide_by_zero"
    IR_MUTATION = "ir_mutation"
    TYPE_MISMATCH = "type_mismatch"
    EXECUTION_LIMIT = "execution_limit"
    EXECUTION_ERROR = "execution_error"


class IRMutationError(RuntimeError):
    """Raised when a validated JayaIR object is mutated."""


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

    # Reserved memory/cache/interop operations. They remain in the schema for
    # compatibility but are rejected until typed runtime semantics exist.
    CACHE_GET = "CACHE_GET"
    CACHE_PUT = "CACHE_PUT"
    MEMORY_TAG = "MEMORY_TAG"
    CALL_STUB = "CALL_STUB"
    PASS_LITERAL = "PASS_LITERAL"


_ACTION_OPCODES = frozenset(
    opcode for opcode in OpCode if opcode.name.startswith("ACTION_")
)
_ARITH_OPCODES = frozenset(
    {
        OpCode.ARITH_ADD,
        OpCode.ARITH_SUB,
        OpCode.ARITH_MUL,
        OpCode.ARITH_DIV,
    }
)
_UNSUPPORTED_OPCODES = frozenset(
    {
        OpCode.CACHE_GET,
        OpCode.CACHE_PUT,
        OpCode.MEMORY_TAG,
        OpCode.CALL_STUB,
    }
)
_SUPPORTED_OPCODES = frozenset(OpCode) - _UNSUPPORTED_OPCODES
_MUTABLE_INSTRUCTION_FIELDS = {
    "opcode",
    "args",
    "target",
    "executable",
    "metadata",
}
_MUTABLE_GRAPH_FIELDS = {
    "instructions",
    "source",
    "version",
    "metadata",
    "signature",
}


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise TypeError("non-finite values are forbidden in JayaIR")
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JayaIR metadata keys must be strings")
            clean[key] = _canonical_value(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported JayaIR value: {type(value).__name__}")


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_value(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


@dataclass
class IRInstruction:
    opcode: Union[OpCode, str]
    args: Tuple[Primitive, ...] = ()
    target: Optional[str] = None
    executable: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)
    _sealed: bool = field(default=False, init=False, repr=False, compare=False)

    def __setattr__(self, name: str, value: Any) -> None:
        if (
            name in _MUTABLE_INSTRUCTION_FIELDS
            and getattr(self, "_sealed", False)
        ):
            raise IRMutationError("validated IRInstruction is immutable")
        object.__setattr__(self, name, value)

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    def canonical(self) -> Dict[str, Any]:
        opcode = (
            self.opcode.value
            if isinstance(self.opcode, OpCode)
            else str(self.opcode)
        )
        return {
            "opcode": opcode,
            "args": _canonical_value(self.args),
            "target": self.target,
            "executable": self.executable,
            "metadata": _canonical_value(self.metadata),
        }

    def seal(self) -> None:
        if self._sealed:
            return
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))
        object.__setattr__(self, "_sealed", True)


@dataclass
class JayaIRGraph:
    instructions: Sequence[IRInstruction]
    source: str = "unknown"
    version: str = JAYA_IR_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)
    signature: str = field(init=False)
    _sealed: bool = field(default=False, init=False, repr=False, compare=False)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _MUTABLE_GRAPH_FIELDS and getattr(self, "_sealed", False):
            raise IRMutationError("validated JayaIRGraph is immutable")
        object.__setattr__(self, name, value)

    def __post_init__(self) -> None:
        self.signature = self.compute_signature()

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    def compute_signature(self) -> str:
        payload = {
            "version": self.version,
            "source": self.source,
            "instructions": [
                instruction.canonical()
                for instruction in self.instructions
            ],
            "metadata": _canonical_value(self.metadata),
        }
        blob = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def refresh_signature(self) -> str:
        if self._sealed:
            raise IRMutationError("cannot refresh a sealed JayaIRGraph")
        self.signature = self.compute_signature()
        return self.signature

    def seal(self) -> None:
        if self._sealed:
            return
        for instruction in self.instructions:
            instruction.seal()
        object.__setattr__(self, "instructions", tuple(self.instructions))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))
        object.__setattr__(self, "signature", self.compute_signature())
        object.__setattr__(self, "_sealed", True)

    def has_valid_integrity(self) -> bool:
        return (
            self._sealed
            and all(instruction.is_sealed for instruction in self.instructions)
            and self.compute_signature() == self.signature
        )


@dataclass(frozen=True)
class ValidationIssue:
    index: int
    message: str
    code: IRFailureCode = IRFailureCode.VALIDATION_FAILED
    critical: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationReport:
    is_valid: bool
    has_critical: bool
    valid_instructions: int
    invalid_instructions: int
    issues: Sequence[ValidationIssue] = field(default_factory=tuple)


def _issue(
    index: int,
    message: str,
    code: IRFailureCode,
    **details: Any,
) -> ValidationIssue:
    return ValidationIssue(
        index=index,
        message=message,
        code=code,
        critical=True,
        details=MappingProxyType(dict(details)),
    )


def _is_public_variable(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.isidentifier()
        and not value.startswith("_")
    )


def _validate_instruction(
    instruction: IRInstruction,
    index: int,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not isinstance(instruction, IRInstruction):
        return [
            _issue(
                index,
                "instruction must be IRInstruction",
                IRFailureCode.INVALID_ARGUMENTS,
            )
        ]
    if not isinstance(instruction.args, tuple):
        return [
            _issue(
                index,
                "args must be tuple",
                IRFailureCode.INVALID_ARGUMENTS,
            )
        ]
    if not instruction.executable:
        issues.append(
            _issue(
                index,
                "disabled instructions are not executable contracts",
                IRFailureCode.UNSUPPORTED_OPCODE,
            )
        )

    if isinstance(instruction.opcode, OpCode):
        opcode = instruction.opcode
    else:
        try:
            opcode = OpCode(str(instruction.opcode))
            instruction.opcode = opcode
        except ValueError:
            return [
                _issue(
                    index,
                    f"unknown opcode: {instruction.opcode}",
                    IRFailureCode.UNKNOWN_OPCODE,
                    opcode=str(instruction.opcode),
                )
            ]

    if opcode in _UNSUPPORTED_OPCODES:
        issues.append(
            _issue(
                index,
                f"opcode has no executable contract: {opcode.value}",
                IRFailureCode.UNSUPPORTED_OPCODE,
                opcode=opcode.value,
            )
        )
        return issues

    if instruction.target is not None and not _is_public_variable(
        instruction.target
    ):
        issues.append(
            _issue(
                index,
                "target must be a public variable identifier",
                IRFailureCode.INVALID_ARGUMENTS,
            )
        )

    args = instruction.args
    if opcode == OpCode.NO_OP and args:
        issues.append(
            _issue(
                index,
                "NO_OP does not accept arguments",
                IRFailureCode.INVALID_ARGUMENTS,
            )
        )
    elif opcode in {OpCode.LOAD_CONST, OpCode.PASS_LITERAL}:
        if len(args) != 1 or instruction.target is None:
            issues.append(
                _issue(
                    index,
                    f"{opcode.value} requires one value and target",
                    IRFailureCode.INVALID_ARGUMENTS,
                )
            )
    elif opcode in {OpCode.LOAD_VAR, OpCode.STORE_VAR}:
        if (
            len(args) != 1
            or instruction.target is None
            or (
                opcode == OpCode.LOAD_VAR
                and not _is_public_variable(args[0])
            )
        ):
            issues.append(
                _issue(
                    index,
                    f"{opcode.value} requires one source and target",
                    IRFailureCode.INVALID_ARGUMENTS,
                )
            )
    elif opcode == OpCode.JUMP:
        if (
            len(args) != 1
            or isinstance(args[0], bool)
            or not isinstance(args[0], int)
        ):
            issues.append(
                _issue(
                    index,
                    "JUMP requires one integer instruction index",
                    IRFailureCode.INVALID_CFG,
                )
            )
    elif opcode == OpCode.BRANCH_IF:
        if (
            len(args) != 3
            or any(
                isinstance(target, bool) or not isinstance(target, int)
                for target in args[1:]
            )
        ):
            issues.append(
                _issue(
                    index,
                    "BRANCH_IF requires condition, true index, false index",
                    IRFailureCode.INVALID_CFG,
                )
            )
    elif opcode == OpCode.RETURN:
        if len(args) > 1 or (not args and instruction.target is None):
            issues.append(
                _issue(
                    index,
                    "RETURN requires one value or target",
                    IRFailureCode.INVALID_ARGUMENTS,
                )
            )
    elif opcode in _ACTION_OPCODES:
        if len(args) != 1:
            issues.append(
                _issue(
                    index,
                    f"{opcode.value} requires exactly one target object",
                    IRFailureCode.INVALID_ARGUMENTS,
                )
            )
    elif opcode == OpCode.QUERY_INFO:
        if len(args) != 2:
            issues.append(
                _issue(
                    index,
                    "QUERY_INFO requires query type and subject",
                    IRFailureCode.INVALID_ARGUMENTS,
                )
            )
    elif opcode in _ARITH_OPCODES:
        if len(args) != 2 or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float, str))
            for value in args
        ):
            issues.append(
                _issue(
                    index,
                    f"{opcode.value} requires two numeric values or variables",
                    IRFailureCode.INVALID_ARGUMENTS,
                )
            )
        elif opcode == OpCode.ARITH_DIV and isinstance(
            args[1],
            (int, float),
        ) and not isinstance(args[1], bool) and float(args[1]) == 0.0:
            issues.append(
                _issue(
                    index,
                    "division by zero is forbidden",
                    IRFailureCode.DIVIDE_BY_ZERO,
                )
            )

    try:
        _canonical_value(instruction.metadata)
    except TypeError as exc:
        issues.append(
            _issue(
                index,
                str(exc),
                IRFailureCode.INVALID_ARGUMENTS,
            )
        )
    return issues


def _validate_cfg(graph: JayaIRGraph) -> List[ValidationIssue]:
    instructions = graph.instructions
    count = len(instructions)
    if count == 0:
        return [
            _issue(
                -1,
                "graph has no instructions",
                IRFailureCode.INVALID_CFG,
            )
        ]

    successors: Dict[int, Tuple[int, ...]] = {}
    issues: List[ValidationIssue] = []
    for index, instruction in enumerate(instructions):
        if not isinstance(instruction.opcode, OpCode):
            continue
        opcode = instruction.opcode
        if opcode == OpCode.RETURN:
            successors[index] = ()
            continue
        if opcode == OpCode.JUMP and len(instruction.args) == 1:
            target = instruction.args[0]
            if isinstance(target, int) and not isinstance(target, bool):
                successors[index] = (target,)
            continue
        if opcode == OpCode.BRANCH_IF and len(instruction.args) == 3:
            true_target, false_target = instruction.args[1:]
            if all(
                isinstance(target, int) and not isinstance(target, bool)
                for target in (true_target, false_target)
            ):
                successors[index] = (true_target, false_target)
            continue
        if index + 1 < count:
            successors[index] = (index + 1,)
        else:
            successors[index] = ()
            issues.append(
                _issue(
                    index,
                    "control flow falls off graph without RETURN",
                    IRFailureCode.INVALID_CFG,
                )
            )

    for index, targets in successors.items():
        for target in targets:
            if target < 0 or target >= count:
                issues.append(
                    _issue(
                        index,
                        f"control-flow target out of range: {target}",
                        IRFailureCode.INVALID_CFG,
                        target=target,
                        instruction_count=count,
                    )
                )

    reachable: set[int] = set()
    visiting: set[int] = set()
    cycle_edges: set[Tuple[int, int]] = set()

    def walk(index: int) -> None:
        if index in visiting:
            return
        if index in reachable or index < 0 or index >= count:
            return
        visiting.add(index)
        reachable.add(index)
        for target in successors.get(index, ()):
            if target in visiting:
                cycle_edges.add((index, target))
            else:
                walk(target)
        visiting.remove(index)

    walk(0)
    for source, target in sorted(cycle_edges):
        issues.append(
            _issue(
                source,
                f"control-flow cycle is forbidden: {source}->{target}",
                IRFailureCode.INVALID_CFG,
                target=target,
            )
        )
    for index in range(count):
        if index not in reachable:
            issues.append(
                _issue(
                    index,
                    "unreachable instruction",
                    IRFailureCode.INVALID_CFG,
                )
            )
    if not any(
        index in reachable
        and isinstance(instructions[index].opcode, OpCode)
        and instructions[index].opcode == OpCode.RETURN
        for index in range(count)
    ):
        issues.append(
            _issue(
                -1,
                "graph has no reachable RETURN",
                IRFailureCode.INVALID_CFG,
            )
        )
    return issues


def validate_graph(
    graph: JayaIRGraph,
    mode: ValidationMode = ValidationMode.STRICT,
) -> ValidationReport:
    del mode  # Unsupported instructions are critical in every mode.
    if graph.is_sealed:
        if graph.has_valid_integrity():
            return ValidationReport(
                is_valid=True,
                has_critical=False,
                valid_instructions=len(graph.instructions),
                invalid_instructions=0,
                issues=(),
            )
        issue = _issue(
            -1,
            "sealed graph signature or instruction integrity mismatch",
            IRFailureCode.IR_MUTATION,
        )
        return ValidationReport(
            is_valid=False,
            has_critical=True,
            valid_instructions=0,
            invalid_instructions=len(graph.instructions),
            issues=(issue,),
        )

    issues: List[ValidationIssue] = []
    invalid_indices: set[int] = set()
    for index, instruction in enumerate(graph.instructions):
        instruction_issues = _validate_instruction(instruction, index)
        if instruction_issues:
            invalid_indices.add(index)
            issues.extend(instruction_issues)

    if not issues:
        cfg_issues = _validate_cfg(graph)
        issues.extend(cfg_issues)
        invalid_indices.update(
            issue.index for issue in cfg_issues if issue.index >= 0
        )
    try:
        _canonical_value(graph.metadata)
    except TypeError as exc:
        issues.append(
            _issue(
                -1,
                str(exc),
                IRFailureCode.INVALID_ARGUMENTS,
            )
        )

    is_valid = not issues
    if is_valid:
        graph.seal()
    return ValidationReport(
        is_valid=is_valid,
        has_critical=bool(issues),
        valid_instructions=max(
            0,
            len(graph.instructions) - len(invalid_indices),
        ),
        invalid_instructions=len(invalid_indices),
        issues=tuple(issues),
    )


def supported_opcodes() -> Sequence[str]:
    return tuple(sorted(opcode.value for opcode in _SUPPORTED_OPCODES))


def contract_metadata() -> Dict[str, Any]:
    return {
        "version": JAYA_IR_VERSION,
        "phase_state": JAYA_IR_PHASE_STATE,
        "opcode_count": len(list(OpCode)),
        "opcodes": tuple(opcode.value for opcode in OpCode),
        "executable_opcodes": supported_opcodes(),
        "rejected_opcodes": tuple(
            sorted(opcode.value for opcode in _UNSUPPORTED_OPCODES)
        ),
        "immutable_after_validation": True,
    }
