"""PDF -> plain text extraction. Layer 1 only: no CandidateProfile interpretation, no LLM.

The only module in this repository that imports pdfplumber. Reads the raw text of a PDF resume,
page by page, in document order, and returns it as a single string. What that text means (skills,
experience, education) is a later task's concern, not this module's.
"""

from pathlib import Path

import pdfplumber


class ResumeExtractionError(Exception):
    """Raised when a PDF cannot be successfully extracted."""


def extract_resume_text(path: str | Path) -> str:
    """Extract the plain text of a PDF resume, in page order.

    Raises FileNotFoundError if the file does not exist and ValueError if its extension is not
    .pdf. Raises ResumeExtractionError if the file cannot be read as a PDF (corrupt, truncated,
    or otherwise unreadable) -- third-party pdfplumber/pdfminer exceptions never cross this
    boundary directly. A structurally valid PDF with no extractable text returns "", not an
    error. Exception messages never include document content, only path/format information.
    """
    path = Path(path)

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported file type {path.suffix or '(none)'}: only .pdf is supported")

    if not path.exists():
        raise FileNotFoundError(path)

    try:
        with pdfplumber.open(path) as pdf:
            page_texts = [page.extract_text() for page in pdf.pages]
    except Exception as exc:
        raise ResumeExtractionError(f"Failed to extract text from PDF: {path.name}") from exc

    return "\n".join(text for text in page_texts if text)
