"""
Self-Improvement Package for JAYA_CORE.

Provides autonomous self-improvement capabilities:
- LiveEvolver: (1+1)-ES micro-evolution on model parameters
- MetaCognitivePlanner: Reflection on performance, generates improvement plans
- MorphicKernel: Runtime patch generation and application
- SelfImprovementOrchestrator: Coordinates the complete improvement loop
- Fitness Functions: Real fitness functions for evolution
"""

from __future__ import annotations

from .loop import (
    EvolutionStatus,
    ReflectionType,
    EvolutionCandidate,
    EvolutionResult,
    ReflectionResult,
    MorphicPatch,
    LiveEvolver,
    MetaCognitivePlanner,
    MorphicKernel,
    SelfImprovementOrchestrator,
    create_self_improvement_orchestrator,
    get_self_improvement_orchestrator,
)
from .fitness_functions import (
    FitnessFunctionRegistry,
    RealTimeFitnessCollector,
    FitnessMetrics,
    get_fitness_registry,
    get_fitness_collector,
    create_real_fitness_function,
    create_evolver_with_real_fitness,
)

__all__ = [
    "EvolutionStatus",
    "ReflectionType",
    "EvolutionCandidate",
    "EvolutionResult",
    "ReflectionResult",
    "MorphicPatch",
    "LiveEvolver",
    "MetaCognitivePlanner",
    "MorphicKernel",
    "SelfImprovementOrchestrator",
    "create_self_improvement_orchestrator",
    "get_self_improvement_orchestrator",
    "FitnessFunctionRegistry",
    "RealTimeFitnessCollector",
    "FitnessMetrics",
    "get_fitness_registry",
    "get_fitness_collector",
    "create_real_fitness_function",
    "create_evolver_with_real_fitness",
]