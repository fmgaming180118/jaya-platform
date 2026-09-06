"""
Advanced Memory Systems for JAYA_CORE.

Provides:
- Semantic Memory: Knowledge graph with entity resolution
- Procedural Memory: Skill acquisition from demonstration
- CRDT-based Cross-Device Sync: Conflict-free replicated data types
- Hierarchical Memory Compression
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from jaya_core.observability import get_structured_logger
from jaya_core.security import get_audit_logger

logger = get_structured_logger(__name__, component="advanced_memory")
audit_logger = get_audit_logger()


# ============================================================================
# CRDT Implementation for Cross-Device Sync
# ============================================================================

class CRDTType(Enum):
    """Types of CRDTs."""
    G_COUNTER = "g_counter"  # Grow-only counter
    PN_COUNTER = "pn_counter"  # Positive-negative counter
    LWW_REGISTER = "lww_register"  # Last-writer-wins register
    LWW_MAP = "lww_map"  # Last-writer-wins map
    OR_SET = "or_set"  # Observed-remove set
    RGA = "rga"  # Replicated Growable Array (for sequences)


@dataclass
class VectorClock:
    """Vector clock for causality tracking."""
    clocks: Dict[str, int] = field(default_factory=dict)
    
    def increment(self, node_id: str):
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1
    
    def merge(self, other: "VectorClock"):
        for node, time in other.clocks.items():
            self.clocks[node] = max(self.clocks.get(node, 0), time)
    
    def happens_before(self, other: "VectorClock") -> bool:
        """Check if self happens before other."""
        dominated = False
        for node, time in self.clocks.items():
            if time > other.clocks.get(node, 0):
                return False
            if time < other.clocks.get(node, 0):
                dominated = True
        return dominated
    
    def concurrent_with(self, other: "VectorClock") -> bool:
        """Check if concurrent with other."""
        return not self.happens_before(other) and not other.happens_before(self)


class CRDT(ABC):
    """Abstract CRDT base class."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.vector_clock = VectorClock()
    
    @abstractmethod
    def merge(self, other: "CRDT") -> "CRDT":
        """Merge with another CRDT."""
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any], node_id: str) -> "CRDT":
        """Deserialize from dictionary."""
        pass


class LWWRegister(CRDT):
    """Last-Writer-Wins Register CRDT."""
    
    def __init__(self, node_id: str, value: Any = None):
        super().__init__(node_id)
        self.value = value
        self.timestamp = time.time()
        self.writer_id = node_id
    
    def set(self, value: Any):
        self.vector_clock.increment(self.node_id)
        self.value = value
        self.timestamp = time.time()
        self.writer_id = self.node_id
    
    def merge(self, other: "LWWRegister") -> "LWWRegister":
        # Merge vector clocks
        self.vector_clock.merge(other.vector_clock)
        
        # LWW: keep value with latest timestamp
        if other.timestamp > self.timestamp:
            self.value = other.value
            self.timestamp = other.timestamp
            self.writer_id = other.writer_id
        elif other.timestamp == self.timestamp:
            # Tie-break by writer ID
            if other.writer_id > self.writer_id:
                self.value = other.value
                self.writer_id = other.writer_id
        
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "LWWRegister",
            "value": self.value,
            "timestamp": self.timestamp,
            "writer_id": self.writer_id,
            "vector_clock": self.vector_clock.clocks,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], node_id: str) -> "LWWRegister":
        reg = cls(node_id, data["value"])
        reg.timestamp = data["timestamp"]
        reg.writer_id = data["writer_id"]
        reg.vector_clock.clocks = data["vector_clock"]
        return reg


class LWWMap(CRDT):
    """Last-Writer-Wins Map CRDT."""
    
    def __init__(self, node_id: str):
        super().__init__(node_id)
        self.entries: Dict[str, LWWRegister] = {}
    
    def set(self, key: str, value: Any):
        if key not in self.entries:
            self.entries[key] = LWWRegister(self.node_id, value)
        else:
            self.entries[key].set(value)
    
    def get(self, key: str) -> Any:
        if key in self.entries:
            return self.entries[key].value
        return None
    
    def delete(self, key: str):
        # Set to tombstone (None with timestamp)
        self.set(key, None)
    
    def merge(self, other: "LWWMap") -> "LWWMap":
        self.vector_clock.merge(other.vector_clock)
        
        for key, other_reg in other.entries.items():
            if key in self.entries:
                self.entries[key].merge(other_reg)
            else:
                self.entries[key] = other_reg
        
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "LWWMap",
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "vector_clock": self.vector_clock.clocks,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], node_id: str) -> "LWWMap":
        m = cls(node_id)
        m.vector_clock.clocks = data["vector_clock"]
        for k, v in data["entries"].items():
            m.entries[k] = LWWRegister.from_dict(v, node_id)
        return m


