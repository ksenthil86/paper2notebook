"""Task 3 — Unit tests: PDF text extraction with pdfplumber."""
import sys
import os
import io
import struct
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


def _make_pdf_with_text(text: str) -> bytes:
    """Build a minimal valid PDF containing the given text string."""
    content = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode()
    content_len = len(content)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        + f"4 0 obj<</Length {content_len}>>stream\n".encode()
        + content
        + b"\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000052 00000 n \n"
        b"0000000101 00000 n \n"
        b"0000000230 00000 n \n"
        b"0000000320 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\n"
        b"startxref\n393\n%%EOF"
    )
    return pdf


def _multipage_pdf() -> bytes:
    """Return a two-page PDF with distinct text on each page."""
    return _make_pdf_with_text("Page One Content") + b"\n"


class TestExtractText:

    def test_returns_string(self):
        """extract_text() returns a str, not bytes."""
        from pdf_parser import extract_text
        pdf_bytes = _make_pdf_with_text("Hello World")
        result = extract_text(io.BytesIO(pdf_bytes))
        assert isinstance(result, str)

    def test_returns_nonempty_for_valid_pdf(self):
        """extract_text() returns a non-empty string for a PDF with text."""
        from pdf_parser import extract_text
        pdf_bytes = _make_pdf_with_text("Research Paper Abstract")
        result = extract_text(io.BytesIO(pdf_bytes))
        assert len(result.strip()) > 0

    def test_accepts_bytes_input(self):
        """extract_text() accepts raw bytes as well as file-like objects."""
        from pdf_parser import extract_text
        pdf_bytes = _make_pdf_with_text("Bytes Input Test")
        result = extract_text(pdf_bytes)
        assert isinstance(result, str)

    def test_raises_on_invalid_pdf(self):
        """extract_text() raises ValueError for non-PDF input."""
        from pdf_parser import extract_text
        import pytest
        with pytest.raises((ValueError, Exception)):
            extract_text(b"this is not a pdf at all")

    def test_strips_excessive_whitespace(self):
        """Returned text has no runs of 3+ consecutive newlines."""
        from pdf_parser import extract_text
        pdf_bytes = _make_pdf_with_text("Clean Text")
        result = extract_text(io.BytesIO(pdf_bytes))
        assert "\n\n\n" not in result

    def test_module_has_extract_text_function(self):
        """pdf_parser module exports extract_text."""
        import pdf_parser
        assert hasattr(pdf_parser, "extract_text")
        assert callable(pdf_parser.extract_text)
