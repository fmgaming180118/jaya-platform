import os
import sys

# Add path to JAYA_CORE
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'JAYA_CORE')))

from JAYA_CORE.src.brain_v2.extensions.nvidia_llm import NvidiaNIMClient

def test_connection():
    # Manual .env load for test
    env_path = '.env'
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    
    print(f"API Key start: {os.getenv('NVIDIA_API_KEY')[:10]}...")
    print(f"Model: {os.getenv('NVIDIA_MODEL')}")
    print(f"Model Reasoning: {os.getenv('NVIDIA_MODEL_REASONING')}")
    
    client_normal = NvidiaNIMClient(is_reasoning=False)
    client_reasoning = NvidiaNIMClient(is_reasoning=True)
    
    print("\nTesting Normal Model...")
    res_n = client_normal.ask("You are a helpful assistant.", "Say 'Hello from JAYA Normal'", max_tokens=20)
    print(f"Response: {res_n}")
    
    print("\nTesting Reasoning Model...")
    res_r = client_reasoning.ask("You are a reasoning assistant.", "Why is 1+1=2?", max_tokens=100)
    print(f"Response: {res_r}")

if __name__ == "__main__":
    test_connection()