class ORSet(CRDT):
    """Observed-Remove Set CRDT."""
    
    def __init__(self, node_id: str):
        super().__init__(node_id)
        # element -> set of (tag, node_id)
        self.elements: Dict[str, Set[Tuple[str, str]]] = {}
    
    def _generate_tag(self) -> str:
        return f"{self.node_id}:{uuid.uuid4().hex[:8]}"
    
    def add(self, element: str):
        tag = self._generate_tag()
        if element not in self.elements:
            self.elements[element] = set()
        self.elements[element].add((tag, self.node_id))
        self.vector_clock.increment(self.node_id)
    
    def remove(self, element: str):
        if element in self.elements:
            # Remove all tags for this element (observed remove)
            self.elements[element].clear()
            self.vector_clock.increment(self.node_id)
    
    def contains(self, element: str) -> bool:
        return element in self.elements and len(self.elements[element]) > 0
    
    def get_all(self) -> Set[str]:
        return {e for e, tags in self.elements.items() if tags}
    
    def merge(self, other: "ORSet") -> "ORSet":
        self.vector_clock.merge(other.vector_clock)
        
        for element, other_tags in other.elements.items():
            if element not in self.elements:
                self.elements[element] = set()
            self.elements[element].update(other_tags)
        
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "ORSet",
            "elements": {k: list(v) for k, v in self.elements.items()},
            "vector_clock": self.vector_clock.clocks,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], node_id: str) -> "ORSet":
        s = cls(node_id)
        s.vector_clock.clocks = data["vector_clock"]
        for k, v in data["elements"].items():
            s.elements[k] = set(tuple(t) for t in v)
        return s


# ============================================================================
# CRDT Sync Manager
# ============================================================================

