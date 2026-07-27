"""
test_multimodal_pdf.py — Integration test for Phase D.4 Multimodal PDF Extraction Engine
"""

import os
import sys
import pytest

pytestmark = pytest.mark.integration

# Ensure sys.path includes JAYA_RESEARCH
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESEARCH_DIR = os.path.join(ROOT_DIR, "JAYA_RESEARCH")
if RESEARCH_DIR not in sys.path:
    sys.path.insert(0, RESEARCH_DIR)

from JAYA_RESEARCH.src.research.multimodal_pdf import (
    MultimodalPDFExtractor,
    MultimodalDocument,
    ExtractedTable,
    ExtractedFigure,
)


def test_multimodal_pdf_extractor(tmp_path):
    """Test extracting text, tables, figures, and formulas from a PDF paper."""
    output_dir = str(tmp_path)
    extractor = MultimodalPDFExtractor(output_dir=output_dir)
    
    doc = extractor.extract("sample_paper.pdf")
    
    assert isinstance(doc, MultimodalDocument)
    assert doc.document_name == "sample_paper.pdf"
    assert doc.total_pages > 0
    assert "Abstract" in doc.sections
    assert len(doc.tables) > 0
    assert len(doc.figures) > 0
    assert len(doc.formulas) > 0
    
    table = doc.tables[0]
    assert isinstance(table, ExtractedTable)
    assert len(table.headers) > 0
    assert len(table.rows) > 0
    
    fig = doc.figures[0]
    assert isinstance(fig, ExtractedFigure)
    assert fig.caption != ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
