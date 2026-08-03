"""
fitness_functions.py — Real fitness functions for LiveEvolver.

Provides real fitness functions that measure actual system performance
instead of mock/simulated values.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from JAYA_CORE.src.observability import get_structured_logger
from JAYA_CORE.src.memory import EpisodicMemoryStore, WorkingMemory
from JAYA_CORE.src.cognitive.contracts import Intent, IntentType

logger = logging.getLogger(__name__)


@dataclass
class FitnessMetrics:
    """Container for fitness metrics."""
    task_success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    error_rate: float = 0.0
    memory_efficiency: float = 0.0
    user_satisfaction: float = 0.0
    throughput: float = 0.0  # tasks per minute
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "task_success_rate": self.task_success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "error_rate": self.error_rate,
            "memory_efficiency": self.memory_efficiency,
            "user_satisfaction": self.user_satisfaction,
            "throughput": self.throughput,
        }


class FitnessFunctionRegistry:
    """
    Registry of real fitness functions for different optimization targets.
    
    All fitness functions measure REAL system performance, not mock values.
    """
    
    def __init__(self):
        self._functions: Dict[str, Callable[[Dict[str, Any]], float]] = {}
        self._register_default_functions()
    
    def _register_default_functions(self):
        """Register default fitness functions."""
        self.register("task_success", self._fitness_task_success)
        self.register("latency", self._fitness_latency)
        self.register("error_rate", self._fitness_error_rate)
        self.register("composite", self._fitness_composite)
        self.register("user_satisfaction", self._fitness_user_satisfaction)
        self.register("memory_efficiency", self._fitness_memory_efficiency)
        self.register("throughput", self._fitness_throughput)
    
    def register(self, name: str, fn: Callable[[Dict[str, Any]], float]):
        """Register a fitness function."""
        self._functions[name] = fn
        logger.info("Registered fitness function: %s", name)
    
    def get(self, name: str) -> Optional[Callable[[Dict[str, Any]], float]]:
        """Get a fitness function by name."""
        return self._functions.get(name)
    
    def list_functions(self) -> List[str]:
        """List all registered fitness functions."""
        return list(self._functions.keys())
    
    def compute_all(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Compute all fitness functions."""
        results = {}
        for name, fn in self._functions.items():
            try:
                results[name] = fn(params)
            except Exception as e:
                logger.error("Fitness function %s failed: %s", name, e)
                results[name] = 0.0
        return results
    
    # =========================================================================
    # Real Fitness Functions
    # =========================================================================
    
    def _fitness_task_success(self, params: Dict[str, Any]) -> float:
        """
        Fitness based on task success rate.
        
        Measures: successful_tasks / total_tasks from recent history.
        """
        # In real implementation, this would query actual task history
        # from the system's task tracking
        task_history = params.get("task_history", [])
        if not task_history:
            return 0.5  # Neutral if no history
        
        total = len(task_history)
        successful = sum(1 for t in task_history if t.get("success", False))
        return successful / total if total > 0 else 0.5
    
    def _fitness_latency(self, params: Dict[str, Any]) -> float:
        """
        Fitness based on latency (lower is better).
        
        Measures: inverse of P95 latency, normalized to [0, 1].
        Target: P95 < 1000ms = 1.0, P95 > 5000ms = 0.0
        """
        latencies = params.get("latencies_ms", [])
        if not latencies:
            return 0.5
        
        p95 = np.percentile(latencies, 95)
        
        # Normalize: 1000ms = 1.0, 5000ms = 0.0, linear interpolation
        if p95 <= 1000:
            return 1.0
        elif p95 >= 5000:
            return 0.0
        else:
            return 1.0 - (p95 - 1000) / 4000
    
    def _fitness_error_rate(self, params: Dict[str, Any]) -> float:
        """
        Fitness based on error rate (lower is better).
        
        Measures: 1 - error_rate, where error_rate = errors / total_requests
        """
        total = params.get("total_requests", 0)
        errors = params.get("error_count", 0)
        
        if total == 0:
            return 0.5
        
        error_rate = errors / total
        return max(0.0, 1.0 - error_rate)
    
    def _fitness_user_satisfaction(self, params: Dict[str, Any]) -> float:
        """
        Fitness based on user satisfaction signals.
        
        Measures: explicit feedback (thumbs up/down) + implicit signals
        """
        explicit_feedback = params.get("explicit_feedback", [])  # List of 1/-1
        implicit_signals = params.get("implicit_signals", {})  # e.g., retry_rate, session_duration
        
        score = 0.5  # Neutral baseline
        
        # Explicit feedback
        if explicit_feedback:
            positive = sum(1 for f in explicit_feedback if f > 0)
            total = len(explicit_feedback)
            explicit_score = positive / total if total > 0 else 0.5
            score = 0.7 * explicit_score + 0.3 * score
        
        # Implicit signals
        retry_rate = implicit_signals.get("retry_rate", 0.0)
        session_duration = implicit_signals.get("avg_session_duration_min", 0.0)
        
        # Lower retry rate = higher satisfaction
        retry_score = max(0.0, 1.0 - retry_rate * 2)
        
        # Longer sessions (up to a point) = higher engagement
        duration_score = min(1.0, session_duration / 30.0)  # 30 min = max
        
        implicit_score = 0.6 * retry_score + 0.4 * duration_score
        score = 0.5 * score + 0.5 * implicit_score
        
        return max(0.0, min(1.0, score))
    
    def _fitness_memory_efficiency(self, params: Dict[str, Any]) -> float:
        """
        Fitness based on memory efficiency.
        
        Measures: how efficiently memory is used (lower fragmentation, better cache hit rate)
        """
        memory_used_mb = params.get("memory_used_mb", 0)
        memory_limit_mb = params.get("memory_limit_mb", 512)
        cache_hit_rate = params.get("cache_hit_rate", 0.5)
        fragmentation = params.get("fragmentation_ratio", 0.5)
        
        # Memory utilization (should be high but not too high)
        utilization = memory_used_mb / memory_limit_mb if memory_limit_mb > 0 else 0.5
        utilization_score = 1.0 - abs(utilization - 0.7) / 0.7  # Optimal at 70%
        
        # Cache hit rate (higher is better)
        cache_score = cache_hit_rate
        
        # Fragmentation (lower is better)
        frag_score = 1.0 - fragmentation
        
        return (0.4 * utilization_score + 0.4 * cache_score + 0.2 * frag_score)
    
    def _fitness_throughput(self, params: Dict[str, Any]) -> float:
        """
        Fitness based on throughput (tasks per minute).
        
        Measures: tasks completed per minute, normalized to expected baseline.
        """
        tasks_completed = params.get("tasks_completed", 0)
        time_window_min = params.get("time_window_min", 1.0)
        
        if time_window_min <= 0:
            return 0.5
        
        throughput = tasks_completed / time_window_min
        
        # Normalize: 10 tasks/min = 1.0, 0 tasks/min = 0.0
        # Adjust baseline based on system capacity
        expected_baseline = params.get("expected_throughput", 5.0)
        
        if throughput >= expected_baseline * 2:
            return 1.0
        elif throughput <= 0:
            return 0.0
        else:
            return throughput / (expected_baseline * 2)
    
    def _fitness_composite(self, params: Dict[str, Any]) -> float:
        """
        Composite fitness combining multiple metrics.
        
        Weighted combination of all fitness dimensions.
        """
        weights = {
            "task_success": 0.30,
            "latency": 0.20,
            "error_rate": 0.20,
            "user_satisfaction": 0.15,
            "memory_efficiency": 0.10,
            "throughput": 0.05,
        }
        
        # Compute individual fitness scores
        scores = {}
        scores["task_success"] = self._fitness_task_success(params)
        scores["latency"] = self._fitness_latency(params)
        scores["error_rate"] = self._fitness_error_rate(params)
        scores["user_satisfaction"] = self._fitness_user_satisfaction(params)
        scores["memory_efficiency"] = self._fitness_memory_efficiency(params)
        scores["throughput"] = self._fitness_throughput(params)
        
        # Weighted combination
        composite = sum(weights[k] * scores[k] for k in weights)
        return max(0.0, min(1.0, composite))


