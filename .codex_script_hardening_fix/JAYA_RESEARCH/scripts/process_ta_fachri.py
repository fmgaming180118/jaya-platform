#!/usr/bin/env python3
# ruff: noqa: E501
"""
Process a single PDF (Tugas Akhir) - Extract text, images, tables, references
Creates organized folder with markdown file
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

import fitz  # PyMuPDF for image extraction
import pdfplumber

# Add project root and src to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = (PROJECT_ROOT / "data").resolve(strict=False)
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from teacher import Teacher  # noqa: E402


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_pdf_path(raw_path: str | os.PathLike[str]) -> Path:
    """Resolve and validate an explicit PDF input path."""
    path = Path(raw_path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"input is not a file: {path}")
    if path.suffix.casefold() != ".pdf":
        raise ValueError(f"input must be a PDF file: {path}")
    return path


def resolve_output_dir(raw_path: str | os.PathLike[str]) -> Path:
    """Keep generated research artifacts under JAYA_RESEARCH/data."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    output_dir = candidate.resolve(strict=False)
    if not _is_relative_to(output_dir, DATA_ROOT):
        raise ValueError(f"output directory must stay inside {DATA_ROOT}: {output_dir}")
    return output_dir


class TugasAkhirProcessor:
    """Process Tugas Akhir PDF and create structured markdown output"""

    def __init__(self, pdf_path: Path, output_dir: Path):
        self.pdf_path = resolve_pdf_path(pdf_path)
        self.output_dir = resolve_output_dir(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize LLM for analysis
        self.teacher = Teacher(model_type="reasoning")

        # Folder name from PDF
        self.folder_name = self.sanitize_folder_name(self.pdf_path.name)
        self.journal_folder = self.output_dir / self.folder_name
        self.journal_folder.mkdir(parents=True, exist_ok=True)

    def sanitize_folder_name(self, name: str) -> str:
        """Create safe folder name from PDF filename"""
        name = name.replace(".pdf", "")
        name = re.sub(r"[^\w\-_]", "_", name)
        return name[:100]

    def extract_with_pdfplumber(self) -> Dict[str, Any]:
        """Extract text, tables using pdfplumber"""
        result = {"pages": [], "tables": [], "full_text": ""}

        with pdfplumber.open(str(self.pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""

                tables = page.extract_tables() or []
                page_tables = []
                for table_idx, table in enumerate(tables):
                    if table and any(cell for row in table for cell in row if cell):
                        page_tables.append(
                            {"page": i, "table_index": table_idx, "data": table}
                        )
                        result["tables"].append(
                            {"page": i, "table_index": table_idx, "data": table}
                        )

                result["pages"].append({"page": i, "text": text, "tables": page_tables})
                result["full_text"] += f"\n--- PAGE {i} ---\n" + text + "\n\n"

        return result

    def extract_images_with_pymupdf(self) -> List[Dict[str, Any]]:
        """Extract images using PyMuPDF"""
        images = []
        images_folder = self.journal_folder / "images"
        images_folder.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(self.pdf_path))

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                img_filename = f"page_{page_num + 1}_img_{img_idx + 1}.{image_ext}"
                img_path = images_folder / img_filename

                with open(img_path, "wb") as f:
                    f.write(image_bytes)

                images.append(
                    {
                        "page": page_num + 1,
                        "index": img_idx + 1,
                        "filename": img_filename,
                        "path": str(img_path.relative_to(self.output_dir)),
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0),
                        "ext": image_ext,
                    }
                )

        doc.close()
        return images

    def extract_references_section(self, full_text: str) -> str:
        """Find and extract references/bibliography section"""
        ref_patterns = [
            r"\n\s*references\s*\n",
            r"\n\s*bibliography\s*\n",
            r"\n\s*reference list\s*\n",
            r"\n\s*literature cited\s*\n",
            r"\n\s*works cited\s*\n",
            r"\n\s*daftar pustaka\s*\n",
            r"\n\s*referensi\s*\n",
        ]

        text_lower = full_text.lower()
        for pattern in ref_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return full_text[match.start() :]

        return full_text[-15000:]

    def analyze_with_llm(self, text: str) -> Dict[str, Any]:
        """Use LLM to analyze and structure the paper content"""
        analysis_text = text[:50000]

        prompt = f"""
Anda adalah Research Analyst. Analisis Tugas Akhir berikut dan ekstrak informasi terstruktur.

Nama File: {self.pdf_path.name}

Konten Tugas Akhir (ekstrak):
{analysis_text}
...

Tugas:
1. Ekstrak metadata: Judul lengkap, Nama Mahasiswa, NIM, Program Studi, Tahun, Dosen Pembimbing
2. Identifikasi struktur: Bab 1-5 (Pendahuluan, Tinjauan Pustaka, Metodologi, Hasil & Pembahasan, Kesimpulan)
3. Ekstrak: Masalah, Tujuan, Metodologi, Hasil Utama, Kesimpulan, Saran
4. Identifikasi tabel dan gambar penting beserta caption/deskripsi
5. Ekstrak referensi utama (top 15 referensi paling relevan)
6. Buat ringkasan eksekutif (3-4 paragraf)

Format output sebagai JSON dengan keys:
- metadata: {{title, student_name, nim, program_studi, year, pembimbing}}
- structure: {{chapters: []}}
- problem_statement: ""
- objectives: []
- methodology: ""
- key_results: []
- conclusions: []
- suggestions: []
- tables_summary: [{{page, description, caption}}]
- figures_summary: [{{page, description, caption}}]
- references: [{{title, authors, year, source}}]
- executive_summary: ""
"""

        try:
            response = self.teacher.ask(
                prompt,
                system_instruction="Anda adalah Research Analyst yang menganalisis Tugas Akhir. Output HANYA JSON valid, tanpa markdown atau penjelasan tambahan.",
            )

            response = response.strip()
            response = re.sub(r"^```json\s*", "", response)
            response = re.sub(r"^```\s*", "", response)
            response = re.sub(r"\s*```$", "", response)

            return json.loads(response)
        except Exception as e:
            print(f"[LLM Analysis Error] {self.pdf_path.name}: {e}")
            return {}

    def create_markdown(
        self,
        pdfplumber_data: Dict,
        images: List,
        llm_analysis: Dict,
        references_text: str,
    ) -> str:
        """Create comprehensive markdown file"""

        metadata = llm_analysis.get("metadata", {})
        structure = llm_analysis.get("structure", {})
        problem = llm_analysis.get("problem_statement", "")
        objectives = llm_analysis.get("objectives", [])
        methodology = llm_analysis.get("methodology", "")
        key_results = llm_analysis.get("key_results", [])
        conclusions = llm_analysis.get("conclusions", [])
        suggestions = llm_analysis.get("suggestions", [])
        tables_summary = llm_analysis.get("tables_summary", [])
        figures_summary = llm_analysis.get("figures_summary", [])
        references = llm_analysis.get("references", [])
        exec_summary = llm_analysis.get("executive_summary", "")

        md_lines = []

        # Header
        title = metadata.get("title", self.pdf_path.name)
        md_lines.append(f"# {title}")
        md_lines.append("")

        # Metadata
        md_lines.append("## 📋 Metadata Tugas Akhir")
        md_lines.append("")
        md_lines.append(f"- **File Asli**: `{self.pdf_path.name}`")
        md_lines.append(f"- **Judul**: {metadata.get('title', 'Tidak diketahui')}")
        md_lines.append(
            f"- **Mahasiswa**: {metadata.get('student_name', 'Tidak diketahui')}"
        )
        md_lines.append(f"- **NIM**: {metadata.get('nim', 'Tidak diketahui')}")
        md_lines.append(
            f"- **Program Studi**: {metadata.get('program_studi', 'Tidak diketahui')}"
        )
        md_lines.append(f"- **Tahun**: {metadata.get('year', 'Tidak diketahui')}")
        md_lines.append(
            f"- **Dosen Pembimbing**: {metadata.get('pembimbing', 'Tidak diketahui')}"
        )
        md_lines.append("")

        # Executive Summary
        if exec_summary:
            md_lines.append("## 🎯 Ringkasan Eksekutif")
            md_lines.append("")
            md_lines.append(exec_summary)
            md_lines.append("")

        # Problem Statement
        if problem:
            md_lines.append("## ❓ Rumusan Masalah")
            md_lines.append("")
            md_lines.append(problem)
            md_lines.append("")

        # Objectives
        if objectives:
            md_lines.append("## 🎯 Tujuan Penelitian")
            md_lines.append("")
            for i, obj in enumerate(objectives, 1):
                md_lines.append(f"{i}. {obj}")
            md_lines.append("")

        # Methodology
        if methodology:
            md_lines.append("## 🔬 Metodologi")
            md_lines.append("")
            md_lines.append(methodology)
            md_lines.append("")

        # Key Results
        if key_results:
            md_lines.append("## 📈 Hasil Utama")
            md_lines.append("")
            for i, result in enumerate(key_results, 1):
                md_lines.append(f"{i}. {result}")
            md_lines.append("")

        # Conclusions
        if conclusions:
            md_lines.append("## ✅ Kesimpulan")
            md_lines.append("")
            for i, conc in enumerate(conclusions, 1):
                md_lines.append(f"{i}. {conc}")
            md_lines.append("")

        # Suggestions
        if suggestions:
            md_lines.append("## 💡 Saran")
            md_lines.append("")
            for i, sug in enumerate(suggestions, 1):
                md_lines.append(f"{i}. {sug}")
            md_lines.append("")

        # Structure
        if structure.get("chapters"):
            md_lines.append("## 📑 Struktur Bab")
            md_lines.append("")
            for chapter in structure["chapters"]:
                md_lines.append(f"- {chapter}")
            md_lines.append("")

        # Tables Summary
        if tables_summary:
            md_lines.append("## 📊 Tabel (Summary LLM)")
            md_lines.append("")
            for table in tables_summary:
                md_lines.append(f"### Tabel Halaman {table.get('page', '?')}")
                md_lines.append(f"**Deskripsi**: {table.get('description', '')}")
                if table.get("caption"):
                    md_lines.append(f"**Caption**: {table['caption']}")
                md_lines.append("")

        # Actual extracted tables
        if pdfplumber_data.get("tables"):
            md_lines.append("## 📋 Data Tabel Lengkap (Ekstraksi Otomatis)")
            md_lines.append("")
            for table in pdfplumber_data["tables"]:
                md_lines.append(
                    f"### Tabel Halaman {table['page']} (Indeks {table['table_index']})"
                )
                md_lines.append("")
                if table["data"]:
                    md_lines.append(
                        "| "
                        + " | ".join(str(cell or "") for cell in table["data"][0])
                        + " |"
                    )
                    md_lines.append(
                        "| " + " | ".join(["---"] * len(table["data"][0])) + " |"
                    )
                    for row in table["data"][1:]:
                        md_lines.append(
                            "| " + " | ".join(str(cell or "") for cell in row) + " |"
                        )
                md_lines.append("")

        # Figures Summary
        if figures_summary:
            md_lines.append("## 🖼️ Gambar/Figur (Summary LLM)")
            md_lines.append("")
            for fig in figures_summary:
                md_lines.append(f"### Gambar Halaman {fig.get('page', '?')}")
                md_lines.append(f"**Deskripsi**: {fig.get('description', '')}")
                if fig.get("caption"):
                    md_lines.append(f"**Caption**: {fig['caption']}")
                md_lines.append("")

        # Extracted images
        if images:
            md_lines.append("## 🖼️ Gambar yang Diekstrak")
            md_lines.append("")
            for img in images:
                md_lines.append(f"### Gambar Halaman {img['page']} #{img['index']}")
                md_lines.append(f"![Gambar]({img['path']})")
                md_lines.append(f"*Ukuran: {img['width']}x{img['height']} px*")
                md_lines.append("")

        # References
        if references:
            md_lines.append("## 📚 Referensi Utama")
            md_lines.append("")
            for i, ref in enumerate(references, 1):
                md_lines.append(f"{i}. **{ref.get('title', 'Judul tidak tersedia')}**")
                if ref.get("authors"):
                    md_lines.append(f"   - Penulis: {', '.join(ref['authors'])}")
                if ref.get("year"):
                    md_lines.append(f"   - Tahun: {ref['year']}")
                if ref.get("source"):
                    md_lines.append(f"   - Sumber: {ref['source']}")
                md_lines.append("")

        # Full references section
        if references_text:
            md_lines.append("## 📖 Bagian Referensi Lengkap (Ekstraksi)")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(references_text[:5000])
            if len(references_text) > 5000:
                md_lines.append("... (dipotong)")
            md_lines.append("```")
            md_lines.append("")

        # Full text (truncated)
        md_lines.append("## 📝 Teks Lengkap (Ekstraksi pdfplumber)")
        md_lines.append("")
        full_text = pdfplumber_data.get("full_text", "")
        md_lines.append("```")
        md_lines.append(full_text[:10000])
        if len(full_text) > 10000:
            md_lines.append("... (dipotong, lihat file teks terpisah)")
        md_lines.append("```")

        return "\n".join(md_lines)

    def process(self) -> bool:
        """Process the PDF"""
        print(f"\n{'=' * 60}")
        print(f"Memproses: {self.pdf_path.name}")
        print(f"Output folder: {self.journal_folder}")
        print(f"{'=' * 60}")

        try:
            # Copy PDF to output folder
            pdf_copy = self.journal_folder / self.pdf_path.name
            shutil.copy2(self.pdf_path, pdf_copy)
            print(f"✓ PDF disalin ke: {pdf_copy}")

            # Extract with pdfplumber
            print("📄 Mengekstrak teks dan tabel dengan pdfplumber...")
            pdfplumber_data = self.extract_with_pdfplumber()

            # Save full text
            text_file = self.journal_folder / "full_text.txt"
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(pdfplumber_data["full_text"])
            print(f"✓ Teks lengkap disimpan: {text_file}")

            # Extract images
            print("🖼️ Mengekstrak gambar dengan PyMuPDF...")
            images = self.extract_images_with_pymupdf()
            print(f"✓ {len(images)} gambar diekstrak")

            # Extract references
            references_text = self.extract_references_section(
                pdfplumber_data["full_text"]
            )

            # Analyze with LLM
            print("🤖 Menganalisis dengan LLM...")
            llm_analysis = self.analyze_with_llm(pdfplumber_data["full_text"])

            # Save LLM analysis
            analysis_file = self.journal_folder / "analysis.json"
            with open(analysis_file, "w", encoding="utf-8") as f:
                json.dump(llm_analysis, f, ensure_ascii=False, indent=2)
            print(f"✓ Analisis LLM disimpan: {analysis_file}")

            # Create markdown
            print("📝 Membuat file markdown...")
            markdown_content = self.create_markdown(
                pdfplumber_data, images, llm_analysis, references_text
            )

            md_file = self.journal_folder / f"{self.folder_name}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"✓ Markdown dibuat: {md_file}")

            # Save references
            ref_file = self.journal_folder / "references.txt"
            with open(ref_file, "w", encoding="utf-8") as f:
                f.write(references_text)
            print(f"✓ Referensi disimpan: {ref_file}")

            # Summary
            summary = {
                "pdf_name": self.pdf_path.name,
                "folder_name": self.folder_name,
                "pages": len(pdfplumber_data["pages"]),
                "tables_count": len(pdfplumber_data["tables"]),
                "images_count": len(images),
                "has_llm_analysis": bool(llm_analysis),
                "markdown_file": str(md_file.relative_to(self.output_dir)),
                "pdf_file": str(pdf_copy.relative_to(self.output_dir)),
                "text_file": str(text_file.relative_to(self.output_dir)),
                "analysis_file": str(analysis_file.relative_to(self.output_dir)),
                "references_file": str(ref_file.relative_to(self.output_dir)),
                "images_folder": "images/",
            }

            summary_file = self.journal_folder / "summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            print(f"✅ Selesai memproses: {self.pdf_path.name}")
            return True

        except Exception as e:
            print(f"❌ Error memproses {self.pdf_path.name}: {e}")
            import traceback

            traceback.print_exc()
            return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract a single thesis PDF into structured research artifacts."
    )
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=os.getenv("JAYA_RESEARCH_TA_PDF"),
        help="input PDF path (env: JAYA_RESEARCH_TA_PDF)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv(
            "JAYA_RESEARCH_TA_OUTPUT_DIR",
            str(DATA_ROOT / "processed_ta"),
        ),
        help="output directory under JAYA_RESEARCH/data",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.pdf_path:
        parser.error("pdf_path or JAYA_RESEARCH_TA_PDF is required")

    try:
        pdf_path = resolve_pdf_path(args.pdf_path)
        output_dir = resolve_output_dir(args.output_dir)
        processor = TugasAkhirProcessor(pdf_path, output_dir)
    except (OSError, ValueError) as exc:
        print(f"invalid processor path: {exc}", file=sys.stderr)
        return 2

    print(f"Input: {pdf_path}")
    print(f"Output: {output_dir}")
    return 0 if processor.process() else 1


if __name__ == "__main__":
    raise SystemExit(main())
