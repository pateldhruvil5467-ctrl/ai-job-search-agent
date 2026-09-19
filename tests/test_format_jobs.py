"""Behavior tests for the jobs.csv -> jobs_formatted.csv cleaning step.

format_jobs.py is a top-level script (it reads jobs.csv and writes
jobs_formatted.csv relative to the working directory when executed), so these
tests run it as a subprocess inside a pytest temp directory holding a synthetic
jobs.csv. That keeps the suite offline, deterministic, and independent of the
repository's own jobs.csv / jobs_formatted.csv.
"""

import csv
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FORMAT_JOBS_SCRIPT = REPO_ROOT / "format_jobs.py"

COLUMNS = ["title", "company", "location", "description"]
DOT = "·"  # LinkedIn's separator inside description metadata


def job_row(**overrides: str) -> dict[str, str]:
    row = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Remote",
        "description": "Berlin, Germany",
    }
    row.update(overrides)
    return row


def run_format_jobs(workdir: Path, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Write rows to <workdir>/jobs.csv, run format_jobs.py there, return its output rows."""
    with open(workdir / "jobs.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    result = subprocess.run(
        [sys.executable, str(FORMAT_JOBS_SCRIPT)],
        cwd=workdir,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr

    with open(workdir / "jobs_formatted.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestOutputShape:
    def test_output_has_exactly_the_expected_columns_in_order(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row()])

        assert list(rows[0].keys()) == COLUMNS

    def test_valid_rows_pass_through_unchanged(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row()])

        assert rows == [job_row()]

    def test_non_ascii_text_is_preserved(self, tmp_path):
        title = "Entwickler für mobile Anwendungen"

        rows = run_format_jobs(tmp_path, [job_row(title=title)])

        assert rows[0]["title"] == title

    def test_raw_input_file_is_left_untouched(self, tmp_path):
        run_format_jobs(tmp_path, [job_row(title="  Messy   Title ")])
        raw_after_first_run = (tmp_path / "jobs.csv").read_bytes()

        # Formatting must write to a separate file, never rewrite the raw scrape.
        assert b"  Messy   Title " in raw_after_first_run


class TestWhitespaceHandling:
    def test_surrounding_whitespace_is_stripped(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(title="  Engineer  ", company="\tAcme ")])

        assert rows[0]["title"] == "Engineer"
        assert rows[0]["company"] == "Acme"

    def test_internal_runs_of_whitespace_collapse_to_single_spaces(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(title="Senior    Software   Engineer")])

        assert rows[0]["title"] == "Senior Software Engineer"

    def test_newlines_are_flattened_into_spaces(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(title="Senior\nSoftware\r\nEngineer")])

        assert rows[0]["title"] == "Senior Software Engineer"


class TestBerlinNormalization:
    def test_doubled_berlin_in_location_is_collapsed(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(location="Berlin, Berlin")])

        assert rows[0]["location"] == "Berlin"

    def test_doubled_berlin_in_description_is_collapsed(self, tmp_path):
        rows = run_format_jobs(
            tmp_path, [job_row(description=f"Berlin, Berlin, Germany {DOT} 3 weeks ago")]
        )

        assert rows[0]["description"] == "Berlin, Germany"

    def test_single_berlin_is_left_alone(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="Berlin, Germany")])

        assert rows[0]["description"] == "Berlin, Germany"


class TestUnknownFiltering:
    def test_rows_with_unknown_title_are_dropped(self, tmp_path):
        rows = run_format_jobs(
            tmp_path, [job_row(title="Unknown Title"), job_row(title="Real Job")]
        )

        assert [r["title"] for r in rows] == ["Real Job"]

    def test_rows_with_unknown_company_are_dropped(self, tmp_path):
        rows = run_format_jobs(
            tmp_path, [job_row(company="Unknown Company"), job_row(company="Real Co")]
        )

        assert [r["company"] for r in rows] == ["Real Co"]

    def test_unknown_location_or_description_does_not_drop_the_row(self, tmp_path):
        rows = run_format_jobs(
            tmp_path,
            [job_row(location="Unknown Location", description="No description available")],
        )

        assert len(rows) == 1


class TestDeduplication:
    def test_duplicate_title_and_company_keeps_first_occurrence(self, tmp_path):
        rows = run_format_jobs(
            tmp_path,
            [
                job_row(description="first"),
                job_row(description="second"),
            ],
        )

        assert [r["description"] for r in rows] == ["first"]

    def test_same_title_at_different_companies_is_not_a_duplicate(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(company="Acme"), job_row(company="Globex")])

        assert [r["company"] for r in rows] == ["Acme", "Globex"]

    def test_same_company_with_different_titles_is_not_a_duplicate(self, tmp_path):
        rows = run_format_jobs(
            tmp_path, [job_row(title="Backend Engineer"), job_row(title="Frontend Engineer")]
        )

        assert [r["title"] for r in rows] == ["Backend Engineer", "Frontend Engineer"]

    def test_duplicates_are_detected_after_whitespace_cleanup(self, tmp_path):
        rows = run_format_jobs(
            tmp_path,
            [job_row(title="Engineer", description="first"), job_row(title="  Engineer  ", description="second")],
        )

        assert [r["description"] for r in rows] == ["first"]


class TestDescriptionTruncation:
    def test_short_description_is_unchanged(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="Short text")])

        assert rows[0]["description"] == "Short text"

    def test_only_the_text_before_the_first_separator_is_kept(self, tmp_path):
        description = f"Berlin, Germany {DOT} 1 week ago {DOT} Over 100 applicants"

        rows = run_format_jobs(tmp_path, [job_row(description=description)])

        assert rows[0]["description"] == "Berlin, Germany"

    def test_long_description_is_cut_to_150_chars_with_ellipsis(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="a" * 200)])

        assert rows[0]["description"] == "a" * 150 + "..."

    def test_long_first_segment_is_also_cut(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="b" * 200 + f" {DOT} tail")])

        assert rows[0]["description"] == "b" * 150 + "..."

    def test_description_of_exactly_150_chars_is_not_cut(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="c" * 150)])

        assert rows[0]["description"] == "c" * 150

    def test_empty_description_gets_placeholder(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="")])

        assert rows[0]["description"] == "No description available"

    def test_whitespace_only_description_gets_placeholder(self, tmp_path):
        rows = run_format_jobs(tmp_path, [job_row(description="   \n  ")])

        assert rows[0]["description"] == "No description available"
