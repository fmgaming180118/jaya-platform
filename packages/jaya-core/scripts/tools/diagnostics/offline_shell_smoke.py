import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CORE_ROOT))

from scripts.jaya_shell import process_offline_response
from jaya_core.brain_v2.soul.language_policy import get_policy

def run_offline_shell_smoke() -> None:
    print("--- Memulai Tes Logika Offline JAYA ---")
    id_pack = get_policy("id")
    en_pack = get_policy("en")
    
    # Mock data dari RAG
    mock_rag_results = [
        {"topic": "Fonologi", "content": "Dialek Jakarta memiliki sistem vokal yang khas, termasuk penggunaan e-pepet."},
        {"topic": "Fonologi", "content": "Perubahan bunyi sering terjadi pada akhiran -a menjadi -e."}
    ]
    
    query = "Apa itu fonologi Jakarta?"
    response = process_offline_response(query, mock_rag_results)
    
    print(f"Query: {query}")
    print(f"JAYA Response:\n{response}")

    # Header can be customized by language-policy override; keep assertion semantic.
    assert "1. Fonologi" in response
    assert "e-pepet" in response

    no_memory_query = "Jelaskan kenapa migrasi device tetap harus bisa berbahasa"
    no_memory_response = process_offline_response(no_memory_query, [], rag_instance=None)
    print(f"\nNo-Memory Query: {no_memory_query}")
    print(f"JAYA No-Memory Response:\n{no_memory_response}")

    assert id_pack["no_memory"] in no_memory_response
    assert id_pack["portable"] in no_memory_response

    mixed_query = "Jelaskan fungsi cache lokal. Then explain why this still works after migration."
    mixed_response = process_offline_response(mixed_query, [], rag_instance=None)
    print(f"\nMixed Query: {mixed_query}")
    print(f"JAYA Mixed Response:\n{mixed_response}")

    assert id_pack["mixed_notice"] in mixed_response
    assert id_pack["segment_no_memory"].format(index=1) in mixed_response
    assert en_pack["segment_no_memory"].format(index=2) in mixed_response
    assert id_pack["portable"] in mixed_response
    assert en_pack["portable"] in mixed_response
    print("\n[SUCCESS] Logika Offline JAYA terverifikasi!")


if __name__ == "__main__":
    run_offline_shell_smoke()
