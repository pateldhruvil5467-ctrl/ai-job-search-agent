"""Storage layer: Job -> DataFrame -> CSV. Offline; every file is written under tmp_path."""

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from job_storage import JOBS_CSV_PATH, clean_jobs_dataframe, jobs_to_dataframe, save_jobs_csv
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent
FORMAT_JOBS_SCRIPT = REPO_ROOT / "format_jobs.py"

COLUMNS = ["title", "company", "location", "description"]


def make_job(**overrides: str) -> Job:
    fields = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Remote",
        "description": "Berlin, Germany",
    }
    fields.update(overrides)
    return Job(**fields)


def read_text_lf(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


class TestJobsToDataFrame:
    def test_columns_are_exactly_the_csv_contract_in_order(self):
        df = jobs_to_dataframe([make_job()])

        assert list(df.columns) == COLUMNS

    def test_one_row_per_job_in_the_given_order(self):
        df = jobs_to_dataframe(
            [make_job(title="First"), make_job(title="Second"), make_job(title="Third")]
        )

        assert list(df["title"]) == ["First", "Second", "Third"]

    def test_values_are_carried_over_unchanged(self):
        job = make_job(description="multi\nline · text")

        row = jobs_to_dataframe([job]).iloc[0]

        assert row.to_dict() == {
            "title": "Software Engineer",
            "company": "Acme",
            "location": "Remote",
            "description": "multi\nline · text",
        }


class TestCleanJobsDataFrame:
    def test_surrounding_whitespace_is_stripped_in_every_column(self):
        df = pd.DataFrame(
            [{"title": " T ", "company": "\tC\n", "location": "  L ", "description": " D "}]
        )

        cleaned = clean_jobs_dataframe(df)

        assert cleaned.iloc[0].to_dict() == {
            "title": "T",
            "company": "C",
            "location": "L",
            "description": "D",
        }

    def test_rows_with_unknown_title_are_removed(self):
        df = jobs_to_dataframe([make_job(title="Unknown Title"), make_job(title="Real")])

        assert list(clean_jobs_dataframe(df)["title"]) == ["Real"]

    def test_rows_with_unknown_company_are_removed(self):
        df = jobs_to_dataframe([make_job(company="Unknown Company"), make_job(company="Real")])

        assert list(clean_jobs_dataframe(df)["company"]) == ["Real"]

    def test_unknown_location_or_description_does_not_remove_the_row(self):
        df = jobs_to_dataframe(
            [make_job(location="Unknown Location", description="No description available")]
        )

        assert len(clean_jobs_dataframe(df)) == 1

    def test_columns_are_preserved(self):
        cleaned = clean_jobs_dataframe(jobs_to_dataframe([make_job()]))

        assert list(cleaned.columns) == COLUMNS

    def test_the_input_dataframe_is_not_mutated(self):
        df = pd.DataFrame(
            [{"title": " T ", "company": "C", "location": "L", "description": "D"}]
        )

        clean_jobs_dataframe(df)

        assert df.iloc[0]["title"] == " T "


class TestSaveJobsCsv:
    def test_default_path_is_jobs_csv_which_the_pipeline_reads(self):
        assert JOBS_CSV_PATH == "jobs.csv"

    def test_relative_default_path_writes_into_the_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        save_jobs_csv([make_job()])

        assert (tmp_path / "jobs.csv").exists()

    def test_header_row_is_the_exact_column_names(self, tmp_path):
        path = tmp_path / "jobs.csv"

        save_jobs_csv([make_job()], path)

        assert read_text_lf(path).splitlines()[0] == '"title","company","location","description"'

    def test_saving_no_jobs_at_all_fails_and_writes_nothing(self, tmp_path):
        # Known limitation of this layer, deliberately left as-is: an empty list gives a DataFrame
        # with no columns, so cleaning raises KeyError. scrape_jobs() guards against this with
        # NoJobsExtractedError, so an empty scrape never reaches storage.
        path = tmp_path / "jobs.csv"

        with pytest.raises(KeyError, match="title"):
            save_jobs_csv([], path)

        assert not path.exists()

    def test_returns_the_cleaned_dataframe_that_was_written(self, tmp_path):
        jobs = [make_job(title="Keep"), make_job(title="Unknown Title"), make_job(company="Unknown Company")]

        df = save_jobs_csv(jobs, tmp_path / "jobs.csv")

        assert list(df.columns) == COLUMNS
        assert list(df["title"]) == ["Keep"]

    def test_unknown_rows_are_not_written(self, tmp_path):
        path = tmp_path / "jobs.csv"

        save_jobs_csv([make_job(title="Unknown Title"), make_job(title="Keep")], path)

        written = pd.read_csv(path)
        assert list(written["title"]) == ["Keep"]

    def test_special_characters_round_trip_through_read_csv(self, tmp_path):
        path = tmp_path / "jobs.csv"
        job = make_job(
            title='Quote "Test", Inc',
            location="München, Bayern",
            description="Berlin, Germany · 1 week ago\n\nPromoted by hirer",
        )

        save_jobs_csv([job], path)

        row = pd.read_csv(path).iloc[0]
        assert row["title"] == 'Quote "Test", Inc'
        assert row["location"] == "München, Bayern"
        assert row["description"] == "Berlin, Germany · 1 week ago\n\nPromoted by hirer"

    def test_csv_format_is_unchanged_quote_all_with_doubled_quotes_and_escaped_backslashes(self, tmp_path):
        # Golden output, captured from the pre-refactor implementation
        # (DataFrame.to_csv(index=False, quoting=1, escapechar='\\')).
        path = tmp_path / "jobs.csv"
        jobs = [
            make_job(
                title="Senior Software Engineer",
                company="browserless",
                description="Berlin, Germany · 1 month ago\n\nPromoted by hirer",
            ),
            make_job(title="Unknown Title", company="Real Co"),
            make_job(
                title='Quote "Test", Inc',
                company="Back\\slash GmbH",
                location="München, Bayern",
                description='He said "hi", then\nleft',
            ),
        ]

        save_jobs_csv(jobs, path)

        assert read_text_lf(path) == (
            '"title","company","location","description"\n'
            '"Senior Software Engineer","browserless","Remote","Berlin, Germany · 1 month ago\n'
            "\n"
            'Promoted by hirer"\n'
            '"Quote ""Test"", Inc","Back\\\\slash GmbH","München, Bayern","He said ""hi"", then\n'
            'left"\n'
        )


class TestDownstreamCompatibility:
    def test_format_jobs_consumes_the_saved_csv(self, tmp_path):
        save_jobs_csv(
            [
                make_job(
                    title='Working Student "Backend", Payments',
                    company="Scalable Capital",
                    description="Berlin, Berlin, Germany · 3 weeks ago\n\nPromoted by hirer",
                ),
                make_job(title="Unknown Title"),
                make_job(title="Other Role", company="Globex", description=""),
            ],
            tmp_path / "jobs.csv",
        )

        result = subprocess.run(
            [sys.executable, str(FORMAT_JOBS_SCRIPT)],
            cwd=tmp_path,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stderr

        formatted = pd.read_csv(tmp_path / "jobs_formatted.csv", keep_default_na=False)
        assert list(formatted.columns) == COLUMNS
        assert formatted.to_dict("records") == [
            {
                "title": 'Working Student "Backend", Payments',
                "company": "Scalable Capital",
                "location": "Remote",
                "description": "Berlin, Germany",
            },
            {
                "title": "Other Role",
                "company": "Globex",
                "location": "Remote",
                "description": "No description available",
            },
        ]
