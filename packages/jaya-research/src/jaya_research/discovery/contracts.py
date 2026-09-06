"""
contracts.py — Data contracts for Scientific & Engineering Discovery Pipeline.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DiscoveryArtifactType(str, Enum):
    SCIENTIFIC_HYPOTHESIS = "SCIENTIFIC_HYPOTHESIS"
    ENGINEERING_REQUIREMENTS = "ENGINEERING_REQUIREMENTS"
    PARAMETRIC_GEOMETRY = "PARAMETRIC_GEOMETRY"
    SIMULATION_RESULT = "SIMULATION_RESULT"
    DIGITAL_TWIN = "DIGITAL_TWIN"
    REJECTED_HYPOTHESIS = "REJECTED_HYPOTHESIS"
    DISCOVERY_CANDIDATE = "DISCOVERY_CANDIDATE"


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"
    UNFEASIBLE_WITH_KNOWN_PHYSICS = "UNFEASIBLE_WITH_KNOWN_PHYSICS"
    REQUIRES_NEW_MATERIALS = "REQUIRES_NEW_MATERIALS"
    REQUIRES_FURTHER_SIMULATION = "REQUIRES_FURTHER_SIMULATION"
    FALSIFIED = "FALSIFIED"


@dataclass
class DiscoveryRequirement:
    requirement_id: str
    concept_name: str
    translated_goal: str
    target_specifications: Dict[str, Any]
    feasibility_status: FeasibilityStatus
    primary_blockers: List[str] = field(default_factory=list)
    researchable_subproblems: List[str] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["feasibility_status"] = self.feasibility_status.value
        return res


@dataclass
class PhysicsConstraint:
    law_name: str
    description: str
    governing_equation: str
    is_strict_boundary: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScientificHypothesis:
    hypothesis_id: str
    title: str
    statement: str
    domain: str
    assumptions: List[str] = field(default_factory=list)
    governing_equations: List[str] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FalsificationResult:
    hypothesis_id: str
    is_falsified: bool
    violating_laws: List[str] = field(default_factory=list)
    numerical_evidence: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryArtifact:
    artifact_id: str
    artifact_type: DiscoveryArtifactType
    concept_name: str
    summary: str
    payload: Dict[str, Any]
    evidence_kind: str = "SIMULATION"  # "SIMULATION", "EMPIRICAL", "THEORETICAL"
    status: str = "CANDIDATE"
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["artifact_type"] = self.artifact_type.value
        return res

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
