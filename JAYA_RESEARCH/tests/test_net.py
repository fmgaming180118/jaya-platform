
import requests
import ssl
import certifi

def test_conn():
    print(f"SSL Context: {ssl.get_default_verify_paths()}")
    try:
        print("Testing Google...")
        r = requests.get("https://www.google.com", timeout=5)
        print(f"Google: {r.status_code}")
    except Exception as e:
        print(f"Google Fail: {e}")

    try:
        print("Testing DuckDuckGo...")
        r = requests.get("https://duckduckgo.com", timeout=5)
        print(f"DDG: {r.status_code}")
    except Exception as e:
        print(f"DDG Fail: {e}")

if __name__ == "__main__":
    test_conn()
