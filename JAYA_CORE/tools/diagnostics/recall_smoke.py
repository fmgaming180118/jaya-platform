import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from JAYA_CORE.src.brain_v2.soul.agentic_rag import AgenticRAG
from JAYA_CORE.src.brain_v2.extensions.nvidia_llm import NvidiaNIMClient

# Load .env
env_path = str(REPO_ROOT / ".env")
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

def run_recall_smoke() -> None:
    rag = AgenticRAG(db_path=str(REPO_ROOT / "rag_vault.db"))
    llm = NvidiaNIMClient()
    
    # Test query that triggers recall from previous autonomous session
    query = "Apa yang kamu ketahui tentang Fonologi Dialek Jakarta?"
    
    print(f"\nUser: {query}")
    
    # Simulate jaya_shell logic
    context_results = rag.recall(query, limit=2)
    context_text = ""
    if context_results:
        print("\n[CONTEXT RECALLED]")
        for r in context_results:
            print(f"- {r['topic']}: {r['content'][:100]}...")
        context_text = "\n\nKonsep/Fakta yang relevan:\n" + "\n".join([f"- {r['content']}" for r in context_results])
    
    messages = [
        {"role": "system", "content": "Anda adalah JAYA. Gunakan data berikut untuk menjawab."},
        {"role": "user", "content": query + context_text}
    ]
    
    print("\nJAYA is thinking...")
    response = llm.chat(messages)
    print(f"\nJAYA: {response}")


if __name__ == "__main__":
    run_recall_smoke()
