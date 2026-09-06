"""Canonical production wiring for cognitive regulation pillars 6, 7, 10, and 17."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jaya_core.brain_v2.engine.spontaneity import (
    ExplorationBudget,
    ExplorationError,
    ExplorationReceiptStore,
    ExplorationRequest,
    ProviderCandidate,
    ProviderResult,
    SpontaneityEngine,
)
from jaya_core.brain_v2.organism.affective_metabolism import (
    AffectiveMetabolismController,
    AffectiveSignal,
    AffectiveSignalConflict,
    ControlSignalSource,
)
from jaya_core.brain_v2.organism.cognitive_silence import (
    CognitiveSilenceController,
    CognitiveSilenceStore,
    RuntimeService,
)
from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyError,
    PolicyRequest,
    PolicyRisk,
)
from jaya_core.brain_v2.soul.socratic import (
    CandidateDecision,
    EvidenceRecord,
    SocraticAuditStore,
    SocraticError,
    SocraticMirror,
)
from jaya_core.capabilities.manifest import CapabilityManifest
from jaya_core.reasoning.pure_logic import Literal, LogicRule, LogicTheory, PureLogicError

from .agentic_rag_capability import AgenticRAGCapability
from .local_capabilities import LocalPillarError, LocalPillarResult
from .reasoning_capabilities import HypothesisProvider

SPONTANEITY_CAPABILITY_ID = "core.exploration.spontaneous"
SILENCE_CAPABILITY_ID = "core.cognition.silence"
AFFECTIVE_CAPABILITY_ID = "core.control.affective"
SOCRATIC_CAPABILITY_ID = "core.reasoning.socratic"

REGULATION_CAPABILITY_IDS = frozenset(
    {
        SPONTANEITY_CAPABILITY_ID,
        SILENCE_CAPABILITY_ID,
        AFFECTIVE_CAPABILITY_ID,
        SOCRATIC_CAPABILITY_ID,
    }
)

INTEGRATED_REGULATION_PILLARS = ("P006", "P007", "P010", "P017")


def _strict(request: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _text(value: object, field: str, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    normalized = " ".join(value.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT", f"{field} must contain {minimum}-{maximum} characters"
        )
    return normalized


def _ratio(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be numeric")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise LocalPillarError("INVALID_INPUT", f"{field} must be in [0, 1]")
    return normalized


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise LocalPillarError("INVALID_INPUT", f"{field} must be boolean")
    return value


class _GroundedSpontaneityProvider:
    """Adapt the existing grounded Ollama hypothesis provider to P6 receipts."""

    def __init__(self, rag: AgenticRAGCapability, provider: HypothesisProvider) -> None:
        self.rag = rag
        self.provider = provider

    def healthcheck(self) -> Mapping[str, object]:
        return {
            "ok": self.rag.health_check() and self.provider.health_check(),
            "provider": "grounded_local_model",
            "model": self.provider.provider_name,
            "provider_type": self.provider.provider_type,
            "supports_seed": True,
            "network_required": False,
        }

    def generate(
        self,
        *,
        topic: str,
        seed: int,
        budget: ExplorationBudget,
    ) -> ProviderResult:
        started = time.monotonic()
        try:
            evidence = self.rag.retrieve(topic, min(8, budget.max_candidates * 2))
            if not evidence:
                raise ExplorationError(
                    "EVIDENCE_UNAVAILABLE", "spontaneous exploration requires evidence"
                )
            raw_candidates = self.provider.generate(
                topic,
                evidence,
                budget.max_candidates,
                seed,
            )
        except LocalPillarError as exc:
            raise ExplorationError(exc.code, str(exc)) from exc
        candidates: list[ProviderCandidate] = []
        for raw in raw_candidates:
            if not isinstance(raw, Mapping):
                raise ExplorationError("PROVIDER_RESPONSE_INVALID", "candidate is invalid")
            statement = _text(raw.get("statement"), "statement", 2_000, 8)
            falsification = _text(
                raw.get("falsification_test"), "falsification_test", 2_000, 8
            )
            candidates.append(
                ProviderCandidate(
                    hypothesis=statement,
                    rationale=falsification,
                    next_step_type="research",
                )
            )
        if not candidates:
            raise ExplorationError("NO_CANDIDATES", "provider returned no candidates")
        request_material = json.dumps(
            {
                "topic": topic,
                "seed": seed,
                "evidence_ids": [item["evidence_id"] for item in evidence],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        response_material = json.dumps(
            [
                {
                    "hypothesis": item.hypothesis,
                    "rationale": item.rationale,
                    "next_step_type": item.next_step_type,
                }
                for item in candidates
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        return ProviderResult(
            candidates=tuple(candidates),
            provider="ollama_grounded_exploration",
            model=self.provider.provider_name,
            provider_version="api-v1",
            prompt_sha256=hashlib.sha256(request_material.encode("utf-8")).hexdigest(),
            response_sha256=hashlib.sha256(response_material.encode("utf-8")).hexdigest(),
            latency_ms=(time.monotonic() - started) * 1_000.0,
        )


class _RAGEvidenceResolver:
    """Resolve P17 evidence from the canonical persistent RAG catalog."""

    def __init__(self, rag: AgenticRAGCapability) -> None:
        self.rag = rag

    def resolve(
        self, refs: Sequence[str]
    ) -> tuple[tuple[EvidenceRecord, ...], tuple[str, ...]]:
        normalized = tuple(dict.fromkeys(str(ref).strip() for ref in refs))
        records = self.rag.evidence_by_ids(normalized)
        indexed = {str(item["evidence_id"]): item for item in records}
        resolved = tuple(
            EvidenceRecord(
                ref_id=ref,
                source_id=str(indexed[ref]["source_ref"]),
                content_sha256=hashlib.sha256(
                    str(indexed[ref]["content"]).encode("utf-8")
                ).hexdigest(),
                source_type="rag_chunk",
            )
            for ref in normalized
            if ref in indexed
        )
        return resolved, tuple(ref for ref in normalized if ref not in indexed)

    def healthcheck(self) -> Mapping[str, object]:
        return {
            "ok": self.rag.storage_health_check(),
            "provider": "canonical_agentic_rag",
        }


class CognitiveRegulationCapabilityService:
    """Expose existing regulation components through the canonical Core runtime."""

    def __init__(
        self,
        data_dir: Path,
        *,
        rag: AgenticRAGCapability,
        hypothesis_provider: HypothesisProvider | None,
        ethical_heart: EthicalHeart,
        actor_brain_id: str,
        node_id: str,
    ) -> None:
        root = data_dir.expanduser().resolve() / "cognitive-regulation"
        root.mkdir(parents=True, exist_ok=True)
        self.rag = rag
        self.actor_brain_id = actor_brain_id
        self.node_id = node_id
        self.silence = CognitiveSilenceController(
            CognitiveSilenceStore(root / "cognitive_silence.sqlite3")
        )
        self.affective = AffectiveMetabolismController()
        spontaneous_provider = (
            _GroundedSpontaneityProvider(rag, hypothesis_provider)
            if hypothesis_provider is not None
            else None
        )
        self.spontaneity = SpontaneityEngine(
            ExplorationReceiptStore(root / "spontaneity.sqlite3"),
            spontaneous_provider,
        )
        self.socratic = SocraticMirror(
            evidence_resolver=_RAGEvidenceResolver(rag),
            ethical_heart=ethical_heart,
            audit_store=SocraticAuditStore(root / "socratic.sqlite3"),
        )

    def integrated_health(self) -> dict[str, bool]:
        spontaneity_status = self.spontaneity.status()
        socratic_status = self.socratic.status()
        return {
            "P006_STOCHASTIC_SPONTANEITY": bool(
                spontaneity_status["storage"].get("ok")
                and spontaneity_status["provider"].get("ok")
            ),
            "P007_COGNITIVE_SILENCE": bool(
                self.silence.status()["storage"].get("ok")
            ),
            "P010_AFFECTIVE_METABOLISM": bool(self.affective.status()["available"]),
            "P017_SOCRATIC_MIRROR": bool(
                socratic_status["evidence"].get("ok")
                and socratic_status["logic_solver"]
                and socratic_status["audit"].get("ok")
            ),
        }

    def manifests(self) -> tuple[CapabilityManifest, ...]:
        health = self.integrated_health()
        specs = (
            (SPONTANEITY_CAPABILITY_ID, "grounded_ollama_spontaneity", "P006_STOCHASTIC_SPONTANEITY"),
            (SILENCE_CAPABILITY_ID, "persistent_cognitive_silence", "P007_COGNITIVE_SILENCE"),
            (AFFECTIVE_CAPABILITY_ID, "bounded_affective_control", "P010_AFFECTIVE_METABOLISM"),
            (SOCRATIC_CAPABILITY_ID, "evidence_logic_policy_review", "P017_SOCRATIC_MIRROR"),
        )
        return tuple(
            CapabilityManifest(
                capability_id=capability_id,
                version="1.0",
                provider=provider,
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["persistent_storage"],
                offline_available=True,
                health_status="HEALTHY" if health[health_key] else "UNHEALTHY",
            )
            for capability_id, provider, health_key in specs
        )

    def _explore(self, request: Mapping[str, Any]) -> LocalPillarResult:
        allowed = {
            "action", "topic", "authorized", "owner_opt_out",
            "privacy_allows_local_model", "resources_available", "seed",
            "max_candidates", "max_tokens", "timeout_seconds", "request_id",
            "evidence_ids",
        }
        _strict(request, allowed, {"action", "topic", "authorized", "request_id"})
        for field in (
            "authorized",
            "owner_opt_out",
            "privacy_allows_local_model",
            "resources_available",
        ):
            if field in request:
                _boolean(request[field], field)
        evidence_ids = ()
        if "evidence_ids" in request:
            raw_eids = request["evidence_ids"]
            if not isinstance(raw_eids, (list, tuple)):
                raise LocalPillarError("INVALID_INPUT", "evidence_ids must be a list of strings")
            evidence_ids = tuple(
                _text(eid, "evidence_id", 256) for eid in raw_eids
            )
        try:
            result = self.spontaneity.explore(
                ExplorationRequest(
                    topic=_text(request["topic"], "topic", 500),
                    authorized=_boolean(request["authorized"], "authorized"),
                    owner_opt_out=request.get("owner_opt_out", False),
                    silence_active=self.silence.active,
                    privacy_allows_local_model=request.get(
                        "privacy_allows_local_model", True
                    ),
                    resources_available=request.get("resources_available", True),
                    seed=request.get("seed"),
                    budget=ExplorationBudget(
                        max_candidates=request.get("max_candidates", 3),
                        max_tokens=request.get("max_tokens", 512),
                        timeout_seconds=request.get("timeout_seconds", 30.0),
                    ),
                    request_id=_text(
                        request["request_id"],
                        "request_id",
                        160,
                    ),
                    evidence_ids=evidence_ids,
                )
            )
        except (ValueError, ExplorationError) as exc:
            code = exc.code if isinstance(exc, ExplorationError) else "INVALID_INPUT"
            raise LocalPillarError(code, str(exc)) from exc
        if not result.get("ok"):
            raise LocalPillarError(str(result["status"]), "exploration gate rejected request")
        return LocalPillarResult("P006", str(result["status"]), result)

    def _silence(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        try:
            if action == "enter":
                _strict(
                    request,
                    {"action", "reason", "checkpoint", "request_id"},
                    {"action", "reason", "checkpoint", "request_id"},
                )
                checkpoint = request["checkpoint"]
                if not isinstance(checkpoint, Mapping):
                    raise LocalPillarError("INVALID_INPUT", "checkpoint must be an object")
                data = self.silence.enter(
                    request["reason"], checkpoint, request_id=request["request_id"]
                )
                return LocalPillarResult("P007", "COGNITIVE_SILENCE_ENTERED", data)
            if action == "exit":
                _strict(
                    request,
                    {"action", "wake_source", "request_id"},
                    {"action", "wake_source", "request_id"},
                )
                data = self.silence.exit(
                    request["wake_source"], request_id=request["request_id"]
                )
                if not data.get("ok"):
                    raise LocalPillarError(str(data["error"]), "wake source was denied")
                return LocalPillarResult("P007", "COGNITIVE_SILENCE_EXITED", data)
            if action == "status":
                _strict(request, {"action"}, {"action"})
                return LocalPillarResult("P007", "COGNITIVE_SILENCE_STATUS", self.silence.status())
            if action == "allows":
                _strict(request, {"action", "service"}, {"action", "service"})
                service = _text(request["service"], "service", 64)
                return LocalPillarResult(
                    "P007", "COGNITIVE_SILENCE_POLICY_CHECKED",
                    {"service": service, "allowed": self.silence.allows(service)},
                )
            if action in ("evaluate", "decide"):
                _strict(
                    request,
                    {"action", "signals", "decision_id"},
                    {"action", "signals"},
                )
                signals_raw = request["signals"]
                if not isinstance(signals_raw, Mapping):
                    raise LocalPillarError("INVALID_INPUT", "signals must be an object")
                dec_id = request.get("decision_id")
                decision = self.silence.evaluate_decision(
                    signals_raw,
                    decision_id=str(dec_id) if dec_id else None,
                )
                return LocalPillarResult(
                    "P007",
                    "COGNITIVE_SILENCE_DECISION_EVALUATED",
                    decision.as_dict(),
                )
        except ValueError as exc:
            raise LocalPillarError("INVALID_INPUT", str(exc)) from exc
        raise LocalPillarError("UNSUPPORTED_ACTION", "Cognitive Silence action is unsupported")

    def _affective(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "status":
            _strict(request, {"action"}, {"action"})
            return LocalPillarResult("P010", "AFFECTIVE_CONTROL_STATUS", self.affective.status())
        if action == "reset":
            _strict(request, {"action"}, {"action"})
            return LocalPillarResult("P010", "AFFECTIVE_CONTROL_RESET", self.affective.reset())
        if action != "apply":
            raise LocalPillarError("UNSUPPORTED_ACTION", "affective action is unsupported")
        allowed = {
            "action", "source", "urgency_delta", "caution_delta", "patience_delta",
            "escalation_delta", "signal_id", "user_state_confirmed",
        }
        _strict(request, allowed, {"action", "source", "signal_id"})
        try:
            signal = AffectiveSignal(
                source=ControlSignalSource(_text(request["source"], "source", 32)),
                urgency_delta=float(request.get("urgency_delta", 0.0)),
                caution_delta=float(request.get("caution_delta", 0.0)),
                patience_delta=float(request.get("patience_delta", 0.0)),
                escalation_delta=float(request.get("escalation_delta", 0.0)),
                signal_id=_text(request["signal_id"], "signal_id", 160),
                user_state_confirmed=_boolean(
                    request.get("user_state_confirmed", False),
                    "user_state_confirmed",
                ),
            )
            result = self.affective.apply(signal)
        except AffectiveSignalConflict as exc:
            raise LocalPillarError("IDEMPOTENCY_CONFLICT", str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", str(exc)) from exc
        return LocalPillarResult("P010", "AFFECTIVE_CONTROL_UPDATED", result)

    def _review(self, request: Mapping[str, Any]) -> LocalPillarResult:
        allowed = {
            "action", "decision_id", "action_text", "risk", "uncertainty", "novelty",
            "impact", "claims", "claim_evidence", "facts", "rules", "query",
        }
        required = allowed - {"facts", "rules", "query"}
        _strict(request, allowed, required)
        claims_raw = request["claims"]
        evidence_raw = request["claim_evidence"]
        if not isinstance(claims_raw, list) or not 1 <= len(claims_raw) <= 64:
            raise LocalPillarError("INVALID_INPUT", "claims must contain 1-64 entries")
        claims = tuple(_text(item, "claim", 2_000) for item in claims_raw)
        if not isinstance(evidence_raw, Mapping):
            raise LocalPillarError("INVALID_INPUT", "claim_evidence must be an object")
        claim_evidence: dict[str, tuple[str, ...]] = {}
        for claim in claims:
            refs = evidence_raw.get(claim)
            if not isinstance(refs, list) or not refs:
                raise LocalPillarError("INVALID_INPUT", "every claim needs evidence IDs")
            claim_evidence[claim] = tuple(_text(ref, "evidence_id", 128) for ref in refs)

        logic_fields = (request.get("facts"), request.get("rules"), request.get("query"))
        if any(item is not None for item in logic_fields) and not all(
            item is not None for item in logic_fields
        ):
            raise LocalPillarError("INVALID_INPUT", "facts, rules, and query must be supplied together")
        theory = None
        query = None
        try:
            if all(item is not None for item in logic_fields):
                facts_raw, rules_raw, query_raw = logic_fields
                if not isinstance(facts_raw, list) or not isinstance(rules_raw, list):
                    raise LocalPillarError("INVALID_INPUT", "facts and rules must be lists")
                theory = LogicTheory(
                    facts=tuple(Literal.parse(item) for item in facts_raw),
                    rules=tuple(LogicRule.from_mapping(item) for item in rules_raw),
                )
                query = Literal.parse(query_raw)
            decision_id = _text(request["decision_id"], "decision_id", 100)
            action_text = _text(request["action_text"], "action_text", 2_000)
            policy_request = PolicyRequest(
                request_id=f"policy-{decision_id}",
                actor_brain_id=self.actor_brain_id,
                node_id=self.node_id,
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(action_text.encode("utf-8")).hexdigest(),
                purpose="socratic.review",
            )
            result = self.socratic.review(
                CandidateDecision(
                    decision_id=decision_id,
                    action=action_text,
                    policy_request=policy_request,
                    risk=_ratio(request["risk"], "risk"),
                    uncertainty=_ratio(request["uncertainty"], "uncertainty"),
                    novelty=_ratio(request["novelty"], "novelty"),
                    impact=_ratio(request["impact"], "impact"),
                    claims=claims,
                    claim_evidence=claim_evidence,
                    logic_theory=theory,
                    logic_query=query,
                )
            )
        except (PolicyError, PureLogicError, SocraticError, ValueError) as exc:
            code = exc.code if isinstance(exc, SocraticError) else "INVALID_INPUT"
            if hasattr(code, "value"):
                code = code.value
            raise LocalPillarError(str(code), str(exc)) from exc
        return LocalPillarResult("P017", "SOCRATIC_REVIEW_RECORDED", result)

    def execute(self, capability_id: str, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        if capability_id == SPONTANEITY_CAPABILITY_ID:
            return self._explore(request)
        if capability_id == SILENCE_CAPABILITY_ID:
            return self._silence(request)
        if capability_id == AFFECTIVE_CAPABILITY_ID:
            return self._affective(request)
        if capability_id == SOCRATIC_CAPABILITY_ID:
            return self._review(request)
        raise LocalPillarError("CAPABILITY_UNAVAILABLE", "regulation capability is not registered")

    def execute_integrated_cycle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Run evidence → bounded control → exploration → Socratic review."""
        allowed = {
            "source_ref", "title", "content", "topic", "exploration_request_id",
            "decision_id", "signal", "risk", "uncertainty", "novelty", "impact",
            "claim", "facts", "rules", "evidence_query", "logic_query", "seed",
        }
        _strict(request, allowed, allowed - {"seed"})
        health = self.integrated_health()
        unavailable = [name for name, ready in health.items() if not ready]
        if unavailable:
            raise LocalPillarError(
                "PROVIDER_UNAVAILABLE",
                f"regulation dependencies unavailable: {', '.join(unavailable)}",
            )
        if not self.silence.allows(RuntimeService.MODEL_GENERATION):
            raise LocalPillarError(
                "COGNITIVE_SILENCE_ACTIVE", "model generation is blocked by Cognitive Silence"
            )
        signal = request["signal"]
        if not isinstance(signal, Mapping):
            raise LocalPillarError("INVALID_INPUT", "signal must be an object")
        ingested = self.rag.execute(
            {
                "action": "ingest",
                "source_ref": _text(request["source_ref"], "source_ref", 512),
                "title": _text(request["title"], "title", 512),
                "content": _text(request["content"], "content", 1_048_576),
            }
        )
        affected = self._affective({"action": "apply", **dict(signal)})
        explored = self._explore(
            {
                "action": "explore",
                "topic": _text(request["topic"], "topic", 500),
                "authorized": True,
                "request_id": _text(
                    request["exploration_request_id"], "exploration_request_id", 160
                ),
                "seed": request.get("seed", 0),
                "max_candidates": 1,
                "max_tokens": 256,
                "timeout_seconds": 60.0,
            }
        )
        evidence = self.rag.retrieve(
            _text(request["evidence_query"], "evidence_query", 1_000), 1
        )
        if not evidence:
            raise LocalPillarError("EVIDENCE_UNAVAILABLE", "review evidence was not retrieved")
        claim = _text(request["claim"], "claim", 2_000)
        review = self._review(
            {
                "action": "review",
                "decision_id": request["decision_id"],
                "action_text": explored.data["candidates"][0]["hypothesis_text"],
                "risk": request["risk"],
                "uncertainty": request["uncertainty"],
                "novelty": request["novelty"],
                "impact": request["impact"],
                "claims": [claim],
                "claim_evidence": {claim: [evidence[0]["evidence_id"]]},
                "facts": request["facts"],
                "rules": request["rules"],
                "query": request["logic_query"],
            }
        )
        if not review.data.get("ok"):
            raise LocalPillarError("SOCRATIC_REVIEW_BLOCKED", "candidate did not pass review")
        return {
            "status": "INTEGRATED_REGULATION_CYCLE_COMPLETED",
            "pillars": list(INTEGRATED_REGULATION_PILLARS),
            "dependency_health": health,
            "evidence": ingested.data,
            "affective_control": affected.data,
            "silence_policy": {
                "model_generation_allowed": True,
                "state": self.silence.status(),
            },
            "exploration": explored.data,
            "socratic_review": review.data,
            "warning": "CANDIDATES_REMAIN_HYPOTHESES_UNTIL_EMPIRICALLY_TESTED",
        }

    def close(self) -> None:
        self.silence.close()
        self.spontaneity.close()
        self.socratic.close()
