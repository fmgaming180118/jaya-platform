"""
router.py — Cognitive Model Router.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.cognitive.contracts import ResourceBudget
from src.resources.modes import ExecutionMode
from .protocol import CognitiveModel, ModelCost, ModelRequest
from .rule_based import RuleBasedCognitiveModel

logger = logging.getLogger(__name__)


class ModelRouter:
    """Selects the best available cognitive model based on budget, mode, and health."""

    def __init__(self, default_model: Optional[CognitiveModel] = None) -> None:
        self._models: Dict[str, CognitiveModel] = {}
        self.fallback_model = RuleBasedCognitiveModel()
        self.register_model(self.fallback_model)
        if default_model is not None:
            self.register_model(default_model)

    def register_model(self, model: CognitiveModel) -> None:
        self._models[model.model_id] = model

    def select_model(
        self,
        request: ModelRequest,
        execution_mode: ExecutionMode,
        budget: ResourceBudget,
        prefer_offline: bool = False,
    ) -> CognitiveModel:
        is_online = execution_mode in (ExecutionMode.ONLINE_FULL, ExecutionMode.ONLINE_DEGRADED)

        # 1. Filter ready models
        ready_models: List[CognitiveModel] = [
            m for m in self._models.values() if m.is_ready()
        ]

        # 2. Filter by network requirement
        if not is_online or prefer_offline or not budget.allow_network:
            ready_models = [
                m for m in ready_models
                if not m.estimate_cost(request).requires_network
            ]

        # 3. Filter by memory budget
        valid_models = [
            m for m in ready_models
            if m.estimate_cost(request).estimated_memory_mb <= budget.max_memory_mb
        ]

        if valid_models:
            # Pick non-fallback if available, else fallback
            non_fallback = [m for m in valid_models if m.model_id != self.fallback_model.model_id]
            if non_fallback:
                return non_fallback[0]
            return valid_models[0]

        logger.warning("No fitting model found in router; using fallback rule-based model.")
        return self.fallback_model