class CRDTSyncManager:
    """Manages CRDT synchronization across devices."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.crdts: Dict[str, CRDT] = {}
        self.peers: Dict[str, Dict[str, CRDT]] = {}  # peer_id -> {crdt_name -> CRDT}
        self._sync_interval = 5.0
        self._running = False
    
    def register_crdt(self, name: str, crdt: CRDT):
        """Register a CRDT for synchronization."""
        self.crdts[name] = crdt
        logger.info("CRDT registered", name=name, type=type(crdt).__name__)
    
    def get_crdt(self, name: str) -> Optional[CRDT]:
        """Get CRDT by name."""
        return self.crdts.get(name)
    
    def create_lww_register(self, name: str, initial_value: Any = None) -> LWWRegister:
        """Create and register LWW register."""
        reg = LWWRegister(self.node_id, initial_value)
        self.register_crdt(name, reg)
        return reg
    
    def create_lww_map(self, name: str) -> LWWMap:
        """Create and register LWW map."""
        m = LWWMap(self.node_id)
        self.register_crdt(name, m)
        return m
    
    def create_or_set(self, name: str) -> ORSet:
        """Create and register OR-Set."""
        s = ORSet(self.node_id)
        self.register_crdt(name, s)
        return s
    
    def receive_sync(self, peer_id: str, crdt_name: str, crdt_data: Dict[str, Any]):
        """Receive CRDT state from peer."""
        if crdt_name not in self.crdts:
            logger.warning("Unknown CRDT in sync", name=crdt_name)
            return
        
        local_crdt = self.crdts[crdt_name]
        crdt_type = crdt_data.get("type")
        
        # Deserialize peer CRDT
        if crdt_type == "LWWRegister":
            peer_crdt = LWWRegister.from_dict(crdt_data, peer_id)
        elif crdt_type == "LWWMap":
            peer_crdt = LWWMap.from_dict(crdt_data, peer_id)
        elif crdt_type == "ORSet":
            peer_crdt = ORSet.from_dict(crdt_data, peer_id)
        else:
            logger.warning("Unknown CRDT type", type=crdt_type)
            return
        
        # Merge
        local_crdt.merge(peer_crdt)
        
        # Store peer state
        if peer_id not in self.peers:
            self.peers[peer_id] = {}
        self.peers[peer_id][crdt_name] = peer_crdt
        
        logger.debug("CRDT synced from peer", peer=peer_id, crdt=crdt_name)
    
    def get_sync_state(self) -> Dict[str, Any]:
        """Get full sync state for sending to peers."""
        return {
            "node_id": self.node_id,
            "timestamp": time.time(),
            "crdts": {name: crdt.to_dict() for name, crdt in self.crdts.items()},
        }
    
    def sync_with_peer(self, peer_id: str, peer_state: Dict[str, Any]):
        """Sync with peer state."""
        for crdt_name, crdt_data in peer_state.get("crdts", {}).items():
            self.receive_sync(peer_id, crdt_name, crdt_data)
    
    async def start_periodic_sync(self, send_fn: Callable[[str, Dict], Any]):
        """Start periodic sync with peers."""
        self._running = True
        
        while self._running:
            state = self.get_sync_state()
            # Send to all known peers
            for peer_id in self.peers:
                try:
                    await send_fn(peer_id, state)
                except Exception as e:
                    logger.error("Sync send failed", peer=peer_id, error=str(e))
            
            await asyncio.sleep(self._sync_interval)
    
    def stop(self):
        """Stop periodic sync."""
        self._running = False


# ============================================================================
# Semantic Memory (Knowledge Graph)
# ============================================================================

@dataclass
class Entity:
    """Knowledge graph entity."""
    entity_id: str
    name: str
    entity_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Relation:
    """Knowledge graph relation."""
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)


class SemanticMemory:
    """Semantic memory with knowledge graph."""
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.name_index: Dict[str, Set[str]] = defaultdict(set)  # name -> entity_ids
        self.type_index: Dict[str, Set[str]] = defaultdict(set)  # type -> entity_ids
    
    def add_entity(self, entity: Entity) -> str:
        """Add entity to knowledge graph."""
        self.entities[entity.entity_id] = entity
        self.name_index[entity.name.lower()].add(entity.entity_id)
        for alias in entity.aliases:
            self.name_index[alias.lower()].add(entity.entity_id)
        self.type_index[entity.entity_type].add(entity.entity_id)
        return entity.entity_id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)
    
    def find_entities_by_name(self, name: str) -> List[Entity]:
        ids = self.name_index.get(name.lower(), set())
        return [self.entities[eid] for eid in ids if eid in self.entities]
    
    def find_entities_by_type(self, entity_type: str) -> List[Entity]:
        ids = self.type_index.get(entity_type, set())
        return [self.entities[eid] for eid in ids if eid in self.entities]
    
    def add_relation(self, relation: Relation) -> str:
        """Add relation between entities."""
        if relation.source_id not in self.entities or relation.target_id not in self.entities:
            raise ValueError("Source or target entity not found")
        
        self.relations[relation.relation_id] = relation
        return relation.relation_id
    
    def get_relations(self, entity_id: str, relation_type: str = None) -> List[Relation]:
        """Get all relations for an entity."""
        results = []
        for rel in self.relations.values():
            if rel.source_id == entity_id or rel.target_id == entity_id:
                if relation_type is None or rel.relation_type == relation_type:
                    results.append(rel)
        return results
    
    def query(self, query: str) -> List[Dict[str, Any]]:
        """Simple query interface."""
        # This would be expanded with a proper query language
        results = []
        
        # Search entities by name
        entities = self.find_entities_by_name(query)
        for e in entities:
            results.append({
                "type": "entity",
                "entity": e,
                "relations": self.get_relations(e.entity_id),
            })
        
        return results
    
    def merge(self, other: "SemanticMemory"):
        """Merge another semantic memory."""
        for entity in other.entities.values():
            if entity.entity_id not in self.entities:
                self.add_entity(entity)
            else:
                # Merge properties
                existing = self.entities[entity.entity_id]
                existing.properties.update(entity.properties)
                existing.aliases.extend(a for a in entity.aliases if a not in existing.aliases)
        
        for relation in other.relations.values():
            if relation.relation_id not in self.relations:
                self.add_relation(relation)


# ============================================================================
# Procedural Memory (Skill Acquisition)
# ============================================================================

@dataclass
class SkillStep:
    """Single step in a skill."""
    step_id: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    """Procedural skill."""
    skill_id: str
    name: str
    description: str
    steps: List[SkillStep] = field(default_factory=list)
    preconditions: Dict[str, Any] = field(default_factory=dict)
    postconditions: Dict[str, Any] = field(default_factory=dict)
    success_rate: float = 0.0
    execution_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ProceduralMemory:
    """Procedural memory for skill acquisition."""
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self.demonstrations: List[Dict[str, Any]] = []
    
    def add_skill(self, skill: Skill):
        """Add a skill."""
        self.skills[skill.skill_id] = skill
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self.skills.get(skill_id)
    
    def find_skills(self, query: str) -> List[Skill]:
        """Find skills matching query."""
        results = []
        query_lower = query.lower()
        for skill in self.skills.values():
            if query_lower in skill.name.lower() or query_lower in skill.description.lower():
                results.append(skill)
        return results
    
    def record_demonstration(self, skill_name: str, steps: List[Dict[str, Any]], outcome: str):
        """Record a skill demonstration."""
        demo = {
            "skill_name": skill_name,
            "steps": steps,
            "outcome": outcome,
            "timestamp": time.time(),
        }
        self.demonstrations.append(demo)
    
    def learn_skill_from_demonstrations(self, skill_name: str, min_demos: int = 3) -> Optional[Skill]:
        """Learn skill from recorded demonstrations."""
        demos = [d for d in self.demonstrations if d["skill_name"] == skill_name]
        
        if len(demos) < min_demos:
            return None
        
        # Find common steps across demonstrations
        # This is simplified - real implementation would use sequence alignment
        common_steps = []
        
        # For now, use the first demonstration as template
        template = demos[0]
        
        skill = Skill(
            skill_id=f"skill_{uuid.uuid4().hex[:8]}",
            name=skill_name,
            description=f"Learned from {len(demos)} demonstrations",
            steps=[
                SkillStep(
                    step_id=f"step_{i}",
                    action=s.get("action", ""),
                    parameters=s.get("parameters", {}),
                    expected_outcome=s.get("expected_outcome", ""),
                )
                for i, s in enumerate(template["steps"])
            ],
        )
        
        self.add_skill(skill)
        return skill
    
    def execute_skill(self, skill_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a skill."""
        skill = self.get_skill(skill_id)
        if not skill:
            return {"success": False, "error": "Skill not found"}
        
        # Check preconditions
        for key, value in skill.preconditions.items():
            if context.get(key) != value:
                return {"success": False, "error": f"Precondition failed: {key}={value}"}
        
        # Execute steps
        results = []
        for step in skill.steps:
            # This would integrate with actual executors
            step_result = {
                "step_id": step.step_id,
                "action": step.action,
                "parameters": step.parameters,
                "success": True,
            }
            results.append(step_result)
        
        # Update statistics
        skill.execution_count += 1
        skill.updated_at = time.time()
        
        return {
            "success": True,
            "skill_id": skill_id,
            "steps": results,
        }


