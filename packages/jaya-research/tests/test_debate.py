import pytest
import requests

pytestmark = [pytest.mark.network, pytest.mark.integration]

API_URL = "http://localhost:8000"


def test_live_debate_endpoint():
    response = requests.post(
        f"{API_URL}/debate",
        json={
            "topic": "The future of AGI: Utopia or Dystopia?",
            "persona_1": "Optimist",
            "persona_2": "Skeptic",
            "rounds": 3,
        },
        timeout=30,
    )

    response.raise_for_status()
    assert "debate_transcript" in response.json()
