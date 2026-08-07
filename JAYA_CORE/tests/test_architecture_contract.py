import yaml
import pytest
from pathlib import Path

# Adjust path based on execution directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT))
from JAYA_CORE.src.brain_v2.format.schema import JayaFlags

def load_manifest():
    manifest_path = PROJECT_ROOT / "JAYA_CORE" / "contracts" / "40_pillars.yaml"
    with open(manifest_path, "r") as f:
        return yaml.safe_load(f)

def test_manifest_has_exactly_40_pillars():
    manifest = load_manifest()
    assert len(manifest) == 40, f"Expected 40 pillars, found {len(manifest)}"

def test_manifest_ids_are_1_to_40_with_no_duplicates():
    manifest = load_manifest()
    ids = [p["id"] for p in manifest]
    assert len(ids) == 40
    assert len(set(ids)) == 40
    assert min(ids) == 1
    assert max(ids) == 40

def test_manifest_no_duplicate_names():
    manifest = load_manifest()
    names = [p["name"] for p in manifest]
    assert len(set(names)) == 40, "Found duplicate names in manifest"

def test_manifest_matches_jaya_flags():
    manifest = load_manifest()
    
    # Get all flags that are actually pillars (ID <= 40).
    # In Python IntFlag, we might have composite flags or extension bits.
    # We'll just look at the members that map to 1 << (id - 1) effectively, 
    # but since schema.py uses auto(), we'll map by name.
    
    flag_names_in_schema = set()
    for name, member in JayaFlags.__members__.items():
        # Exclude known aliases or extension flags
        if name in ("QUANTIZED", "ENCRYPTED_AES256", "QUANTUM_SAFE", "HAS_LORA", "PACKED_WEIGHTS", "NANO_PROFILE", "SELF_EVOLVING"):
            continue
        flag_names_in_schema.add(name)
        
    assert len(flag_names_in_schema) == 40, f"Expected 40 core flags, found {len(flag_names_in_schema)}"
    
    manifest_flag_names = {p["source_flag"].replace("JayaFlags.", "") for p in manifest}
    
    assert manifest_flag_names == flag_names_in_schema, "Manifest flags do not perfectly match JayaFlags schema"

def test_layer_ranges():
    manifest = load_manifest()
    for p in manifest:
        pid = p["id"]
        layer = p["layer"]
        if 1 <= pid <= 10:
            assert layer == "BIOLOGICAL_SOUL"
        elif 11 <= pid <= 20:
            assert layer == "SOVEREIGN_ARMOR"
        elif 21 <= pid <= 29:
            assert layer == "IRON_ENGINE"
        elif 30 <= pid <= 40:
            assert layer == "TRANSCENDENTAL"
        else:
            pytest.fail(f"Invalid pillar ID {pid}")

def test_canary_pillars():
    manifest = load_manifest()
    pillars_by_id = {p["id"]: p for p in manifest}
    
    assert pillars_by_id[33]["name"] == "Agentic RAG"
    assert pillars_by_id[38]["name"] == "Meta Cognitive Planning"
    assert pillars_by_id[40]["name"] == "Intent Extrapolation"

def test_canonical_names_snapshot():
    manifest = load_manifest()
    expected_names = [
        "Pure Logic", "Resource Aware", "Active Dreaming", "Multimodal Reflex", "Logical Homeostasis",
        "Stochastic Spontaneity", "Cognitive Silence", "Holographic Memory", "Neural Regeneration", "Affective Metabolism",
        "DNA Anchor", "Immune System", "Cryptographic Skin", "Hardware Locked", "Ethical Heart",
        "Quantum Resistant", "Socratic Mirror", "Zero Trust", "Legacy Protocol", "Sovereign Privacy",
        "Lingua Logica", "Ternary Precision", "Sandboxed Imagination", "Morphic Kernel", "Digital Epigenetics",
        "Semantic Bridge", "Temporal Weighting", "Self Bootstrapping", "Binary Cortex",
        "Twin Protocol", "Narrative Continuity", "Collective Pulse", "Agentic RAG", "Dynamic Sparsity MoE",
        "Activation Sparsity", "Speculative Reasoning", "Hybrid Consciousness", "Meta Cognitive Planning", "Dynamic Objective", "Intent Extrapolation"
    ]
    manifest_names = [p["name"] for p in sorted(manifest, key=lambda x: x["id"])]
    assert manifest_names == expected_names, "Canonical names do not match the expected snapshot!"

def test_binary_flag_values_snapshot():
    # Enforce exact binary values to avoid .jay format breakage
    expected_values = {
        "PURE_LOGIC": 1,
        "RESOURCE_AWARE": 2,
        "ACTIVE_DREAMING": 4,
        "MULTIMODAL_REFLEX": 8,
        "LOGICAL_HOMEOSTASIS": 16,
        "STOCHASTIC_SPONTANEITY": 32,
        "COGNITIVE_SILENCE": 64,
        "HOLOGRAPHIC_MEMORY": 128,
        "NEURAL_REGENERATION": 256,
        "AFFECTIVE_METABOLISM": 512,
        "DNA_ANCHOR": 1024,
        "IMMUNE_SYSTEM": 2048,
        "CRYPTOGRAPHIC_SKIN": 4096,
        "HARDWARE_LOCKED": 8192,
        "ETHICAL_HEART": 16384,
        "QUANTUM_RESISTANT": 32768,
        "SOCRATIC_MIRROR": 65536,
        "ZERO_TRUST": 131072,
        "LEGACY_PROTOCOL": 262144,
        "SOVEREIGN_PRIVACY": 524288,
        "LINGUA_LOGICA": 1048576,
        "TERNARY_PRECISION": 2097152,
        "SANDBOXED_IMAGINATION": 4194304,
        "MORPHIC_KERNEL": 8388608,
        "DIGITAL_EPIGENETICS": 16777216,
        "SEMANTIC_BRIDGE": 33554432,
        "TEMPORAL_WEIGHTING": 67108864,
        "SELF_BOOTSTRAPPING": 134217728,
        "BINARY_CORTEX": 268435456,
        "TWIN_PROTOCOL": 536870912,
        "NARRATIVE_CONTINUITY": 1073741824,
        "COLLECTIVE_PULSE": 2147483648,
        "AGENTIC_RAG": 4294967296,
        "DYNAMIC_SPARSITY_MOE": 8589934592,
        "ACTIVATION_SPARSITY": 17179869184,
        "SPECULATIVE_REASONING": 34359738368,
        "HYBRID_CONSCIOUSNESS": 68719476736,
        "META_COGNITIVE_PLANNING": 137438953472,
        "DYNAMIC_OBJECTIVE": 274877906944,
        "INTENT_EXTRAPOLATION": 549755813888,
    }
    
    for flag_name, expected_val in expected_values.items():
        actual_val = getattr(JayaFlags, flag_name).value
        assert actual_val == expected_val, f"Binary compatibility broken! {flag_name} expected {expected_val}, got {actual_val}"

def test_architecture_jarvis_drift():
    jarvis_path = PROJECT_ROOT / "docs" / "ARCHITECTURE_JARVIS.md"
    with open(jarvis_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Ensure it references the canonical document
    assert "arsitektur_40_pilar_jaya.md" in content, "ARCHITECTURE_JARVIS.md must reference the canonical 40-pillar document"
    # Ensure it doesn't try to duplicate the list incorrectly
    assert "Core Cognitive Pillars (1-10)" not in content, "ARCHITECTURE_JARVIS.md contains duplicated/conflicting pillar definitions"
