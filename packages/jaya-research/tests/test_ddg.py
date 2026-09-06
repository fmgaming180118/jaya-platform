import pytest

pytestmark = [pytest.mark.network, pytest.mark.integration]


def test_ddg_live_search():
    from duckduckgo_search import DDGS

    results = list(DDGS().text("machine learning research", max_results=2))

    assert results
    assert all(result.get("title") for result in results)
