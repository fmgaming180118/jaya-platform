import sys, os
from pathlib import Path

# Configure sys.stdout to handle UTF-8 printing in Windows terminals
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from src.research.academic.novelty_checker import NoveltyChecker

async def test_novelty_checker_known_theory():
    checker = NoveltyChecker()
    
    hypothesis = "Energy equals mass times the speed of light squared (E=mc^2)."
    
    # We use a broad term so ArXiv will definitely catch something related to relativity or mass energy, compensating for Scholar rate limits.
    result = await checker.verify_novelty(hypothesis, keywords=["relativity", "Einstein", "mass", "energy"])
    
    # It should confidently say NO it is NOT novel
    assert result["is_novel"] is False
    assert result["confidence"] > 0.7

async def test_novelty_checker_absurd_theory():
    checker = NoveltyChecker()
    
    hypothesis = "A neural network architecture where weight updates are transmitted backward in time using tachyon fields to eliminate training latency entirely."
    
    result = await checker.verify_novelty(hypothesis)
    
    # It should say YES it is novel (because it doesn't exist)
    assert result["is_novel"] is True

if __name__ == "__main__":
    import asyncio
    print("Running Novelty Checker tests...")
    
    async def run_tests():
        try:
            print("\n1. Testing known theory (E=mc^2)...")
            checker1 = NoveltyChecker()
            result1 = await checker1.verify_novelty("Energy equals mass times the speed of light squared (E=mc^2).", keywords=["relativity", "Einstein", "mass", "energy"])
            print("Raw Response 1:\n", result1.get("raw_response"))
            assert result1["is_novel"] is False
            print("=> Success!")
            
            print("\n2. Testing absurd theory (Tachyon updates)...")
            checker2 = NoveltyChecker()
            result2 = await checker2.verify_novelty("A neural network architecture where weight updates are transmitted backward in time using tachyon fields to eliminate training latency entirely.")
            print("Raw Response 2:\n", result2.get("raw_response"))
            assert result2["is_novel"] is True
            print("=> Success!")
            
            print("\nAll tests completed successfully!")
        except Exception as e:
            import traceback
            print(f"\nTest failed: {e}")
            traceback.print_exc()
            import sys
            sys.exit(1)
            
    asyncio.run(run_tests())
