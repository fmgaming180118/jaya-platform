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

def test_architecture_jarvis_drift():
    jarvis_path = PROJECT_ROOT / "docs" / "ARCHITECTURE_JARVIS.md"
    with open(jarvis_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Ensure it references the canonical document
    assert "arsitektur_40_pilar_jaya.md" in content, "ARCHITECTURE_JARVIS.md must reference the canonical 40-pillar document"
    # Ensure it doesn't try to duplicate the list incorrectly
    assert "Core Cognitive Pillars (1-10)" not in content, "ARCHITECTURE_JARVIS.md contains duplicated/conflicting pillar definitions"