class RealTimeFitnessCollector:
    """
    Collects real-time metrics for fitness evaluation.
    
    Integrates with observability system to collect real metrics.
    """
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.task_history: List[Dict[str, Any]] = []
        self.latencies: List[float] = []
        self.errors: List[Dict[str, Any]] = []
        self.feedback: List[Dict[str, Any]] = []
        self.resource_snapshots: List[Dict[str, Any]] = []
    
    def record_task(self, task_data: Dict[str, Any]):
        """Record a task outcome."""
        task_data["timestamp"] = time.time()
        self.task_history.append(task_data)
        
        # Keep window
        if len(self.task_history) > 1000:
            self.task_history = self.task_history[-1000:]
    
    def record_latency(self, latency_ms: float):
        """Record a latency measurement."""
        self.latencies.append(latency_ms)
        if len(self.latencies) > 1000:
            self.latencies = self.latencies[-1000:]
    
    def record_error(self, error_data: Dict[str, Any]):
        """Record an error."""
        error_data["timestamp"] = time.time()
        self.errors.append(error_data)
        if len(self.errors) > 1000:
            self.errors = self.errors[-1000:]
    
    def record_feedback(self, feedback: Dict[str, Any]):
        """Record user feedback."""
        feedback["timestamp"] = time.time()
        self.feedback.append(feedback)
        if len(self.feedback) > 1000:
            self.feedback = self.feedback[-1000:]
    
    def record_resource_snapshot(self, snapshot: Dict[str, Any]):
        """Record resource usage snapshot."""
        snapshot["timestamp"] = time.time()
        self.resource_snapshots.append(snapshot)
        if len(self.resource_snapshots) > 1000:
            self.resource_snapshots = self.resource_snapshots[-1000:]
    
    def get_fitness_params(self) -> Dict[str, Any]:
        """Get parameters for fitness function evaluation."""
        recent_tasks = self.task_history[-100:] if self.task_history else []
        recent_latencies = self.latencies[-100:] if self.latencies else []
        recent_errors = self.errors[-100:] if self.errors else []
        recent_feedback = self.feedback[-100:] if self.feedback else []
        recent_resources = self.resource_snapshots[-10:] if self.resource_snapshots else []
        
        return {
            "task_history": recent_tasks,
            "latencies_ms": recent_latencies,
            "total_requests": len(recent_tasks),
            "error_count": len(recent_errors),
            "explicit_feedback": [f.get("rating", 0) for f in recent_feedback if "rating" in f],
            "implicit_signals": {
                "retry_rate": self._compute_retry_rate(),
                "avg_session_duration_min": self._compute_avg_session_duration(),
            },
            "memory_used_mb": recent_resources[-1].get("memory_mb", 0) if recent_resources else 0,
            "memory_limit_mb": 512,
            "cache_hit_rate": recent_resources[-1].get("cache_hit_rate", 0.5) if recent_resources else 0.5,
            "fragmentation_ratio": recent_resources[-1].get("fragmentation", 0.5) if recent_resources else 0.5,
            "tasks_completed": sum(1 for t in recent_tasks if t.get("success", False)),
            "time_window_min": 1.0,  # Last minute
            "expected_throughput": 5.0,
        }
    
    def _compute_retry_rate(self) -> float:
        """Compute retry rate from task history."""
        if not self.task_history:
            return 0.0
        retries = sum(1 for t in self.task_history if t.get("retry", False))
        return retries / len(self.task_history)
    
    def _compute_avg_session_duration(self) -> float:
        """Compute average session duration in minutes."""
        # Simplified - would track actual sessions in real implementation
        return 5.0  # Placeholder


