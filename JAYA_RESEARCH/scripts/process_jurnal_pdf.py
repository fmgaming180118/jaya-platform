#!/usr/bin/env python3
"""
Process Jurnal PDFs - Extract text, images, tables, references
Creates organized folder structure with markdown files for each journal
"""

import os
import sys
import re
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import pdfplumber
import fitz  # PyMuPDF for image extraction

# Add project root and src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

# Now import from research module
from research.academic.journal_processor import JournalProcessor
from teacher import Teacher


class JurnalPDFProcessor:
    """Process academic PDF journals and create structured markdown outputs"""
    
    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize LLM for analysis
        self.teacher = Teacher(model_type="reasoning")
        self.journal_processor = JournalProcessor()
        
    def sanitize_folder_name(self, name: str) -> str:
        """Create safe folder name from PDF filename"""
        # Remove extension and clean up
        name = name.replace('.pdf', '')
        # Keep alphanumeric, underscore, hyphen
        name = re.sub(r'[^\w\-_]', '_', name)
        # Limit length
        return name[:100]
    
    def extract_with_pdfplumber(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract text, tables using pdfplumber"""
        result = {
            "pages": [],
            "tables": [],
            "full_text": ""
        }
        
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                # Extract text
                text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                
                # Extract tables
                tables = page.extract_tables() or []
                page_tables = []
                for table_idx, table in enumerate(tables):
                    if table and any(cell for row in table for cell in row if cell):
                        page_tables.append({
                            "page": i,
                            "table_index": table_idx,
                            "data": table
                        })
                        result["tables"].append({
                            "page": i,
                            "table_index": table_idx,
                            "data": table
                        })
                
                result["pages"].append({
                    "page": i,
                    "text": text,
                    "tables": page_tables
                })
                result["full_text"] += f"\n--- PAGE {i} ---\n" + text + "\n\n"
        
        return result
    
    def extract_images_with_pymupdf(self, pdf_path: Path, output_folder: Path) -> List[Dict[str, Any]]:
        """Extract images using PyMuPDF"""
        images = []
        images_folder = output_folder / "images"
        images_folder.mkdir(parents=True, exist_ok=True)
        
        doc = fitz.open(str(pdf_path))
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Generate filename
                img_filename = f"page_{page_num+1}_img_{img_idx+1}.{image_ext}"
                img_path = images_folder / img_filename
                
                # Save image
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                
                images.append({
                    "page": page_num + 1,
                    "index": img_idx + 1,
                    "filename": img_filename,
                    "path": str(img_path.relative_to(self.output_dir)),
                    "width": base_image.get("width", 0),
                    "height": base_image.get("height", 0),
                    "ext": image_ext
                })
        
        doc.close()
        return images
    
    def extract_references_section(self, full_text: str) -> str:
        """Find and extract references/bibliography section"""
        # Common reference section headers
        ref_patterns = [
            r'\n\s*references\s*\n',
            r'\n\s*bibliography\s*\n',
            r'\n\s*reference list\s*\n',
            r'\n\s*literature cited\s*\n',
            r'\n\s*works cited\s*\n',
            r'\n\s*daftar pustaka\s*\n',
            r'\n\s*referensi\s*\n',
        ]
        
        text_lower = full_text.lower()
        for pattern in ref_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return full_text[match.start():]
        
        # Fallback: last 15000 characters
        return full_text[-15000:]
    
    def analyze_with_llm(self, text: str, pdf_name: str) -> Dict[str, Any]:
        """Use LLM to analyze and structure the paper content"""
        
        # Truncate if too long
        analysis_text = text[:50000]
        
        prompt = f"""
Anda adalah Research Analyst. Analisis paper akademik berikut dan ekstrak informasi terstruktur.

Nama File: {pdf_name}

Konten Paper (ekstrak):
{analysis_text}
...

Tugas:
1. Ekstrak metadata: Judul, Penulis, Tahun, Abstrak, Kata Kunci
2. Identifikasi struktur: Pendahuluan, Metodologi, Hasil, Diskusi, Kesimpulan
3. Ekstrak temuan utama (key findings), metodologi, kontribusi
4. Identifikasi tabel dan gambar penting beserta caption/deskripsi
5. Ekstrak referensi utama (top 10-15 referensi paling relevan)
6. Buat ringkasan eksekutif (2-3 paragraf)

Format output sebagai JSON dengan keys:
- metadata: {{title, authors, year, abstract, keywords}}
- structure: {{sections: []}}
- key_findings: []
- methodology: ""
- contributions: []
- tables_summary: [{{page, description, caption}}]
- figures_summary: [{{page, description, caption}}]
- references: [{{title, authors, year, source}}]
- executive_summary: ""
"""
        
        try:
            response = self.teacher.ask(
                prompt,
                system_instruction="Anda adalah Research Analyst yang menganalisis paper akademik. Output HANYA JSON valid, tanpa markdown atau penjelasan tambahan."
            )
            
            # Clean response
            response = response.strip()
            response = re.sub(r'^```json\s*', '', response)
            response = re.sub(r'^```\s*', '', response)
            response = re.sub(r'\s*```$', '', response)
            
            return json.loads(response)
        except Exception as e:
            print(f"[LLM Analysis Error] {pdf_name}: {e}")
            return {}
    
    def create_markdown(self, pdf_name: str, pdfplumber_data: Dict, images: List, 
                       llm_analysis: Dict, references_text: str) -> str:
        """Create comprehensive markdown file"""
        
        metadata = llm_analysis.get("metadata", {})
        structure = llm_analysis.get("structure", {})
        key_findings = llm_analysis.get("key_findings", [])
        methodology = llm_analysis.get("methodology", "")
        contributions = llm_analysis.get("contributions", [])
        tables_summary = llm_analysis.get("tables_summary", [])
        figures_summary = llm_analysis.get("figures_summary", [])
        references = llm_analysis.get("references", [])
        exec_summary = llm_analysis.get("executive_summary", "")
        
        md_lines = []
        
        # Header
        md_lines.append(f"# {metadata.get('title', pdf_name)}")
        md_lines.append("")
        
        # Metadata
        md_lines.append("## 📋 Metadata")
        md_lines.append("")
        md_lines.append(f"- **File Asli**: `{pdf_name}`")
        md_lines.append(f"- **Penulis**: {', '.join(metadata.get('authors', ['Tidak diketahui']))}")
        md_lines.append(f"- **Tahun**: {metadata.get('year', 'Tidak diketahui')}")
        md_lines.append(f"- **Kata Kunci**: {', '.join(metadata.get('keywords', []))}")
        md_lines.append("")
        
        # Abstract
        if metadata.get('abstract'):
            md_lines.append("## 📄 Abstrak")
            md_lines.append("")
            md_lines.append(metadata['abstract'])
            md_lines.append("")
        
        # Executive Summary
        if exec_summary:
            md_lines.append("## 🎯 Ringkasan Eksekutif")
            md_lines.append("")
            md_lines.append(exec_summary)
            md_lines.append("")
        
        # Key Findings
        if key_findings:
            md_lines.append("## 🔑 Temuan Utama (Key Findings)")
            md_lines.append("")
            for i, finding in enumerate(key_findings, 1):
                md_lines.append(f"{i}. {finding}")
            md_lines.append("")
        
        # Contributions
        if contributions:
            md_lines.append("## 💡 Kontribusi Penelitian")
            md_lines.append("")
            for contrib in contributions:
                md_lines.append(f"- {contrib}")
            md_lines.append("")
        
        # Methodology
        if methodology:
            md_lines.append("## 🔬 Metodologi")
            md_lines.append("")
            md_lines.append(methodology)
            md_lines.append("")
        
        # Structure
        if structure.get('sections'):
            md_lines.append("## 📑 Struktur Paper")
            md_lines.append("")
            for section in structure['sections']:
                md_lines.append(f"- {section}")
            md_lines.append("")
        
        # Tables
        if tables_summary:
            md_lines.append("## 📊 Tabel")
            md_lines.append("")
            for table in tables_summary:
                md_lines.append(f"### Tabel Halaman {table.get('page', '?')}")
                md_lines.append(f"**Deskripsi**: {table.get('description', '')}")
                if table.get('caption'):
                    md_lines.append(f"**Caption**: {table['caption']}")
                md_lines.append("")
        
        # Actual extracted tables from pdfplumber
        if pdfplumber_data.get("tables"):
            md_lines.append("## 📋 Data Tabel Lengkap (Ekstraksi Otomatis)")
            md_lines.append("")
            for table in pdfplumber_data["tables"]:
                md_lines.append(f"### Tabel Halaman {table['page']} (Indeks {table['table_index']})")
                md_lines.append("")
                md_lines.append("| " + " | ".join(str(cell or "") for cell in table['data'][0]) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(table['data'][0])) + " |")
                for row in table['data'][1:]:
                    md_lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")
                md_lines.append("")
        
        # Figures
        if figures_summary:
            md_lines.append("## 🖼️ Gambar/Figur")
            md_lines.append("")
            for fig in figures_summary:
                md_lines.append(f"### Gambar Halaman {fig.get('page', '?')}")
                md_lines.append(f"**Deskripsi**: {fig.get('description', '')}")
                if fig.get('caption'):
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
                if ref.get('authors'):
                    md_lines.append(f"   - Penulis: {', '.join(ref['authors'])}")
                if ref.get('year'):
                    md_lines.append(f"   - Tahun: {ref['year']}")
                if ref.get('source'):
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
    
    def process_single_pdf(self, pdf_path: Path) -> bool:
        """Process a single PDF file"""
        pdf_name = pdf_path.name
        folder_name = self.sanitize_folder_name(pdf_name)
        output_folder = self.output_dir / folder_name
        
        print(f"\n{'='*60}")
        print(f"Memproses: {pdf_name}")
        print(f"Output folder: {output_folder}")
        print(f"{'='*60}")
        
        try:
            # Create output folder
            output_folder.mkdir(parents=True, exist_ok=True)
            
            # Copy PDF to output folder
            pdf_copy = output_folder / pdf_name
            shutil.copy2(pdf_path, pdf_copy)
            print(f"✓ PDF disalin ke: {pdf_copy}")
            
            # Extract with pdfplumber
            print("📄 Mengekstrak teks dan tabel dengan pdfplumber...")
            pdfplumber_data = self.extract_with_pdfplumber(pdf_path)
            
            # Save full text separately
            text_file = output_folder / "full_text.txt"
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(pdfplumber_data["full_text"])
            print(f"✓ Teks lengkap disimpan: {text_file}")
            
            # Extract images
            print("🖼️ Mengekstrak gambar dengan PyMuPDF...")
            images = self.extract_images_with_pymupdf(pdf_path, output_folder)
            print(f"✓ {len(images)} gambar diekstrak")
            
            # Extract references section
            references_text = self.extract_references_section(pdfplumber_data["full_text"])
            
            # Analyze with LLM
            print("🤖 Menganalisis dengan LLM...")
            llm_analysis = self.analyze_with_llm(pdfplumber_data["full_text"], pdf_name)
            
            # Save LLM analysis as JSON
            analysis_file = output_folder / "analysis.json"
            with open(analysis_file, "w", encoding="utf-8") as f:
                json.dump(llm_analysis, f, ensure_ascii=False, indent=2)
            print(f"✓ Analisis LLM disimpan: {analysis_file}")
            
            # Create markdown
            print("📝 Membuat file markdown...")
            markdown_content = self.create_markdown(
                pdf_name, pdfplumber_data, images, llm_analysis, references_text
            )
            
            md_file = output_folder / f"{folder_name}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"✓ Markdown dibuat: {md_file}")
            
            # Save references separately
            ref_file = output_folder / "references.txt"
            with open(ref_file, "w", encoding="utf-8") as f:
                f.write(references_text)
            print(f"✓ Referensi disimpan: {ref_file}")
            
            # Create summary JSON
            summary = {
                "pdf_name": pdf_name,
                "folder_name": folder_name,
                "pages": len(pdfplumber_data["pages"]),
                "tables_count": len(pdfplumber_data["tables"]),
                "images_count": len(images),
                "has_llm_analysis": bool(llm_analysis),
                "markdown_file": str(md_file.relative_to(self.output_dir)),
                "pdf_file": str(pdf_copy.relative_to(self.output_dir)),
                "text_file": str(text_file.relative_to(self.output_dir)),
                "analysis_file": str(analysis_file.relative_to(self.output_dir)),
                "references_file": str(ref_file.relative_to(self.output_dir)),
                "images_folder": "images/"
            }
            
            summary_file = output_folder / "summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Selesai memproses: {pdf_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error memproses {pdf_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def process_all(self) -> Dict[str, Any]:
        """Process all PDFs in input directory"""
        pdf_files = list(self.input_dir.glob("*.pdf"))
        print(f"Ditemukan {len(pdf_files)} file PDF")
        
        results = {
            "total": len(pdf_files),
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        for pdf_path in pdf_files:
            success = self.process_single_pdf(pdf_path)
            results["details"].append({
                "pdf": pdf_path.name,
                "success": success
            })
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
        
        # Save overall summary
        summary_file = self.output_dir / "processing_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*60}")
        print(f"RINGKASAN PEMROSESAN")
        print(f"{'='*60}")
        print(f"Total PDF: {results['total']}")
        print(f"Berhasil: {results['success']}")
        print(f"Gagal: {results['failed']}")
        print(f"Ringkasan disimpan: {summary_file}")
        
        return results


def main():
    # Paths
    base_dir = Path(__file__).parent.parent
    input_dir = base_dir / "jurnal_pdf"
    output_dir = base_dir / "data" / "processed_journals"
    
    if not input_dir.exists():
        print(f"❌ Folder input tidak ditemukan: {input_dir}")
        return
    
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    
    # Process
    processor = JurnalPDFProcessor(input_dir, output_dir)
    results = processor.process_all()
    
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()