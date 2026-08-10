"""
runtime.py — JayaCoreRuntime: Main portable cognitive engine for JAYA Core.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
from src.brain_v2.engine.jaya_ir_translator import logic_request_to_ir
from src.brain_v2.organism.homeostasis import (
    HomeostasisEventStore,
    HomeostasisState,
    LogicalHomeostasisController,
)
from src.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
)
from src.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyEffect,
    PolicyError,
    PolicyRequest,
    PolicyRisk,
    default_core_policy,
)
from src.capabilities.manifest import CapabilityManifest
from src.capabilities.negotiation import CapabilityNegotiator, NegotiationResultStatus
from src.capabilities.puzzle import (
    CapabilityPuzzleRegistry,
    PuzzleManifest,
)
from src.capabilities.registry import CapabilityRegistry
from src.identity.models import (
    AuthorityLevel,
    JayaIdentity,
    NodeClass,
    NodeIdentity,
    NodeRole,
)
from src.identity.verifier import LocalIdentityVerifier
from src.memory.episodic import EpisodicMemoryStore
from src.memory.events import MemoryEvent
from src.memory.working import WorkingMemory
from src.models.protocol import ModelRequest
from src.models.router import ModelRouter
from src.reasoning.pure_logic import (
    LogicFailureCode,
    LogicProofStore,
    LogicResult,
    PureLogicError,
    PureLogicService,
    PureLogicSolver,
)
from src.resources.budget import ResourceBudgetCalculator
from src.resources.modes import ExecutionModeController
from src.resources.profiler import ResourceProfiler

from .context import ContextManager
from .contracts import (
    ActionResult,
    Goal,
    JayaIRAction,
    JayaIRRequest,
    UserRequest,
)
from .decision import DecisionGate
from .evaluation import ActionEvaluator
from .intent import IntentEngine
from .planner import GenericHierarchicalPlanner

logger = logging.getLogger(__name__)


class _PureLogicPuzzle:
    """Expose Pure Logic through Core's detachable puzzle contract."""

    def __init__(self, runtime: "JayaCoreRuntime") -> None:
        self._runtime = runtime

    def health_check(self) -> bool:
        return self._runtime.logic_service.is_ready()

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._runtime.reason_logic(**payload).to_dict()


