import pytest

from jaya_research.research.academic.literature import ArxivClient

pytestmark = [pytest.mark.network, pytest.mark.integration]


@pytest.mark.parametrize(
    "topic",
    ["Fullstack Development", "Artificial Intelligence", "ReactJS"],
)
def test_live_arxiv_search(topic):
    papers = ArxivClient().search_papers(topic, max_results=2)

    assert papers
    assert all(paper.get("title") for paper in papers)
