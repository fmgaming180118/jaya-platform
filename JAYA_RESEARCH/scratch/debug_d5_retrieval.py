import sys, os, re, json, time, hashlib, pickle
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
EMBED_MODEL = ENV.get("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
CHAT_MODEL  = "meta/llama-3.3-70b-instruct"

# Hanny PDF cache path
pdf_fn = "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"
pdf_path = PDF_FOLDER / pdf_fn
fhash  = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:10]
cf     = CACHE_DIR / f"{pdf_path.stem[:40]}_{fhash}_v4.pkl"

if cf.exists():
    with open(cf, "rb") as f:
        c = pickle.load(f)
    pages = c["pages"]
    print(f"Loaded {len(pages)} pages from cache.")
else:
    print("Cache not found!")
    sys.exit(1)

# Now, retrieve logic
cover = pages[:5]
hint = [46, 47, 48]
question = "Dalam landasan teori BPMN, apa fungsi dan definisi elemen Gateway menurut dokumen ini?"

# Let's inspect pages 46, 47, 48 in page_map
page_map = {p["page"]: p for p in pages}
print("\n--- Inspecting page numbers in page_map ---")
for pnum in hint:
    if pnum in page_map:
        print(f"Page {pnum} found, text length: {len(page_map[pnum]['text'])}")
        print(page_map[pnum]['text'][:200])
        print("...")
    else:
        print(f"Page {pnum} NOT found in page_map!")

# Let's check which page actually contains "Gateway untuk mengontrol"
for p in pages:
    if "gateway untuk mengontrol" in p["text"].lower():
        print(f"Found search string in Page {p['page']}!")
        print(p["text"][:500])
