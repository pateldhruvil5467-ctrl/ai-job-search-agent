"""resume_pdf.py: PDF -> plain text extraction only. No interpretation, no CandidateProfile.

Layer 1 only (see the Task 1.2 inspection report): mechanical text extraction, nothing else.
Fixtures are minimal, hand-built PDF byte strings (see _build_pdf below), generated at test time
rather than committed binary files -- following this repo's own precedent for hand-rolling PDF
bytes without a third-party library (generate_repo_summary_pdf.py). All resume content here is
fictional: invented names, a .invalid email domain (reserved for documentation/testing by
RFC 2606), no real data.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from resume_pdf import ResumeExtractionError, extract_resume_text

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_NAME = "Jordan Rivers"
SYNTHETIC_EMAIL = "jordan.rivers@example.invalid"
SYNTHETIC_ORG = "Fictional Systems GmbH"

PAGE_ONE = [
    f"{SYNTHETIC_NAME} - Fictional Resume (synthetic test data)",
    f"Email: {SYNTHETIC_EMAIL}",
    f"Experience: Working Student, {SYNTHETIC_ORG}, 2024-2025",
]
PAGE_TWO = [
    "Education: B.Sc. Computer Science, Fictional State University",
    "Skills: Python, SQL, synthetic-test-only-skill-marker",
]
UNICODE_PAGE = [
    "Name: Jürgen Müller (synthetic)",
    "University: Universität Fiktiv, Straße 1",
]


# --------------------------------------------------------------------------------------------
# Synthetic PDF construction (stdlib only -- pdfplumber is a reader, not a writer, and is not
# installed at this stage; see generate_repo_summary_pdf.py for this repo's existing precedent
# for hand-building minimal PDF bytes without any library).
# --------------------------------------------------------------------------------------------

def _pdf_escape(data: bytes) -> bytes:
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _text_stream(lines: list[str]) -> bytes:
    """A content stream drawing each line via Tj, encoded with WinAnsiEncoding (cp1252)."""
    parts = [b"BT", b"/F1 11 Tf", b"14 TL", b"1 0 0 1 48 744 Tm"]
    for index, line in enumerate(lines):
        if index:
            parts.append(b"T*")
        parts.append(b"(" + _pdf_escape(line.encode("cp1252")) + b") Tj")
    parts.append(b"ET")
    return b"\n".join(parts) + b"\n"


def _build_pdf(pages: list[list[str]]) -> bytes:
    """A minimal, valid, multi-page PDF with no external dependency. One content stream per page."""
    resolved_pages = pages if pages else [[]]
    num_pages = len(resolved_pages)
    font_obj = 3 + num_pages
    first_stream_obj = font_obj + 1

    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + i} 0 R" for i in range(num_pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>".encode("ascii"))
    for i in range(num_pages):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> "
                f"/Contents {first_stream_obj + i} 0 R >>"
            ).encode("ascii")
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for page in resolved_pages:
        stream = _text_stream(page)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _empty_pdf() -> bytes:
    """A structurally valid single-page PDF with no text-drawing operators at all."""
    return _build_pdf([[]])


def write_pdf(path: Path, pages: list[list[str]]) -> Path:
    path.write_bytes(_build_pdf(pages))
    return path


class TestValidPdf:
    def test_returns_a_string(self, tmp_path):
        path = write_pdf(tmp_path / "resume.pdf", [PAGE_ONE])

        assert isinstance(extract_resume_text(path), str)

    def test_extracted_text_contains_the_synthetic_resume_content(self, tmp_path):
        path = write_pdf(tmp_path / "resume.pdf", [PAGE_ONE])

        text = extract_resume_text(path)

        assert SYNTHETIC_NAME in text
        assert SYNTHETIC_EMAIL in text
        assert SYNTHETIC_ORG in text

    @pytest.mark.parametrize("as_str", [True, False], ids=["str-path", "path-object"])
    def test_accepts_both_a_string_path_and_a_path_object(self, tmp_path, as_str):
        path = write_pdf(tmp_path / "resume.pdf", [PAGE_ONE])

        text = extract_resume_text(str(path) if as_str else path)

        assert SYNTHETIC_NAME in text


class TestMultiplePages:
    def test_text_from_every_page_is_returned(self, tmp_path):
        path = write_pdf(tmp_path / "resume.pdf", [PAGE_ONE, PAGE_TWO])

        text = extract_resume_text(path)

        assert SYNTHETIC_NAME in text
        assert "Fictional State University" in text
        assert "synthetic-test-only-skill-marker" in text

    def test_page_content_appears_in_document_order(self, tmp_path):
        path = write_pdf(tmp_path / "resume.pdf", [PAGE_ONE, PAGE_TWO])

        text = extract_resume_text(path)

        assert text.index(SYNTHETIC_ORG) < text.index("Fictional State University")

    def test_a_three_page_document_preserves_order_across_all_pages(self, tmp_path):
        third_page = ["Certifications: synthetic-test-only-certificate-marker"]
        path = write_pdf(tmp_path / "resume.pdf", [PAGE_ONE, PAGE_TWO, third_page])

        text = extract_resume_text(path)

        assert (
            text.index(SYNTHETIC_ORG)
            < text.index("Fictional State University")
            < text.index("synthetic-test-only-certificate-marker")
        )


class TestUnicode:
    def test_non_ascii_text_is_preserved(self, tmp_path):
        path = write_pdf(tmp_path / "resume.pdf", [UNICODE_PAGE])

        text = extract_resume_text(path)

        assert "Jürgen Müller" in text
        assert "Universität Fiktiv" in text
        assert "Straße" in text


class TestMissingFile:
    def test_a_missing_path_object_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_resume_text(tmp_path / "does_not_exist.pdf")

    def test_a_missing_string_path_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_resume_text(str(tmp_path / "does_not_exist.pdf"))


class TestInvalidOrCorruptPdf:
    def test_plain_text_pretending_to_be_a_pdf_raises_the_dedicated_exception(self, tmp_path):
        path = tmp_path / "resume.pdf"
        path.write_bytes(b"This is not a PDF file at all, just plain text pretending to be one.")

        with pytest.raises(ResumeExtractionError):
            extract_resume_text(path)

    def test_a_pdf_header_with_garbage_afterwards_raises_the_dedicated_exception(self, tmp_path):
        path = tmp_path / "resume.pdf"
        path.write_bytes(b"%PDF-1.4\n" + b"\x00\x01\x02CORRUPT" * 50)

        with pytest.raises(ResumeExtractionError):
            extract_resume_text(path)

    def test_an_empty_file_raises_the_dedicated_exception(self, tmp_path):
        path = tmp_path / "resume.pdf"
        path.write_bytes(b"")

        with pytest.raises(ResumeExtractionError):
            extract_resume_text(path)

    def test_a_truncated_but_otherwise_valid_pdf_raises_the_dedicated_exception(self, tmp_path):
        # A well-formed PDF with its xref table and trailer cut off -- structurally broken,
        # not merely unusual content.
        full_pdf = _build_pdf([PAGE_ONE])
        path = tmp_path / "resume.pdf"
        path.write_bytes(full_pdf[: len(full_pdf) // 2])

        with pytest.raises(ResumeExtractionError):
            extract_resume_text(path)


class TestUnsupportedFileType:
    @pytest.mark.parametrize("extension", [".docx", ".txt"])
    def test_a_non_pdf_extension_is_rejected_without_attempting_to_parse_it(self, tmp_path, extension):
        # DOCX parsing is explicitly not implemented in this task; the rejection must happen
        # on the file type itself, not depend on whatever bytes happen to be inside.
        path = tmp_path / f"resume{extension}"
        path.write_bytes(b"arbitrary bytes, never meant to be parsed")

        with pytest.raises(ValueError):
            extract_resume_text(path)


class TestEmptyTextlessPdf:
    def test_a_structurally_valid_pdf_with_no_text_returns_an_empty_string(self, tmp_path):
        # Consistent with job_page_parser.py's precedent: a well-formed document that simply
        # has nothing to extract is not an error condition. extract_resume_text's return type
        # is `str`, not `str | None`, so "nothing found" is the empty string, not None.
        path = tmp_path / "resume.pdf"
        path.write_bytes(_empty_pdf())

        text = extract_resume_text(path)

        assert text == ""

    def test_no_exception_is_raised_for_a_textless_pdf(self, tmp_path):
        path = tmp_path / "resume.pdf"
        path.write_bytes(_empty_pdf())

        extract_resume_text(path)  # must not raise


class TestPrivacyOfFixtures:
    def test_the_synthetic_email_uses_the_reserved_invalid_domain(self):
        # RFC 2606 reserves .invalid for exactly this purpose: guaranteed never to be a real,
        # deliverable address.
        assert SYNTHETIC_EMAIL.endswith("@example.invalid")

    def test_no_fixture_uses_a_real_looking_top_level_domain(self):
        forbidden_domains = (".com", ".org", ".net", ".de", ".io")
        all_fixture_text = " ".join(PAGE_ONE + PAGE_TWO + UNICODE_PAGE)

        assert not any(domain in all_fixture_text for domain in forbidden_domains)


class TestErrorMessagePrivacy:
    def test_a_corrupt_file_containing_real_seeming_text_never_quotes_it_in_the_error(self, tmp_path):
        # The file genuinely contains SYNTHETIC_NAME/SYNTHETIC_EMAIL in its raw bytes (that's
        # what makes this test meaningful), but the truncation makes it unparseable. The
        # exception message must describe the failure, never echo document content.
        full_pdf = _build_pdf([PAGE_ONE])
        path = tmp_path / "resume.pdf"
        path.write_bytes(full_pdf[: len(full_pdf) // 2])

        with pytest.raises(ResumeExtractionError) as exc_info:
            extract_resume_text(path)

        message = str(exc_info.value)
        assert SYNTHETIC_NAME not in message
        assert SYNTHETIC_EMAIL not in message
        assert SYNTHETIC_ORG not in message

    def test_a_plain_text_file_disguised_as_a_pdf_does_not_echo_its_body_in_the_error(self, tmp_path):
        secret_marker = "SHOULD_NEVER_APPEAR_IN_THE_EXCEPTION_MESSAGE"
        path = tmp_path / "resume.pdf"
        path.write_bytes(secret_marker.encode("ascii"))

        with pytest.raises(ResumeExtractionError) as exc_info:
            extract_resume_text(path)

        assert secret_marker not in str(exc_info.value)


class TestDependencyIsolation:
    @pytest.mark.parametrize("module", ["selenium", "pandas", "webdriver_manager"])
    def test_importing_resume_pdf_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, resume_pdf; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr

    def test_candidate_remains_independent_of_pdfplumber(self):
        # candidate.py must stay a plain domain model, with no coupling to how a resume is
        # eventually read from disk. Checked without modifying candidate.py or its tests.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, candidate; "
                "loaded = sorted(m for m in sys.modules if m == 'pdfplumber' or m.startswith('pdfplumber.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
