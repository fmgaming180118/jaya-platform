import sys, os, re, json, requests, pickle, hashlib
from pathlib import Path
import numpy as np
import faiss

JAYA_ROOT  = Path(__file__).resolve().parents[1]
PDF_FOLDER = Path(os.environ.get("JAYA_PDF_TRAINING_DIR", JAYA_ROOT.parent / "data-training" / "PDF-TugasAkhir")).expanduser().resolve()
CACHE_DIR  = JAYA_ROOT / "data" / "embedding_cache_v4"

def load_dotenv(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_dotenv(JAYA_ROOT / ".env")
API_KEY     = ENV.get("NVIDIA_API_KEY", "")
BASE_URL    = ENV.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
EMBED_MODEL = ENV.get("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
CHAT_MODEL  = "meta/llama-3.3-70b-instruct"

pdf_fn = "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"
pdf_path = PDF_FOLDER / pdf_fn
fhash  = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:10]
cf     = CACHE_DIR / f"{pdf_path.stem[:40]}_{fhash}_v4.pkl"

with open(cf, "rb") as f:
    c = pickle.load(f)
pages = c["pages"]
idx = faiss.deserialize_index(c["index"])

cover = pages[:5]
hint = [46, 47, 48]
question = "Dalam landasan teori BPMN, apa fungsi dan definisi elemen Gateway menurut dokumen ini?"

# Run retrieve
parts = []
seen = set()

# 1. Cover
for p in cover:
    parts.append(f"[HAL.{p['page']} - IDENTITAS]\n{p['text'][:1200]}")
    seen.add(p["page"])

# 2. Hint
page_map = {p["page"]: p for p in pages}
for pnum in hint:
    if pnum in page_map and pnum not in seen:
        parts.append(f"[HAL.{pnum} - KUNCI]\n{page_map[pnum]['text'][:1200]}")
        seen.add(pnum)

# 3. FAISS
q_txt = question[:1600]
resp = requests.post(
    f"{BASE_URL}/embeddings",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json={"input": [q_txt], "model": EMBED_MODEL, "input_type": "query"},
    timeout=30
)
if resp.status_code == 200:
    q_emb = np.array([resp.json()["data"][0]["embedding"]], dtype=np.float32)
    faiss.normalize_L2(q_emb)
    dists, idxs = idx.search(q_emb, 12 + len(seen) + 5)
    added = 0
    print("FAISS Search Results:")
    for d, si in zip(dists[0], idxs[0]):
        if si < 0 or added >= 12:
            break
        page = pages[si]
        print(f"  Page {page['page']} (score={d:.3f})")
        if page["page"] not in seen:
            parts.append(f"[HAL.{page['page']} score={d:.3f}]\n{page['text'][:1000]}")
            seen.add(page["page"])
            added += 1

context = "\n\n---\n\n".join(parts)

SYS = (
    "Kamu adalah ekstraktor informasi faktual dari dokumen akademik Indonesia.\n"
    "ATURAN MUTLAK:\n"
    "1. Jawab HANYA dari teks KONTEKS\n"
    "2. DILARANG gunakan pengetahuan di luar konteks\n"
    "3. Jika tidak ada: tulis hanya 'TIDAK DITEMUKAN'\n"
    "4. Jawab singkat dan langsung, max 3 kalimat\n"
    "5. Kutip data spesifik (nama, angka, kode warna) persis dari dokumen"
)

msg = f"KONTEKS:\n{context}\n\nPERTANYAAN: {question}\n\nJAWABAN SINGKAT:"

print("\n=== Sending request to LLM with full context ===")
resp = requests.post(
    f"{BASE_URL}/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json={
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user",   "content": msg}
        ],
        "temperature": 0.0,
        "max_tokens": 200,
        "stop": [
            "PERTANYAAN:", "KONTEKS:", "ATURAN:",
            "Perhatian", "Lihat Konteks", "Penjelasan:",
            "Rasmi", "Catatan:"
        ],
    },
    timeout=45
)
if resp.status_code == 200:
    ans = resp.json()["choices"][0]["message"]["content"].strip()
    print("LLM RESPONSE:")
    print(repr(ans))
else:
    print(f"API Error: {resp.status_code}")
