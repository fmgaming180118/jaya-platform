import sys, os, re, json, requests
from pathlib import Path

JAYA_ROOT  = Path(r"d:\Kampus\coba-coba\jaya-research\JAYA_RESEARCH")
PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")
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
CHAT_MODEL  = "meta/llama-3.3-70b-instruct"

# Load the cache file
import pickle
pdf_fn = "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"
pdf_path = PDF_FOLDER / pdf_fn
import hashlib
fhash  = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:10]
cf     = CACHE_DIR / f"{pdf_path.stem[:40]}_{fhash}_v4.pkl"

with open(cf, "rb") as f:
    c = pickle.load(f)
pages = c["pages"]

# Mock cover pages
cover = pages[:5]
hint = [46, 47, 48]
question = "Dalam landasan teori BPMN, apa fungsi dan definisi elemen Gateway menurut dokumen ini?"

# Retrieve context
parts = []
seen = set()
for p in cover:
    parts.append(f"[HAL.{p['page']} - IDENTITAS]\n{p['text'][:1200]}")
    seen.add(p["page"])

page_map = {p["page"]: p for p in pages}
for pnum in hint:
    if pnum in page_map and pnum not in seen:
        parts.append(f"[HAL.{pnum} - KUNCI]\n{page_map[pnum]['text'][:1200]}")
        seen.add(pnum)

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

print("=== Sending request to LLM ===")
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
    },
    timeout=45
)
if resp.status_code == 200:
    ans = resp.json()["choices"][0]["message"]["content"].strip()
    print("LLM RESPONSE:")
    print(ans)
else:
    print(f"API Error: {resp.status_code}")
    print(resp.text)
