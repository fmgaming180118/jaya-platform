import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from research.enhanced_rag import EnhancedRAGClient

rag = EnhancedRAGClient(vector_store_path="workspaces/test_qa_workspace/vector_store.json")
pdf_paths = [
    r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir\1318029_Affifah Nasrillah Fajri_TA.pdf",
    r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir\1319058_Ihsan Ali_TA.pdf",
    r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir\Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf",
    r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir\TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"
]

documents = []
texts = []
for path in pdf_paths:
    pdf_result = rag._ingest_pdf_multimodal(path)
    for block in pdf_result.get("documents", []):
        content = block.get("content", "") or block.get("caption", "")
        if content is None:
            content = ""
        documents.append(block)
        texts.append(content)

print("Total texts:", len(texts))
print("None count:", sum(1 for t in texts if t is None))
print("Empty string count:", sum(1 for t in texts if t == ""))
print("Types in texts:", set(type(t) for t in texts))

# Let's find some sample texts that might cause issue
for i, t in enumerate(texts):
    if len(t.strip()) == 0:
        print(f"Index {i} is empty/whitespace")

try:
    print("Testing embedder with first 20 texts:")
    embs = rag.embedder.embed_texts(texts[:20])
    print("Success! Embedding shape:", len(embs), "x", len(embs[0]))
except Exception as e:
    print("Failed to embed first 20:", e)

# Test full list
try:
    print("Testing embedder with all texts:")
    embs = rag.embedder.embed_texts(texts)
    print("Success! Embedding shape:", len(embs), "x", len(embs[0]))
except Exception as e:
    print("Failed to embed all:", e)
