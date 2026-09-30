"""RED: the intended future employment-type domain field and parser extraction (Task 1.15A).

Job does not yet have an employment_type field, and job_page_parser does not yet extract one; both
are exercised here against their CURRENT public APIs, so most of this file is expected to fail
until that work is done. Only "Part-time" and "Full-time" are used, because those are the only
employment-type chip values actually observed in tests/fixtures/linkedin/ -- no other value is
invented. All data here is either a committed synthetic fixture or synthetic inline text.

This file does NOT touch job_storage.py or jobs.csv: whether/how employment_type would join the
CSV schema is an open design question (see the accompanying inspection report), not something a
RED test should silently decide.
"""

from pathlib import Path

from job_page_parser import parse_job_page
from models import Job

FIXTURES = Path(__file__).parent / "fixtures" / "linkedin"


def fixture_html(name: str) -> str:
    return (FIXTURES / f"job_detail_{name}.html").read_text(encoding="utf-8")


def make_job(**overrides) -> Job:
    fields = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "Great role",
    }
    fields.update(overrides)
    return Job(**fields)


class TestJobEmploymentTypeField:
    """Job should eventually expose employment_type: str | None, defaulting to None."""

    def test_can_be_constructed_with_an_explicit_employment_type(self):
        job = make_job(employment_type="Part-time")

        assert job.employment_type == "Part-time"

    def test_defaults_to_none_when_not_supplied(self):
        job = make_job()

        assert job.employment_type is None

    def test_preserves_the_exact_supplied_string_without_normalization(self):
        # Not testing normalization/canonicalization (none is specified yet): only that the field
        # is a plain pass-through, the same convention every other Job string field already follows.
        job = make_job(employment_type="  full-time  ")

        assert job.employment_type == "  full-time  "


class TestParsedEmploymentType:
    """parse_job_page() should eventually expose .employment_type from the top-card chip."""

    def test_the_berlin_fixture_parses_as_part_time(self):
        # tests/fixtures/linkedin/job_detail_berlin.html carries a "Part-time" chip alongside the
        # "On-site" workplace chip in the same <ul>.
        result = parse_job_page(fixture_html("berlin"))

        assert result.employment_type == "Part-time"

    def test_the_remote_fixture_parses_as_full_time(self):
        # job_detail_remote.html carries a "Full-time" chip alongside the "Remote" workplace chip.
        result = parse_job_page(fixture_html("remote"))

        assert result.employment_type == "Full-time"

    def test_the_hybrid_fixture_parses_as_part_time(self):
        # job_detail_hybrid.html carries a "Part-time" chip alongside the "Hybrid" workplace chip.
        # Confirms employment type and work mode are read as two separate concepts even though
        # their chips share the same HTML container.
        result = parse_job_page(fixture_html("hybrid"))

        assert result.employment_type == "Part-time"


class TestMissingEmploymentTypeChip:
    def test_a_page_with_no_chips_at_all_has_no_employment_type(self):
        # job_detail_missing_location.html's top card has no chip <ul> whatsoever.
        result = parse_job_page(fixture_html("missing_location"))

        assert result.employment_type is None


class TestNoAccidentalProseExtraction:
    """Every fixture's title contains "Working Student"; that must never leak into employment_type."""

    def test_no_fixture_ever_reports_working_student_as_the_employment_type(self):
        for name in ("berlin", "remote", "hybrid", "missing_location"):
            result = parse_job_page(fixture_html(name))

            assert result.employment_type != "Working Student"
            assert result.employment_type != "Werkstudent"

    def test_the_chip_value_not_the_title_text_determines_employment_type(self):
        # The berlin fixture's <h1> is "Working Student Software Engineer" (prose), while its chip
        # is "Part-time" (structured). The structured chip must win.
        result = parse_job_page(fixture_html("berlin"))

        assert result.employment_type == "Part-time"
        assert "Working Student" not in (result.employment_type or "")


class TestExistingWorkModeBehaviorIsUnaffected:
    """The future employment-type extraction must not disturb the already-established location
    composition behavior for these same fixtures (Tasks up to and including 1.14)."""

    def test_the_berlin_fixture_location_is_unchanged(self):
        assert parse_job_page(fixture_html("berlin")).location == "Berlin, Germany"

    def test_the_remote_fixture_location_is_unchanged(self):
        assert parse_job_page(fixture_html("remote")).location == "Germany (Remote)"

    def test_the_hybrid_fixture_location_is_unchanged(self):
        assert parse_job_page(fixture_html("hybrid")).location == "Berlin, Germany (Hybrid)"

    def test_the_missing_location_fixture_still_has_no_location(self):
        assert parse_job_page(fixture_html("missing_location")).location is None
