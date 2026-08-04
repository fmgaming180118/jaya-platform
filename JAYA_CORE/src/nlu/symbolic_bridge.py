"""
symbolic_bridge.py — Bridge between NLU (LLM) and Symbolic Reasoner.

This module bridges the NLU output (from LLM) to the Symbolic Reasoner
without any mock implementations. All components are real implementations.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from JAYA_CORE.src.ai_connectors.cognitive_model_adapter import (
    CognitiveModelAdapter,
    CognitiveResponse,
    create_cognitive_adapter_from_env,
)
from JAYA_CORE.src.cognitive.contracts import (
    Intent,
    IntentType,
    Goal,
    ActionPlan,
    ActionStep,
    ActionStatus,
    RiskClass,
    JayaIRRequest,
    ResourceBudget,
)
from JAYA_CORE.src.cognitive.intent import IntentEngine
from JAYA_CORE.src.cognitive.planner import GenericHierarchicalPlanner
from JAYA_CORE.src.reasoning.symbolic_reasoner import SymbolicReasoner
from JAYA_CORE.src.reasoning.logic_engine import LogicEngine
from JAYA_CORE.src.reasoning.constraint_solver import ConstraintSolver
from JAYA_CORE.src.capabilities.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


# JSON Schema for structured LLM NLU output
NLU_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [t.value for t in IntentType],
            "description": "Classified intent type"
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence score for intent classification"
        },
        "entities": {
            "type": "object",
            "description": "Extracted entities with types",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "slots": {
            "type": "object",
            "description": "Slot-value pairs for task completion",
            "additionalProperties": {"type": "string"}
        },
        "constraints": {
            "type": "object",
            "description": "Constraints extracted from user input",
            "additionalProperties": True
        },
        "relations": {
            "type": "array",
            "description": "Relations between entities",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"}
                },
                "required": ["subject", "predicate", "object"]
            }
        },
        "ambiguity": {
            "type": "array",
            "description": "Ambiguous parts needing clarification",
            "items": {"type": "string"}
        },
        "alternative_intents": {
            "type": "array",
            "description": "Alternative intent interpretations",
            "items": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": [t.value for t in IntentType]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                },
                "required": ["intent", "confidence"]
            }
        }
    },
    "required": ["intent", "confidence", "entities", "slots", "constraints", "relations", "ambiguity", "alternative_intents"]
}


@dataclass
class NLUResult:
    """Result from NLU processing."""
    intent: Intent
    entities: Dict[str, List[str]]
    slots: Dict[str, str]
    constraints: Dict[str, Any]
    relations: List[Dict[str, str]]
    ambiguity: List[str]
    alternative_intents: List[Dict[str, Any]]
    confidence: float
    raw_response: str


@dataclass
class SymbolicPlan:
    """Plan in symbolic form (JayaIR)."""
    ir: JayaIRRequest
    nlu_result: NLUResult
    goal: Goal
    plan: ActionPlan


@dataclass
class ClarificationNeeded:
    """Signal that clarification is needed from user."""
    alternatives: List[Intent]
    message: str = "Perlu klarifikasi: beberapa informasi penting hilang."
    missing_slots: List[str] = None
    ambiguity: List[str] = None


@dataclass
class IRVerificationFailed:
    """Signal that IR verification failed."""
    errors: List[str]
    message: str = "Verifikasi IR gagal."


class NLUSymbolicBridge:
    """
    Bridge between NLU (LLM-based) and Symbolic Reasoner.
    
    This bridge:
    1. Takes natural language input
    2. Uses LLM for NLU (intent classification, entity extraction, slot filling)
    3. Converts to Symbolic IR (JayaIR) with full structure
    4. Validates IR with Symbolic Reasoner
    5. Returns SymbolicPlan for execution
    """
    
    def __init__(
        self,
        nlu_adapter: CognitiveModelAdapter,
        symbolic_reasoner: SymbolicReasoner,
        intent_engine: IntentEngine = None,
        planner: GenericHierarchicalPlanner = None,
        confidence_threshold: float = 0.7,
        capability_registry: CapabilityRegistry = None,
    ):
        self.nlu = nlu_adapter
        self.reasoner = symbolic_reasoner
        self.intent_engine = intent_engine or IntentEngine()
        self.planner = planner or GenericHierarchicalPlanner()
        self.confidence_threshold = confidence_threshold
        self.capability_registry = capability_registry or CapabilityRegistry()
        
        logger.info("NLUSymbolicBridge initialized with confidence_threshold=%.2f", 
                   confidence_threshold)
    
    def process(
        self, 
        user_input: str, 
        context: Dict[str, Any] = None
    ) -> SymbolicPlan | ClarificationNeeded | IRVerificationFailed:
        """
        Process natural language input through NLU → Symbolic pipeline.
        
        Args:
            user_input: Natural language input from user
            context: Optional context (session, user info, etc.)
            
        Returns:
            SymbolicPlan if successful, ClarificationNeeded or IRVerificationFailed otherwise
        """
        ctx = context or {}
        
        # Step 1: NLU - Intent classification + Entity extraction + Slot filling
        nlu_result = self._run_nlu(user_input, ctx)
        
        # Step 2: Check confidence threshold
        if nlu_result.confidence < self.confidence_threshold:
            logger.warning("Low confidence NLU result: %.2f", nlu_result.confidence)
            return ClarificationNeeded(
                alternatives=[Intent(intent_type=IntentType(a["intent"]), confidence=a["confidence"]) for a in nlu_result.alternative_intents],
                message=f"Confidence rendah ({nlu_result.confidence:.2f}). Perlu klarifikasi.",
                missing_slots=[k for k, v in nlu_result.slots.items() if not v],
                ambiguity=nlu_result.ambiguity,
            )
        
        # Step 3: Check for required slots that are empty
        missing_required = self._check_required_slots(nlu_result)
        if missing_required:
            return ClarificationNeeded(
                alternatives=[Intent(intent_type=IntentType(a["intent"]), confidence=a["confidence"]) for a in nlu_result.alternative_intents],
                message=f"Slot wajib hilang: {', '.join(missing_required)}",
                missing_slots=missing_required,
                ambiguity=nlu_result.ambiguity,
            )
        
        # Step 4: Convert to Symbolic IR (JayaIR)
        ir = self._nlu_to_ir(nlu_result, ctx)
        
        # Step 5: Verify IR with Symbolic Reasoner
        if not self.reasoner.verify_ir(ir):
            logger.error("IR verification failed: %s", ir.errors if hasattr(ir, 'errors') else 'Unknown')
            return IRVerificationFailed(
                errors=ir.errors if hasattr(ir, 'errors') else ['Unknown verification error']
            )
        
        # Step 6: Create Goal and Plan
        goal = self._create_goal(nlu_result, ctx)
        plan = self.planner.create_plan(goal)
        
        # Step 7: Validate plan with Symbolic Reasoner
        if not self.reasoner.verify_plan(plan):
            logger.error("Plan verification failed")
            return IRVerificationFailed(errors=["Plan verification failed"])
        
        logger.info("Successfully processed input through NLU→Symbolic pipeline")
        
        return SymbolicPlan(
            ir=ir,
            nlu_result=nlu_result,
            goal=goal,
            plan=plan,
        )
    
    def _run_nlu(self, user_input: str, context: Dict[str, Any]) -> NLUResult:
        """Run NLU processing using LLM adapter with structured output."""
        try:
            # Use IntentEngine for basic intent classification as fallback
            base_intent = self.intent_engine.detect_intent(user_input, context)
            
            # Use LLM adapter for richer understanding if available
            if self.nlu and self.nlu.is_local_available():
                # Use structured prompt for NLU
                prompt = self._build_nlu_prompt(user_input, context)
                
                response = self.nlu.generate(
                    prompt=prompt,
                    context={"user_input": user_input, "context": context},
                    temperature=0.1,  # Low temperature for structured output
                )
                
                # Parse structured LLM response
                nlu_data = self._parse_structured_nlu(response.text)
                
                # Create Intent from parsed data
                intent = Intent(
                    intent_type=IntentType(nlu_data["intent"]),
                    confidence=nlu_data["confidence"],
                    domain=self._infer_domain(nlu_data["intent"], nlu_data["entities"]),
                )
                
                # Convert alternative intents
                alternatives = []
                for alt in nlu_data.get("alternative_intents", []):
                    alternatives.append({
                        "intent": alt["intent"],
                        "confidence": alt["confidence"],
                    })
                
                return NLUResult(
                    intent=intent,
                    entities=nlu_data.get("entities", {}),
                    slots=nlu_data.get("slots", {}),
                    constraints=nlu_data.get("constraints", {}),
                    relations=nlu_data.get("relations", []),
                    ambiguity=nlu_data.get("ambiguity", []),
                    alternative_intents=alternatives,
                    confidence=nlu_data["confidence"],
                    raw_response=user_input,
                )
            else:
                # Fallback: extract slots/entities from base intent
                entities = base_intent.extracted_entities or {}
                slots = self._extract_slots_from_entities(base_intent.intent_type, entities, user_input)
                
                return NLUResult(
                    intent=base_intent,
                    entities=entities,
                    slots=slots,
                    constraints={},
                    relations=[],
                    ambiguity=base_intent.missing_context or [],
                    alternative_intents=[],
                    confidence=base_intent.confidence,
                    raw_response=user_input,
                )
        except Exception as e:
            logger.error("NLU processing failed: %s", e)
            # Fallback to basic intent engine
            intent = self.intent_engine.detect_intent(user_input, context)
            entities = intent.extracted_entities or {}
            slots = self._extract_slots_from_entities(intent.intent_type, entities, user_input)
            return NLUResult(
                intent=intent,
                entities=entities,
                slots=slots,
                constraints={},
                relations=[],
                ambiguity=intent.missing_context or [],
                alternative_intents=[],
                confidence=intent.confidence,
                raw_response=user_input,
            )
    
    def _extract_slots_from_entities(self, intent_type: IntentType, entities: Dict[str, Any], user_input: str) -> Dict[str, str]:
        """Extract slots from entities when LLM is not available."""
        slots = {}
        
        if intent_type == IntentType.CREATE_PLAN:
            # Extract topic and duration from entities/input
            if "language" in entities:
                slots["topic"] = entities["language"]
            elif "object_type" in entities:
                slots["topic"] = entities["object_type"]
            else:
                # Try to extract from input
                import re
                # Look for "belajar X" or "rencana X"
                match = re.search(r'(?:belajar|rencana)\s+(\w+(?:\s+\w+)*)', user_input.lower())
                if match:
                    slots["topic"] = match.group(1)
            
            # Extract duration
            import re
            duration_match = re.search(r'(\d+\s*(?:hari|minggu|bulan|tahun))', user_input.lower())
            if duration_match:
                slots["duration"] = duration_match.group(1)
            elif "duration" in entities:
                slots["duration"] = entities["duration"]
        
        elif intent_type == IntentType.WRITE_CODE:
            if "language" in entities:
                slots["language"] = entities["language"]
            if "topic" in entities:
                slots["topic"] = entities["topic"]
            else:
                # Try to extract topic from input for code execution
                import re
                match = re.search(r'(?:eksekusi|jalankan|run)\s+(?:kode|code)\s*[:\-]?\s*(.+)', user_input.lower())
                if match:
                    slots["topic"] = match.group(1).strip()
                elif "kode" in user_input.lower() or "code" in user_input.lower():
                    # Default topic for code execution
                    slots["topic"] = "code execution"
        
        elif intent_type == IntentType.CREATE_3D_DESIGN:
            if "object_type" in entities:
                slots["object_type"] = entities["object_type"]
            if "parameters" in entities:
                slots["parameters"] = str(entities["parameters"])
        
        elif intent_type == IntentType.CONTROL_DEVICE:
            if "device_id" in entities:
                slots["device_id"] = entities["device_id"]
            if "action" in entities:
                slots["action"] = entities["action"]
        
        return slots
    
    def _build_nlu_prompt(self, user_input: str, context: Dict[str, Any]) -> str:
        """Build structured prompt for NLU with JSON schema."""
        schema_str = json.dumps(NLU_OUTPUT_SCHEMA, indent=2, ensure_ascii=False)
        
        return f"""Anda adalah sistem NLU untuk asisten JAYA. Ekstrak informasi terstruktur dari input pengguna.

