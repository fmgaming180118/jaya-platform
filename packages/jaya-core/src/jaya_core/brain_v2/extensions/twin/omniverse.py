"""Stub module for potential Omniverse SDK integration.

The real implementation will use NVIDIA Omniverse Kit APIs once the
project moves beyond the conceptual stage. For now, the functions simply
log calls and indicate the SDK is unavailable.
"""

_available = False


def is_available() -> bool:
    """Return whether the Omniverse SDK was successfully initialised."""
    return _available


def initialize_sdk() -> bool:
    """Attempt to initialize the Omniverse environment.

    Returns ``True`` if the SDK is successfully imported/initialized.  In
    this stub it always returns ``False``.
    """
    global _available
    _available = False
    return _available


def load_scene(path: str) -> bool:
    logger = __import__("logging").getLogger("OmniverseStub")
    logger.warning("load_scene called, but Omniverse SDK is not available")
    return False


def step(actions):
    logger = __import__("logging").getLogger("OmniverseStub")
    logger.warning("step called with %r, no simulation occurs", actions)
    return {}


def shutdown():
    logger = __import__("logging").getLogger("OmniverseStub")
    logger.info("shutdown called on stub")
