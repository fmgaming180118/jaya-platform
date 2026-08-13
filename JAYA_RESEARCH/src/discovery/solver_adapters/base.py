"""
base.py — Abstract interface / contracts for Domain Solver Adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class SolverInput:
    solver_name: str
    domain: str
    parameters: Dict[str, Any]
    boundary_conditions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SolverOutput:
    solver_name: str
    status: str  # "SUCCESS", "FAILED", "DEGRADED"
    metrics: Dict[str, Any]
    output_files: List[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SolverAdapter(ABC):
    """Abstract base class for physical domain solvers."""

    @property
    @abstractmethod
    def solver_name(self) -> str:
        ...

    @property
    @abstractmethod
    def domain(self) -> str:
        ...

    @abstractmethod
    def solve(self, solver_input: SolverInput) -> SolverOutput:
        ...
