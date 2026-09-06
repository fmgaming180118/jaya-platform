"""
runtime.py — JayaCoreRuntime: Main portable cognitive engine for JAYA Core.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jaya_core.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
from jaya_core.brain_v2.engine.jaya_ir_translator import logic_request_to_ir
from jaya_core.brain_v2.engine.narrative_continuity import (
    DNAAnchorNarrativeSigner,
    NarrativeContinuity,
    NarrativeContinuityError,
    NarrativeEventType,
    NarrativeFailureCode,
    NarrativeTruthClass,
)
from jaya_core.brain_v2.organism.homeostasis import (
    HomeostasisEventStore,
    HomeostasisState,
    LogicalHomeostasisController,
)
from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
)
from jaya_core.brain_v2.protection.hardware import NodeBindingAuthority, NodeBootReceipt
from jaya_core.brain_v2.protection.zero_trust import (
    ZeroTrustAuthority,
    create_trust_envelope,
)
from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyDecision,
    PolicyEffect,
    PolicyError,
    PolicyRequest,
    PolicyRisk,
    default_core_policy,
)
from jaya_core.capabilities.manifest import CapabilityManifest
from jaya_core.capabilities.negotiation import CapabilityNegotiator, NegotiationResultStatus
from jaya_core.capabilities.puzzle import (
    CapabilityPuzzleRegistry,
    PuzzleManifest,
)
from jaya_core.capabilities.registry import CapabilityRegistry
from jaya_core.identity.models import (
    AuthorityLevel,
    JayaIdentity,
    NodeClass,
    NodeIdentity,
    NodeRole,
)
from jaya_core.identity.verifier import LocalIdentityVerifier
from jaya_core.memory.episodic import EpisodicMemoryStore
from jaya_core.memory.events import MemoryEvent
from jaya_core.memory.working import WorkingMemory
from jaya_core.models.protocol import ModelRequest
from jaya_core.models.router import ModelRouter
from jaya_core.pillars.advanced_capabilities import (
    ADVANCED_CAPABILITY_IDS,
    AdvancedPillarCapabilityService,
)
from jaya_core.pillars.foundation_capabilities import (
    FOUNDATION_CAPABILITY_IDS,
    FoundationPillarCapabilityService,
)
from jaya_core.pillars.local_capabilities import (
    LocalPillarCapabilityService,
    LocalPillarError,
    LocalPillarResult,
)
from jaya_core.pillars.regulation_capabilities import (
    REGULATION_CAPABILITY_IDS,
    CognitiveRegulationCapabilityService,
)
from jaya_core.pillars.ternary_capability import (
    TERNARY_CAPABILITY_ID,
    TernaryPrecisionCapabilityService,
)
from jaya_core.reasoning.pure_logic import (
    LogicFailureCode,
    LogicProofStore,
    LogicResult,
    PureLogicError,
    PureLogicService,
    PureLogicSolver,
)
from jaya_core.resources.budget import ResourceBudgetCalculator
from jaya_core.resources.modes import ExecutionModeController
from jaya_core.resources.profiler import ResourceProfiler
from jaya_core.security.capsule import CapsuleKind, JayaCapsuleCodec
from jaya_core.security.cryptographic_skin import (
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
    SealedEnvelope,
)
from jaya_core.security.immune_system import ImmuneSystem
from jaya_core.security.quantum_lifecycle import PersistentQuantumAuthority
from jaya_core.security.sovereign_privacy import (
    DataClassification,
    DataDestination,
    DataPurpose,
    PrivacyEffect,
    PrivacyMemoryCodec,
    PrivacyUseRequest,
    SovereignPrivacy,
)

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

    def __init__(self, runtime: JayaCoreRuntime) -> None:
        self._runtime = runtime

    def health_check(self) -> bool:
        return self._runtime.logic_service.is_ready()

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.reason_logic(**payload).to_dict()


@dataclass
class CoreResponse:
    request_id: str
    status: str  # SUCCESS, CAPABILITY_UNAVAILABLE, OFFLOAD_REQUIRED, or FAILED
    message: str
    execution_mode: str
    intent_type: str
    jayair_request: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
        privacy_guard: SovereignPrivacy | None = None,
        privacy_required: bool = False,
        zero_trust_authority: ZeroTrustAuthority | None = None,
        zero_trust_required: bool = False,
        cryptographic_skin: CryptographicSkin | None = None,
        cryptographic_skin_required: bool = False,
        hardware_binding: NodeBindingAuthority | None = None,
        hardware_boot_receipt: NodeBootReceipt | None = None,
        hardware_lock_required: bool = False,
        immune_system: ImmuneSystem | None = None,
        immune_system_required: bool = False,
        quantum_authority: PersistentQuantumAuthority | None = None,
        quantum_security_required: bool = False,
        capsule_codec: JayaCapsuleCodec | None = None,
        pillar_registry: Any | None = None,
        pillar_runtime_view: Any | None = None,
        narrative_db_path: Path | str | None = None,
        narrative_required: bool = False,
        narrative_max_payload_bytes: int = 65_536,
        local_pillar_data_dir: Path | str | None = None,
        lineage_signing_key: bytes | None = None,
        twin_shared_secret: str | None = None,
        local_media_root: Path | str | None = None,
        ollama_base_url: str | None = None,
        local_model_name: str | None = None,
        local_model_timeout_seconds: float = 60.0,
        local_expert_root: Path | str | None = None,
        twin_allowed_peers: tuple[str, ...] = (),
        ternary_model_path: Path | str | None = None,
        ternary_model_sha256: str | None = None,
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
        selected_pillar_data_dir = local_pillar_data_dir
        if selected_pillar_data_dir is None:
            selected_pillar_data_dir = (
                Path.cwd() / ".jaya-local-pillars"
                if str(db_path) == ":memory:"
                else Path(db_path).expanduser().resolve().parent / "pillar_capabilities"
            )
        self.local_pillar_capabilities = LocalPillarCapabilityService(
            data_dir=selected_pillar_data_dir,
            lineage_signing_key=lineage_signing_key,
            cryptographic_skin=cryptographic_skin,
        )
        for manifest in self.local_pillar_capabilities.manifests():
            self.capability_registry.register(manifest)
        self.pillar_registry = pillar_registry
        self.pillar_runtime_view = pillar_runtime_view

        # Models
        self.model_router = ModelRouter()

        # Memory
        self.privacy_guard = privacy_guard
        self.privacy_required = privacy_required
        if privacy_required and privacy_guard is None:
            raise RuntimeError("authorized Core runtime requires Sovereign Privacy")
        self.zero_trust_authority = zero_trust_authority
        self.zero_trust_required = zero_trust_required
        if zero_trust_required and (
            zero_trust_authority is None or identity_anchor is None or privacy_guard is None
        ):
            raise RuntimeError("authorized Core runtime requires Zero Trust and DNA Anchor")
        self.cryptographic_skin = cryptographic_skin
        self.cryptographic_skin_required = cryptographic_skin_required
        if cryptographic_skin_required and cryptographic_skin is None:
            raise RuntimeError("authorized Core runtime requires Cryptographic Skin")
        self.hardware_binding = hardware_binding
        self.hardware_boot_receipt = hardware_boot_receipt
        self.hardware_lock_required = hardware_lock_required
        if hardware_lock_required and (hardware_binding is None or hardware_boot_receipt is None):
            raise RuntimeError("authorized Core runtime requires Hardware Locked")
        self.immune_system = immune_system
        self.immune_system_required = immune_system_required
        if immune_system_required and immune_system is None:
            raise RuntimeError("authorized Core runtime requires Immune System")
        self.quantum_authority = quantum_authority
        self.quantum_security_required = quantum_security_required
        if quantum_security_required and quantum_authority is None:
            raise RuntimeError("authorized Core runtime requires Quantum Security")
        self.capsule_codec = capsule_codec
        memory_codec = PrivacyMemoryCodec(privacy_guard) if privacy_guard is not None else None
        self.episodic_memory = EpisodicMemoryStore(
            db_path=db_path,
            payload_codec=memory_codec,
        )
        self.foundation_pillar_capabilities = FoundationPillarCapabilityService(
            data_dir=Path(selected_pillar_data_dir),
            episodic_memory=self.episodic_memory,
        )
        for manifest in self.foundation_pillar_capabilities.manifests():
            self.capability_registry.register(manifest)
        self.advanced_pillar_capabilities = AdvancedPillarCapabilityService(
            Path(selected_pillar_data_dir),
            media_root=Path(local_media_root) if local_media_root is not None else None,
            ollama_base_url=ollama_base_url,
            local_model_name=local_model_name,
            model_timeout_seconds=local_model_timeout_seconds,
            sandbox=self.foundation_pillar_capabilities.sandbox,
            control_approval_key=lineage_signing_key,
            expert_root=Path(local_expert_root) if local_expert_root is not None else None,
            expert_signing_key=lineage_signing_key,
            sparse=self.foundation_pillar_capabilities.sparse,
            maintenance_key=lineage_signing_key,
            node_id=self.node_identity.node_id,
            twin_shared_secret=twin_shared_secret,
            twin_allowed_peers=twin_allowed_peers,
        )
        for manifest in self.advanced_pillar_capabilities.manifests():
            self.capability_registry.register(manifest)
        self.narrative_required = bool(narrative_required)
        self.narrative_continuity: NarrativeContinuity | None = None
        selected_narrative_path = narrative_db_path
        if selected_narrative_path is None and str(db_path) != ":memory:":
            selected_narrative_path = (
                Path(db_path).expanduser().resolve().parent / "narrative_continuity.sqlite3"
            )
        if identity_anchor is not None and selected_narrative_path is not None:
            self.narrative_continuity = NarrativeContinuity(
                database_path=selected_narrative_path,
                signer=DNAAnchorNarrativeSigner(identity_anchor),
                max_payload_bytes=narrative_max_payload_bytes,
            )
        elif self.narrative_required:
            raise NarrativeContinuityError(
                NarrativeFailureCode.IDENTITY_NOT_CONFIGURED,
                "Narrative Continuity requires DNA Anchor and persistent storage",
            )
        narrative_capability = self.capability_registry.lookup("core.narrative.context")
        if narrative_capability is not None:
            narrative_capability.health_status = (
                "HEALTHY" if self._narrative_is_ready() else "UNHEALTHY"
            )
        self.working_memory = WorkingMemory(session_id="default_session")
        self.logic_service = PureLogicService(
            store=LogicProofStore(db_path),
            solver=logic_solver,
        )
        logic_capability = self.capability_registry.lookup("core.logic.evaluate")
        if logic_capability is not None:
            logic_capability.health_status = (
                "HEALTHY" if self.logic_service.is_ready() else "UNHEALTHY"
            )
        self.homeostasis = LogicalHomeostasisController(HomeostasisEventStore(db_path))
        policy_actor_id = (
            self.master_identity.identity_id if self.identity_mode == "ENROLLED" else "UNENROLLED"
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
            )
            if identity_anchor is not None
            else None,
            attestation_verifier=(
                identity_anchor.verify_attestation if identity_anchor is not None else None
            ),
        )
        self.regulation_pillar_capabilities = CognitiveRegulationCapabilityService(
            Path(selected_pillar_data_dir),
            rag=self.advanced_pillar_capabilities.rag,
            hypothesis_provider=self.advanced_pillar_capabilities.dream.provider,
            ethical_heart=self.ethical_heart,
            actor_brain_id=policy_actor_id,
            node_id=self.node_identity.node_id,
        )
        for manifest in self.regulation_pillar_capabilities.manifests():
            self.capability_registry.register(manifest)
        self.ternary_pillar_capabilities = TernaryPrecisionCapabilityService(
            Path(selected_pillar_data_dir),
            artifact_path=ternary_model_path,
            expected_sha256=ternary_model_sha256,
        )
        self.capability_registry.register(self.ternary_pillar_capabilities.manifest())
        self.puzzle_registry = CapabilityPuzzleRegistry(
            puzzle_dirs,
            authorization_required=True,
            authorization_validator=self._authorizes_capability,
            capsule_codec=capsule_codec,
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
        if zero_trust_authority is not None:
            zero_trust_authority.ensure_principal(
                policy_actor_id,
                self.node_identity.node_id,
                tuple(item.capability_id for item in self.puzzle_registry.capabilities()),
            )
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
            and self._narrative_is_ready()
            and self._pillars_are_ready()
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
        self.capability_registry.register(
            CapabilityManifest(
                capability_id="core.narrative.context",
                version="1.0",
                provider="signed_narrative_ledger",
                execution_location="local",
                min_memory_mb=8,
                offline_available=True,
            )
        )

    def is_ready(self) -> bool:
        return (
            self._is_ready
            and self._identity_is_ready()
            and self._hardware_is_ready()
            and self._immune_is_ready()
            and self._quantum_is_ready()
            and self.episodic_memory.health_check()
            and self.logic_service.is_ready()
            and self.homeostasis.is_ready()
            and self._narrative_is_ready()
            and self._pillars_are_ready()
        )

    def _narrative_is_ready(self) -> bool:
        if self.narrative_continuity is None:
            return not self.narrative_required and self.identity_anchor is None
        return self.narrative_continuity.health_check()

    def _pillars_are_ready(self) -> bool:
        """Fail closed only when a pillar registry was explicitly configured."""
        if self.pillar_registry is None:
            return True
        health_check = getattr(self.pillar_registry, "health_check", None)
        if not callable(health_check):
            return False
        try:
            return bool(health_check())
        except Exception:
            return False

    def reason_logic(
        self,
        *,
        request_id: str,
        facts: list[str],
        rules: list[dict[str, Any]],
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
        if profile.process_memory_mb is None:
            raise PureLogicError(
                LogicFailureCode.RESOURCE_PROBE_UNAVAILABLE,
                "cannot establish the solver process-memory baseline",
            )
        process_memory_ceiling_mb = profile.process_memory_mb + budget.max_memory_mb

        result = self.logic_service.evaluate(
            request_id=request_id,
            facts=facts,
            rules=rules,
            query=query,
            max_process_memory_mb=process_memory_ceiling_mb,
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
        facts: list[str],
        rules: list[dict[str, Any]],
        query: str,
    ) -> dict[str, Any]:
        """Evaluate Pure Logic through Lingua Logica's immutable JayaIR path."""
        graph = logic_request_to_ir(
            request_id=request_id,
            facts=facts,
            rules=rules,
            query=query,
        )
        return self.logic_ir_executor.execute_graph(graph)

    def narrative_boot_context(self, snapshot_version: int | None = None) -> dict[str, Any]:
        """Return only provenance-bearing facts, commitments and labelled inferences."""
        if self.narrative_continuity is None:
            return {
                "available": False,
                "code": NarrativeFailureCode.IDENTITY_NOT_CONFIGURED.value,
            }
        try:
            return {
                "available": True,
                **self.narrative_continuity.boot_context(snapshot_version),
            }
        except NarrativeContinuityError as exc:
            return {"available": False, "code": exc.code.value}

    def record_narrative_rollback(
        self,
        *,
        request_id: str,
        target_snapshot_version: int,
        reason: str,
    ) -> dict[str, Any]:
        """Record logical rollback without mutating or deleting narrative history."""
        if self.narrative_continuity is None:
            return {
                "ok": False,
                "code": NarrativeFailureCode.IDENTITY_NOT_CONFIGURED.value,
            }
        try:
            event = self.narrative_continuity.record_rollback(
                request_id=request_id,
                target_snapshot_version=target_snapshot_version,
                reason=reason,
            )
            return {"ok": True, "event": event.to_dict()}
        except NarrativeContinuityError as exc:
            return {"ok": False, "code": exc.code.value}

    def refresh_puzzles(self) -> dict[str, str]:
        """Discover newly installed puzzles without restarting Core."""
        return self.puzzle_registry.refresh()

    def execute_local_pillar(
        self, capability_id: str, request: Mapping[str, Any]
    ) -> LocalPillarResult:
        """Execute an implemented-local pillar through the canonical runtime."""
        manifest = self.capability_registry.lookup(capability_id)
        if manifest is None or manifest.health_status != "HEALTHY":
            raise LocalPillarError(
                "CAPABILITY_UNAVAILABLE", "local pillar capability is not healthy"
            )
        if capability_id in FOUNDATION_CAPABILITY_IDS:
            return self.foundation_pillar_capabilities.execute(capability_id, request)
        if capability_id in ADVANCED_CAPABILITY_IDS:
            return self.advanced_pillar_capabilities.execute(capability_id, request)
        if capability_id in REGULATION_CAPABILITY_IDS:
            return self.regulation_pillar_capabilities.execute(capability_id, request)
        if capability_id == TERNARY_CAPABILITY_ID:
            return self.ternary_pillar_capabilities.execute(request)
        return self.local_pillar_capabilities.execute(capability_id, request)

    def execute_integrated_reasoning_cycle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Run the canonical evidence-to-plan slice through production capabilities."""
        return self.advanced_pillar_capabilities.execute_integrated_reasoning_cycle(request)

    def execute_integrated_memory_cycle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one source through semantic, temporal, and memory providers."""
        return self.foundation_pillar_capabilities.execute_integrated_memory_cycle(request)

    def execute_integrated_regulation_cycle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Run evidence-grounded exploration through live regulation gates."""
        return self.regulation_pillar_capabilities.execute_integrated_cycle(request)

    def operational_snapshot(self) -> dict[str, Any]:
        """Return sanitized live state for authenticated monitoring."""
        profile = self.profiler.profile()
        pillar_snapshot: dict[str, Any] = {
            "ready": False,
            "code": "PILLAR_REGISTRY_NOT_CONFIGURED",
        }
        if self.pillar_runtime_view is not None:
            snapshot = getattr(self.pillar_runtime_view, "snapshot", None)
            if callable(snapshot):
                try:
                    value = snapshot()
                    if isinstance(value, dict):
                        pillar_snapshot = value
                except Exception:
                    pillar_snapshot = {
                        "ready": False,
                        "code": "PILLAR_SNAPSHOT_FAILED",
                    }
        integrated_reasoning_health = (
            self.advanced_pillar_capabilities.integrated_reasoning_health()
        )
        integrated_memory_health = self.foundation_pillar_capabilities.integrated_memory_health()
        integrated_regulation_health = self.regulation_pillar_capabilities.integrated_health()
        integrated_ternary_health = self.ternary_pillar_capabilities.health_check()
        return {
            "ready": self.is_ready(),
            "node_id": self.node_identity.node_id,
            "brain_id": self.master_identity.identity_id,
            "identity_mode": self.identity_mode,
            "homeostasis_state": self.homeostasis.state.value,
            "logic_proofs": self.logic_service.store.count(),
            "puzzles": len(self.puzzle_registry.capabilities()),
            "pillars": pillar_snapshot,
            "local_pillar_capabilities": (
                {
                    "status": "INTEGRATED",
                    "integrated_reasoning_cycle": {
                        "ready": all(integrated_reasoning_health.values()),
                        "dependencies": integrated_reasoning_health,
                    },
                    "integrated_memory_cycle": {
                        "ready": all(integrated_memory_health.values()),
                        "dependencies": integrated_memory_health,
                    },
                    "integrated_regulation_cycle": {
                        "ready": all(integrated_regulation_health.values()),
                        "dependencies": integrated_regulation_health,
                    },
                    "integrated_ternary_precision": {
                        "ready": integrated_ternary_health,
                        "dependencies": {
                            "P022_TERNARY_PRECISION": integrated_ternary_health,
                        },
                        "status": self.ternary_pillar_capabilities.status(),
                    },
                    "capabilities": {
                        manifest.capability_id: manifest.health_status
                        for manifest in (
                            *self.local_pillar_capabilities.manifests(),
                            *self.foundation_pillar_capabilities.manifests(),
                            *self.advanced_pillar_capabilities.manifests(),
                            *self.regulation_pillar_capabilities.manifests(),
                            self.ternary_pillar_capabilities.manifest(),
                        )
                    },
                }
            ),
            "ethical_heart": self.ethical_heart.status(),
            "sovereign_privacy": (
                self.privacy_guard.status()
                if self.privacy_guard is not None
                else {"ready": False, "mode": "UNCONFIGURED"}
            ),
            "zero_trust": (
                self.zero_trust_authority.status()
                if self.zero_trust_authority is not None
                else {"ready": False, "mode": "UNCONFIGURED"}
            ),
            "cryptographic_skin": (
                self.cryptographic_skin.status()
                if self.cryptographic_skin is not None
                else {"ready": False, "mode": "UNCONFIGURED"}
            ),
            "hardware_locked": (
                self.hardware_binding.status(self.hardware_boot_receipt.brain_id)
                if self.hardware_binding is not None and self.hardware_boot_receipt is not None
                else {"ready": False, "mode": "UNCONFIGURED"}
            ),
            "immune_system": (
                self.immune_system.status()
                if self.immune_system is not None
                else {"ready": False, "mode": "UNCONFIGURED"}
            ),
            "quantum_security": (
                self.quantum_authority.status()
                if self.quantum_authority is not None
                else {"ready": False, "mode": "UNCONFIGURED"}
            ),
            "narrative_continuity": (
                self.narrative_continuity.status()
                if self.narrative_continuity is not None
                else {
                    "available": False,
                    "code": "IDENTITY_NOT_CONFIGURED",
                }
            ),
            "resource_profile": profile.to_dict(),
        }

    def seal_artifact(
        self,
        payload: bytes,
        *,
        purpose: str,
        subject: str,
        content_type: str = "application/octet-stream",
        ttl_seconds: int = 3_600,
    ) -> SealedEnvelope:
        """Seal a Core-owned artifact through the configured P13 boundary."""

        if self.cryptographic_skin is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.NOT_CONFIGURED,
                "Cryptographic Skin is not configured",
            )
        return self.cryptographic_skin.seal(
            payload,
            purpose=purpose,
            subject=subject,
            content_type=content_type,
            ttl_seconds=ttl_seconds,
        )

    def open_artifact(
        self,
        envelope: SealedEnvelope | Mapping[str, object],
    ) -> bytes:
        """Verify and open a Core-owned artifact through P13."""

        if self.cryptographic_skin is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.NOT_CONFIGURED,
                "Cryptographic Skin is not configured",
            )
        return self.cryptographic_skin.open(envelope)

    def seal_capsule(
        self,
        payload: bytes,
        *,
        kind: CapsuleKind,
        subject: str,
    ) -> bytes:
        if self.capsule_codec is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.NOT_CONFIGURED,
                "JAYA capsule boundary is not configured",
            )
        return self.capsule_codec.seal(payload, kind=kind, subject=subject)

    def open_capsule(
        self,
        container: bytes,
        *,
        expected_kind: CapsuleKind,
        expected_subject: str,
    ) -> bytes:
        if self.capsule_codec is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.NOT_CONFIGURED,
                "JAYA capsule boundary is not configured",
            )
        return self.capsule_codec.open(
            container,
            expected_kind=expected_kind,
            expected_subject=expected_subject,
        )

    def _identity_is_ready(self) -> bool:
        if self.identity_anchor is None:
            return not self.identity_required
        try:
            return bool(self.identity_anchor.health_check())
        except DNAAnchorError:
            return False

    def process(
        self,
        request: UserRequest,
        known_remote_capabilities: dict[str, list[str]] | None = None,
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

        narrative_request_event = None
        if self.narrative_continuity is not None:
            try:
                narrative_request_event = self.narrative_continuity.append_event(
                    request_id=f"conversation:{request.request_id}",
                    event_type=NarrativeEventType.CONVERSATION_TURN,
                    truth_class=NarrativeTruthClass.RAW_EVENT,
                    subject="conversation.request",
                    payload={
                        "request_id": request.request_id,
                        "user_id": request.user_id,
                        "raw_prompt": request.raw_prompt,
                        "active_context_keys": sorted(request.active_context),
                    },
                )
            except NarrativeContinuityError as exc:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message="Narrative ledger rejected the request event.",
                    execution_mode=self.mode_controller.current_mode.value,
                    intent_type="UNKNOWN",
                    metadata={"narrative_error": exc.code.value},
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
        trusted_context = dict(request.active_context)
        if self.narrative_continuity is not None:
            try:
                trusted_context["narrative_boot_context"] = self.narrative_continuity.boot_context()
            except NarrativeContinuityError as exc:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message="Narrative boot context failed integrity verification.",
                    execution_mode=execution_mode.value,
                    intent_type=intent.intent_type.value,
                    metadata={"narrative_error": exc.code.value},
                )
        snapshot = self.context_manager.build_snapshot(
            session_id=request.user_id,
            user_prompt=request.raw_prompt,
            node_identity=self.node_identity,
            resource_profile=profile,
            execution_mode=execution_mode,
            recent_events=recent_events,
            extra_context=trusted_context,
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
        jayair_steps: list[JayaIRAction] = []
        approval_before: list[str] = []
        required_caps: list[str] = []
        status = "SUCCESS"
        response_msg = ""

        for step in plan.steps:
            dec = self.decision_gate.evaluate_step(step)
            if not dec.allowed:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message=(f"Step '{step.step_id}' blocked by decision gate: {dec.reason}"),
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
                            f"plan:{request.request_id}:{step.step_id}".encode()
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
            policy_requires_approval = policy_decision.effect is PolicyEffect.REQUIRE_APPROVAL
            if step.approval_required or dec.requires_user_approval or policy_requires_approval:
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
        if self.privacy_guard is not None:
            model_cost = model.estimate_cost(model_req)
            provider_id = str(model.model_id)
            destination = (
                DataDestination.EXTERNAL_PROVIDER
                if model_cost.requires_network
                else DataDestination.LOCAL
            )
            prompt_digest = hashlib.sha256(request.raw_prompt.encode("utf-8")).hexdigest()
            privacy_decision = self.privacy_guard.evaluate(
                PrivacyUseRequest(
                    request_id=hashlib.sha256(f"model:{request.request_id}".encode()).hexdigest(),
                    actor_id=request.user_id,
                    owner_id=request.user_id,
                    subject_id=request.user_id,
                    data_id=f"prompt:{request.request_id}",
                    classification=DataClassification.CONFIDENTIAL,
                    purpose=DataPurpose.MODEL_INFERENCE,
                    destination=destination,
                    provider_id=provider_id,
                    payload_sha256=prompt_digest,
                    consent_id=request.active_context.get("privacy_consent_id"),
                )
            )
            if privacy_decision.effect is PrivacyEffect.DENY:
                model = self.model_router.select_model(
                    model_req,
                    execution_mode,
                    budget,
                    prefer_offline=True,
                )
                if model.estimate_cost(model_req).requires_network:
                    return CoreResponse(
                        request_id=request.request_id,
                        status="FAILED",
                        message="Sovereign Privacy denied external model use.",
                        execution_mode=execution_mode.value,
                        intent_type=intent.intent_type.value,
                        metadata={"privacy_receipt": privacy_decision.to_dict()},
                    )
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
        event_timestamp = int(datetime.now(UTC).timestamp() * 1_000)
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

        if self.narrative_continuity is not None:
            try:
                self.narrative_continuity.append_event(
                    request_id=f"planner:{request.request_id}",
                    event_type=NarrativeEventType.PLANNER_DECISION,
                    truth_class=NarrativeTruthClass.RAW_EVENT,
                    subject="planner.decision",
                    payload={
                        "request_id": request.request_id,
                        "goal_id": goal_id,
                        "intent_type": intent.intent_type.value,
                        "status": status,
                        "required_capabilities": required_caps,
                        "approval_required_before": approval_before,
                    },
                    causation_id=(
                        narrative_request_event.event_id
                        if narrative_request_event is not None
                        else None
                    ),
                )
            except NarrativeContinuityError as exc:
                return CoreResponse(
                    request_id=request.request_id,
                    status="FAILED",
                    message="Narrative ledger rejected the planner event.",
                    execution_mode=execution_mode.value,
                    intent_type=intent.intent_type.value,
                    metadata={"narrative_error": exc.code.value},
                )

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
        req_id = f"req-chat-{int(datetime.now(UTC).timestamp() * 1000)}"
        req = UserRequest(request_id=req_id, raw_prompt=message)
        resp = self.process(req)
        return resp.message

    def process_action_result(self, result: ActionResult, total_steps: int = 1) -> CoreResponse:
        """Processes execution result returned from JAYA Agent."""
        eval_res = self.evaluator.evaluate(result, total_steps_in_plan=total_steps)

        # Record event
        event_timestamp = int(datetime.now(UTC).timestamp() * 1_000)
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

        if self.narrative_continuity is not None:
            try:
                self.narrative_continuity.append_event(
                    request_id=f"action:{result.request_id}:{result.step_id}",
                    event_type=NarrativeEventType.ACTION_RESULT,
                    truth_class=NarrativeTruthClass.RAW_EVENT,
                    subject="agent.action_result",
                    payload={
                        "request_id": result.request_id,
                        "step_id": result.step_id,
                        "evaluation": eval_res.to_dict(),
                    },
                )
            except NarrativeContinuityError as exc:
                return CoreResponse(
                    request_id=result.request_id,
                    status="FAILED",
                    message="Narrative ledger rejected the action result.",
                    execution_mode=self.mode_controller.current_mode.value,
                    intent_type="EXECUTE_TASK",
                    metadata={"narrative_error": exc.code.value},
                )

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

    def _authorizes_capability(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        authorization: object,
    ) -> bool:
        """Require an Ethical Heart receipt and a fresh DNA-bound trust proof."""

        if not self.ethical_heart.authorizes_capability(capability_id, payload, authorization):
            return False
        if self.zero_trust_authority is None:
            return not self.zero_trust_required
        anchor = self.identity_anchor
        privacy = self.privacy_guard
        if anchor is None or privacy is None or not isinstance(authorization, PolicyDecision):
            return False
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            privacy_decision = privacy.evaluate(
                PrivacyUseRequest(
                    request_id=hashlib.sha256(
                        f"capability:{authorization.receipt_sha256}".encode()
                    ).hexdigest(),
                    actor_id=self._policy_actor_id,
                    owner_id=self._policy_actor_id,
                    subject_id=self._policy_actor_id,
                    data_id=f"capability:{capability_id}",
                    classification=DataClassification.CONFIDENTIAL,
                    purpose=DataPurpose.CORE_REASONING,
                    destination=DataDestination.LOCAL,
                    provider_id=capability_id,
                    payload_sha256=hashlib.sha256(encoded).hexdigest(),
                )
            )
            if privacy_decision.effect is not PrivacyEffect.ALLOW:
                return False
            envelope = create_trust_envelope(
                principal_id=self._policy_actor_id,
                node_id=self.node_identity.node_id,
                capability_id=capability_id,
                payload=payload,
                policy_receipt_sha256=authorization.receipt_sha256,
                privacy_receipt_sha256=privacy_decision.receipt_sha256,
                signer=lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict(),
            )
            decision = self.zero_trust_authority.authorize(envelope, payload)
            return self.zero_trust_authority.validates(capability_id, payload, decision)
        except (RuntimeError, TypeError, ValueError):
            return False

    def close(self) -> None:
        """Close all persistent stores owned by this runtime."""
        self.regulation_pillar_capabilities.close()
        self.advanced_pillar_capabilities.close()
        self.puzzle_registry.close()
        self.ethical_heart.close()
        self.episodic_memory.close()
        self.logic_service.close()
        self.homeostasis.close()
        if self.narrative_continuity is not None:
            self.narrative_continuity.close()
        if self.privacy_guard is not None:
            self.privacy_guard.close()
        if self.zero_trust_authority is not None:
            self.zero_trust_authority.close()
        if self.immune_system is not None:
            self.immune_system.close()
        if self.quantum_authority is not None:
            self.quantum_authority.close()
        if self.cryptographic_skin is not None:
            self.cryptographic_skin.close()
        if self.hardware_binding is not None:
            self.hardware_binding.close()
        if self.identity_anchor is not None:
            self.identity_anchor.close()

    def _hardware_is_ready(self) -> bool:
        if self.hardware_binding is None or self.hardware_boot_receipt is None:
            return not self.hardware_lock_required
        return bool(self.hardware_binding.status(self.hardware_boot_receipt.brain_id).get("ready"))

    def _immune_is_ready(self) -> bool:
        if self.immune_system is None:
            return not self.immune_system_required
        return bool(self.immune_system.status().get("ready"))

    def _quantum_is_ready(self) -> bool:
        if self.quantum_authority is None:
            return not self.quantum_security_required
        return bool(self.quantum_authority.status().get("ready"))
