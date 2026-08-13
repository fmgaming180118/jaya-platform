import sys, os, re, json, time, hashlib, pickle
from pathlib import Path

JAYA_ROOT  = Path(__file__).resolve().parents[1]
PDF_FOLDER = Path(os.environ.get("JAYA_PDF_TRAINING_DIR", JAYA_ROOT.parent / "data-training" / "PDF-TugasAkhir")).expanduser().resolve()
CACHE_DIR  = JAYA_ROOT / "data" / "embedding_cache_v4"

pdf_fn = "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"
pdf_path = PDF_FOLDER / pdf_fn
fhash  = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:10]
cf     = CACHE_DIR / f"{pdf_path.stem[:40]}_{fhash}_v4.pkl"

with open(cf, "rb") as f:
    c = pickle.load(f)
pages = c["pages"]
page_47 = next(p for p in pages if p["page"] == 47)

print(f"Index of 'Gateway': {page_47['text'].find('Gateway')}")
print(f"Index of 'Gateway untuk mengontrol': {page_47['text'].lower().find('gateway untuk mengontrol')}")
print("\n--- FIRST 1200 CHARACTERS ---")
print(page_47['text'][:1200])
