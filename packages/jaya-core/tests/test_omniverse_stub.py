import pytest

from jaya_core.brain_v2.extensions.twin import omniverse


def test_omniverse_stub_not_available():
    # initialization should return False in stub
    assert omniverse.initialize_sdk() is False
    assert omniverse.load_scene("dummy") is False
    assert omniverse.step({'action': 'noop'}) == {}
    omniverse.shutdown()  # should not raise
