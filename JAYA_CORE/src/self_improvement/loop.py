"""
Self-Improvement Loop for JAYA_CORE.

Provides:
- LiveEvolver: (1+1)-ES micro-evolution on model weights
- MetaCognitivePlanner: Reflection on weak tasks, triggers improvements
- MorphicKernel: Runtime patch generation from feedback
- Continuous learning and adaptation
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from JAYA_CORE.src.observability import get_structured_logger, record_error
from JAYA_CORE.src.security import get_audit_logger

logger = get_structured_logger(__name__, component="self_improvement")
audit_logger = get_audit_logger()


# ============================================================================
# Data Classes
# ============================================================================

class EvolutionStatus(Enum):
    """Evolution status."""
    IDLE = "idle"
    RUNNING = "running"
    EVALUATING = "evaluating"
    APPLYING = "applying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ReflectionType(Enum):
    """Types of meta-cognitive reflection."""
    TASK_FAILURE = "task_failure"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    USER_FEEDBACK = "user_feedback"
    PERIODIC_REVIEW = "periodic_review"
    ANOMALY_DETECTION = "anomaly_detection"


@dataclass
class EvolutionCandidate:
    """Candidate solution for evolution."""
    candidate_id: str
    parameters: Dict[str, Any]  # Model parameters / weights
    fitness: float = 0.0
    generation: int = 0
    parent_id: Optional[str] = None
    mutations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvolutionResult:
    """Result of evolution cycle."""
    cycle_id: str
    status: EvolutionStatus
    best_candidate: Optional[EvolutionCandidate] = None
    population_size: int = 0
    generations: int = 0
    generation: int = 0  # Add this for backward compatibility
    fitness_improvement: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class ReflectionResult:
    """Result of meta-cognitive reflection."""
    reflection_id: str
    reflection_type: ReflectionType
    trigger: str
    findings: List[str] = field(default_factory=list)
    recommended_actions: List[Dict[str, Any]] = field(default_factory=list)
    priority: int = 0  # 0-10
    created_at: float = field(default_factory=time.time)


@dataclass
class MorphicPatch:
    """Runtime patch generated from feedback."""
    patch_id: str
    target_component: str
    patch_type: str  # "parameter", "logic", "prompt", "config"
    changes: Dict[str, Any]
    confidence: float
    source_feedback: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, applied, reverted, failed
    applied_at: Optional[float] = None


# ============================================================================
# LiveEvolver: (1+1)-ES Micro-Evolution
# ============================================================================

class LiveEvolver:
    """
    Live Evolution using (1+1)-ES (Evolution Strategy).
    
    Continuously evolves model parameters/weights based on performance feedback.
    """
    
    def __init__(
        self,
        parameter_space: Dict[str, Tuple[float, float]],  # param_name -> (min, max)
        fitness_fn: Callable[[Dict[str, Any]], float],
        mutation_rate: float = 0.1,
        mutation_strength: float = 0.1,
        population_size: int = 10,
        elite_size: int = 2,
    ):
        self.parameter_space = parameter_space
        self.fitness_fn = fitness_fn
        self.mutation_rate = mutation_rate
        self.mutation_strength = mutation_strength
        self.population_size = population_size
        self.elite_size = elite_size
        
        self.population: List[EvolutionCandidate] = []
        self.generation = 0
        self.best_fitness = -float('inf')
        self.best_candidate: Optional[EvolutionCandidate] = None
        self.history: List[EvolutionResult] = []
        self._running = False
    
    def initialize_population(self, seed_params: Dict[str, Any] = None):
        """Initialize population with random or seeded candidates."""
        self.population = []
        
        for i in range(self.population_size):
            if seed_params and i == 0:
                params = seed_params.copy()
            else:
                params = {}
                for name, (min_val, max_val) in self.parameter_space.items():
                    params[name] = random.uniform(min_val, max_val)
            
            candidate = EvolutionCandidate(
                candidate_id=str(uuid.uuid4())[:8],
                parameters=params,
                generation=0,
            )
            self.population.append(candidate)
        
        logger.info("Population initialized", size=self.population_size)
    
    def mutate(self, candidate: EvolutionCandidate) -> EvolutionCandidate:
        """Create mutated offspring."""
        new_params = candidate.parameters.copy()
        mutations = []
        
        for name, (min_val, max_val) in self.parameter_space.items():
            if random.random() < self.mutation_rate:
                # Gaussian mutation
                current = new_params[name]
                sigma = (max_val - min_val) * self.mutation_strength
                new_val = current + random.gauss(0, sigma)
                new_val = max(min_val, min(max_val, new_val))
                new_params[name] = new_val
                mutations.append(f"{name}: {current:.4f} -> {new_val:.4f}")
        
        offspring = EvolutionCandidate(
            candidate_id=str(uuid.uuid4())[:8],
            parameters=new_params,
            generation=candidate.generation + 1,
            parent_id=candidate.candidate_id,
            mutations=mutations,
        )
        
        return offspring
    
    def evaluate_population(self) -> List[Tuple[EvolutionCandidate, float]]:
        """Evaluate fitness for all candidates."""
        results = []
        for candidate in self.population:
            try:
                fitness = self.fitness_fn(candidate.parameters)
                candidate.fitness = fitness
                results.append((candidate, fitness))
            except Exception as e:
                logger.error("Fitness evaluation failed", candidate_id=candidate.candidate_id, error=str(e))
                candidate.fitness = -float('inf')
                results.append((candidate, -float('inf')))
        
        return results
    
    def select_next_generation(self, evaluated: List[Tuple[EvolutionCandidate, float]]):
        """Select next generation using (1+1)-ES with elitism."""
        # Sort by fitness descending
        evaluated.sort(key=lambda x: x[1], reverse=True)
        
        # Keep elites
        new_population = [c for c, f in evaluated[:self.elite_size]]
        
        # Generate offspring from best
        best_candidate = evaluated[0][0]
        
        while len(new_population) < self.population_size:
            offspring = self.mutate(best_candidate)
            new_population.append(offspring)
        
        self.population = new_population
        self.generation += 1
        
        # Update best
        if evaluated[0][1] > self.best_fitness:
            self.best_fitness = evaluated[0][1]
            self.best_candidate = evaluated[0][0]
    
    def evolve_cycle(self) -> EvolutionResult:
        """Run one evolution cycle."""
        cycle_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        try:
            # Evaluate
            evaluated = self.evaluate_population()
            
            # Select next generation
            self.select_next_generation(evaluated)
            
            # Calculate improvement
            fitness_improvement = self.best_fitness - (self.history[-1].best_candidate.fitness if self.history and self.history[-1].best_candidate else 0)
            
            result = EvolutionResult(
                cycle_id=cycle_id,
                status=EvolutionStatus.COMPLETED,
                best_candidate=self.best_candidate,
                population_size=len(self.population),
                generations=self.generation,
                fitness_improvement=fitness_improvement,
                duration_ms=(time.time() - start_time) * 1000,
            )
            
            self.history.append(result)
            
            logger.info("Evolution cycle completed",
                   cycle_id=cycle_id,
                   generation=self.generation,
                   best_fitness=self.best_fitness,
                   improvement=fitness_improvement)
            
            return result
            
        except Exception as e:
            logger.error("Evolution cycle failed", cycle_id=cycle_id, error=str(e))
            return EvolutionResult(
                cycle_id=cycle_id,
                status=EvolutionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    def run_continuous(self, max_cycles: int = 100, target_fitness: float = None, interval_seconds: float = 60.0):
        """Run continuous evolution."""
        self._running = True
        
        for cycle in range(max_cycles):
            if not self._running:
                break
            
            result = self.evolve_cycle()
            
            if target_fitness and self.best_fitness >= target_fitness:
                logger.info("Target fitness reached", fitness=self.best_fitness)
                break
            
            if cycle < max_cycles - 1:
                time.sleep(interval_seconds)
        
        self._running = False
    
    def stop(self):
        """Stop continuous evolution."""
        self._running = False
    
    def get_best_parameters(self) -> Dict[str, Any]:
        """Get best evolved parameters."""
        if self.best_candidate:
            return self.best_candidate.parameters.copy()
        return {}


# ============================================================================
# MetaCognitivePlanner: Reflection & Planning
# ============================================================================

class MetaCognitivePlanner:
    """
    Meta-cognitive planner for reflection and self-improvement planning.
    
    Periodically reflects on performance, identifies weaknesses,
    and generates improvement plans.
    """
    
    def __init__(
        self,
        reflection_interval_seconds: float = 600.0,  # 10 minutes
        performance_window: int = 100,  # Last N tasks to analyze
    ):
        self.reflection_interval = reflection_interval_seconds
        self.performance_window = performance_window
        
        self.task_history: List[Dict[str, Any]] = []
        self.reflections: List[ReflectionResult] = []
        self.improvement_plans: List[Dict[str, Any]] = []
        self._running = False
        self._last_reflection = 0
    
    def record_task(self, task_data: Dict[str, Any]):
        """Record task outcome for analysis."""
        task_data["timestamp"] = time.time()
        self.task_history.append(task_data)
        
        # Keep window
        if len(self.task_history) > self.performance_window:
            self.task_history = self.task_history[-self.performance_window:]
    
    def should_reflect(self) -> bool:
        """Check if reflection is due."""
        return time.time() - self._last_reflection >= self.reflection_interval
    
    def reflect(self, trigger: ReflectionType = ReflectionType.PERIODIC_REVIEW) -> ReflectionResult:
        """Perform meta-cognitive reflection."""
        reflection_id = str(uuid.uuid4())[:8]
        
        # Analyze recent performance
        findings = []
        recommended_actions = []
        
        if not self.task_history:
            findings.append("No task history available for analysis")
        else:
            # Analyze failure rate
            total = len(self.task_history)
            failures = sum(1 for t in self.task_history if not t.get("success", True))
            failure_rate = failures / total if total > 0 else 0
            
            if failure_rate > 0.2:
                findings.append(f"High failure rate: {failure_rate:.1%} ({failures}/{total})")
                recommended_actions.append({
                    "action": "investigate_failures",
                    "priority": 8,
                    "details": "Analyze failure patterns and root causes",
                })
            
            # Analyze latency
            latencies = [t.get("duration_ms", 0) for t in self.task_history if t.get("duration_ms")]
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
                
                if p95_latency > 5000:  # 5 seconds
                    findings.append(f"High latency: P95={p95_latency:.0f}ms")
                    recommended_actions.append({
                        "action": "optimize_performance",
                        "priority": 6,
                        "details": "Profile and optimize slow operations",
                    })
            
            # Analyze error patterns
            errors = defaultdict(int)
            for t in self.task_history:
                if not t.get("success", True):
                    error_type = t.get("error_type", "unknown")
                    errors[error_type] += 1
            
            if errors:
                top_error = max(errors.items(), key=lambda x: x[1])
                findings.append(f"Top error: {top_error[0]} ({top_error[1]} occurrences)")
                recommended_actions.append({
                    "action": "fix_error_pattern",
                    "priority": 7,
                    "details": f"Address recurring error: {top_error[0]}",
                })
            
            # Check for capability gaps
            capabilities_used = set()
            for t in self.task_history:
                caps = t.get("capabilities", [])
                capabilities_used.update(caps)
            
            # This would check against available capabilities
            findings.append(f"Capabilities used: {len(capabilities_used)} unique")
        
        # Determine priority
        priority = 5
        if any("High" in f for f in findings):
            priority = 8
        elif any("error" in f.lower() for f in findings):
            priority = 7
        
        reflection = ReflectionResult(
            reflection_id=reflection_id,
            reflection_type=trigger,
            trigger=trigger.value,
            findings=findings,
            recommended_actions=recommended_actions,
            priority=priority,
        )
        
        self.reflections.append(reflection)
        self._last_reflection = time.time()
        
        logger.info("Reflection completed",
                   reflection_id=reflection_id,
                   findings=len(findings),
                   actions=len(recommended_actions),
                   priority=priority)
        
        return reflection
    
    def generate_improvement_plan(self, reflection: ReflectionResult) -> Dict[str, Any]:
        """Generate concrete improvement plan from reflection."""
        plan_id = str(uuid.uuid4())[:8]
        
        plan = {
            "plan_id": plan_id,
            "reflection_id": reflection.reflection_id,
            "created_at": time.time(),
            "actions": [],
            "status": "pending",
        }
        
        for action in reflection.recommended_actions:
            plan_action = {
                "action_id": str(uuid.uuid4())[:8],
                "type": action["action"],
                "priority": action["priority"],
                "details": action["details"],
                "status": "pending",
                "assigned_to": "system",
            }
            plan["actions"].append(plan_action)
        
        self.improvement_plans.append(plan)
        
        logger.info("Improvement plan generated", plan_id=plan_id, actions=len(plan["actions"]))
        
        return plan
    
    def run_reflection_loop(self):
        """Run continuous reflection loop."""
        self._running = True
        
        while self._running:
            if self.should_reflect():
                reflection = self.reflect()
                if reflection.recommended_actions:
                    plan = self.generate_improvement_plan(reflection)
                    logger.info("Improvement plan created", plan_id=plan["plan_id"])
            
            time.sleep(60)  # Check every minute
    
    def stop(self):
        """Stop reflection loop."""
        self._running = False


# ============================================================================
# MorphicKernel: Runtime Patch Generation
# ============================================================================

class MorphicKernel:
    """
    Morphic Kernel for runtime patch generation.
    
    Generates and applies patches to system components based on
    feedback, reflections, and evolution results.
    """
    
    def __init__(self):
        self.patches: Dict[str, MorphicPatch] = {}
        self.patch_history: List[MorphicPatch] = []
        self.component_interfaces: Dict[str, Any] = {}  # component_name -> interface
    
    def register_component(self, name: str, interface: Any):
        """Register component interface for patching."""
        self.component_interfaces[name] = interface
        logger.info("Component registered for patching", component=name)
    
    def generate_patch(
        self,
        target_component: str,
        patch_type: str,
        changes: Dict[str, Any],
        source_feedback: List[str],
        confidence: float = 0.8,
    ) -> MorphicPatch:
        """Generate a morphic patch."""
        patch_id = str(uuid.uuid4())[:8]
        
        patch = MorphicPatch(
            patch_id=patch_id,
            target_component=target_component,
            patch_type=patch_type,
            changes=changes,
            confidence=confidence,
            source_feedback=source_feedback,
        )
        
        self.patches[patch_id] = patch
        self.patch_history.append(patch)
        
        logger.info("Morphic patch generated",
                   patch_id=patch_id,
                   component=target_component,
                   type=patch_type,
                   confidence=confidence)
        
        return patch
    
    def generate_from_reflection(self, reflection: ReflectionResult) -> List[MorphicPatch]:
        """Generate patches from reflection recommendations."""
        patches = []
        
        for action in reflection.recommended_actions:
            if action["action"] == "optimize_performance":
                # Generate performance optimization patches
                patch = self.generate_patch(
                    target_component="cognitive_model",
                    patch_type="parameter",
                    changes={
                        "temperature": 0.5,  # Lower temperature for more deterministic
                        "max_tokens": 512,   # Reduce token limit
                    },
                    source_feedback=[f"Reflection: {reflection.reflection_id}"],
                    confidence=0.7,
                )
                patches.append(patch)
            
            elif action["action"] == "fix_error_pattern":
                # Generate error handling patches
                patch = self.generate_patch(
                    target_component="error_handler",
                    patch_type="logic",
                    changes={
                        "retry_attempts": 3,
                        "fallback_enabled": True,
                    },
                    source_feedback=[f"Reflection: {reflection.reflection_id}"],
                    confidence=0.8,
                )
                patches.append(patch)
            
            elif action["action"] == "investigate_failures":
                # Generate debugging patches
                patch = self.generate_patch(
                    target_component="monitoring",
                    patch_type="config",
                    changes={
                        "log_level": "DEBUG",
                        "trace_enabled": True,
                    },
                    source_feedback=[f"Reflection: {reflection.reflection_id}"],
                    confidence=0.6,
                )
                patches.append(patch)
        
        return patches
    
    def generate_from_evolution(self, evolution_result: EvolutionResult) -> List[MorphicPatch]:
        """Generate patches from evolution results."""
        patches = []
        
        if evolution_result.best_candidate and evolution_result.fitness_improvement > 0:
            # Apply evolved parameters
            patch = self.generate_patch(
                target_component="model_parameters",
                patch_type="parameter",
                changes=evolution_result.best_candidate.parameters,
                source_feedback=[f"Evolution: {evolution_result.cycle_id}"],
                confidence=min(0.9, 0.5 + evolution_result.fitness_improvement),
            )
            patches.append(patch)
        
        return patches
    
    def apply_patch(self, patch_id: str) -> bool:
        """Apply a patch to target component."""
        patch = self.patches.get(patch_id)
        if not patch:
            logger.error("Patch not found", patch_id=patch_id)
            return False
        
        if patch.status != "pending":
            logger.warning("Patch not in pending state", patch_id=patch_id, status=patch.status)
            return False
        
        component = self.component_interfaces.get(patch.target_component)
        if not component:
            logger.error("Target component not registered", component=patch.target_component)
            patch.status = "failed"
            return False
        
        try:
            # Apply based on patch type
            if patch.patch_type == "parameter":
                self._apply_parameter_patch(component, patch.changes)
            elif patch.patch_type == "config":
                self._apply_config_patch(component, patch.changes)
            elif patch.patch_type == "logic":
                self._apply_logic_patch(component, patch.changes)
            elif patch.patch_type == "prompt":
                self._apply_prompt_patch(component, patch.changes)
            else:
                logger.warning("Unknown patch type", patch_type=patch.patch_type)
                return False
            
            patch.status = "applied"
            patch.applied_at = time.time()
            
            logger.info("Patch applied successfully", patch_id=patch_id)
            return True
            
        except Exception as e:
            logger.error("Patch application failed", patch_id=patch_id, error=str(e))
            patch.status = "failed"
            return False
    
    def _apply_parameter_patch(self, component: Any, changes: Dict[str, Any]):
        """Apply parameter changes."""
        for key, value in changes.items():
            if hasattr(component, key):
                setattr(component, key, value)
            elif hasattr(component, 'config') and hasattr(component.config, key):
                setattr(component.config, key, value)
    
    def _apply_config_patch(self, component: Any, changes: Dict[str, Any]):
        """Apply configuration changes."""
        if hasattr(component, 'config'):
            for key, value in changes.items():
                if hasattr(component.config, key):
                    setattr(component.config, key, value)
    
    def _apply_logic_patch(self, component: Any, changes: Dict[str, Any]):
        """Apply logic/behavior changes."""
        # This would modify component behavior
        # For example, adding retry logic, fallback handlers, etc.
        pass
    
    def _apply_prompt_patch(self, component: Any, changes: Dict[str, Any]):
        """Apply prompt template changes."""
        if hasattr(component, 'prompt_templates'):
            component.prompt_templates.update(changes)
    
    def revert_patch(self, patch_id: str) -> bool:
        """Revert a previously applied patch."""
        patch = self.patches.get(patch_id)
        if not patch or patch.status != "applied":
            return False
        
        # In a real implementation, this would restore previous state
        patch.status = "reverted"
        logger.info("Patch reverted", patch_id=patch_id)
        return True
    
    def get_patch_status(self, patch_id: str) -> Optional[MorphicPatch]:
        """Get patch status."""
        return self.patches.get(patch_id)
    
    def list_patches(self, status: str = None) -> List[MorphicPatch]:
        """List patches, optionally filtered by status."""
        patches = list(self.patches.values())
        if status:
            patches = [p for p in patches if p.status == status]
        return patches


# ============================================================================
# Self-Improvement Orchestrator
# ============================================================================

class SelfImprovementOrchestrator:
    """
    Orchestrates the complete self-improvement loop.
    
    Coordinates LiveEvolver, MetaCognitivePlanner, and MorphicKernel
    for continuous autonomous improvement.
    """
    
    def __init__(
        self,
        parameter_space: Dict[str, Tuple[float, float]],
        fitness_fn: Callable[[Dict[str, Any]], float],
    ):
        self.evolver = LiveEvolver(parameter_space, fitness_fn)
        self.planner = MetaCognitivePlanner()
        self.kernel = MorphicKernel()
        
        self._running = False
        self.cycle_count = 0
    
    def register_component(self, name: str, interface: Any):
        """Register component for patching."""
        self.kernel.register_component(name, interface)
    
    def record_task_outcome(self, task_data: Dict[str, Any]):
        """Record task outcome for planner analysis."""
        self.planner.record_task(task_data)
    
    def run_improvement_cycle(self) -> Dict[str, Any]:
        """Run one complete improvement cycle."""
        self.cycle_count += 1
        cycle_id = str(uuid.uuid4())[:8]
        
        results = {
            "cycle_id": cycle_id,
            "evolution": None,
            "reflection": None,
            "patches": [],
        }
        
        # 1. Evolution step
        if self.evolver.population:
            evolution_result = self.evolver.evolve_cycle()
            results["evolution"] = {
                "status": evolution_result.status.value,
                "best_fitness": self.evolver.best_fitness,
                "generation": self.evolver.generation,
                "improvement": evolution_result.fitness_improvement,
            }
            
            # Generate patches from evolution
            evo_patches = self.kernel.generate_from_evolution(evolution_result)
            for patch in evo_patches:
                self.kernel.apply_patch(patch.patch_id)
            results["patches"].extend([p.patch_id for p in evo_patches])
        
        # 2. Reflection step
        if self.planner.should_reflect():
            reflection = self.planner.reflect()
            results["reflection"] = {
                "reflection_id": reflection.reflection_id,
                "findings": reflection.findings,
                "actions": len(reflection.recommended_actions),
                "priority": reflection.priority,
            }
            
            # Generate and apply patches from reflection
            reflection_patches = self.kernel.generate_from_reflection(reflection)
            for patch in reflection_patches:
                self.kernel.apply_patch(patch.patch_id)
            results["patches"].extend([p.patch_id for p in reflection_patches])
            
            # Generate improvement plan
            plan = self.planner.generate_improvement_plan(reflection)
            logger.info("Improvement plan generated", plan_id=plan["plan_id"])
        
        logger.info("Improvement cycle completed", cycle_id=cycle_id, patches=len(results["patches"]))
        
        return results
    
    def run_continuous(self, interval_seconds: float = 300.0):
        """Run continuous improvement loop."""
        self._running = True
        
        # Initialize evolver if needed
        if not self.evolver.population:
            self.evolver.initialize_population()
        
        while self._running:
            self.run_improvement_cycle()
            time.sleep(interval_seconds)
    
    def stop(self):
        """Stop continuous improvement."""
        self._running = False
        self.evolver.stop()
        self.planner.stop()
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            "cycle_count": self.cycle_count,
            "evolver": {
                "generation": self.evolver.generation,
                "best_fitness": self.evolver.best_fitness,
                "population_size": len(self.evolver.population),
            },
            "planner": {
                "reflections": len(self.planner.reflections),
                "plans": len(self.planner.improvement_plans),
                "task_history_size": len(self.planner.task_history),
            },
            "kernel": {
                "patches_total": len(self.kernel.patches),
                "patches_applied": len([p for p in self.kernel.patches.values() if p.status == "applied"]),
                "components_registered": len(self.kernel.component_interfaces),
            },
        }


# ============================================================================
# Default Instances
# ============================================================================

_self_improvement_orchestrator: Optional[SelfImprovementOrchestrator] = None


def create_self_improvement_orchestrator(
    parameter_space: Dict[str, Tuple[float, float]],
    fitness_fn: Callable[[Dict[str, Any]], float],
) -> SelfImprovementOrchestrator:
    """Create self-improvement orchestrator."""
    global _self_improvement_orchestrator
    _self_improvement_orchestrator = SelfImprovementOrchestrator(parameter_space, fitness_fn)
    return _self_improvement_orchestrator


def get_self_improvement_orchestrator() -> Optional[SelfImprovementOrchestrator]:
    """Get global self-improvement orchestrator."""
    return _self_improvement_orchestrator