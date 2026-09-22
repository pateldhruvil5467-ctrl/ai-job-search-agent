"""Storage layer: Job -> DataFrame -> CSV. Offline; every file is written under tmp_path."""

import csv
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from job_storage import JOBS_CSV_PATH, clean_jobs_dataframe, jobs_to_dataframe, load_jobs_csv, save_jobs_csv
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent
FORMAT_JOBS_SCRIPT = REPO_ROOT / "format_jobs.py"

# The jobs.csv contract: the original four columns keep their positions and url is appended.
COLUMNS = ["title", "company", "location", "description", "url"]
# format_jobs.py still selects exactly these four for jobs_formatted.csv, so url is not forwarded.
FORMATTED_COLUMNS = ["title", "company", "location", "description"]
JOB_URL = "https://www.linkedin.com/jobs/view/3812345678/"


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
        job = make_job(description="multi\nline · text", url=JOB_URL)

        row = jobs_to_dataframe([job]).iloc[0]

        assert row.to_dict() == {
            "title": "Software Engineer",
            "company": "Acme",
            "location": "Remote",
            "description": "multi\nline · text",
            "url": JOB_URL,
        }

    def test_a_job_without_a_url_has_an_empty_url_cell(self):
        assert jobs_to_dataframe([make_job()]).iloc[0]["url"] == ""

    def test_the_original_four_columns_keep_their_positions(self):
        assert list(jobs_to_dataframe([make_job()]).columns)[:4] == FORMATTED_COLUMNS

    def test_url_is_the_last_column(self):
        assert list(jobs_to_dataframe([make_job()]).columns)[-1] == "url"


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

        assert read_text_lf(path).splitlines()[0] == '"title","company","location","description","url"'

    def test_url_is_preserved_in_the_last_column(self, tmp_path):
        path = tmp_path / "jobs.csv"

        save_jobs_csv([make_job(url=JOB_URL)], path)

        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0] == COLUMNS
        assert rows[1][-1] == JOB_URL
        assert rows[1][:4] == ["Software Engineer", "Acme", "Remote", "Berlin, Germany"]

    def test_an_empty_url_is_written_as_an_empty_quoted_field(self, tmp_path):
        path = tmp_path / "jobs.csv"

        save_jobs_csv([make_job()], path)

        assert read_text_lf(path).splitlines()[1] == '"Software Engineer","Acme","Remote","Berlin, Germany",""'

    def test_an_empty_url_reads_back_as_empty_with_the_csv_module(self, tmp_path):
        path = tmp_path / "jobs.csv"

        save_jobs_csv([make_job(), make_job(title="Other", url=JOB_URL)], path)

        with open(path, newline="", encoding="utf-8") as f:
            urls = [row["url"] for row in csv.DictReader(f)]
        assert urls == ["", JOB_URL]

    def test_urls_with_query_strings_commas_and_quotes_survive_a_round_trip(self, tmp_path):
        path = tmp_path / "jobs.csv"
        url = 'https://example.test/jobs/view/1/?a=1&b=%2Fx%3D&c="q",d'

        save_jobs_csv([make_job(url=url)], path)

        with open(path, newline="", encoding="utf-8") as f:
            assert next(csv.DictReader(f))["url"] == url

    def test_the_url_survives_cleaning_of_the_other_columns(self, tmp_path):
        df = save_jobs_csv([make_job(title="  Padded  ", url=JOB_URL)], tmp_path / "jobs.csv")

        assert df.iloc[0]["title"] == "Padded"
        assert df.iloc[0]["url"] == JOB_URL

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
        # Golden output. The first four columns are byte-for-byte what the pre-refactor implementation
        # wrote (DataFrame.to_csv(index=False, quoting=1, escapechar='\\')); url is appended as column five.
        path = tmp_path / "jobs.csv"
        jobs = [
            make_job(
                title="Senior Software Engineer",
                company="browserless",
                description="Berlin, Germany · 1 month ago\n\nPromoted by hirer",
                url=JOB_URL,
            ),
            make_job(title="Unknown Title", company="Real Co"),
            make_job(
                title='Quote "Test", Inc',
                company="Back\\slash GmbH",
                location="München, Bayern",
                description='He said "hi", then\nleft',
                url='https://example.test/a?x=1&y="q",z\\w',
            ),
            make_job(title="No Link", company="Nowhere"),
        ]

        save_jobs_csv(jobs, path)

        assert read_text_lf(path) == (
            '"title","company","location","description","url"\n'
            '"Senior Software Engineer","browserless","Remote","Berlin, Germany · 1 month ago\n'
            "\n"
            'Promoted by hirer","https://www.linkedin.com/jobs/view/3812345678/"\n'
            '"Quote ""Test"", Inc","Back\\\\slash GmbH","München, Bayern","He said ""hi"", then\n'
            'left","https://example.test/a?x=1&y=""q"",z\\\\w"\n'
            '"No Link","Nowhere","Remote","Berlin, Germany",""\n'
        )


