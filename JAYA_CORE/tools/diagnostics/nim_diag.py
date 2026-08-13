import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from JAYA_CORE.src.brain_v2.extensions.nvidia_llm import NvidiaNIMClient

def run_nim_diagnostic() -> None:
    # Manual .env load for test
    env_path = str(REPO_ROOT / ".env")
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    
    api_key = os.getenv("NVIDIA_API_KEY") or ""
    api_key_preview = f"{api_key[:10]}..." if api_key else "<missing>"
    print(f"API Key start: {api_key_preview}")
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
    run_nim_diagnostic()
