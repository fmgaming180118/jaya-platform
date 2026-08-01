"""
runtime.py — JayaCoreRuntime: Main portable cognitive engine for JAYA Core.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.capabilities.manifest import CapabilityManifest
from src.capabilities.negotiation import CapabilityNegotiator, NegotiationResultStatus
from src.capabilities.registry import CapabilityRegistry
from src.identity.models import AuthorityLevel, JayaIdentity, NodeClass, NodeIdentity, NodeRole
from src.identity.verifier import LocalIdentityVerifier
from src.memory.episodic import EpisodicMemoryStore
from src.memory.events import MemoryEvent
from src.memory.working import WorkingMemory
from src.models.protocol import ModelRequest
from src.models.router import ModelRouter
from src.resources.budget import ResourceBudgetCalculator
from src.resources.modes import ExecutionMode, ExecutionModeController
from src.resources.profiler import ResourceProfiler

from .context import ContextManager, ContextSnapshot
from .decision import DecisionGate
from .evaluation import ActionEvaluator
from .intent import IntentEngine
from .planner import GenericHierarchicalPlanner
from .contracts import (
    ActionResult,
    ActionStep,
    EvaluationResult,
    Goal,
    IntentType,
    JayaIRAction,
    JayaIRRequest,
    ResourceBudget,
    UserRequest,
)

logger = logging.getLogger(__name__)


@dataclass
class CoreResponse:
    request_id: str
    status: str  # "SUCCESS", "CAPABILITY_UNAVAILABLE", "OFFLOAD_REQUIRED", "REQUIRES_APPROVAL", "FAILED"
    message: str
    execution_mode: str
    intent_type: str
    jayair_request: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JayaCoreRuntime:
    """Portable, domain-neutral Cognitive Engine runtime for JAYA Core."""

    def __init__(
        self,
        db_path: Path | str = ":memory:",
        node_id: str = "local-node",
        jaya_identity_id: str = "jaya-master",
        node_class: NodeClass = NodeClass.STANDARD,
    ) -> None:
        # Identity
        self.master_identity = JayaIdentity(identity_id=jaya_identity_id, owner_id="owner")
        self.node_identity = NodeIdentity(
            node_id=node_id,
            jaya_identity_id=jaya_identity_id,
            node_class=node_class,
            role=NodeRole.PERSONAL_WORKSTATION_NODE,
            authority=AuthorityLevel.STANDARD_WORKER,
        )
        self.identity_verifier = LocalIdentityVerifier(self.master_identity)
        self.identity_verifier.register_node(self.node_identity)

        # Resources & Modes
        self.profiler = ResourceProfiler()
        self.budget_calculator = ResourceBudgetCalculator()
        self.mode_controller = ExecutionModeController()

        # Capabilities
        self.capability_registry = CapabilityRegistry()
        self.negotiator = CapabilityNegotiator(self.capability_registry)
        self._register_default_capabilities()

        # Models
        self.model_router = ModelRouter()

        # Memory
        self.episodic_memory = EpisodicMemoryStore(db_path=db_path)
        self.working_memory = WorkingMemory(session_id="default_session")

        # Cognitive Pipeline
        self.intent_engine = IntentEngine()
        self.context_manager = ContextManager()
        self.planner = GenericHierarchicalPlanner()
        self.decision_gate = DecisionGate()
        self.evaluator = ActionEvaluator()

        self._is_ready = True
        logger.info("JayaCoreRuntime initialized on node '%s' (%s)", node_id, node_class.value)

    def _register_default_capabilities(self) -> None:
        """Register default built-in capabilities."""
        self.capability_registry.register(
            CapabilityManifest(
                capability_id="text.reasoning.basic",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            )
        )
        self.capability_registry.register(
            CapabilityManifest(
                capability_id="system.file.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_read"],
                offline_available=True,
            )
        )

    def is_ready(self) -> bool:
        return self._is_ready

    def process(
        self,
        request: UserRequest,
        known_remote_capabilities: Optional[dict[str, list[str]]] = None,
    ) -> CoreResponse:
        """Process a UserRequest through the full cognitive pipeline."""
        if not self.is_ready():
            return CoreResponse(
                request_id=request.request_id,
                status="FAILED",
                message="Runtime is not ready",
                execution_mode=self.mode_controller.current_mode.value,
                intent_type="UNKNOWN",
            )

        # 1. Profile Resource & Determine Execution Mode
        profile = self.profiler.profile()
        execution_mode = self.mode_controller.auto_determine_mode(profile)
        budget = self.budget_calculator.calculate(profile)

        # 2. Detect Intent
        intent = self.intent_engine.detect_intent(
            request.raw_prompt, context=request.active_context
        )

        # 3. Retrieve Memory & Build Bounded Context
        recent_events = self.episodic_memory.get_recent_events(limit=10)
        snapshot = self.context_manager.build_snapshot(
            session_id=request.user_id,
            user_prompt=request.raw_prompt,
            node_identity=self.node_identity,
            resource_profile=profile,
            execution_mode=execution_mode,
            recent_events=recent_events,
            extra_context=request.active_context,
        )

        # 4. Create Goal & Action Plan
        goal_id = f"goal-{request.request_id[:8]}"
        goal = Goal(
            goal_id=goal_id,
            title=request.raw_prompt,
            intent_type=intent.intent_type,
            domain=intent.domain,
            constraints=intent.extracted_entities,
        )

        plan = self.planner.create_plan(goal)

        # 5. Capability Negotiation & Step Evaluation
        jayair_steps: List[JayaIRAction] = []
        approval_before: List[str] = []
        required_caps: List[str] = []
        status = "SUCCESS"
        response_msg = ""

        for step in plan.steps:
            dec = self.decision_gate.evaluate_step(step)
            if not dec.allowed:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message=f"Step '{step.step_id}' blocked by decision gate: {dec.reason}",
                    execution_mode=execution_mode.value,
                    intent_type=intent.intent_type.value,
                )

            # Negotiate capability
            neg = self.negotiator.negotiate(
                capability_id=step.required_capability,
                execution_mode=execution_mode,
                budget=budget,
                known_remote_capabilities=known_remote_capabilities,
            )

            if neg.status == NegotiationResultStatus.CAPABILITY_UNAVAILABLE:
                status = "CAPABILITY_UNAVAILABLE"
                response_msg = (
                    f"Kemampuan '{step.required_capability}' tidak tersedia pada node ini "
                    f"maupun node remote (Mode: {execution_mode.value})."
                )
                break
            elif neg.status == NegotiationResultStatus.OFFLOAD_TO_NODE:
                status = "OFFLOAD_REQUIRED"
                response_msg = (
                    f"Kemampuan '{step.required_capability}' memerlukan offload ke node '{neg.target_node}'."
                )

            exec_target = neg.target_node
            required_caps.append(step.required_capability)
            if step.approval_required or dec.requires_user_approval:
                approval_before.append(step.step_id)

            jayair_steps.append(
                JayaIRAction(
                    step_id=step.step_id,
                    action=step.action_type,
                    capability=step.required_capability,
                    execution_target=exec_target,
                    approval_required=step.approval_required or dec.requires_user_approval,
                    risk_class=step.risk_class.value,
                    inputs=step.inputs,
                )
            )

        # Select Model for narrative response
        model_req = ModelRequest(prompt=request.raw_prompt, context=snapshot.to_dict())
        model = self.model_router.select_model(model_req, execution_mode, budget)
        model_resp = model.generate(model_req)

        if not response_msg:
            response_msg = model_resp.text

        # Build JayaIR Request
        jayair = JayaIRRequest(
            request_id=request.request_id,
            schema_version="1.0",
            goal={"goal_id": goal_id, "title": goal.title, "domain": goal.domain},
            constraints=goal.constraints,
            required_capabilities=required_caps,
            steps=jayair_steps,
            resource_budget=budget,
            approval_required_before=approval_before,
        )

        # Record Episodic Event
        event_id = f"evt-{request.request_id[:8]}-{int(datetime.now(timezone.utc).timestamp()*1000)}"
        mem_event = MemoryEvent(
            event_id=event_id,
            event_type="COGNITIVE_REQUEST_PROCESSED",
            session_id=request.user_id,
            goal_id=goal_id,
            payload={
                "intent": intent.to_dict(),
                "status": status,
                "execution_mode": execution_mode.value,
                "step_count": len(jayair_steps),
            },
            node_id=self.node_identity.node_id,
        )
        self.episodic_memory.append_event(mem_event)

        return CoreResponse(
            request_id=request.request_id,
            status=status,
            message=response_msg,
            execution_mode=execution_mode.value,
            intent_type=intent.intent_type.value,
            jayair_request=jayair.to_dict(),
            metadata={
                "node_id": self.node_identity.node_id,
                "node_class": profile.node_class.value,
                "available_memory_mb": profile.available_memory_mb,
                "model_id": model.model_id,
                "clarification_required": intent.clarification_required,
                "missing_context": intent.missing_context,
            },
        )

    def chat(self, message: str) -> str:
        """Helper method for backward compatibility with legacy string-based chat endpoints."""
        req_id = f"req-chat-{int(datetime.now(timezone.utc).timestamp()*1000)}"
        req = UserRequest(request_id=req_id, raw_prompt=message)
        resp = self.process(req)
        return resp.message

    def process_action_result(self, result: ActionResult, total_steps: int = 1) -> CoreResponse:
        """Processes execution result returned from JAYA Agent."""
        eval_res = self.evaluator.evaluate(result, total_steps_in_plan=total_steps)

        # Record event
        event_id = f"evt-result-{result.step_id}-{int(datetime.now(timezone.utc).timestamp()*1000)}"
        mem_event = MemoryEvent(
            event_id=event_id,
            event_type="ACTION_RESULT_EVALUATED",
            session_id="default",
            goal_id="default",
            payload={
                "result": result.to_dict(),
                "evaluation": eval_res.to_dict(),
            },
            node_id=self.node_identity.node_id,
        )
        self.episodic_memory.append_event(mem_event)

        status_str = "SUCCESS" if eval_res.is_goal_achieved else ("FAILED" if eval_res.should_replan else "IN_PROGRESS")

        return CoreResponse(
            request_id=result.request_id,
            status=status_str,
            message=eval_res.summary,
            execution_mode=self.mode_controller.current_mode.value,
            intent_type="EXECUTE_TASK",
            evaluation=eval_res.to_dict(),
        )
