"""Offline Phase A tests for truthful, bounded PDF ingestion."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from jaya_research.research.multimodal_pdf import (
    MultimodalPDFExtractor,
    PDFExtractionCode,
    PDFExtractionError,
)


def _escape_pdf_text(value: str) -> bytes:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")


def _write_pdf(path: Path, page_texts: list[str], *, encrypt: bool = False) -> Path:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)

    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_reference}
                )
            }
        )
        if text:
            operations = [b"BT /F1 12 Tf 72 720 Td"]
            for line_index, line in enumerate(text.splitlines()):
                if line_index:
                    operations.append(b"0 -20 Td")
                operations.append(b"(" + _escape_pdf_text(line) + b") Tj")
            operations.append(b"ET")
            stream = DecodedStreamObject()
            stream.set_data(b"\n".join(operations))
            page[NameObject("/Contents")] = writer._add_object(stream)

    if encrypt:
        writer.encrypt("test-password")
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_extracts_only_real_multilingual_text_and_provenance(tmp_path: Path) -> None:
    pdf_path = _write_pdf(
        tmp_path / "thesis.pdf",
        [
            "Abstract\nMeasured latency equals 42 ms.\nE = m * c^2",
            "Pendahuluan\nPenelitian kecerdasan buatan berbasis bukti.",
        ],
    )
    source_uri = "https://repository.example/thesis.pdf"

    document = MultimodalPDFExtractor().extract(
        pdf_path,
        source_uri=source_uri,
        license_id="CC-BY-4.0",
    )

    assert document.status == PDFExtractionCode.COMPLETE.value
    assert document.total_pages == 2
    assert "Measured latency equals 42 ms." in document.full_text
    assert "Penelitian kecerdasan buatan berbasis bukti." in document.full_text
    assert "abstract" in document.sections
    assert "pendahuluan" in document.sections
    assert document.formulas == ["E = m * c^2"]
    assert document.tables == []
    assert document.figures == []
    assert document.pages[0].extraction_method == "PDF_TEXT"
    assert document.pages[1].page_number == 2
    assert document.pages[1].char_start > document.pages[0].char_end
    assert document.metadata["source_uri"] == source_uri
    assert document.metadata["license_id"] == "CC-BY-4.0"
    assert document.metadata["promotable"] is True
    assert document.metadata["source_sha256"] == hashlib.sha256(
        pdf_path.read_bytes()
    ).hexdigest()


def test_scanned_page_requires_explicit_ocr_provider(tmp_path: Path) -> None:
    pdf_path = _write_pdf(tmp_path / "scan.pdf", [""])

    document = MultimodalPDFExtractor().extract(pdf_path)

    assert document.status == PDFExtractionCode.PARTIAL_OCR_REQUIRED.value
    assert document.full_text == ""
    assert document.pages[0].extraction_method == "NO_TEXT_OCR_REQUIRED"
    assert document.metadata["pages_requiring_ocr"] == [1]
    assert document.metadata["promotable"] is False
    assert any("pages: 1" in warning for warning in document.warnings)


def test_injected_ocr_is_recorded_without_becoming_hidden_fallback(
    tmp_path: Path,
) -> None:
    pdf_path = _write_pdf(tmp_path / "scan.pdf", [""])
    calls: list[tuple[Path, int]] = []

    def ocr_provider(path: Path, page_index: int) -> str:
        calls.append((path, page_index))
        return "Hasil OCR halaman pindai."

    document = MultimodalPDFExtractor(ocr_provider=ocr_provider).extract(
        pdf_path,
        source_uri="https://repository.example/scan.pdf",
        license_id="CC0-1.0",
    )

    assert calls == [(pdf_path.resolve(), 0)]
    assert document.full_text == "Hasil OCR halaman pindai."
    assert document.pages[0].extraction_method == "OCR"
    assert document.metadata["ocr_pages"] == 1
    assert document.metadata["promotable"] is True


def test_corrupt_and_non_pdf_inputs_fail_with_stable_codes(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-1.7\nnot a valid object graph")
    not_pdf = tmp_path / "renamed.pdf"
    not_pdf.write_text("plain text", encoding="utf-8")

    with pytest.raises(PDFExtractionError) as corrupt_error:
        MultimodalPDFExtractor().extract(corrupt)
    with pytest.raises(PDFExtractionError) as signature_error:
        MultimodalPDFExtractor().extract(not_pdf)

    assert corrupt_error.value.code is PDFExtractionCode.INVALID_PDF
    assert signature_error.value.code is PDFExtractionCode.INVALID_PDF


def test_page_and_byte_limits_reject_before_extraction(tmp_path: Path) -> None:
    many_pages = _write_pdf(tmp_path / "many-pages.pdf", ["one", "two", "three"])
    oversized = _write_pdf(tmp_path / "oversized.pdf", ["content"])
    with oversized.open("ab") as handle:
        handle.write(b"x" * 2048)

    with pytest.raises(PDFExtractionError) as page_error:
        MultimodalPDFExtractor(max_pages=2).extract(many_pages)
    with pytest.raises(PDFExtractionError) as byte_error:
        MultimodalPDFExtractor(max_bytes=1024).extract(oversized)

    assert page_error.value.code is PDFExtractionCode.PAGE_LIMIT_EXCEEDED
    assert byte_error.value.code is PDFExtractionCode.FILE_TOO_LARGE


def test_encrypted_pdf_fails_closed(tmp_path: Path) -> None:
    encrypted = _write_pdf(tmp_path / "encrypted.pdf", ["secret"], encrypt=True)

    with pytest.raises(PDFExtractionError) as error:
        MultimodalPDFExtractor().extract(encrypted)

    assert error.value.code is PDFExtractionCode.ENCRYPTED_PDF


def test_provider_outputs_are_explicit_and_never_synthesized(tmp_path: Path) -> None:
    pdf_path = _write_pdf(tmp_path / "paper.pdf", ["Results\nObserved value."])

    def table_provider(_path: Path, _page_index: int):
        return [
            {
                "table_id": "measured-table",
                "headers": ["Metric", "Value"],
                "rows": [["latency", "42"]],
                "source": "test-table-adapter",
            }
        ]

    document = MultimodalPDFExtractor(table_provider=table_provider).extract(pdf_path)

    assert len(document.tables) == 1
    assert document.tables[0].source == "test-table-adapter"
    assert document.tables[0].rows == [["latency", "42"]]
    assert document.figures == []
    assert all("97.6" not in value for row in document.tables[0].rows for value in row)


def test_ocr_failure_is_typed_and_does_not_return_partial_content(
    tmp_path: Path,
) -> None:
    pdf_path = _write_pdf(tmp_path / "scan.pdf", [""])

    def failing_ocr(_path: Path, _page_index: int) -> str:
        raise TimeoutError("provider timed out")

    with pytest.raises(PDFExtractionError) as error:
        MultimodalPDFExtractor(ocr_provider=failing_ocr).extract(pdf_path)

    assert error.value.code is PDFExtractionCode.OCR_FAILED
    assert "timed out" not in str(error.value)