# ============================================================================
# Hierarchical Memory Compression
# ============================================================================

@dataclass
class MemoryNode:
    """Node in hierarchical memory."""
    node_id: str
    level: int  # 0 = raw, 1 = summary, 2 = abstract, etc.
    content: str
    summary: str = ""
    children: List[str] = field(default_factory=list)  # child node_ids
    parent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    importance: float = 1.0


class HierarchicalMemory:
    """Hierarchical memory with multi-level compression."""
    
    def __init__(self, max_levels: int = 4, compression_ratio: float = 0.3):
        self.max_levels = max_levels
        self.compression_ratio = compression_ratio
        self.nodes: Dict[str, MemoryNode] = {}
        self.root_nodes: List[str] = []  # Top-level nodes
    
    def add_memory(self, content: str, metadata: Dict[str, Any] = None, importance: float = 1.0) -> str:
        """Add raw memory at level 0."""
        node = MemoryNode(
            node_id=f"mem_{uuid.uuid4().hex[:8]}",
            level=0,
            content=content,
            metadata=metadata or {},
            importance=importance,
        )
        self.nodes[node.node_id] = node
        self.root_nodes.append(node.node_id)
        return node.node_id
    
    def compress_level(self, level: int, compressor: Callable[[List[str]], str]) -> List[str]:
        """Compress memories at given level to next level."""
        if level >= self.max_levels - 1:
            return []
        
        # Get nodes at this level
        level_nodes = [n for n in self.nodes.values() if n.level == level]
        
        if not level_nodes:
            return []
        
        # Group by some criteria (e.g., time, topic)
        # For simplicity, compress all into one summary
        contents = [n.content for n in level_nodes]
        summary = compressor(contents)
        
        # Create parent node
        parent = MemoryNode(
            node_id=f"mem_{uuid.uuid4().hex[:8]}",
            level=level + 1,
            content=summary,
            summary=summary,
            children=[n.node_id for n in level_nodes],
            metadata={"compressed_from": len(level_nodes)},
        )
        
        self.nodes[parent.node_id] = parent
        
        # Update children
        for child in level_nodes:
            child.parent = parent.node_id
        
        return [parent.node_id]
    
    def get_memory_at_level(self, level: int) -> List[MemoryNode]:
        """Get all memories at specific level."""
        return [n for n in self.nodes.values() if n.level == level]
    
    def get_hierarchy(self, node_id: str) -> List[MemoryNode]:
        """Get full hierarchy from node to root."""
        path = []
        current = self.nodes.get(node_id)
        while current:
            path.append(current)
            if current.parent:
                current = self.nodes.get(current.parent)
            else:
                break
        return path
    
    def search(self, query: str, max_level: int = None) -> List[MemoryNode]:
        """Search memories by content."""
        max_level = max_level or self.max_levels - 1
        results = []
        
        for node in self.nodes.values():
            if node.level <= max_level and query.lower() in node.content.lower():
                results.append(node)
        
        # Sort by importance and recency
        results.sort(key=lambda n: (n.importance, n.created_at), reverse=True)
        return results


