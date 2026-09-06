"""
Killer Test 3: Native Core Remediation
Tests SQLite persistence, NativeJayaLibrarianRuntime format validation, and Strict Evidence Grounding.
"""

import pytest
import os
import json
import hashlib
from pathlib import Path

try:
    from jaya_core.runtime.librarian_loop import LibrarianLoop
    from jaya_core.library.library_manager import LibraryManager
    import torch
    import safetensors
    from transformers import AutoTokenizer
    import sentence_transformers
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

def test_library_persistence(tmp_path):
    if not HAS_DEPS:
        pytest.skip("BLOCKED_EXTERNAL")
    db_path = str(tmp_path / "persistence.db")
    
    # Process 1
    lib1 = LibraryManager(db_path=db_path)
    lib1.add_document("doc1", "The capital of France is Paris.", {"title": "Geography"})
    
    # Assert it's in the catalog
    res1 = lib1.retrieve_evidence("capital of France")
    assert len(res1) > 0
    assert "Paris" in res1[0]["content"]
    
    # Process 2 (simulate restart by reinitializing)
    lib2 = LibraryManager(db_path=db_path)
    # The document should have been loaded into the catalog
    res2 = lib2.retrieve_evidence("capital of France")
    assert len(res2) > 0
    assert "Paris" in res2[0]["content"]

def test_invalid_evidence_rejection(tmp_path, monkeypatch):
    if not HAS_DEPS:
        pytest.skip("BLOCKED_EXTERNAL")
        
    loop = LibrarianLoop()
    loop.library.db_path = str(tmp_path / "test_library.db")
    
    if not getattr(loop.model, "_is_loaded", False):
        pytest.skip("BLOCKED_EXTERNAL: Checkpoint missing")
        
    # Mock the model's reason_and_respond to return hallucinated references
    def mock_reason(*args, **kwargs):
        return {
            "retrieval_required": False,
            "answer": "This is a hallucinated answer.",
            "evidence_refs": ["fake_doc_123"], # This doesn't exist in the library
            "confidence": 0.99
        }
    monkeypatch.setattr(loop.model, "reason_and_respond", mock_reason)
    
    result = loop.run("Tell me something")
    
    # Should reject the answer because evidence_refs contains a hallucinated ref
    assert result["status"] == "INVALID_EVIDENCE_REFERENCE"
    assert "fake_doc_123" in result["evidence_refs"]

def test_native_runtime_format(tmp_path):
    if not HAS_DEPS:
        pytest.skip("BLOCKED_EXTERNAL")
        
    # Test loading a mocked checkpoint with mismatching SHA
    model_dir = tmp_path / "fake_model"
    model_dir.mkdir()
    
    with open(model_dir / "model_config.json", "w") as f:
        json.dump({"vocab_size": 100, "d_model": 16, "n_layers": 1, "n_heads": 1}, f)
        
    with open(model_dir / "model.safetensors", "wb") as f:
        f.write(b"fake_weights")
        
    with open(model_dir / "training_manifest.json", "w") as f:
        json.dump({"artifact_sha256": "expected_hash"}, f)
        
    from jaya_core.model.native_architecture import NativeJayaLibrarianRuntime
    
    runtime = NativeJayaLibrarianRuntime(model_dir=str(model_dir))
    
    with pytest.raises(ValueError, match="MODEL_ARTIFACT_INTEGRITY_ERROR"):
        runtime.load()