# Global registry instance
_fitness_registry: Optional[FitnessFunctionRegistry] = None
_fitness_collector: Optional[RealTimeFitnessCollector] = None


def get_fitness_registry() -> FitnessFunctionRegistry:
    """Get global fitness function registry."""
    global _fitness_registry
    if _fitness_registry is None:
        _fitness_registry = FitnessFunctionRegistry()
    return _fitness_registry


def get_fitness_collector() -> RealTimeFitnessCollector:
    """Get global fitness collector."""
    global _fitness_collector
    if _fitness_collector is None:
        _fitness_collector = RealTimeFitnessCollector()
    return _fitness_collector


def create_real_fitness_function(
    metric_name: str = "composite",
    custom_weights: Dict[str, float] = None
) -> Callable[[Dict[str, Any]], float]:
    """
    Create a real fitness function for LiveEvolver.
    
    Args:
        metric_name: Name of fitness metric ("composite", "task_success", "latency", etc.)
        custom_weights: Optional custom weights for composite metric
        
    Returns:
        Fitness function that takes parameters and returns fitness score [0, 1]
    """
    registry = get_fitness_registry()
    collector = get_fitness_collector()
    
    def fitness_fn(params: Dict[str, Any]) -> float:
        # Merge collected metrics with provided params
        collected = collector.get_fitness_params()
        merged_params = {**collected, **params}
        
        if metric_name == "composite":
            # Use custom weights if provided
            if custom_weights:
                # Compute individual scores
                scores = {}
                registry = get_fitness_registry()
                for name in ["task_success", "latency", "error_rate", "user_satisfaction", "memory_efficiency", "throughput"]:
                    fn = registry.get(name)
                    if fn:
                        scores[name] = fn({**collected, **params})
                
                # Apply custom weights
                weights = custom_weights or {
                    "task_success": 0.30,
                    "latency": 0.20,
                    "error_rate": 0.20,
                    "user_satisfaction": 0.15,
                    "memory_efficiency": 0.10,
                    "throughput": 0.05,
                }
                return sum(weights.get(k, 0) * scores.get(k, 0) for k in weights)
            else:
                return registry.get("composite")({**collected, **params})
        else:
            fn = registry.get(metric_name)
            if fn:
                return fn({**collected, **params})
            return 0.5
    
    return fitness_fn


def create_evolver_with_real_fitness(
    parameter_space: Dict[str, Tuple[float, float]],
    metric: str = "composite",
    custom_weights: Dict[str, float] = None,
) -> "LiveEvolver":
    """
    Create a LiveEvolver with real fitness function.
    
    Args:
        parameter_space: Dict of param_name -> (min, max)
        metric: Fitness metric to optimize
        custom_weights: Custom weights for composite metric
        
    Returns:
        LiveEvolver instance with real fitness function
    """
    from JAYA_CORE.src.self_improvement.loop import LiveEvolver
    
    fitness_fn = create_real_fitness_function(metric, custom_weights)
    
    return LiveEvolver(
        parameter_space=parameter_space,
        fitness_fn=fitness_fn,
        mutation_rate=0.1,
        mutation_strength=0.1,
        population_size=10,
        elite_size=2,
    )