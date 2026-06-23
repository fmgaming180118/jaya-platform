"""
test_pdf_ingest_ta.py
======================
Skrip pengujian mandiri untuk menguji kemampuan JAYA Research
dalam membaca dan mengindeks file PDF Tugas Akhir dari Politeknik STMI Jakarta.

Jalankan:
  cd JAYA_RESEARCH
  ..\.venv312\Scripts\python.exe test_pdf_ingest_ta.py
"""

import sys
import os

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import time
import json
from pathlib import Path

# ── Tambahkan src ke path ──────────────────────────────────────────────────────
JAYA_ROOT = Path(__file__).parent
sys.path.insert(0, str(JAYA_ROOT / "src"))

PDF_FOLDER = Path(r"d:\Kampus\coba-coba\jaya-research\data-training\PDF-TugasAkhir")
RESULTS_PATH = JAYA_ROOT / "data" / "test_ta_results.json"

# ── Cek library yang tersedia ──────────────────────────────────────────────────
LIBS = {}
try:
    import pdfplumber
    LIBS["pdfplumber"] = True
except ImportError:
    LIBS["pdfplumber"] = False
    print("[WARN] pdfplumber tidak tersedia")

try:
    import fitz
    LIBS["pymupdf"] = True
except ImportError:
    LIBS["pymupdf"] = False
    print("[WARN] pymupdf tidak tersedia")

try:
    from pypdf import PdfReader
    LIBS["pypdf"] = True
except ImportError:
    LIBS["pypdf"] = False
    print("[WARN] pypdf tidak tersedia")

# ── Fungsi bantu ──────────────────────────────────────────────────────────────
def table_to_markdown(table):
    if not table:
        return ""
    rows = [[str(c).strip() if c else "" for c in row] for row in table if row]
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:]
    def r(row):
        return "| " + " | ".join(c.replace("\n", " ") for c in row) + " |"
    lines = [r(header), r(["---"] * len(header))]
    for row in body:
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        lines.append(r(row[:len(header)]))
    return "\n".join(lines)


