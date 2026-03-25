"""PDF text extraction using pdfplumber."""
import io
import re
from typing import Union


def extract_text(source: Union[bytes, io.IOBase]) -> str:
    """Extract clean text from a PDF.

    Args:
        source: Raw PDF bytes or a file-like object.

    Returns:
        Extracted text as a single string with normalised whitespace.

    Raises:
        ValueError: If the input is not a valid PDF.
    """
    import pdfplumber

    if isinstance(source, (bytes, bytearray)):
        file_obj: io.IOBase = io.BytesIO(source)
    else:
        file_obj = source

    # Validate PDF header before handing to pdfplumber
    file_obj.seek(0)
    header = file_obj.read(5)
    file_obj.seek(0)
    if header != b"%PDF-":
        raise ValueError("Input is not a valid PDF (missing %PDF- header)")

    try:
        with pdfplumber.open(file_obj) as pdf:
            pages: list[str] = []
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    pages.append(text.strip())
            full_text = "\n\n".join(pages)
    except Exception as exc:
        raise ValueError(f"Failed to extract text from PDF: {exc}") from exc

    # Normalise: collapse runs of 3+ newlines to two, strip leading/trailing
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    return full_text.strip()