@dataclass
class CoreResponse:
    request_id: str
    status: str  # SUCCESS, CAPABILITY_UNAVAILABLE, OFFLOAD_REQUIRED, or FAILED
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
        node_id: str | None = None,
        jaya_identity_id: str | None = None,
        node_class: NodeClass = NodeClass.STANDARD,
        resource_profiler: ResourceProfiler | None = None,
        logic_solver: PureLogicSolver | None = None,
        puzzle_dirs: tuple[Path | str, ...] = (),
        identity_anchor: DNAAnchor | None = None,
        identity_required: bool = False,
        owner_approval_public_keys: dict[str, bytes | str] | None = None,
    ) -> None:
        # Identity
        self.identity_anchor = identity_anchor
        self.identity_required = identity_required
        active_node_id = node_id or platform.node().strip() or f"node-{uuid.uuid4()}"
        if identity_anchor is not None:
            identity_record = identity_anchor.load_identity()
            self.identity_mode = "ENROLLED"
            self.master_identity = JayaIdentity(
                identity_id=identity_record.brain_id,
                owner_id=identity_record.owner_id,
                version=f"1.{identity_record.key_version}",
                created_at=identity_record.created_at,
            )
            identity_fingerprint = identity_record.public_key_fingerprint
            authority = AuthorityLevel.STANDARD_WORKER
        else:
            if identity_required:
                raise DNAAnchorError(
                    DNAFailureCode.IDENTITY_NOT_ENROLLED,
                    "authorized Core runtime requires an enrolled DNA Anchor",
                )
            self.identity_mode = "UNENROLLED"
            self.master_identity = JayaIdentity(
                identity_id=jaya_identity_id or f"unclaimed-{uuid.uuid4()}",
                owner_id="UNENROLLED",
                version="0",
            )
            identity_fingerprint = None
            authority = AuthorityLevel.MICRO_SENSOR
        self.node_identity = NodeIdentity(
            node_id=active_node_id,
            jaya_identity_id=self.master_identity.identity_id,
            node_class=node_class,
            role=NodeRole.PERSONAL_WORKSTATION_NODE,
            authority=authority,
            public_key_fingerprint=identity_fingerprint,
        )
        self.identity_verifier = LocalIdentityVerifier(self.master_identity)
        self.identity_verifier.register_node(self.node_identity)

        # Resources & Modes
        self.profiler = resource_profiler or ResourceProfiler()
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
        self.logic_service = PureLogicService(
            store=LogicProofStore(db_path),
            solver=logic_solver,
        )
        self.homeostasis = LogicalHomeostasisController(HomeostasisEventStore(db_path))
        policy_actor_id = (
            self.master_identity.identity_id
            if self.identity_mode == "ENROLLED"
            else "UNENROLLED"
        )
        self._policy_actor_id = policy_actor_id
        self.ethical_heart = EthicalHeart(
            db_path,
            default_core_policy(policy_actor_id),
            approval_public_keys=owner_approval_public_keys,
            attestation_signer=(
                lambda purpose, digest: identity_anchor.sign_attestation(
                    purpose,
                    digest,
                ).to_dict()
            ) if identity_anchor is not None else None,
            attestation_verifier=(
                identity_anchor.verify_attestation
                if identity_anchor is not None
                else None
            ),
        )
        self.puzzle_registry = CapabilityPuzzleRegistry(
            puzzle_dirs,
            authorization_required=True,
            authorization_validator=self.ethical_heart.authorizes_capability,
        )
        self.puzzle_registry.attach(
            PuzzleManifest(
                puzzle_id="core.pure-logic",
                capability_id="core.logic.evaluate",
                version="1.0.0",
                timeout_seconds=2.0,
                max_payload_bytes=512_000,
                risk_class="READ_ONLY",
            ),
            _PureLogicPuzzle(self),
        )
        self.puzzle_registry.refresh()
        self.logic_ir_executor = JayaIRExecutor(
            logic_service=self.logic_service,
            puzzle_registry=self.puzzle_registry,
            policy_engine=self.ethical_heart,
            actor_brain_id=policy_actor_id,
            node_id=self.node_identity.node_id,
        )

        # Cognitive Pipeline
        self.intent_engine = IntentEngine()
        self.context_manager = ContextManager()
        self.planner = GenericHierarchicalPlanner()
        self.decision_gate = DecisionGate()
        self.evaluator = ActionEvaluator()

        self._is_ready = (
            self.episodic_memory.health_check()
            and self.logic_service.is_ready()
            and self.homeostasis.is_ready()
        )
        logger.info(
            "JayaCoreRuntime initialized on node '%s' (%s)",
            active_node_id,
            node_class.value,
        )

    def _register_default_capabilities(self) -> None:
        """Register default built-in capabilities."""
        self.capability_registry.register(
            CapabilityManifest(
                capability_id="core.reason",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            )
        )
        self.capability_registry.register(
            CapabilityManifest(
                capability_id="core.logic.evaluate",
                version="1.0",
                provider="pure_logic_solver",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            )
        )
        self.capability_registry.register(
            CapabilityManifest(
                capability_id="fs.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_read"],
                offline_available=True,
            )
        )

    def is_ready(self) -> bool:
        return (
            self._is_ready
            and self._identity_is_ready()
            and self.episodic_memory.health_check()
            and self.logic_service.is_ready()
            and self.homeostasis.is_ready()
        )

    def reason_logic(
        self,
        *,
        request_id: str,
        facts: List[str],
        rules: List[Dict[str, Any]],
        query: str,
    ) -> LogicResult:
        """Evaluate and persist one structured Pure Logic request."""
        if not self._identity_is_ready():
            raise PureLogicError(
                LogicFailureCode.RUNTIME_NOT_READY,
                "authorized runtime identity is unavailable",
            )
        profile = self.profiler.profile()
        decision = self.homeostasis.evaluate(
            profile,
            logic_ready=self.logic_service.is_ready(),
            memory_ready=self.episodic_memory.health_check(),
        )
        if decision.state is HomeostasisState.SAFE_STOP:
            raise PureLogicError(
                LogicFailureCode.RUNTIME_NOT_READY,
                f"logical foundation entered SAFE_STOP: {', '.join(decision.reasons)}",
            )
        budget = self.budget_calculator.calculate(profile)

        result = self.logic_service.evaluate(
            request_id=request_id,
            facts=facts,
            rules=rules,
            query=query,
            max_process_memory_mb=budget.max_memory_mb,
        )
        event = MemoryEvent(
            event_id=f"evt-logic-{request_id}",
            event_type="PURE_LOGIC_EVALUATED",
            session_id="logic",
            goal_id=request_id,
            payload={
                "status": result.status.value,
                "query": result.query.key,
                "contradictions": list(result.contradictions),
                "proof_steps": len(result.proof),
            },
            node_id=self.node_identity.node_id,
        )
        self.episodic_memory.append_event(event)
        return result

    def reason_logic_ir(
        self,
        *,
        request_id: str,
        facts: List[str],
        rules: List[Dict[str, Any]],
        query: str,
    ) -> Dict[str, Any]:
        """Evaluate Pure Logic through Lingua Logica's immutable JayaIR path."""
        graph = logic_request_to_ir(
            request_id=request_id,
            facts=facts,
            rules=rules,
            query=query,
        )
        return self.logic_ir_executor.execute_graph(graph)

    def refresh_puzzles(self) -> Dict[str, str]:
        """Discover newly installed puzzles without restarting Core."""
        return self.puzzle_registry.refresh()

    def operational_snapshot(self) -> Dict[str, Any]:
        """Return sanitized live state for authenticated monitoring."""
        profile = self.profiler.profile()
        return {
            "ready": self.is_ready(),
            "node_id": self.node_identity.node_id,
            "brain_id": self.master_identity.identity_id,
            "identity_mode": self.identity_mode,
            "homeostasis_state": self.homeostasis.state.value,
            "logic_proofs": self.logic_service.store.count(),
            "puzzles": len(self.puzzle_registry.capabilities()),
            "ethical_heart": self.ethical_heart.status(),
            "resource_profile": profile.to_dict(),
        }

    def _identity_is_ready(self) -> bool:
        if self.identity_anchor is None:
            return not self.identity_required
        try:
            self.identity_anchor.load_identity()
        except DNAAnchorError:
            return False
        return True

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
        homeostasis = self.homeostasis.evaluate(
            profile,
            logic_ready=self.logic_service.is_ready(),
            memory_ready=self.episodic_memory.health_check(),
        )
        if homeostasis.state is HomeostasisState.SAFE_STOP:
            return CoreResponse(
                request_id=request.request_id,
                status="FAILED",
                message="Logical foundation is in SAFE_STOP.",
                execution_mode=execution_mode.value,
                intent_type="UNKNOWN",
                metadata={
                    "homeostasis": homeostasis.to_dict(),
                    "resource_profile": profile.to_dict(),
                },
            )
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
                    message=(
                        f"Step '{step.step_id}' blocked by decision gate: "
                        f"{dec.reason}"
                    ),
                    execution_mode=execution_mode.value,
                    intent_type=intent.intent_type.value,
                )

            try:
                policy_payload = json.dumps(
                    step.inputs,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                policy_decision = self.ethical_heart.evaluate(
                    PolicyRequest(
                        request_id=hashlib.sha256(
                            f"plan:{request.request_id}:{step.step_id}".encode(
                                "utf-8"
                            )
                        ).hexdigest(),
                        actor_brain_id=self._policy_actor_id,
                        node_id=self.node_identity.node_id,
                        capability_id=step.required_capability,
                        risk_class=PolicyRisk(step.risk_class.value),
                        permissions=(),
                        payload_sha256=hashlib.sha256(policy_payload).hexdigest(),
                        purpose="planner.capability-selection",
                    )
                )
            except (PolicyError, TypeError, ValueError) as exc:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message=f"Ethical Heart unavailable for '{step.step_id}': {exc}",
                    execution_mode=execution_mode.value,
                    intent_type=intent.intent_type.value,
                )
            if policy_decision.effect is PolicyEffect.DENY:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message=(
                        f"Step '{step.step_id}' denied by Ethical Heart: "
                        f"{policy_decision.reason_code}"
                    ),
                    execution_mode=execution_mode.value,
                    intent_type=intent.intent_type.value,
                    metadata={"policy_receipt": policy_decision.to_dict()},
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
                    f"Kemampuan '{step.required_capability}' tidak tersedia "
                    "pada node ini "
                    f"maupun node remote (Mode: {execution_mode.value})."
                )
                break
            elif neg.status == NegotiationResultStatus.OFFLOAD_TO_NODE:
                status = "OFFLOAD_REQUIRED"
                response_msg = (
                    f"Kemampuan '{step.required_capability}' memerlukan offload "
                    f"ke node '{neg.target_node}'."
                )

            exec_target = neg.target_node
            required_caps.append(step.required_capability)
            policy_requires_approval = (
                policy_decision.effect is PolicyEffect.REQUIRE_APPROVAL
            )
            if (
                step.approval_required
                or dec.requires_user_approval
                or policy_requires_approval
            ):
                approval_before.append(step.step_id)

            jayair_steps.append(
                JayaIRAction(
                    step_id=step.step_id,
                    action=step.action_type,
                    capability=step.required_capability,
                    execution_target=exec_target,
                    approval_required=step.approval_required
                    or dec.requires_user_approval
                    or policy_requires_approval,
                    risk_class=step.risk_class.value,
                    inputs=step.inputs,
                    policy_receipt=policy_decision.to_dict(),
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
        event_timestamp = int(datetime.now(timezone.utc).timestamp() * 1_000)
        event_id = f"evt-{request.request_id[:8]}-{event_timestamp}"
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
                "resource_profile": profile.to_dict(),
                "homeostasis": homeostasis.to_dict(),
                "model_id": model.model_id,
                "clarification_required": intent.clarification_required,
                "missing_context": intent.missing_context,
            },
        )

    def chat(self, message: str) -> str:
        """Provide compatibility for legacy string-based chat endpoints."""
        req_id = f"req-chat-{int(datetime.now(timezone.utc).timestamp()*1000)}"
        req = UserRequest(request_id=req_id, raw_prompt=message)
        resp = self.process(req)
        return resp.message

    def process_action_result(
        self, result: ActionResult, total_steps: int = 1
    ) -> CoreResponse:
        """Processes execution result returned from JAYA Agent."""
        eval_res = self.evaluator.evaluate(result, total_steps_in_plan=total_steps)

        # Record event
        event_timestamp = int(datetime.now(timezone.utc).timestamp() * 1_000)
        event_id = f"evt-result-{result.step_id}-{event_timestamp}"
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

        status_str = (
            "SUCCESS"
            if eval_res.is_goal_achieved
            else ("FAILED" if eval_res.should_replan else "IN_PROGRESS")
        )

        return CoreResponse(
            request_id=result.request_id,
            status=status_str,
            message=eval_res.summary,
            execution_mode=self.mode_controller.current_mode.value,
            intent_type="EXECUTE_TASK",
            evaluation=eval_res.to_dict(),
        )

    def close(self) -> None:
        """Close all persistent stores owned by this runtime."""
        self.puzzle_registry.close()
        self.ethical_heart.close()
        self.episodic_memory.close()
        self.logic_service.close()
        self.homeostasis.close()
        if self.identity_anchor is not None:
            self.identity_anchor.close()
