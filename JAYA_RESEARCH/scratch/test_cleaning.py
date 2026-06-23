import sys, os, requests, re
from pathlib import Path

JAYA_ROOT  = Path(r"d:\Kampus\coba-coba\jaya-research\JAYA_RESEARCH")
PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")

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

pdf_fn = "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"
pdf_path = PDF_FOLDER / pdf_fn

import pdfplumber

with pdfplumber.open(str(pdf_path)) as pdf:
    # Page 8 is index 7
    page_8_raw = pdf.pages[7].extract_text() or ""
    # Page 12 is index 11
    page_12_raw = pdf.pages[11].extract_text() or ""

def clean_text(text):
    # Replace 2 or more dots with a single space
    text = re.sub(r'\.{2,}', ' ', text)
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

p8_cleaned = clean_text(page_8_raw)
p12_cleaned = clean_text(page_12_raw)

print(f"Page 8 raw char count: {len(page_8_raw)} | cleaned: {len(p8_cleaned)}")
print(f"Page 12 raw char count: {len(page_12_raw)} | cleaned: {len(p12_cleaned)}")

# Let's try embedding them (first 1200 chars)
for name, txt in [("Page 8 (cleaned)", p8_cleaned[:1200]), ("Page 12 (cleaned)", p12_cleaned[:1200])]:
    try:
        resp = requests.post(
            f"{BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"input": [txt], "model": EMBED_MODEL, "input_type": "passage"},
            timeout=10
        )
        if resp.status_code == 200:
            print(f"{name} embedding success!")
        else:
            print(f"{name} embedding failed: {resp.text}")
    except Exception as e:
        print(f"{name} error: {e}")
