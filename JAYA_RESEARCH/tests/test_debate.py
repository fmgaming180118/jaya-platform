import requests
import json
import time

API_URL = "http://localhost:8000"

def test_debate():
    print("Testing Debate Endpoint...")
    payload = {
        "topic": "The future of AGI: Utopia or Dystopia?",
        "persona_1": "Optimist",
        "persona_2": "Doomer",
        "rounds": 3
    }
    
    try:
        response = requests.post(f"{API_URL}/debate", json=payload)
        response.raise_for_status()
        data = response.json()
        print("Debate Response Received:")
        print(json.dumps(data, indent=2))
        assert "debate_transcript" in data
        print("✅ Debate Test Passed")
    except Exception as e:
        print(f"❌ Debate Test Failed: {e}")

if __name__ == "__main__":
    # Wait for server to be potentially ready if we were starting it here, 
    # but we assume it's running or we might need to start it manually in another terminal for this test.
    # For this check, we'll try to hit it.
    test_debate()
