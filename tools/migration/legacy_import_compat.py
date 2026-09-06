# Backwards compatibility layer for JAYA_CORE imports
# This allows existing code using `from JAYA_CORE.src.xxx` to work

import sys
from pathlib import Path

# Resolve package locations from the repository root rather than the caller's cwd.
_repository_root = Path(__file__).resolve().parents[2]
_packages_root = _repository_root / "packages"
_new_core_path = _packages_root / "jaya-core" / "src"
_new_agent_path = _packages_root / "jaya-agent" / "src"
_new_os_path = _packages_root / "jaya-os" / "src"
_new_research_path = _packages_root / "jaya-research" / "src"

for p in [_new_core_path, _new_agent_path, _new_os_path, _new_research_path]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Module mapping for backwards compatibility
_MODULE_MAP = {
    # JAYA_CORE -> jaya_core
    "JAYA_CORE": "jaya_core",
    "JAYA_CORE.src": "jaya_core",
    "JAYA_CORE.src.agents": "jaya_core.agents",
    "JAYA_CORE.src.ai_connectors": "jaya_core.ai_connectors",
    "JAYA_CORE.src.artifacts": "jaya_core.artifacts",
    "JAYA_CORE.src.brain_v2": "jaya_core.brain_v2",
    "JAYA_CORE.src.capabilities": "jaya_core.capabilities",
    "JAYA_CORE.src.cli": "jaya_core.cli",
    "JAYA_CORE.src.cognitive": "jaya_core.cognitive",
    "JAYA_CORE.src.consciousness": "jaya_core.consciousness",
    "JAYA_CORE.src.contracts": "jaya_core.contracts",
    "JAYA_CORE.src.devices": "jaya_core.devices",
    "JAYA_CORE.src.engine": "jaya_core.engine",
    "JAYA_CORE.src.evolution": "jaya_core.evolution",
    "JAYA_CORE.src.genesis": "jaya_core.genesis",
    "JAYA_CORE.src.identity": "jaya_core.identity",
    "JAYA_CORE.src.jaya_language": "jaya_core.jaya_language",
    "JAYA_CORE.src.jbc": "jaya_core.jbc",
    "JAYA_CORE.src.jbc_x": "jaya_core.jbc_x",
    "JAYA_CORE.src.library": "jaya_core.library",
    "JAYA_CORE.src.memory": "jaya_core.memory",
    "JAYA_CORE.src.mesh": "jaya_core.mesh",
    "JAYA_CORE.src.model": "jaya_core.model",
    "JAYA_CORE.src.models": "jaya_core.models",
    "JAYA_CORE.src.multimodal": "jaya_core.multimodal",
    "JAYA_CORE.src.neural": "jaya_core.neural",
    "JAYA_CORE.src.nlu": "jaya_core.nlu",
    "JAYA_CORE.src.observability": "jaya_core.observability",
    "JAYA_CORE.src.operations": "jaya_core.operations",
    "JAYA_CORE.src.organism": "jaya_core.organism",
    "JAYA_CORE.src.os_kernel": "jaya_core.os_kernel",
    "JAYA_CORE.src.performance": "jaya_core.performance",
    "JAYA_CORE.src.privacy": "jaya_core.privacy",
    "JAYA_CORE.src.production": "jaya_core.production",
    "JAYA_CORE.src.protection": "jaya_core.protection",
    "JAYA_CORE.src.rag": "jaya_core.rag",
    "JAYA_CORE.src.reasoning": "jaya_core.reasoning",
    "JAYA_CORE.src.resources": "jaya_core.resources",
    "JAYA_CORE.src.runtime": "jaya_core.runtime",
    "JAYA_CORE.src.sandbox": "jaya_core.sandbox",
    "JAYA_CORE.src.security": "jaya_core.security",
    "JAYA_CORE.src.self_improvement": "jaya_core.self_improvement",
    "JAYA_CORE.src.skills": "jaya_core.skills",
    "JAYA_CORE.src.soul": "jaya_core.soul",
    "JAYA_CORE.src.sync": "jaya_core.sync",
    "JAYA_CORE.src.verification": "jaya_core.verification",
    "JAYA_CORE.src.voice": "jaya_core.voice",
    "JAYA_CORE.src.worker": "jaya_core.worker",
    # JAYA_AGENT -> jaya_agent
    "JAYA_AGENT": "jaya_agent",
    "JAYA_AGENT.src": "jaya_agent",
    "JAYA_AGENT.src.contracts": "jaya_agent.contracts",
    "JAYA_AGENT.src.interfaces": "jaya_agent.interfaces",
    "JAYA_AGENT.src.memory": "jaya_agent.memory",
    "JAYA_AGENT.src.multiagent": "jaya_agent.multiagent",
    "JAYA_AGENT.src.runtime": "jaya_agent.runtime",
    "JAYA_AGENT.src.security": "jaya_agent.security",
    "JAYA_AGENT.src.skills": "jaya_agent.skills",
    # JAYA_OS -> jaya_os
    "JAYA_OS": "jaya_os",
    "JAYA_OS.src": "jaya_os",
    "JAYA_OS.src.jaya_os": "jaya_os",
    # JAYA_RESEARCH -> jaya_research
    "JAYA_RESEARCH": "jaya_research",
    "JAYA_RESEARCH.src": "jaya_research",
    "JAYA_RESEARCH.src.academic": "jaya_research.academic",
    "JAYA_RESEARCH.src.benchmark": "jaya_research.benchmark",
    "JAYA_RESEARCH.src.brain": "jaya_research.brain",
    "JAYA_RESEARCH.src.capability_boundary": "jaya_research.capability_boundary",
    "JAYA_RESEARCH.src.config": "jaya_research.config",
    "JAYA_RESEARCH.src.discovery": "jaya_research.discovery",
    "JAYA_RESEARCH.src.digital_twin": "jaya_research.digital_twin",
    "JAYA_RESEARCH.src.edge": "jaya_research.edge",
    "JAYA_RESEARCH.src.engine": "jaya_research.engine",
    "JAYA_RESEARCH.src.evolution": "jaya_research.evolution",
    "JAYA_RESEARCH.src.graphrag": "jaya_research.graphrag",
    "JAYA_RESEARCH.src.immune_system": "jaya_research.immune_system",
    "JAYA_RESEARCH.src.integrity": "jaya_research.integrity",
    "JAYA_RESEARCH.src.introspection": "jaya_research.introspection",
    "JAYA_RESEARCH.src.jit": "jaya_research.jit",
    "JAYA_RESEARCH.src.memory": "jaya_research.memory",
    "JAYA_RESEARCH.src.network": "jaya_research.network",
    "JAYA_RESEARCH.src.optimizer": "jaya_research.optimizer",
    "JAYA_RESEARCH.src.playground": "jaya_research.playground",
    "JAYA_RESEARCH.src.provider": "jaya_research.provider",
    "JAYA_RESEARCH.src.proactive": "jaya_research.proactive",
    "JAYA_RESEARCH.src.research": "jaya_research.research",
    "JAYA_RESEARCH.src.safeguard": "jaya_research.safeguard",
    "JAYA_RESEARCH.src.sandbox": "jaya_research.sandbox",
    "JAYA_RESEARCH.src.synthesize": "jaya_research.synthesize",
    "JAYA_RESEARCH.src.tools": "jaya_research.tools",
    "JAYA_RESEARCH.src.training": "jaya_research.training",
    "JAYA_RESEARCH.src.voice_agent": "jaya_research.voice_agent",
    "JAYA_RESEARCH.src.auto_finetune": "jaya_research.auto_finetune",
    "JAYA_RESEARCH.src.dataset": "jaya_research.dataset",
    "JAYA_RESEARCH.src.tokenizer": "jaya_research.tokenizer",
    "JAYA_RESEARCH.src.distill": "jaya_research.distill",
}


class _CompatibilityLoader:
    """PEP 302 compatible loader for backwards compatibility."""

    def __init__(self, target_module):
        self.target_module = target_module

    def create_module(self, spec):
        return None  # Use default module creation

    def exec_module(self, module):
        # Import the actual module and copy its attributes
        import importlib
        actual = importlib.import_module(self.target_module)
        for attr in dir(actual):
            if not attr.startswith("_"):
                setattr(module, attr, getattr(actual, attr))


class _CompatibilityFinder:
    """PEP 302 compatible finder for backwards compatibility."""

    def find_spec(self, fullname, path, target=None):
        if fullname in _MODULE_MAP:
            from importlib.util import spec_from_loader
            return spec_from_loader(fullname, _CompatibilityLoader(_MODULE_MAP[fullname]))
        return None


# Install the compatibility finder
sys.meta_path.insert(0, _CompatibilityFinder())

# Also create direct module aliases in sys.modules for immediate access
for old_name, new_name in _MODULE_MAP.items():
    try:
        import importlib
        module = importlib.import_module(new_name)
        sys.modules[old_name] = module
    except ImportError:
        pass  # Module not yet available, will be handled by finder
