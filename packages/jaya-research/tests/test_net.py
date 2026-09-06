import ssl

import pytest
import requests

pytestmark = [pytest.mark.network, pytest.mark.integration]


def test_live_tls_connections():
    assert ssl.get_default_verify_paths()

    google = requests.get("https://www.google.com", timeout=5)
    duckduckgo = requests.get("https://duckduckgo.com", timeout=5)

    google.raise_for_status()
    duckduckgo.raise_for_status()
