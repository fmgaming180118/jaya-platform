import os

import pdfplumber
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PDF_FOLDER = Path(
    os.environ.get(
        "JAYA_PDF_TRAINING_DIR",
        REPOSITORY_ROOT / "data-training" / "PDF-TugasAkhir",
    )
).expanduser().resolve()
pdf_path = PDF_FOLDER / "TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf"

with pdfplumber.open(str(pdf_path)) as pdf:
    page = pdf.pages[46] # page 47
    print(f"=== Text of Page 47 ===")
    print(page.extract_text() or "")
    print(f"=== Tables of Page 47 ===")
    for table in (page.extract_tables() or []):
        for row in table:
            if row:
                print(" | ".join(str(c or "").strip() for c in row if c))
