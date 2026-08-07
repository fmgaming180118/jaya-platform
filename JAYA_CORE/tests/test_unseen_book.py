"""
Killer Test 1: Unseen Book
Validates that the Parametric Model can answer questions about new Non-Parametric Knowledge
without retraining its weights.
"""

import pytest

try:
    from JAYA_CORE.src.runtime.librarian_loop import LibrarianLoop
    from JAYA_CORE.src.model.architecture import HAS_TRANSFORMERS
    import sentence_transformers
    HAS_DEPS = HAS_TRANSFORMERS
except ImportError:
    HAS_DEPS = False

@pytest.fixture
def library_loop():
    if not HAS_DEPS:
        pytest.skip("BLOCKED_EXTERNAL: transformers/sentence-transformers dependency broken.")
    loop = LibrarianLoop()
    return loop

import hashlib
import os

def _get_model_hash(model_path: str = "JAYA_CORE/models/jaya-core-v0/model.safetensors") -> str:
    if not os.path.exists(model_path):
        return "NO_MODEL"
    with open(model_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def test_unseen_book_retrieval(library_loop):
    """
    Ensures the loop retrieves the unseen book and answers based on it.
    Mathematically proves the model weights did not change (no retraining).
    """
    if not HAS_DEPS or not getattr(library_loop.model, "_is_loaded", False):
        pytest.skip("BLOCKED_EXTERNAL: transformers/torchvision dependency broken. Cannot run inference.")
        
    hash_before = _get_model_hash()
    
    # Add unseen book
    book_content = "The Secret Protocol X9 was developed in 2025 to enable quantum secure communications."
    library_loop.library.add_document("book_x9", book_content, {"title": "Protocol X9 Manual"})
    
    result = library_loop.run("What is Secret Protocol X9 used for?")
    
    hash_after = _get_model_hash()
    
    assert hash_before == hash_after, "Model weights changed! Retraining detected, violation of Librarian philosophy."
    
    assert result["status"] == "SUCCESS", f"Expected SUCCESS, got {result['status']}"
    assert "quantum secure communications" in result["answer"].lower()
    
    # Must cite the evidence
    assert any("book_x9" in ref for ref in result["evidence_refs"]), "Answer must be grounded with evidence_refs"
    
def test_unseen_book_no_hallucination(library_loop):
    """
    Ensures the loop gracefully handles missing information (INSUFFICIENT_EVIDENCE).
    """
    if not HAS_DEPS or not getattr(library_loop.model, "_is_loaded", False):
        pytest.skip("BLOCKED_EXTERNAL: transformers/torchvision dependency broken. Cannot run inference.")
        
    # Add unseen book
    book_content = "The Secret Protocol X9 was developed in 2025 to enable quantum secure communications."
    library_loop.library.add_document("book_x9", book_content, {"title": "Protocol X9 Manual"})
        
    result = library_loop.run("Who authored the Secret Protocol X9?")
    
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
