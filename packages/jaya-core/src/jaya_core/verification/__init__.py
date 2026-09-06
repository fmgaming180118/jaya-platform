"""
Formal Verification Package for JAYA_CORE.

Provides property-based testing, TLA+ model checking,
contract verification, and runtime verification.
"""

from __future__ import annotations

from .formal import (
    PropertyType,
    Property,
    VerificationResult,
    PropertyVerifier,
    HypothesisVerifier,
    TLAModel,
    TLAModelChecker,
    Contract,
    ContractVerifier,
    RuntimeVerifier,
    create_jaya_properties,
    get_runtime_verifier,
    verify_system,
)
from .phase2_gates import (
    Phase2VerificationGates,
    GateResult,
    VerificationReport,
    get_phase2_gates,
    run_phase2_verification,
    verify_phase2_ready,
)

__all__ = [
    "PropertyType",
    "Property",
    "VerificationResult",
    "PropertyVerifier",
    "HypothesisVerifier",
    "TLAModel",
    "TLAModelChecker",
    "Contract",
    "ContractVerifier",
    "RuntimeVerifier",
    "create_jaya_properties",
    "get_runtime_verifier",
    "verify_system",
    "Phase2VerificationGates",
    "GateResult",
    "VerificationReport",
    "get_phase2_gates",
    "run_phase2_verification",
    "verify_phase2_ready",
]