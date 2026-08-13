"""
reasoning package — Symbolic Reasoning components for JAYA Core.

Provides:
- SymbolicReasoner: Main reasoning engine
- LogicEngine: Logic verification engine
- ConstraintSolver: Constraint checking
"""

from __future__ import annotations

from .constraint_solver import ConstraintSolver
from .logic_engine import LogicEngine
from .pure_logic import (
    Literal,
    LogicFailureCode,
    LogicProofStore,
    LogicResult,
    LogicRule,
    LogicStatus,
    LogicTheory,
    PureLogicError,
    PureLogicService,
    PureLogicSolver,
    SolverLimits,
)
from .symbolic_reasoner import (
    ConstraintSolver,
    ConstraintViolation,
    LogicEngine,
    SymbolicReasoner,
    VerificationResult,
    create_symbolic_reasoner,
)

__all__ = [
    "SymbolicReasoner",
    "ConstraintSolver",
    "LogicEngine",
    "ConstraintViolation",
    "VerificationResult",
    "create_symbolic_reasoner",
    "Literal",
    "LogicFailureCode",
    "LogicProofStore",
    "LogicResult",
    "LogicRule",
    "LogicStatus",
    "LogicTheory",
    "PureLogicError",
    "PureLogicService",
    "PureLogicSolver",
    "SolverLimits",
]
