
from duckduckgo_search import DDGS

def test_ddg():
    print("Testing DDG...")
    try:
        results = DDGS().text("president of Indonesia", max_results=2)
        print(f"Results found: {len(results)}")
        for r in results:
            print(f"- {r['title']}")
    except Exception as e:
        print(f"DDG Error: {e}")

if __name__ == "__main__":
    test_ddg()
