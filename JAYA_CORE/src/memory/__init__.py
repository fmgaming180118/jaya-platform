"""
Advanced Memory Package for JAYA_CORE.

Provides advanced memory systems:
- Semantic Memory: Knowledge graph with entity resolution
- Procedural Memory: Skill acquisition from demonstration
- CRDT-based Cross-Device Sync: Conflict-free replicated data types
- Hierarchical Memory Compression
- Episodic Memory: SQLite-based event storage
- Working Memory: In-memory cache with TTL
"""

from __future__ import annotations

from .advanced import (
    CRDTType,
    VectorClock,
    CRDT,
    LWWRegister,
    LWWMap,
    ORSet,
    CRDTSyncManager,
    Entity,
    Relation,
    SemanticMemory,
    SkillStep,
    Skill,
    ProceduralMemory,
    MemoryNode,
    HierarchicalMemory,
    AdvancedMemorySystem,
    create_advanced_memory,
    get_advanced_memory,
)
from .episodic import EpisodicMemoryStore, MemoryEvent
from .working import WorkingMemory, WorkingMemoryItem

__all__ = [
    "CRDTType",
    "VectorClock",
    "CRDT",
    "LWWRegister",
    "LWWMap",
    "ORSet",
    "CRDTSyncManager",
    "Entity",
    "Relation",
    "SemanticMemory",
    "SkillStep",
    "Skill",
    "ProceduralMemory",
    "MemoryNode",
    "HierarchicalMemory",
    "AdvancedMemorySystem",
    "create_advanced_memory",
    "get_advanced_memory",
    "EpisodicMemoryStore",
    "MemoryEvent",
    "WorkingMemory",
    "WorkingMemoryItem",
]