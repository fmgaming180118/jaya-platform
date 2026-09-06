#!/usr/bin/env python3
"""
PDF to Markdown Converter with Full Image & Table Extraction
Konversi PDF ke Markdown dengan ekstraksi lengkap gambar dan tabel
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import re

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pdfplumber
    import pymupdf
    from pdf2image import convert_from_path
    from PIL import Image
    import tabulate
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Install with: pip install pdfplumber pymupdf pdf2image pillow tabulate")
    sys.exit(1)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)


class PDFToMarkdownConverter:
    """Convert PDF to Markdown with image and table extraction"""
    
    def __init__(self, pdf_path: str, output_dir: Optional[str] = None):
        """
        Initialize converter
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Output directory (default: docs/pdf_conversions/{pdf_name})
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        # Setup output directory
        pdf_name = self.pdf_path.stem.replace(" ", "_")[:50]
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            base_dir = Path(__file__).parent.parent / "data" / "pdf_conversions"
            self.output_dir = base_dir / pdf_name
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.images_dir = self.output_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        
        self.tables_dir = self.output_dir / "tables"
        self.tables_dir.mkdir(exist_ok=True)
        
        self.markdown_path = self.output_dir / f"{pdf_name}.md"
        
        self.pdf = None
        self.images_extracted: List[Dict[str, str]] = []
        self.tables_extracted: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        
        logger.info(f"📄 Input PDF: {self.pdf_path}")
        logger.info(f"📁 Output directory: {self.output_dir}")
    
    def extract_metadata(self) -> Dict[str, Any]:
        """Extract PDF metadata"""
        logger.info("🔍 Extracting metadata...")
        
        pdf = pymupdf.open(str(self.pdf_path))
        metadata = pdf.metadata.copy() if pdf.metadata else {}
        metadata['total_pages'] = len(pdf)
        metadata['pdf_path'] = str(self.pdf_path)
        metadata['conversion_timestamp'] = datetime.now().isoformat()
        
        pdf.close()
        
        self.metadata = metadata
        logger.info(f"   Total pages: {metadata['total_pages']}")
        return metadata
    
    def extract_images(self) -> List[Dict[str, str]]:
        """Extract all images from PDF"""
        logger.info("🖼️  Extracting images...")
        
        images_list = []
        image_count = 0
        
        with pdfplumber.open(str(self.pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract images using pdfplumber
                if hasattr(page, 'images') and page.images:
                    for img_idx, img in enumerate(page.images):
                        try:
                            # Extract image rect and save
                            crop = page.crop((img['x0'], img['top'], img['x1'], img['bottom']))
                            cropped_page = crop.to_image()
                            
                            img_filename = f"page_{page_num:03d}_image_{img_idx:02d}.png"
                            img_path = self.images_dir / img_filename
                            cropped_page.save(str(img_path), 'PNG')
                            
                            images_list.append({
                                'page': page_num,
                                'filename': img_filename,
                                'relative_path': f"images/{img_filename}"
                            })
                            image_count += 1
                            logger.debug(f"   ✓ Page {page_num}: {img_filename}")
                        except Exception as e:
                            logger.warning(f"   ⚠ Failed to extract image on page {page_num}: {e}")
        
        # Also try PyMuPDF for more complete extraction
        try:
            pdf = pymupdf.open(str(self.pdf_path))
            for page_num, page in enumerate(pdf, 1):
                image_list = page.get_images()
                for img_idx, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        pix = pymupdf.Pixmap(pdf, xref)
                        
                        # Check for duplicate
                        img_filename = f"page_{page_num:03d}_pymupdf_{img_idx:02d}.png"
                        img_path = self.images_dir / img_filename
                        
                        if pix.n - pix.alpha < 4:  # GRAY or RGB
                            pix.save(str(img_path))
                        else:  # CMYK
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                            pix.save(str(img_path))
                        
                        images_list.append({
                            'page': page_num,
                            'filename': img_filename,
                            'relative_path': f"images/{img_filename}"
                        })
                        image_count += 1
                        logger.debug(f"   ✓ Page {page_num}: {img_filename}")
                    except Exception as e:
                        logger.warning(f"   ⚠ PyMuPDF extraction failed: {e}")
            pdf.close()
        except Exception as e:
            logger.warning(f"PyMuPDF extraction: {e}")
        
        self.images_extracted = images_list
        logger.info(f"   Total images extracted: {image_count}")
        return images_list
    
    def extract_tables(self) -> List[Dict[str, Any]]:
        """Extract all tables from PDF"""
        logger.info("📊 Extracting tables...")
        
        tables_list = []
        table_count = 0
        
        with pdfplumber.open(str(self.pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract tables
                try:
                    page_tables = page.extract_tables()
                    
                    if page_tables:
                        for table_idx, table in enumerate(page_tables):
                            try:
                                # Convert table to markdown
                                if table and len(table) > 0:
                                    headers = table[0] if table else []
                                    rows = table[1:] if len(table) > 1 else []
                                    
                                    markdown_table = tabulate.tabulate(
                                        rows,
                                        headers=headers,
                                        tablefmt="github"
                                    )
                                    
                                    # Save table to file
                                    table_filename = f"page_{page_num:03d}_table_{table_idx:02d}.md"
                                    table_path = self.tables_dir / table_filename
                                    
                                    with open(table_path, 'w', encoding='utf-8') as f:
                                        f.write(markdown_table)
                                    
                                    tables_list.append({
                                        'page': page_num,
                                        'table_index': table_idx,
                                        'filename': table_filename,
                                        'relative_path': f"tables/{table_filename}",
                                        'rows': len(rows),
                                        'cols': len(headers)
                                    })
                                    table_count += 1
                                    logger.debug(f"   ✓ Page {page_num}: {table_filename} ({len(rows)}x{len(headers)})")
                            except Exception as e:
                                logger.warning(f"   ⚠ Failed to process table on page {page_num}: {e}")
                except Exception as e:
                    logger.warning(f"   ⚠ Table extraction failed on page {page_num}: {e}")
        
        self.tables_extracted = tables_list
        logger.info(f"   Total tables extracted: {table_count}")
        return tables_list
    
    def extract_text_with_structure(self) -> str:
        """Extract text with page structure"""
        logger.info("📝 Extracting text...")
        
        markdown_content = []
        
        with pdfplumber.open(str(self.pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                text = page.extract_text()
                
                if text:
                    # Add page header
                    markdown_content.append(f"\n## Halaman {page_num}\n")
                    
                    # Add text with minimal processing
                    lines = text.split('\n')
                    for line in lines:
                        line = line.rstrip()
                        if line:
                            markdown_content.append(line)
                    
                    # Add images for this page
                    page_images = [img for img in self.images_extracted if img['page'] == page_num]
                    if page_images:
                        markdown_content.append("\n### Gambar pada halaman ini\n")
                        for img in page_images:
                            markdown_content.append(f"![Image]({img['relative_path']})")
                    
                    # Add tables for this page
                    page_tables = [tbl for tbl in self.tables_extracted if tbl['page'] == page_num]
                    if page_tables:
                        markdown_content.append("\n### Tabel pada halaman ini\n")
                        for tbl in page_tables:
                            markdown_content.append(f"\n**Tabel {tbl['table_index'] + 1}** ({tbl['rows']} baris × {tbl['cols']} kolom)")
                            markdown_content.append(f"\n```\n")
                            with open(self.tables_dir / tbl['filename'], 'r', encoding='utf-8') as f:
                                markdown_content.append(f.read())
                            markdown_content.append(f"\n```\n")
        
        return '\n'.join(markdown_content)
    
    def generate_markdown(self) -> str:
        """Generate final markdown file"""
        logger.info("✍️  Generating markdown...")
        
        # Generate header with metadata
        header_parts = [
            f"# {self.pdf_path.stem}\n",
            f"**Konversi dari PDF → Markdown**\n",
            f"- 📄 Sumber: `{self.pdf_path.name}`\n",
            f"- 📅 Konversi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"- 📄 Total halaman: {self.metadata.get('total_pages', '?')}\n",
            f"- 🖼️  Gambar: {len(self.images_extracted)}\n",
            f"- 📊 Tabel: {len(self.tables_extracted)}\n",
        ]
        
        if self.metadata.get('subject'):
            header_parts.append(f"- 📋 Subject: {self.metadata.get('subject')}\n")
        if self.metadata.get('author'):
            header_parts.append(f"- 👤 Author: {self.metadata.get('author')}\n")
        
        header_parts.append("\n---\n\n## Daftar Isi\n")
        header_parts.append("1. [Konten](#konten)\n")
        header_parts.append("2. [Gambar](#gambar)\n")
        header_parts.append("3. [Tabel](#tabel)\n\n")
        
        # Generate table of contents for images
        if self.images_extracted:
            header_parts.append("### Gambar\n\n")
            for img in self.images_extracted:
                header_parts.append(f"- Page {img['page']}: {img['filename']}\n")
            header_parts.append("\n")
        
        # Generate table of contents for tables
        if self.tables_extracted:
            header_parts.append("### Tabel\n\n")
            for tbl in self.tables_extracted:
                header_parts.append(f"- Page {tbl['page']}, Tabel {tbl['table_index'] + 1}: {tbl['rows']}×{tbl['cols']}\n")
            header_parts.append("\n")
        
        header_parts.append("---\n\n## Konten\n\n")
        
        # Extract text with structure
        text_content = self.extract_text_with_structure()
        
        full_content = ''.join(header_parts) + text_content
        
        # Save markdown
        with open(self.markdown_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        logger.info(f"✅ Markdown saved: {self.markdown_path}")
        return full_content
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate conversion report"""
        report = {
            'pdf_file': str(self.pdf_path),
            'output_directory': str(self.output_dir),
            'markdown_file': str(self.markdown_path),
            'metadata': self.metadata,
            'images_extracted': len(self.images_extracted),
            'images_list': self.images_extracted,
            'tables_extracted': len(self.tables_extracted),
            'tables_list': self.tables_extracted,
            'timestamp': datetime.now().isoformat()
        }
        
        report_path = self.output_dir / "conversion_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📋 Report saved: {report_path}")
        return report
    
    def convert(self) -> Dict[str, Any]:
        """Execute full conversion pipeline"""
        logger.info("=" * 60)
        logger.info(f"🚀 Starting PDF conversion: {self.pdf_path.name}")
        logger.info("=" * 60)
        
        try:
            # Step 1: Extract metadata
            self.extract_metadata()
            
            # Step 2: Extract images
            self.extract_images()
            
            # Step 3: Extract tables
            self.extract_tables()
            
            # Step 4: Generate markdown
            self.generate_markdown()
            
            # Step 5: Generate report
            report = self.generate_report()
            
            logger.info("=" * 60)
            logger.info("✅ Conversion completed successfully!")
            logger.info("=" * 60)
            logger.info(f"\n📁 Output Directory: {self.output_dir}")
            logger.info(f"📄 Markdown File: {self.markdown_path}")
            logger.info(f"🖼️  Images: {len(self.images_extracted)}")
            logger.info(f"📊 Tables: {len(self.tables_extracted)}")
            
            return report
        
        except Exception as e:
            logger.error(f"❌ Conversion failed: {e}")
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Convert PDF to Markdown with complete image and table extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdf_to_markdown_converter.py "docs/sample.pdf"
  python pdf_to_markdown_converter.py "docs/sample.pdf" -o "JAYA_RESEARCH/data/pdf_conversions/sample"
  python pdf_to_markdown_converter.py "docs/*.pdf"  (batch processing)
        """
    )
    
    parser.add_argument(
        'pdf_path',
        help='Path to PDF file or pattern (e.g., "docs/*.pdf")'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory (default: JAYA_RESEARCH/data/pdf_conversions/{pdf_name})'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle glob patterns
    from glob import glob
    pdf_files = glob(args.pdf_path)
    
    if not pdf_files:
        logger.error(f"❌ No PDF files found: {args.pdf_path}")
        sys.exit(1)
    
    logger.info(f"Found {len(pdf_files)} PDF file(s)")
    
    results = []
    for pdf_path in pdf_files:
        try:
            converter = PDFToMarkdownConverter(pdf_path, args.output)
            report = converter.convert()
            results.append(report)
        except Exception as e:
            logger.error(f"❌ Failed to convert {pdf_path}: {e}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info(f"📊 Summary: {len(results)} file(s) converted successfully")
    logger.info("=" * 60)
    
    return 0 if results else 1


if __name__ == '__main__':
    sys.exit(main())
