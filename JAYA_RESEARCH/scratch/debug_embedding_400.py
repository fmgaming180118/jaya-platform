import sys, os, requests, time
from pathlib import Path

JAYA_ROOT  = Path(__file__).resolve().parents[1]
PDF_FOLDER = Path(os.environ.get("JAYA_PDF_TRAINING_DIR", JAYA_ROOT.parent / "data-training" / "PDF-TugasAkhir")).expanduser().resolve()
OUT_FILE   = JAYA_ROOT / "scratch" / "debug_embedding_results.txt"

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
pages = []
with pdfplumber.open(str(pdf_path)) as pdf:
    for i, page in enumerate(pdf.pages, 1):
        text = (page.extract_text(x_tolerance=2, y_tolerance=2) or "").strip()
        try:
            for table in (page.extract_tables() or []):
                for row in table:
                    if row:
                        rt = " | ".join(str(c or "").strip() for c in row if c and str(c).strip())
                        if rt:
                            text += "\n" + rt
        except:
            pass
        if text.strip():
            pages.append({"page": i, "text": text.strip()})

# Test only first 45 pages to make it quick, using 1000 limit
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write(f"Testing first 45 pages with 1000 limit...\n")
    f.flush()
    failed = []
    for idx, p in enumerate(pages[:45]):
        txt = p["text"][:1000]
        if not txt.strip():
            continue
        try:
            resp = requests.post(
                f"{BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"input": [txt], "model": EMBED_MODEL, "input_type": "passage"},
                timeout=10
            )
            if resp.status_code != 200:
                f.write(f"Page {p['page']} failed with code {resp.status_code}: {resp.text}\n")
                f.flush()
                failed.append(p['page'])
            else:
                # success
                pass
        except Exception as e:
            f.write(f"Page {p['page']} error: {e}\n")
            f.flush()
            failed.append(p['page'])
        time.sleep(0.05)
    f.write(f"Finished testing 1000 limit. Failed pages: {failed}\n")
    f.flush()
print("Finished quick test.")