class TestDownstreamCompatibility:
    def test_format_jobs_consumes_the_saved_csv_and_does_not_forward_the_url(self, tmp_path):
        save_jobs_csv(
            [
                make_job(
                    title='Working Student "Backend", Payments',
                    company="Scalable Capital",
                    description="Berlin, Berlin, Germany · 3 weeks ago\n\nPromoted by hirer",
                    url=JOB_URL,
                ),
                make_job(title="Unknown Title"),
                make_job(title="Other Role", company="Globex", description=""),
            ],
            tmp_path / "jobs.csv",
        )
        assert list(pd.read_csv(tmp_path / "jobs.csv").columns) == COLUMNS  # the input really has url

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
        assert list(formatted.columns) == FORMATTED_COLUMNS
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


HEADER = '"title","company","location","description","url"'
LEGACY_HEADER = '"title","company","location","description"'


def round_trip_jobs() -> list[Job]:
    """Jobs as the scraper produces them (already normalized), full of characters that stress CSV quoting."""
    rows = [
        {
            "title": 'Quote "Test", Inc',
            "company": "Back\\slash GmbH",
            "location": "M\u00fcnchen, Bayern",
            "description": 'He said "hi", then\nleft\n\nPath C:\\temp\\new, a literal \\n, and a trailing backslash \\',
            "url": 'https://example.test/a?x=1&y="q",z\\w',
        },
        {
            "title": "Multi-line",
            "company": "Windows Newlines AG",
            "location": "Berlin, Germany (Hybrid)",
            "description": "line one\r\nline two\r\n\r\nline four",
            "url": "https://www.linkedin.com/jobs/view/4457758762/",
        },
        {
            "title": "\U0001f680 Rocket Engineer",
            "company": "Gr\u00f6\u00dfe & S\u00f6hne \u2728",
            "location": "Germany (Remote)",
            "description": "Wir suchen Entwickler f\u00fcr KI \u2014 mit \U0001f680 und \u201eAnf\u00fchrungszeichen\u201c",
            "url": "",
        },
    ]
    return [Job.from_scraped_data(row) for row in rows]