# ============================================================================
# Unified Advanced Memory System
# ============================================================================

class AdvancedMemorySystem:
    """Unified advanced memory system combining all memory types."""
    
    def __init__(self, node_id: str = "local"):
        self.node_id = node_id
        
        # Core memory systems
        self.semantic = SemanticMemory()
        self.procedural = ProceduralMemory()
        self.hierarchical = HierarchicalMemory()
        
        # CRDT sync for cross-device
        self.crdt_sync = CRDTSyncManager(node_id)
        
        # Register CRDTs for each memory type
        self._setup_crdts()
    
    def _setup_crdts(self):
        """Setup CRDTs for memory synchronization."""
        # Semantic memory as LWW Map
        self.crdt_sync.create_lww_map("semantic_entities")
        self.crdt_sync.create_lww_map("semantic_relations")
        
        # Procedural memory as LWW Map
        self.crdt_sync.create_lww_map("procedural_skills")
        
        # Hierarchical memory as LWW Map
        self.crdt_sync.create_lww_map("hierarchical_nodes")
    
    def sync_to_crdts(self):
        """Sync memory state to CRDTs."""
        # Sync semantic entities
        entities_map = self.crdt_sync.get_crdt("semantic_entities")
        if entities_map:
            for eid, entity in self.semantic.entities.items():
                entities_map.set(eid, asdict(entity))
        
        # Sync relations
        relations_map = self.crdt_sync.get_crdt("semantic_relations")
        if relations_map:
            for rid, relation in self.semantic.relations.items():
                relations_map.set(rid, asdict(relation))
        
        # Sync skills
        skills_map = self.crdt_sync.get_crdt("procedural_skills")
        if skills_map:
            for sid, skill in self.procedural.skills.items():
                skills_map.set(sid, asdict(skill))
        
        # Sync hierarchical nodes
        nodes_map = self.crdt_sync.get_crdt("hierarchical_nodes")
        if nodes_map:
            for nid, node in self.hierarchical.nodes.items():
                nodes_map.set(nid, asdict(node))
    
    def sync_from_crdts(self):
        """Sync memory state from CRDTs."""
        # This would merge CRDT state into memory
        # Implementation depends on specific merge strategies
        pass
    
    async def start_sync(self, send_fn: Callable):
        """Start CRDT synchronization."""
        await self.crdt_sync.start_periodic_sync(send_fn)
    
    def stop_sync(self):
        """Stop CRDT synchronization."""
        self.crdt_sync.stop()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        return {
            "semantic": {
                "entities": len(self.semantic.entities),
                "relations": len(self.semantic.relations),
            },
            "procedural": {
                "skills": len(self.procedural.skills),
                "demonstrations": len(self.procedural.demonstrations),
            },
            "hierarchical": {
                "nodes": len(self.hierarchical.nodes),
                "levels": self.hierarchical.max_levels,
            },
            "crdt_sync": {
                "registered_crdts": len(self.crdt_sync.crdts),
                "peers": len(self.crdt_sync.peers),
            },
        }


# ============================================================================
# Default Instance
# ============================================================================

_advanced_memory: Optional[AdvancedMemorySystem] = None


def create_advanced_memory(node_id: str = "local") -> AdvancedMemorySystem:
    """Create advanced memory system."""
    global _advanced_memory
    _advanced_memory = AdvancedMemorySystem(node_id)
    return _advanced_memory


def get_advanced_memory() -> Optional[AdvancedMemorySystem]:
    """Get global advanced memory system."""
    return _advanced_memory