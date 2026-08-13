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
    print(f"Total pages: {len(pdf.pages)}")
    for idx, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        # search tables too
        for table in (page.extract_tables() or []):
            for row in table:
                if row:
                    text += "\n" + " | ".join(str(c or "").strip() for c in row if c)
        if "gateway" in text.lower():
            print(f"=== Page {idx+1} ===")
            for line in text.split("\n"):
                if "gateway" in line.lower() or "gerbang" in line.lower() or "bpmn" in line.lower():
                    print(line)
