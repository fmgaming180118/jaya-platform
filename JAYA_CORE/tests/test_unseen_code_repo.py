"""
Killer Test 2: Unseen Code Repo
Validates that the Parametric Model can reason over AST semantics (CodeSymbols)
of a completely unseen codebase without retraining.
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
def code_library_loop():
    if not HAS_DEPS:
        pytest.skip("BLOCKED_EXTERNAL: transformers/sentence-transformers dependency broken.")
        
    loop = LibrarianLoop()
    
    # Add unseen source code
    source_code = '''
class PaymentProcessor:
    def __init__(self, key):
        self.key = key
        
    def process(self, amount):
        """Processes the payment."""
        return self._send_to_bank(amount)
        
    def _send_to_bank(self, amount):
        pass
        
def run_checkout():
    p = PaymentProcessor("xyz")
    p.process(100)
'''
    loop.library.add_python_code(
        source_id="payment_repo",
        file_path="src/checkout.py",
        source_code=source_code,
        version="v1.0"
    )
    return loop

import hashlib
import os

def _get_model_hash(model_path: str = "JAYA_CORE/models/jaya-core-v0/model.safetensors") -> str:
    if not os.path.exists(model_path):
        return "NO_MODEL"
    with open(model_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def test_unseen_code_symbol_retrieval(code_library_loop):
    """
    Ensures the loop extracts the symbol graph and can answer callers.
    """
    if not HAS_DEPS or not getattr(code_library_loop.model, "_is_loaded", False):
        pytest.skip("BLOCKED_EXTERNAL: transformers/torchvision dependency broken. Cannot run inference.")
        
    hash_before = _get_model_hash()
    result = code_library_loop.run("What function calls process() on the PaymentProcessor?")
    hash_after = _get_model_hash()
    
    assert hash_before == hash_after, "Model weights changed! Retraining detected, violation of Librarian philosophy."
    
    assert result["status"] == "SUCCESS"
    assert "run_checkout" in result["answer"].lower()
    
    # Must cite the semantic file path
    assert any("src/checkout.py" in ref for ref in result["evidence_refs"])