def write_text(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


def reported_columns(error) -> list[str]:
    """The column names listed after 'column(s): ' in a missing-columns ValueError."""
    return str(error.value).split("column(s): ")[-1].split(", ")


class TestLoadJobsCsvRoundTrip:
    def test_a_saved_file_loads_back_to_the_same_jobs(self, tmp_path):
        jobs = round_trip_jobs()
        save_jobs_csv(jobs, tmp_path / "jobs.csv")

        assert load_jobs_csv(tmp_path / "jobs.csv") == jobs

    def test_backslashes_survive_because_reader_and_writer_share_the_escape_character(self, tmp_path):
        job = Job.from_scraped_data(
            {"title": "T", "company": "Back\\slash GmbH", "location": "L", "description": "path C:\\temp\\new, a literal \\n, ends with \\"}
        )
        save_jobs_csv([job], tmp_path / "jobs.csv")

        loaded = load_jobs_csv(tmp_path / "jobs.csv")[0]

        assert loaded.company == "Back\\slash GmbH"
        assert loaded.description == "path C:\\temp\\new, a literal \\n, ends with \\"
        assert "\n" not in loaded.description  # the two characters backslash-n did not become a newline

    def test_quotes_commas_and_embedded_newlines_survive(self, tmp_path):
        job = round_trip_jobs()[0]
        save_jobs_csv([job], tmp_path / "jobs.csv")

        loaded = load_jobs_csv(tmp_path / "jobs.csv")[0]

        assert loaded.title == 'Quote "Test", Inc'
        assert loaded.description == job.description
        assert loaded.description.count("\n") == 3

    def test_windows_line_endings_inside_a_field_survive(self, tmp_path):
        job = round_trip_jobs()[1]
        save_jobs_csv([job], tmp_path / "jobs.csv")

        assert load_jobs_csv(tmp_path / "jobs.csv")[0].description == "line one\r\nline two\r\n\r\nline four"

    def test_unicode_and_emoji_survive_regardless_of_the_platform_default_encoding(self, tmp_path):
        job = round_trip_jobs()[2]
        save_jobs_csv([job], tmp_path / "jobs.csv")

        loaded = load_jobs_csv(tmp_path / "jobs.csv")[0]

        assert loaded.title == "\U0001f680 Rocket Engineer"
        assert loaded.company == "Gr\u00f6\u00dfe & S\u00f6hne \u2728"
        assert loaded.description == job.description

    def test_an_empty_url_stays_empty_and_never_becomes_nan(self, tmp_path):
        save_jobs_csv([Job.from_scraped_data({"title": "No Link", "company": "Nowhere"})], tmp_path / "jobs.csv")

        loaded = load_jobs_csv(tmp_path / "jobs.csv")[0]

        assert loaded.url == ""
        assert loaded.url != "nan"

    def test_the_url_is_preserved_when_there_is_one(self, tmp_path):
        save_jobs_csv(round_trip_jobs(), tmp_path / "jobs.csv")

        assert [job.url for job in load_jobs_csv(tmp_path / "jobs.csv")] == [job.url for job in round_trip_jobs()]

    def test_loading_and_saving_again_reproduces_the_writers_bytes(self, tmp_path):
        first, second = tmp_path / "first.csv", tmp_path / "second.csv"
        save_jobs_csv(round_trip_jobs(), first)

        save_jobs_csv(load_jobs_csv(first), second)

        assert second.read_bytes() == first.read_bytes()

    def test_the_writers_golden_output_loads_into_the_expected_jobs(self, tmp_path):
        golden = (
            '"title","company","location","description","url"\n'
            '"Senior Software Engineer","browserless","Remote","Berlin, Germany \u00b7 1 month ago\n'
            "\n"
            'Promoted by hirer","https://www.linkedin.com/jobs/view/3812345678/"\n'
            '"Quote ""Test"", Inc","Back\\\\slash GmbH","M\u00fcnchen, Bayern","He said ""hi"", then\n'
            'left","https://example.test/a?x=1&y=""q"",z\\\\w"\n'
            '"No Link","Nowhere","Remote","Berlin, Germany",""\n'
        )

        loaded = load_jobs_csv(write_text(tmp_path / "jobs.csv", golden))

        assert loaded == [
            Job("Senior Software Engineer", "browserless", "Remote", "Berlin, Germany \u00b7 1 month ago\n\nPromoted by hirer", JOB_URL),
            Job('Quote "Test", Inc', "Back\\slash GmbH", "M\u00fcnchen, Bayern", 'He said "hi", then\nleft', 'https://example.test/a?x=1&y="q",z\\w'),
            Job("No Link", "Nowhere", "Remote", "Berlin, Germany", ""),
        ]


class TestLoadJobsCsvContents:
    def test_rows_come_back_in_file_order(self, tmp_path):
        titles = ["Zebra", "Apple", "Mango", "Banana", "Cherry", "Zebra 2"]
        save_jobs_csv([make_job(title=t, company=f"Co {i}") for i, t in enumerate(titles)], tmp_path / "jobs.csv")

        assert [job.title for job in load_jobs_csv(tmp_path / "jobs.csv")] == titles

    def test_a_header_only_file_gives_no_jobs(self, tmp_path):
        assert load_jobs_csv(write_text(tmp_path / "jobs.csv", HEADER + "\r\n")) == []

    def test_a_header_only_file_written_by_saving_only_unknown_jobs_gives_no_jobs(self, tmp_path):
        save_jobs_csv([Job.from_scraped_data({})], tmp_path / "jobs.csv")

        assert load_jobs_csv(tmp_path / "jobs.csv") == []

    def test_a_legacy_four_column_file_loads_with_empty_urls(self, tmp_path):
        text = LEGACY_HEADER + '\r\n"Old Role","Old Co","Remote","the old description"\r\n"Second","Co 2","Berlin","more"\r\n'

        loaded = load_jobs_csv(write_text(tmp_path / "jobs.csv", text))

        assert loaded == [
            Job("Old Role", "Old Co", "Remote", "the old description", ""),
            Job("Second", "Co 2", "Berlin", "more", ""),
        ]

    def test_extra_columns_are_ignored_and_column_order_does_not_matter(self, tmp_path):
        text = '"notes","url","description","title","score","location","company"\r\n"n","https://www.linkedin.com/jobs/view/1/","d","T","9","L","C"\r\n'

        assert load_jobs_csv(write_text(tmp_path / "jobs.csv", text)) == [
            Job("T", "C", "L", "d", "https://www.linkedin.com/jobs/view/1/")
        ]

    def test_missing_cells_take_the_same_defaults_as_the_scraper_uses(self, tmp_path):
        text = HEADER + '\r\n"Only Title","","","",""\r\n'

        loaded = load_jobs_csv(write_text(tmp_path / "jobs.csv", text))

        assert loaded == [Job("Only Title", "Unknown Company", "Unknown Location", "No description available", "")]

    def test_a_short_row_is_completed_with_defaults_and_a_long_row_loses_only_its_extra_cells(self, tmp_path):
        text = HEADER + '\r\n"Short"\r\n"Long","Co","L","d","u","extra","cells"\r\n'

        loaded = load_jobs_csv(write_text(tmp_path / "jobs.csv", text))

        assert loaded == [
            Job("Short", "Unknown Company", "Unknown Location", "No description available", ""),
            Job("Long", "Co", "L", "d", "u"),
        ]

    def test_conversion_reuses_the_scrapers_sanitization(self, tmp_path):
        text = HEADER + '\r\n"  Padded  ","  Co  ","  L  ","  d  ","  https://www.linkedin.com/jobs/view/1/  "\r\n'

        assert load_jobs_csv(write_text(tmp_path / "jobs.csv", text)) == [
            Job("Padded", "Co", "L", "d", "https://www.linkedin.com/jobs/view/1/")
        ]

    def test_nothing_is_deduplicated_filtered_or_repaired(self, tmp_path):
        text = (
            HEADER + "\r\n"
            '"Same","Co","L","first","u1"\r\n'
            '"Same","Co","L","first","u1"\r\n'
            '"Same","Co","L","second","u2"\r\n'
            '"Unknown Title","Unknown Company","Unknown Location","No description available",""\r\n'
        )

        loaded = load_jobs_csv(write_text(tmp_path / "jobs.csv", text))

        assert [(job.title, job.description) for job in loaded] == [
            ("Same", "first"),  # an exact duplicate row is kept, not merged
            ("Same", "first"),
            ("Same", "second"),
            ("Unknown Title", "No description available"),  # unknown rows are not filtered out
        ]

    def test_the_result_is_a_list_of_immutable_jobs(self, tmp_path):
        save_jobs_csv([make_job()], tmp_path / "jobs.csv")

        loaded = load_jobs_csv(tmp_path / "jobs.csv")

        assert isinstance(loaded, list)
        assert all(isinstance(job, Job) for job in loaded)


class TestLoadJobsCsvPathAndErrors:
    def test_a_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_jobs_csv(tmp_path / "does_not_exist.csv")

    def test_the_default_path_is_jobs_csv_in_the_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        save_jobs_csv([make_job(title="From Default Path")])

        assert [job.title for job in load_jobs_csv()] == ["From Default Path"]

    def test_a_string_path_works_as_well_as_a_path_object(self, tmp_path):
        save_jobs_csv([make_job()], tmp_path / "jobs.csv")

        assert load_jobs_csv(str(tmp_path / "jobs.csv")) == load_jobs_csv(tmp_path / "jobs.csv")

    @pytest.mark.parametrize("missing", ["title", "company", "location", "description"])
    def test_a_header_without_a_required_column_raises_value_error_naming_it(self, tmp_path, missing):
        columns = [c for c in ["title", "company", "location", "description", "url"] if c != missing]
        text = ",".join(f'"{c}"' for c in columns) + "\r\n" + ",".join('"x"' for _ in columns) + "\r\n"

        with pytest.raises(ValueError) as error:
            load_jobs_csv(write_text(tmp_path / "jobs.csv", text))

        assert reported_columns(error) == [missing]

    def test_every_missing_required_column_is_reported(self, tmp_path):
        with pytest.raises(ValueError) as error:
            load_jobs_csv(write_text(tmp_path / "jobs.csv", '"title","url"\r\n"T","u"\r\n'))

        assert reported_columns(error) == ["company", "location", "description"]

    def test_the_error_names_the_file(self, tmp_path):
        path = write_text(tmp_path / "custom_name.csv", '"foo"\r\n')

        with pytest.raises(ValueError, match="custom_name.csv"):
            load_jobs_csv(path)

    def test_a_file_with_unrelated_columns_is_rejected_rather_than_read_as_empty_jobs(self, tmp_path):
        with pytest.raises(ValueError):
            load_jobs_csv(write_text(tmp_path / "jobs.csv", '"foo","bar"\r\n"1","2"\r\n'))

    def test_a_completely_empty_file_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            load_jobs_csv(write_text(tmp_path / "jobs.csv", ""))

    def test_a_missing_url_column_alone_is_not_an_error(self, tmp_path):
        assert load_jobs_csv(write_text(tmp_path / "jobs.csv", LEGACY_HEADER + "\r\n")) == []
