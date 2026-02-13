"""
JAYA Research Assistant - AI-Q Integration Package

A general-purpose deep research system built on NVIDIA's AI-Q blueprint.
Enables autonomous research on any topic with multimodal RAG and parallel search.
"""

__version__ = "0.1.0"
__author__ = "JAYA Research Team"

# Import core components
try:
    from .agent import ResearchAgent
except ImportError as e:
    print(f"Warning: Could not import ResearchAgent: {e}")
    ResearchAgent = None

try:
    from .enhanced_rag import EnhancedRAGClient
except ImportError as e:
    print(f"Warning: Could not import EnhancedRAGClient: {e}")
    try:
        from .rag_client import RAGClient as EnhancedRAGClient
    except ImportError:
        EnhancedRAGClient = None

__all__ = ["ResearchAgent", "EnhancedRAGClient"]
