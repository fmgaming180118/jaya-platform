"""
JAYA Research Platform

Knowledge discovery, evolutionary research, and experimentation platform
for advancing AI capabilities through systematic research.
"""

__version__ = "0.1.0"
__author__ = "JAYA Research Team"

# Stable, side-effect-free package exports. Domain services stay in their
# owning modules so importing ``jaya_research`` never loads models or providers.
from .config import ResearchSettings, get_settings
from .research.config import ResearchConfig

__all__ = [
    "ResearchConfig",
    "ResearchSettings",
    "get_settings",
    "__version__",
]
