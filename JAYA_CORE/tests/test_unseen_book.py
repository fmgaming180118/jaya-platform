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
    # Add unseen book
    book_content = "The Secret Protocol X9 was developed in 2025 to enable quantum secure communications."
    loop.library.add_document("book_x9", book_content, {"title": "Protocol X9 Manual"})
    return loop

def test_unseen_book_retrieval(library_loop):
    """
    Ensures the loop retrieves the unseen book and answers based on it.
    """
    if not HAS_DEPS or not library_loop.model._is_loaded:
        pytest.skip("BLOCKED_EXTERNAL: transformers/torchvision dependency broken. Cannot run inference.")
        
    result = library_loop.run("What is Secret Protocol X9 used for?")
    
    assert result["status"] == "SUCCESS", f"Expected SUCCESS, got {result['status']}"
    assert "quantum secure communications" in result["answer"].lower()
    
    # Must cite the evidence
    assert any("book_x9" in ref for ref in result["evidence_refs"]), "Answer must be grounded with evidence_refs"
    
def test_unseen_book_no_hallucination(library_loop):
    """
    Ensures the loop gracefully handles missing information (INSUFFICIENT_EVIDENCE).
    """
    if not HAS_DEPS or not library_loop.model._is_loaded:
        pytest.skip("BLOCKED_EXTERNAL: transformers/torchvision dependency broken. Cannot run inference.")
        
    result = library_loop.run("Who authored the Secret Protocol X9?")
    
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert not result["evidence_refs"] or "book_x9" in result["evidence_refs"][0]