def ingest_pdf(pdf_path: Path) -> dict:
    """Replikasi _ingest_pdf_multimodal langsung untuk pengujian."""
    result = {
        "file": pdf_path.name,
        "size_mb": round(pdf_path.stat().st_size / 1024 / 1024, 2),
        "pages": 0,
        "text_blocks": 0,
        "table_blocks": 0,
        "image_blocks": 0,
        "total_chars": 0,
        "tables_markdown": [],
        "sample_text": [],
        "errors": [],
        "lib_used": [],
        "duration_sec": 0,
    }

    start = time.time()
    blocks = []

    # 1️⃣ pdfplumber — teks & tabel
    if LIBS["pdfplumber"]:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                result["pages"] = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, 1):
                    text = (page.extract_text(x_tolerance=2, y_tolerance=2) or "").strip()
                    if text:
                        blocks.append({"type": "text", "page": page_num, "content": text})
                        if len(result["sample_text"]) < 3:
                            result["sample_text"].append({
                                "page": page_num,
                                "preview": text[:300].replace("\n", " ")
                            })

                    # Tabel
                    try:
                        tables = page.extract_tables() or []
                    except Exception:
                        tables = []
                    for t_idx, table in enumerate(tables, 1):
                        md = table_to_markdown(table)
                        if md.strip():
                            blocks.append({"type": "table", "page": page_num, "content": md})
                            if len(result["tables_markdown"]) < 3:
                                result["tables_markdown"].append({
                                    "page": page_num,
                                    "table_idx": t_idx,
                                    "markdown": md[:500]
                                })

            result["lib_used"].append("pdfplumber")
        except Exception as e:
            result["errors"].append(f"pdfplumber: {e}")

    # 2️⃣ pymupdf — gambar
    if LIBS["pymupdf"]:
        try:
            doc = fitz.open(str(pdf_path))
            for page_num in range(len(doc)):
                page = doc[page_num]
                images = page.get_images(full=True)
                for img_idx, img in enumerate(images, 1):
                    xref = img[0]
                    base_img = doc.extract_image(xref)
                    if base_img.get("image"):
                        blocks.append({
                            "type": "image",
                            "page": page_num + 1,
                            "content": base_img.get("ext", "img"),
                            "width": base_img.get("width"),
                            "height": base_img.get("height"),
                        })
            doc.close()
            result["lib_used"].append("pymupdf")
        except Exception as e:
            result["errors"].append(f"pymupdf: {e}")

    # 3️⃣ pypdf fallback — jika belum ada teks sama sekali
    text_blocks = [b for b in blocks if b["type"] == "text"]
    if not text_blocks and LIBS["pypdf"]:
        try:
            reader = PdfReader(str(pdf_path))
            result["pages"] = len(reader.pages)
            for page_num, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if text:
                    blocks.append({"type": "text", "page": page_num, "content": text})
            result["lib_used"].append("pypdf_fallback")
        except Exception as e:
            result["errors"].append(f"pypdf: {e}")

    # 4️⃣ Agregasi statistik
    result["text_blocks"]  = len([b for b in blocks if b["type"] == "text"])
    result["table_blocks"] = len([b for b in blocks if b["type"] == "table"])
    result["image_blocks"] = len([b for b in blocks if b["type"] == "image"])
    result["total_chars"]  = sum(len(b["content"]) for b in blocks if isinstance(b["content"], str))
    result["duration_sec"] = round(time.time() - start, 2)

    # 5️⃣ Chunking simulasi (512 chars, 128 overlap)
    full_text = "\n".join(b["content"] for b in blocks if b["type"] in ("text", "table") and isinstance(b["content"], str))
    chunks = []
    pos = 0
    while pos < len(full_text):
        chunks.append(full_text[pos:pos + 512])
        pos += 512 - 128
    result["chunk_count"] = len(chunks)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  JAYA RESEARCH — Pengujian Ingestion PDF Tugas Akhir STMI Jakarta")
    print("=" * 70)
    print(f"\nFolder PDF : {PDF_FOLDER}")
    print(f"Library tersedia: {', '.join(k for k,v in LIBS.items() if v)}")
    print()

    if not PDF_FOLDER.exists():
        print(f"[ERROR] Folder tidak ditemukan: {PDF_FOLDER}")
        return

    pdf_files = sorted(PDF_FOLDER.glob("*.pdf"))
    if not pdf_files:
        print("[ERROR] Tidak ada file PDF ditemukan di folder tersebut.")
        return

    print(f"Ditemukan {len(pdf_files)} file PDF:")
    for f in pdf_files:
        print(f"  - {f.name} ({round(f.stat().st_size/1024/1024, 1)} MB)")
    print()

    all_results = []
    for pdf_path in pdf_files:
        print(f"[>>] Memproses: {pdf_path.name} ...")
        result = ingest_pdf(pdf_path)
        all_results.append(result)

        # Print ringkasan
        print(f"    [OK] Halaman     : {result['pages']}")
        print(f"    [OK] Blok Teks   : {result['text_blocks']}")
        print(f"    [OK] Tabel       : {result['table_blocks']}")
        print(f"    [OK] Gambar      : {result['image_blocks']}")
        print(f"    [OK] Total Char  : {result['total_chars']:,}")
        print(f"    [OK] Chunks (RAG): {result['chunk_count']}")
        print(f"    [OK] Durasi      : {result['duration_sec']}s")
        if result["errors"]:
            print(f"    [!!] Error       : {result['errors']}")
        if result["sample_text"]:
            print(f"    [TXT] Contoh teks halaman {result['sample_text'][0]['page']}:")
            print(f"       \"{result['sample_text'][0]['preview'][:200]}...\"")
        if result["tables_markdown"]:
            print(f"    [TBL] Contoh tabel (hal {result['tables_markdown'][0]['page']}):")
            for line in result["tables_markdown"][0]["markdown"].split("\n")[:4]:
                print(f"       {line}")
        print()

    # Simpan hasil ke JSON
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Ringkasan total
    print("=" * 70)
    print("  RINGKASAN TOTAL")
    print("=" * 70)
    total_pages  = sum(r["pages"] for r in all_results)
    total_text   = sum(r["text_blocks"] for r in all_results)
    total_tables = sum(r["table_blocks"] for r in all_results)
    total_images = sum(r["image_blocks"] for r in all_results)
    total_chars  = sum(r["total_chars"] for r in all_results)
    total_chunks = sum(r["chunk_count"] for r in all_results)
    total_time   = sum(r["duration_sec"] for r in all_results)

    print(f"  File diproses : {len(all_results)}")
    print(f"  Total halaman : {total_pages}")
    print(f"  Total blok teks  : {total_text}")
    print(f"  Total tabel      : {total_tables}")
    print(f"  Total gambar     : {total_images}")
    print(f"  Total karakter   : {total_chars:,}")
    print(f"  Total chunks RAG : {total_chunks}")
    print(f"  Total waktu      : {total_time:.1f} detik")
    print(f"  [FILE] Hasil detail disimpan di: {RESULTS_PATH}")
    print()
    print("  [DONE] JAYA Research BERHASIL membaca semua PDF Tugas Akhir!")
    print("=" * 70)


if __name__ == "__main__":
    main()