Input: "{user_input}"
Konteks: {json.dumps(context, ensure_ascii=False)}

Keluarkan HANYA JSON valid yang mengikuti schema ini:
{schema_str}

Contoh output:
{{
  "intent": "CREATE_PLAN",
  "confidence": 0.92,
  "entities": {{
    "TOPIC": ["Python", "machine learning"],
    "DURATION": ["30 hari"],
    "LEVEL": ["pemula"]
  }},
  "slots": {{
    "topic": "Python machine learning",
    "duration": "30 hari",
    "level": "pemula",
    "format": "rencana belajar"
  }},
  "constraints": {{
    "max_hours_per_week": 10,
    "language": "indonesian"
  }},
  "relations": [
    {{"subject": "Python", "predicate": "includes", "object": "machine learning"}},
    {{"subject": "rencana", "predicate": "duration", "object": "30 hari"}}
  ],
  "ambiguity": [],
  "alternative_intents": [
    {{"intent": "ASK_INFORMATION", "confidence": 0.05}},
    {{"intent": "WRITE_CODE", "confidence": 0.03}}
  ]
}}"""
    
    def _parse_structured_nlu(self, llm_response: str) -> Dict[str, Any]:
        """Parse structured NLU output from LLM response."""
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse NLU JSON: %s", e)
        
        # Fallback: try to parse entire response as JSON
        try:
            return json.loads(llm_response)
        except json.JSONDecodeError:
            pass
        
        # Ultimate fallback: return minimal structure
        logger.warning("LLM did not return valid JSON, using fallback")
        return {
            "intent": "ASK_INFORMATION",
            "confidence": 0.5,
            "entities": {},
            "slots": {},
            "constraints": {},
            "relations": [],
            "ambiguity": ["LLM output not parseable"],
            "alternative_intents": [],
        }
    
    def _infer_domain(self, intent: str, entities: Dict[str, List[str]]) -> str:
        """Infer domain from intent and entities."""
        domain_map = {
            "CREATE_3D_DESIGN": "cad",
            "WRITE_CODE": "programming",
            "CREATE_PLAN": "planning",
            "ASK_INFORMATION": "general",
            "CONTROL_DEVICE": "iot",
            "MANAGE_MEMORY": "memory",
        }
        return domain_map.get(intent, "general")
    
    def _check_required_slots(self, nlu_result: NLUResult) -> List[str]:
        """Check for required slots based on intent."""
        required_slots = {
            "CREATE_PLAN": ["topic", "duration"],
            "WRITE_CODE": ["topic", "language"],
            "CREATE_3D_DESIGN": ["object_type", "parameters"],
            "CONTROL_DEVICE": ["device_id", "action"],
        }
        
        required = required_slots.get(nlu_result.intent.intent_type.value, [])
        return [slot for slot in required if not nlu_result.slots.get(slot)]
    
    def _nlu_to_ir(self, nlu_result: NLUResult, context: Dict[str, Any]) -> JayaIRRequest:
        """Convert NLU result to proper JayaIR (Intermediate Representation)."""
        # Get required capabilities from registry
        required_capabilities = self._get_required_capabilities(nlu_result.intent.intent_type, nlu_result.entities)
        
        # Build resource budget from constraints
        resource_budget = ResourceBudget(
            max_memory_mb=nlu_result.constraints.get("max_memory_mb", 512),
            max_duration_seconds=nlu_result.constraints.get("max_duration_seconds", 300),
            allow_network=nlu_result.constraints.get("allow_network", True),
            allow_remote_offload=nlu_result.constraints.get("allow_remote_offload", True),
        )
        
        return JayaIRRequest(
            request_id=f"ir-{hash(nlu_result.raw_response) % 10000:04d}",
            schema_version="1.0",
            goal={
                "intent_type": nlu_result.intent.intent_type.value,
                "domain": nlu_result.intent.domain,
                "entities": nlu_result.entities,
                "slots": nlu_result.slots,
                "relations": nlu_result.relations,
            },
            constraints=nlu_result.constraints,
            required_capabilities=required_capabilities,
            resource_budget=resource_budget,
        )
    
    def _get_required_capabilities(self, intent_type: IntentType, entities: Dict[str, List[str]]) -> List[str]:
        """Map intent type to required capabilities using CapabilityRegistry."""
        # Base capabilities by intent
        base_capabilities = {
            IntentType.CREATE_3D_DESIGN: ["cad.parametric_modeling", "text.reasoning.basic"],
            IntentType.WRITE_CODE: ["text.reasoning.basic", "system.file.read", "system.file.write"],
            IntentType.CREATE_PLAN: ["text.reasoning.basic", "system.file.read"],
            IntentType.ASK_INFORMATION: ["text.reasoning.basic", "web.search"],
            IntentType.CONTROL_DEVICE: ["device.control", "system.file.read"],
            IntentType.MANAGE_MEMORY: ["memory.read", "memory.write"],
        }
        
        caps = base_capabilities.get(intent_type, ["text.reasoning.basic"])
        
        # Add entity-specific capabilities
        if "CODE" in entities or "PROGRAMMING_LANGUAGE" in entities:
            caps.append("code.execution")
        if "FILE_PATH" in entities:
            caps.append("system.file.read")
        if "URL" in entities:
            caps.append("web.fetch")
        
        # Filter to only available capabilities in registry
        available = set()
        for cap in caps:
            if self.capability_registry.has_capability(cap):
                available.add(cap)
            else:
                logger.warning("Capability not in registry: %s", cap)
        
        return list(available) if available else ["text.reasoning.basic"]
    
    def _create_goal(self, nlu_result: NLUResult, context: Dict[str, Any]) -> Goal:
        """Create Goal from NLU result."""
        return Goal(
            goal_id=f"goal-{hash(nlu_result.raw_response) % 10000:04d}",
            title=nlu_result.raw_response[:100],
            intent_type=nlu_result.intent.intent_type,
            domain=nlu_result.intent.domain,
            constraints=nlu_result.constraints,
        )


def create_nlu_symbolic_bridge(
    nlu_adapter: CognitiveModelAdapter = None,
    symbolic_reasoner: SymbolicReasoner = None,
    confidence_threshold: float = 0.7,
    capability_registry: CapabilityRegistry = None,
) -> NLUSymbolicBridge:
    """Factory function to create NLUSymbolicBridge with default components."""
    if nlu_adapter is None:
        nlu_adapter = create_cognitive_adapter_from_env()
    
    if symbolic_reasoner is None:
        from JAYA_CORE.src.reasoning.symbolic_reasoner import SymbolicReasoner
        from JAYA_CORE.src.reasoning.logic_engine import LogicEngine
        from JAYA_CORE.src.reasoning.constraint_solver import ConstraintSolver
        from JAYA_CORE.src.cognitive.planner import GenericHierarchicalPlanner
        from JAYA_CORE.src.reasoning.symbolic_reasoner import ResourceProfile
        from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
        from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
        
        resource_profile = ResourceProfile(
            max_memory_mb=512,
            max_duration_seconds=300,
            allow_network=True,
            allow_remote_offload=True,
        )
        
        cap_registry = capability_registry or CapabilityRegistry()
        
        # Register default capabilities if registry is empty
        if not cap_registry.list_capabilities():
            default_capabilities = [
                CapabilityManifest(
                    capability_id="text.reasoning.basic",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=16,
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="system.file.read",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=16,
                    permissions_required=["file_read"],
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="system.file.write",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=16,
                    permissions_required=["file_write"],
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="web.search",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=32,
                    offline_available=False,
                ),
                CapabilityManifest(
                    capability_id="web.fetch",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=32,
                    offline_available=False,
                ),
                CapabilityManifest(
                    capability_id="code.execution",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=64,
                    permissions_required=["code_exec"],
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="cad.parametric_modeling",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=128,
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="device.control",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=32,
                    permissions_required=["device_control"],
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="memory.read",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=16,
                    offline_available=True,
                ),
                CapabilityManifest(
                    capability_id="memory.write",
                    version="1.0",
                    provider="built_in",
                    execution_location="local",
                    min_memory_mb=16,
                    permissions_required=["memory_write"],
                    offline_available=True,
                ),
            ]
            
            for cap in default_capabilities:
                cap_registry.register(cap)
        
        symbolic_reasoner = SymbolicReasoner(
            htn_planner=GenericHierarchicalPlanner(),
            logic_engine=LogicEngine(),
            constraint_solver=ConstraintSolver(
                resource_profile=resource_profile,
                capability_registry=cap_registry,
            ),
        )
    
    return NLUSymbolicBridge(
        nlu_adapter=nlu_adapter,
        symbolic_reasoner=symbolic_reasoner,
        confidence_threshold=confidence_threshold,
        capability_registry=capability_registry,
    )