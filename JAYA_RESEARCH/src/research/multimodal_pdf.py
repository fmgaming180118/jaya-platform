"""Truthful, bounded PDF ingestion for JAYA Research.

The extractor only reports content read from the supplied document or from an
explicitly injected OCR/table/figure provider.  Missing optional providers are
represented as typed extraction status and warnings; they never produce sample
papers, benchmark numbers, figures, tables, or formulas.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class PDFExtractionCode(str, Enum):
    """Stable result and failure codes for callers and API responses."""

    COMPLETE = "COMPLETE"
    PARTIAL_OCR_REQUIRED = "PARTIAL_OCR_REQUIRED"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_PDF = "INVALID_PDF"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    PARSER_FAILED = "PARSER_FAILED"
    OCR_FAILED = "OCR_FAILED"


class PDFExtractionError(RuntimeError):
    """Actionable PDF failure without leaking document contents."""

    def __init__(self, code: PDFExtractionCode, message: str) -> None:
        self.code = code
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": str(self)}


@dataclass(frozen=True)
class ExtractedTable:
    """A table returned by an explicitly configured table provider."""

    table_id: str
    page_number: int
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    caption: str = ""
    source: str = "TABLE_PROVIDER"


@dataclass(frozen=True)
class ExtractedFigure:
    """A figure returned by an explicitly configured figure provider."""

    figure_id: str
    page_number: int
    caption: str = ""
    image_path: str | None = None
    source: str = "FIGURE_PROVIDER"


@dataclass(frozen=True)
class ExtractedPage:
    """Text and immutable provenance for one 1-based PDF page."""

    page_number: int
    text: str
    extraction_method: str
    text_sha256: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class MultimodalDocument:
    """Structured PDF content with truthful extraction status."""

    document_name: str
    total_pages: int
    full_text: str
    sections: dict[str, str] = field(default_factory=dict)
    tables: list[ExtractedTable] = field(default_factory=list)
    figures: list[ExtractedFigure] = field(default_factory=list)
    formulas: list[str] = field(default_factory=list)
    pages: list[ExtractedPage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = PDFExtractionCode.COMPLETE.value
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OCRProvider = Callable[[Path, int], str]
TableProvider = Callable[[Path, int], Sequence[Mapping[str, Any]]]
FigureProvider = Callable[[Path, int, Path], Sequence[Mapping[str, Any]]]


class MultimodalPDFExtractor:
    """Extract real PDF content with size, page, and provider boundaries.

    ``ocr_provider`` receives ``(pdf_path, zero_based_page_index)``.  OCR is
    attempted only for pages whose embedded text is empty.  Table and figure
    extraction are likewise opt-in because the base ``pypdf`` parser does not
    provide reliable multimodal extraction.
    """

    PARSER_ID = "jaya-pypdf-v1"

    def __init__(
        self,
        output_dir: str | os.PathLike[str] | None = None,
        *,
        max_bytes: int = 50 * 1024 * 1024,
        max_pages: int = 500,
        ocr_provider: OCRProvider | None = None,
        table_provider: TableProvider | None = None,
        figure_provider: FigureProvider | None = None,
    ) -> None:
        if not 1024 <= max_bytes <= 500 * 1024 * 1024:
            raise ValueError("max_bytes must be between 1024 and 524288000")
        if not 1 <= max_pages <= 10_000:
            raise ValueError("max_pages must be between 1 and 10000")

        self.output_dir = (
            Path(output_dir).resolve()
            if output_dir is not None
            else None
        )
        self.max_bytes = max_bytes
        self.max_pages = max_pages
        self.ocr_provider = ocr_provider
        self.table_provider = table_provider
        self.figure_provider = figure_provider

    def extract(
        self,
        pdf_path: str | os.PathLike[str],
        *,
        source_uri: str | None = None,
        license_id: str = "UNKNOWN",
    ) -> MultimodalDocument:
        """Extract one PDF or raise :class:`PDFExtractionError`.

        A successful return does not necessarily mean every page had text.
        Callers must inspect ``status``, ``warnings``, and ``promotable`` in
        metadata before using the output as research evidence.
        """

        path = Path(pdf_path).expanduser().resolve()
        self._validate_file(path)
        file_sha256 = self._sha256_file(path)
        reader = self._open_reader(path)

        total_pages = len(reader.pages)
        if total_pages == 0:
            return self._empty_document(path, file_sha256, source_uri, license_id)
        if total_pages > self.max_pages:
            raise PDFExtractionError(
                PDFExtractionCode.PAGE_LIMIT_EXCEEDED,
                f"PDF has {total_pages} pages; configured maximum is {self.max_pages}",
            )

        page_records: list[ExtractedPage] = []
        text_parts: list[str] = []
        tables: list[ExtractedTable] = []
        figures: list[ExtractedFigure] = []
        warnings: list[str] = []
        cursor = 0
        pages_requiring_ocr: list[int] = []

        for page_index, page in enumerate(reader.pages):
            page_number = page_index + 1
            text = self._extract_embedded_text(page, page_number)
            method = "PDF_TEXT"
            if not text:
                if self.ocr_provider is None:
                    pages_requiring_ocr.append(page_number)
                    method = "NO_TEXT_OCR_REQUIRED"
                else:
                    text = self._run_ocr(path, page_index)
                    method = "OCR" if text else "OCR_EMPTY"
                    if not text:
                        pages_requiring_ocr.append(page_number)

            separator = "\n\n" if text_parts and text else ""
            if separator:
                cursor += len(separator)
            char_start = cursor
            if text:
                text_parts.append(text)
                cursor += len(text)
            page_records.append(
                ExtractedPage(
                    page_number=page_number,
                    text=text,
                    extraction_method=method,
                    text_sha256=self._sha256_text(text),
                    char_start=char_start,
                    char_end=cursor,
                )
            )

            tables.extend(self._extract_tables(path, page_index, page_number))
            figures.extend(self._extract_figures(path, page_index, page_number))

        full_text = "\n\n".join(text_parts)
        if pages_requiring_ocr:
            warnings.append(
                "Embedded text was unavailable on pages: "
                + ", ".join(str(page) for page in pages_requiring_ocr)
            )
        if self.table_provider is None:
            warnings.append("Table extraction provider is not configured")
        if self.figure_provider is None:
            warnings.append("Figure extraction provider is not configured")

        status = (
            PDFExtractionCode.PARTIAL_OCR_REQUIRED.value
            if pages_requiring_ocr
            else PDFExtractionCode.COMPLETE.value
        )
        normalized_license = license_id.strip() or "UNKNOWN"
        provenance_complete = bool(source_uri and normalized_license != "UNKNOWN")
        return MultimodalDocument(
            document_name=path.name,
            total_pages=total_pages,
            full_text=full_text,
            sections=self._extract_sections(full_text),
            tables=tables,
            figures=figures,
            formulas=self._extract_formula_candidates(full_text),
            pages=page_records,
            status=status,
            warnings=warnings,
            metadata={
                "schema_version": "jaya-pdf-extraction-v1",
                "parser": self.PARSER_ID,
                "source_uri": source_uri or "",
                "source_sha256": file_sha256,
                "source_size_bytes": path.stat().st_size,
                "license_id": normalized_license,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "embedded_text_pages": sum(
                    page.extraction_method == "PDF_TEXT" for page in page_records
                ),
                "ocr_pages": sum(
                    page.extraction_method == "OCR" for page in page_records
                ),
                "pages_requiring_ocr": pages_requiring_ocr,
                "provenance_complete": provenance_complete,
                "promotable": (
                    status == PDFExtractionCode.COMPLETE.value
                    and bool(full_text)
                    and provenance_complete
                ),
            },
        )

    def _validate_file(self, path: Path) -> None:
        if not path.is_file():
            raise PDFExtractionError(
                PDFExtractionCode.FILE_NOT_FOUND,
                "PDF file does not exist",
            )
        file_size = path.stat().st_size
        if file_size > self.max_bytes:
            raise PDFExtractionError(
                PDFExtractionCode.FILE_TOO_LARGE,
                f"PDF is {file_size} bytes; configured maximum is {self.max_bytes}",
            )
        try:
            with path.open("rb") as handle:
                signature = handle.read(5)
        except OSError as exc:
            raise PDFExtractionError(
                PDFExtractionCode.PARSER_FAILED,
                "PDF could not be read",
            ) from exc
        if signature != b"%PDF-":
            raise PDFExtractionError(
                PDFExtractionCode.INVALID_PDF,
                "Input does not have a PDF signature",
            )

    @staticmethod
    def _open_reader(path: Path) -> Any:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as exc:
            raise PDFExtractionError(
                PDFExtractionCode.DEPENDENCY_UNAVAILABLE,
                "pypdf is required for PDF extraction",
            ) from exc

        try:
            reader = PdfReader(path, strict=True)
            if reader.is_encrypted:
                raise PDFExtractionError(
                    PDFExtractionCode.ENCRYPTED_PDF,
                    "Encrypted PDFs require explicit decryption before ingestion",
                )
            return reader
        except PDFExtractionError:
            raise
        except (PdfReadError, OSError, ValueError) as exc:
            raise PDFExtractionError(
                PDFExtractionCode.INVALID_PDF,
                "PDF structure is malformed or unsupported",
            ) from exc

    @staticmethod
    def _extract_embedded_text(page: Any, page_number: int) -> str:
        try:
            value = page.extract_text()
        except Exception as exc:
            raise PDFExtractionError(
                PDFExtractionCode.PARSER_FAILED,
                f"Embedded text extraction failed on page {page_number}",
            ) from exc
        return MultimodalPDFExtractor._normalize_text(value)

    def _run_ocr(self, path: Path, page_index: int) -> str:
        assert self.ocr_provider is not None
        try:
            value = self.ocr_provider(path, page_index)
        except Exception as exc:
            raise PDFExtractionError(
                PDFExtractionCode.OCR_FAILED,
                f"OCR provider failed on page {page_index + 1}",
            ) from exc
        if not isinstance(value, str):
            raise PDFExtractionError(
                PDFExtractionCode.OCR_FAILED,
                "OCR provider returned a non-text result",
            )
        return self._normalize_text(value)

    def _extract_tables(
        self,
        path: Path,
        page_index: int,
        page_number: int,
    ) -> list[ExtractedTable]:
        if self.table_provider is None:
            return []
        try:
            raw_tables = self.table_provider(path, page_index)
            return [
                ExtractedTable(
                    table_id=str(item.get("table_id") or f"table-{page_number}-{index}"),
                    page_number=page_number,
                    headers=[str(value) for value in item.get("headers") or []],
                    rows=[
                        [str(value) for value in row]
                        for row in item.get("rows") or []
                    ],
                    caption=str(item.get("caption") or ""),
                    source=str(item.get("source") or "TABLE_PROVIDER"),
                )
                for index, item in enumerate(raw_tables, start=1)
                if isinstance(item, Mapping)
            ]
        except Exception as exc:
            raise PDFExtractionError(
                PDFExtractionCode.PARSER_FAILED,
                f"Table provider failed on page {page_number}",
            ) from exc

    def _extract_figures(
        self,
        path: Path,
        page_index: int,
        page_number: int,
    ) -> list[ExtractedFigure]:
        if self.figure_provider is None:
            return []
        output_dir = self.output_dir
        if output_dir is None:
            raise PDFExtractionError(
                PDFExtractionCode.PARSER_FAILED,
                "output_dir is required when a figure provider is configured",
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            raw_figures = self.figure_provider(path, page_index, output_dir)
            return [
                ExtractedFigure(
                    figure_id=str(
                        item.get("figure_id") or f"figure-{page_number}-{index}"
                    ),
                    page_number=page_number,
                    caption=str(item.get("caption") or ""),
                    image_path=(
                        str(item["image_path"])
                        if item.get("image_path") is not None
                        else None
                    ),
                    source=str(item.get("source") or "FIGURE_PROVIDER"),
                )
                for index, item in enumerate(raw_figures, start=1)
                if isinstance(item, Mapping)
            ]
        except PDFExtractionError:
            raise
        except Exception as exc:
            raise PDFExtractionError(
                PDFExtractionCode.PARSER_FAILED,
                f"Figure provider failed on page {page_number}",
            ) from exc

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        lines = [" ".join(line.split()) for line in value.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    @staticmethod
    def _extract_sections(text: str) -> dict[str, str]:
        """Split only headings that are actually present in extracted text."""
        if not text:
            return {}
        heading_pattern = re.compile(
            r"(?im)^(abstract|abstrak|introduction|pendahuluan|methods?|"
            r"methodology|metodologi|results?|hasil|discussion|pembahasan|"
            r"conclusions?|kesimpulan)\s*:?\s*$"
        )
        matches = list(heading_pattern.finditer(text))
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections[match.group(1).casefold()] = text[start:end].strip()
        return sections

    @staticmethod
    def _extract_formula_candidates(text: str) -> list[str]:
        """Return equation-like source lines without interpreting them."""
        candidates: list[str] = []
        for line in text.splitlines():
            normalized = line.strip()
            if (
                3 <= len(normalized) <= 300
                and "=" in normalized
                and re.search(r"[A-Za-zΑ-Ωα-ω]", normalized)
                and re.search(r"[+\-*/^=]", normalized)
            ):
                candidates.append(normalized)
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _empty_document(
        self,
        path: Path,
        digest: str,
        source_uri: str | None,
        license_id: str,
    ) -> MultimodalDocument:
        return MultimodalDocument(
            document_name=path.name,
            total_pages=0,
            full_text="",
            status=PDFExtractionCode.EMPTY_DOCUMENT.value,
            warnings=["PDF contains no pages"],
            metadata={
                "schema_version": "jaya-pdf-extraction-v1",
                "parser": self.PARSER_ID,
                "source_uri": source_uri or "",
                "source_sha256": digest,
                "source_size_bytes": path.stat().st_size,
                "license_id": license_id.strip() or "UNKNOWN",
                "provenance_complete": False,
                "promotable": False,
            },
        )
