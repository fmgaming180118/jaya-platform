"""JAYA Research Assistant package with lazy capability exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import ResearchAgent as ResearchAgent
    from .enhanced_rag import EnhancedRAGClient as EnhancedRAGClient

__version__ = "0.1.0"
__author__ = "JAYA Research Team"
__all__ = ["ResearchAgent", "EnhancedRAGClient"]

_LAZY_EXPORTS = {
    "ResearchAgent": (".agent", "ResearchAgent"),
    "EnhancedRAGClient": (".enhanced_rag", "EnhancedRAGClient"),
}


def __getattr__(name: str) -> Any:
    """Load model/provider-backed components only when explicitly requested."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
