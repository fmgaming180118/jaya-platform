"""Runtime dispatcher for dependency-ready advanced local pillar capabilities."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jaya_core.capabilities.manifest import CapabilityManifest

from .agentic_rag_capability import (
    RAG_CAPABILITY_ID,
    AgenticRAGCapability,
    OllamaGroundedAnswerProvider,
)
from .control_capabilities import (
    HYBRID_CAPABILITY_ID,
    INTENT_CAPABILITY_ID,
    OBJECTIVE_CAPABILITY_ID,
    DynamicObjectiveCapability,
    HybridRoutingCapability,
    IntentExtrapolationCapability,
)
from .distributed_capabilities import (
    COLLECTIVE_EVIDENCE_CAPABILITY_ID,
    TWIN_TRANSFER_CAPABILITY_ID,
    CollectiveEvidenceCapability,
    TwinMigrationCapability,
)
from .foundation_capabilities import (
    SPARSE_CAPABILITY_ID,
    ActivationSparsityCapability,
    SandboxedImaginationCapability,
)
from .local_capabilities import LocalPillarError, LocalPillarResult
from .maintenance_capabilities import (
    BOOTSTRAP_CAPABILITY_ID,
    LEGACY_CAPABILITY_ID,
    REGENERATION_CAPABILITY_ID,
    LegacyProtocolCapability,
    NeuralRegenerationCapability,
    SelfBootstrappingCapability,
)
from .media_capability import MEDIA_CAPABILITY_ID, MediaObservationCapability
from .moe_capability import MOE_CAPABILITY_ID, DynamicSparsityMoECapability
from .reasoning_capabilities import (
    DREAM_CAPABILITY_ID,
    META_PLANNING_CAPABILITY_ID,
    SPECULATIVE_CAPABILITY_ID,
    ActiveDreamingCapability,
    MetaPlanningCapability,
    OllamaHypothesisProvider,
    SpeculativeReasoningCapability,
)

ADVANCED_CAPABILITY_IDS = frozenset(
    {
        MEDIA_CAPABILITY_ID,
        RAG_CAPABILITY_ID,
        DREAM_CAPABILITY_ID,
        SPECULATIVE_CAPABILITY_ID,
        META_PLANNING_CAPABILITY_ID,
        INTENT_CAPABILITY_ID,
        OBJECTIVE_CAPABILITY_ID,
        HYBRID_CAPABILITY_ID,
        MOE_CAPABILITY_ID,
        REGENERATION_CAPABILITY_ID,
        BOOTSTRAP_CAPABILITY_ID,
        LEGACY_CAPABILITY_ID,
        TWIN_TRANSFER_CAPABILITY_ID,
        COLLECTIVE_EVIDENCE_CAPABILITY_ID,
    }
)

INTEGRATED_REASONING_PILLARS = (
    "P003",
    "P023",
    "P033",
    "P036",
    "P037",
    "P038",
    "P039",
)


class AdvancedPillarCapabilityService:
    """Own advanced capability providers and expose validated runtime dispatch."""

    def __init__(
        self,
        data_dir: Path,
        *,
        media_root: Path | None = None,
        ollama_base_url: str | None = None,
        local_model_name: str | None = None,
        model_timeout_seconds: float = 60.0,
        sandbox: SandboxedImaginationCapability | None = None,
        control_approval_key: bytes | None = None,
        expert_root: Path | None = None,
        expert_signing_key: bytes | None = None,
        sparse: ActivationSparsityCapability | None = None,
        maintenance_key: bytes | None = None,
        node_id: str = "local-node",
        twin_shared_secret: str | None = None,
        twin_allowed_peers: tuple[str, ...] = (),
    ) -> None:
        root = data_dir.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.media = MediaObservationCapability(
            root=(media_root or root / "media-inputs"),
            database_path=root / "media_observations.sqlite3",
        )
        provider = (
            OllamaGroundedAnswerProvider(
                base_url=ollama_base_url,
                model=local_model_name,
                timeout_seconds=model_timeout_seconds,
            )
            if ollama_base_url and local_model_name
            else None
        )
        self.rag = AgenticRAGCapability(root / "agentic_rag.sqlite3", provider)
        active_sandbox = sandbox or SandboxedImaginationCapability()
        hypothesis_provider = (
            OllamaHypothesisProvider(
                base_url=ollama_base_url,
                model=local_model_name,
                timeout_seconds=model_timeout_seconds,
            )
            if ollama_base_url and local_model_name
            else None
        )
        self.dream = ActiveDreamingCapability(
            root / "active_dreaming.sqlite3",
            self.rag,
            active_sandbox,
            hypothesis_provider,
        )
        self.speculative = SpeculativeReasoningCapability(
            root / "speculative_reasoning.sqlite3", self.rag, active_sandbox
        )
        self.meta_planning = MetaPlanningCapability(
            root / "meta_planning.sqlite3", self.rag, active_sandbox, self.speculative
        )
        self.intent = IntentExtrapolationCapability(root / "intent_extrapolation.sqlite3")
        self.objective = DynamicObjectiveCapability(
            root / "dynamic_objective.sqlite3",
            control_approval_key,
            self.rag,
            active_sandbox,
        )
        self.meta_planning.objective_resolver = self.objective.active
        self.hybrid = HybridRoutingCapability(
            root / "hybrid_routing.sqlite3", self.rag, active_sandbox, self.media
        )
        self.moe = DynamicSparsityMoECapability(
            expert_root=expert_root or root / "experts",
            database_path=root / "dynamic_moe.sqlite3",
            signing_key=expert_signing_key,
        )
        self.sparse = sparse or ActivationSparsityCapability(database_path=root / "activation_sparsity.sqlite3")
        maintenance_root = root / "maintenance"
        self.regeneration = NeuralRegenerationCapability(
            maintenance_root / "recovery",
            root / "neural_regeneration.sqlite3",
            maintenance_key,
        )
        self.bootstrap = SelfBootstrappingCapability(
            maintenance_root / "bootstrap",
            root / "self_bootstrap.sqlite3",
            maintenance_key,
            self.rag,
        )
        self.legacy = LegacyProtocolCapability(
            maintenance_root / "migration",
            root / "legacy_protocol.sqlite3",
            maintenance_key,
        )
        self.twin_transfer = TwinMigrationCapability(
            node_id=node_id,
            root=root / "twin-node",
            database_path=root / "twin_transfer.sqlite3",
            shared_secret=twin_shared_secret,
            allowed_peers=twin_allowed_peers,
        )
        self.collective_evidence = CollectiveEvidenceCapability(
            node_id=node_id,
            database_path=root / "collective_evidence.sqlite3",
            shared_secret=twin_shared_secret,
            allowed_peers=twin_allowed_peers,
            rag=self.rag,
        )

    def manifests(self) -> tuple[CapabilityManifest, ...]:
        return (
            CapabilityManifest(
                capability_id=MEDIA_CAPABILITY_ID,
                version="1.0",
                provider="ffprobe_media_adapter",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["filesystem_read", "process_execute", "persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if self.media.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=RAG_CAPABILITY_ID,
                version="1.0",
                provider="ollama_grounded_rag",
                execution_location="local",
                min_memory_mb=1024,
                permissions_required=["persistent_storage", "local_model_connect"],
                offline_available=True,
                health_status="HEALTHY" if self.rag.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=DREAM_CAPABILITY_ID,
                version="1.0",
                provider="ollama_sandboxed_dreaming",
                execution_location="local",
                min_memory_mb=1024,
                permissions_required=["persistent_storage", "local_model_connect", "process_execute"],
                offline_available=True,
                health_status="HEALTHY" if self.dream.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=SPECULATIVE_CAPABILITY_ID,
                version="1.0",
                provider="independent_local_verifiers",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["persistent_storage", "process_execute"],
                offline_available=True,
                health_status="HEALTHY" if self.speculative.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=META_PLANNING_CAPABILITY_ID,
                version="1.0",
                provider="bounded_local_plan_executor",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["persistent_storage", "process_execute"],
                offline_available=True,
                health_status="HEALTHY" if self.meta_planning.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=INTENT_CAPABILITY_ID,
                version="1.0",
                provider="consent_bound_transition_model",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if self.intent.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=OBJECTIVE_CAPABILITY_ID,
                version="1.0",
                provider="signed_bounded_objective_store",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["persistent_storage", "owner_approval"],
                offline_available=True,
                health_status="HEALTHY" if self.objective.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=HYBRID_CAPABILITY_ID,
                version="1.0",
                provider="live_local_capability_router",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["persistent_storage", "process_execute"],
                offline_available=True,
                health_status="HEALTHY" if self.hybrid.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=MOE_CAPABILITY_ID,
                version="1.0",
                provider="signed_numpy_expert_runtime",
                execution_location="local",
                min_memory_mb=64,
                permissions_required=["filesystem_read", "persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if self.moe.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=SPARSE_CAPABILITY_ID,
                version="1.0",
                provider="numpy_topk_sparse_kernel",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=[],
                offline_available=True,
                health_status=(
                    "HEALTHY"
                    if self.moe.health_check() and self.sparse.health_check()
                    else "UNHEALTHY"
                ),
            ),
            CapabilityManifest(
                capability_id=REGENERATION_CAPABILITY_ID,
                version="1.0",
                provider="encrypted_local_recovery",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["filesystem_read", "filesystem_write", "persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if self.regeneration.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=BOOTSTRAP_CAPABILITY_ID,
                version="1.0",
                provider="signed_declarative_bootstrap",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["filesystem_write", "persistent_storage", "owner_approval"],
                offline_available=True,
                health_status="HEALTHY" if self.bootstrap.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=LEGACY_CAPABILITY_ID,
                version="1.0",
                provider="encrypted_one_way_legacy_migrator",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["filesystem_read", "filesystem_write", "persistent_storage", "owner_approval"],
                offline_available=True,
                health_status="HEALTHY" if self.legacy.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=TWIN_TRANSFER_CAPABILITY_ID,
                version="2.0",
                provider="resumable_tcp_aesgcm_transfer",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["network_loopback", "filesystem_read", "filesystem_write", "persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if self.twin_transfer.health_check() else "UNHEALTHY",
            ),
            CapabilityManifest(
                capability_id=COLLECTIVE_EVIDENCE_CAPABILITY_ID,
                version="1.0",
                provider="signed_robust_evidence_aggregation",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["persistent_storage", "peer_evidence"],
                offline_available=True,
                health_status=(
                    "HEALTHY" if self.collective_evidence.health_check() else "UNHEALTHY"
                ),
            ),
        )

    def execute(self, capability_id: str, request: Mapping[str, Any]) -> LocalPillarResult:
        if capability_id == MEDIA_CAPABILITY_ID:
            return self.media.execute(request)
        if capability_id == RAG_CAPABILITY_ID:
            return self.rag.execute(request)
        if capability_id == DREAM_CAPABILITY_ID:
            return self.dream.execute(request)
        if capability_id == SPECULATIVE_CAPABILITY_ID:
            return self.speculative.execute(request)
        if capability_id == META_PLANNING_CAPABILITY_ID:
            return self.meta_planning.execute(request)
        if capability_id == INTENT_CAPABILITY_ID:
            return self.intent.execute(request)
        if capability_id == OBJECTIVE_CAPABILITY_ID:
            return self.objective.execute(request)
        if capability_id == HYBRID_CAPABILITY_ID:
            return self.hybrid.execute(request)
        if capability_id == MOE_CAPABILITY_ID:
            return self.moe.execute(request)
        if capability_id == REGENERATION_CAPABILITY_ID:
            return self.regeneration.execute(request)
        if capability_id == BOOTSTRAP_CAPABILITY_ID:
            return self.bootstrap.execute(request)
        if capability_id == LEGACY_CAPABILITY_ID:
            return self.legacy.execute(request)
        if capability_id == TWIN_TRANSFER_CAPABILITY_ID:
            return self.twin_transfer.execute(request)
        if capability_id == COLLECTIVE_EVIDENCE_CAPABILITY_ID:
            return self.collective_evidence.execute(request)
        raise LocalPillarError("CAPABILITY_UNAVAILABLE", "advanced pillar is not registered")

    def integrated_reasoning_health(self) -> dict[str, bool]:
        """Probe every production dependency used by the integrated reasoning slice."""
        return {
            "P003_ACTIVE_DREAMING": self.dream.health_check(),
            "P023_SANDBOXED_IMAGINATION": self.dream.sandbox.health_check(),
            "P033_AGENTIC_RAG": self.rag.health_check(),
            "P036_SPECULATIVE_REASONING": self.speculative.health_check(),
            "P037_HYBRID_INTELLIGENCE": self.hybrid.health_check(),
            "P038_META_COGNITIVE_PLANNING": self.meta_planning.health_check(),
            "P039_DYNAMIC_OBJECTIVE": self.objective.health_check(),
        }

    @staticmethod
    def _validate_reasoning_cycle_request(request: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "source_ref",
            "title",
            "content",
            "topic",
            "query",
            "constraints",
            "candidate_limit",
            "seed",
            "goal",
            "owner_id",
            "objective_id",
            "weights",
        }
        required = allowed - {"candidate_limit", "seed"}
        unknown = set(request) - allowed
        missing = required - set(request)
        if unknown:
            raise LocalPillarError(
                "UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise LocalPillarError(
                "MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}"
            )
        text_limits = {
            "source_ref": (1, 512),
            "title": (1, 512),
            "content": (1, AgenticRAGCapability.MAX_SOURCE_BYTES),
            "topic": (3, 1_000),
            "query": (1, 1_000),
            "goal": (8, 2_000),
            "owner_id": (1, 128),
            "objective_id": (1, 128),
        }
        normalized = dict(request)
        for field, (minimum, maximum) in text_limits.items():
            value = request[field]
            if not isinstance(value, str):
                raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
            value = " ".join(value.strip().split())
            if not minimum <= len(value) <= maximum:
                raise LocalPillarError(
                    "INVALID_INPUT",
                    f"{field} must contain {minimum}-{maximum} characters",
                )
            normalized[field] = value
        if len(normalized["content"].encode("utf-8")) > AgenticRAGCapability.MAX_SOURCE_BYTES:
            raise LocalPillarError("RESOURCE_LIMIT", "content exceeds 1 MiB")
        constraints = request["constraints"]
        if not isinstance(constraints, list) or not 1 <= len(constraints) <= 16:
            raise LocalPillarError(
                "RESOURCE_LIMIT", "constraints must contain 1-16 expressions"
            )
        if any(not isinstance(item, str) or not item.strip() for item in constraints):
            raise LocalPillarError("INVALID_INPUT", "constraints must be non-empty text")
        weights = request["weights"]
        if not isinstance(weights, Mapping) or not 1 <= len(weights) <= 32:
            raise LocalPillarError("INVALID_INPUT", "weights must contain 1-32 entries")
        candidate_limit = request.get("candidate_limit", 3)
        seed = request.get("seed", 0)
        if type(candidate_limit) is not int or not 1 <= candidate_limit <= 8:
            raise LocalPillarError("RESOURCE_LIMIT", "candidate_limit must be 1-8")
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise LocalPillarError("INVALID_INPUT", "seed is invalid")
        normalized["candidate_limit"] = candidate_limit
        normalized["seed"] = seed
        normalized["constraints"] = list(constraints)
        normalized["weights"] = dict(weights)
        return normalized

    def execute_integrated_reasoning_cycle(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Run the canonical evidence-to-plan vertical slice over real providers."""
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        payload = self._validate_reasoning_cycle_request(request)
        health = self.integrated_reasoning_health()
        unavailable = [name for name, ready in health.items() if not ready]
        if unavailable:
            raise LocalPillarError(
                "PROVIDER_UNAVAILABLE",
                f"integrated reasoning dependencies unavailable: {', '.join(unavailable)}",
            )

        # Validate every sandbox expression and objective weight before the first write.
        for expression in payload["constraints"]:
            checked = self.dream.sandbox.evaluate(expression).data["result"]
            if type(checked) is not bool:
                raise LocalPillarError(
                    "INVALID_CONSTRAINT", "constraint must return boolean"
                )
            if not checked:
                raise LocalPillarError(
                    "CONSTRAINT_REJECTED", "one or more cycle constraints failed"
                )
        _ = self.objective._weights(payload["weights"])
        try:
            self.objective.active(payload["objective_id"])
        except LocalPillarError as exc:
            if exc.code != "OBJECTIVE_NOT_FOUND":
                raise
        else:
            raise LocalPillarError("OBJECTIVE_EXISTS", "objective_id already exists")

        ingested = self.rag.execute(
            {
                "action": "ingest",
                "source_ref": payload["source_ref"],
                "title": payload["title"],
                "content": payload["content"],
            }
        )
        routed = self.hybrid.execute(
            {
                "action": "route",
                "request_kind": "grounded_answer",
                "sensitivity": "internal",
                "payload": {"question": payload["query"]},
            }
        )
        dreamed = self.dream.execute(
            {
                "action": "dream",
                "topic": payload["topic"],
                "query": payload["query"],
                "constraints": payload["constraints"],
                "candidate_limit": payload["candidate_limit"],
                "seed": payload["seed"],
            }
        )
        verified = self.speculative.execute(
            {"action": "evaluate", "candidates": dreamed.data["candidates"]}
        )
        if verified.data["selected"] is None:
            raise LocalPillarError(
                "NO_CANDIDATE_VERIFIED", "no hypothesis passed citation and invariant checks"
            )
        objective = self.objective.execute(
            {
                "action": "create",
                "objective_id": payload["objective_id"],
                "owner_id": payload["owner_id"],
                "owner_goal": payload["goal"],
                "invariants": payload["constraints"],
                "weights": payload["weights"],
            }
        )
        plan = self.meta_planning.execute(
            {
                "action": "run",
                "objective_id": payload["objective_id"],
                "goal": payload["goal"],
                "invariants": payload["constraints"],
                "steps": [
                    {
                        "type": "retrieve",
                        "query": payload["query"],
                        "minimum_results": 1,
                    },
                    {"type": "speculate", "candidates": dreamed.data["candidates"]},
                ],
                "maximum_steps": 2,
            }
        )
        if plan.data["status"] != "COMPLETED":
            raise LocalPillarError("PLAN_FAILED", "integrated reasoning plan did not complete")

        return {
            "cycle_id": uuid.uuid4().hex,
            "status": "INTEGRATED_REASONING_CYCLE_COMPLETED",
            "pillars": list(INTEGRATED_REASONING_PILLARS),
            "dependency_health": health,
            "evidence": ingested.data,
            "grounded_answer": routed.data,
            "hypothesis_artifact": dreamed.data,
            "verification": {
                **verified.data,
                "scope": "CITATION_AND_SANDBOX_INVARIANTS_ONLY",
                "empirical_status": "UNVERIFIED",
            },
            "objective": objective.data,
            "plan": plan.data,
            "warning": "MODEL_HYPOTHESES_ARE_NOT_EMPIRICAL_DISCOVERIES",
        }

    def close(self) -> None:
        self.twin_transfer.close()
        self.rag.close()
        close_dream = getattr(self.dream, "close", None)
        if callable(close_dream):
            close_dream()
        close_hypothesis_provider = getattr(self.dream.provider, "close", None)
        if callable(close_hypothesis_provider):
            close_hypothesis_provider()
