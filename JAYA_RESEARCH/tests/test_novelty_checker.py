import pytest
from src.research.academic.novelty_checker import NoveltyChecker

@pytest.mark.asyncio
async def test_novelty_checker_known_theory():
    checker = NoveltyChecker()
    
    hypothesis = "Energy equals mass times the speed of light squared (E=mc^2)."
    
    # We use a broad term so ArXiv will definitely catch something related to relativity or mass energy, compensating for Scholar rate limits.
    result = await checker.verify_novelty(hypothesis, keywords=["relativity", "Einstein", "mass", "energy"])
    
    # It should confidently say NO it is NOT novel
    assert result["is_novel"] is False
    assert result["confidence"] > 0.7

@pytest.mark.asyncio
async def test_novelty_checker_absurd_theory():
    checker = NoveltyChecker()
    
    hypothesis = "A neural network architecture where weight updates are transmitted backward in time using tachyon fields to eliminate training latency entirely."
    
    result = await checker.verify_novelty(hypothesis)
    
    # It should say YES it is novel (because it doesn't exist)
    assert result["is_novel"] is True
