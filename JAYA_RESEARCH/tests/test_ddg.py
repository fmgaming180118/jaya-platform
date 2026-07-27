import pytest
from duckduckgo_search import DDGS

pytestmark = [pytest.mark.network, pytest.mark.integration]


def test_ddg_live_search():
    results = list(DDGS().text("machine learning research", max_results=2))

    assert results
    assert all(result.get("title") for result in results)
