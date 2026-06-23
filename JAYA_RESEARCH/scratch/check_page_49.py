import pdfplumber
from pathlib import Path

pdf_path = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir\TA_1318001_Hanny-Kurnia-Putri_FINAL_SIDANG.pdf")

with pdfplumber.open(str(pdf_path)) as pdf:
    page = pdf.pages[48] # page 49
    print(f"=== Text of Page 49 ===")
    print(page.extract_text() or "")
    print(f"=== Tables of Page 49 ===")
    for table in (page.extract_tables() or []):
        for row in table:
            if row:
                print(" | ".join(str(c or "").strip() for c in row if c))
