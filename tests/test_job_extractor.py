"""Extraction layer: raw scraped values -> Job. No browser, no Selenium, no LinkedIn."""

import subprocess
import sys
from pathlib import Path

import pytest

from job_extractor import extract_job
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent

FIELDS = ["title", "company", "location", "description", "url"]
DEFAULTS = {
    "title": "Unknown Title",
    "company": "Unknown Company",
    "location": "Unknown Location",
    "description": "No description available",
    "url": "",
}
JOB_URL = "https://www.linkedin.com/jobs/view/3812345678/"


def raw_job(**overrides) -> dict:
    raw = {
        "title": "Software Engineer",
        "company": "Example GmbH",
        "location": "Berlin",
        "description": "Some description",
        "url": JOB_URL,
    }
    raw.update(overrides)
    return raw


class TestValidData:
    def test_valid_scraped_data_becomes_a_job(self):
        job = extract_job(raw_job())

        assert job == Job(
            title="Software Engineer",
            company="Example GmbH",
            location="Berlin",
            description="Some description",
            url=JOB_URL,
        )

    def test_the_url_is_carried_from_the_raw_data_into_the_job(self):
        assert extract_job(raw_job(url=JOB_URL)).url == JOB_URL

    def test_raw_data_without_a_url_still_becomes_a_job_with_an_empty_url(self):
        raw = raw_job()
        del raw["url"]

        assert extract_job(raw).url == ""

    def test_result_is_a_job_instance(self):
        assert isinstance(extract_job(raw_job()), Job)

    def test_input_dict_is_not_mutated(self):
        raw = raw_job(title="  padded  ")
        snapshot = dict(raw)

        extract_job(raw)

        assert raw == snapshot


class TestMissingValues:
    @pytest.mark.parametrize("field", FIELDS)
    def test_a_missing_field_falls_back_to_its_default(self, field):
        raw = raw_job()
        del raw[field]

        job = extract_job(raw)

        assert getattr(job, field) == DEFAULTS[field]

    @pytest.mark.parametrize("field", FIELDS)
    def test_a_missing_field_does_not_affect_the_other_fields(self, field):
        raw = raw_job()
        del raw[field]

        job = extract_job(raw)

        for other in FIELDS:
            if other != field:
                assert getattr(job, other) == raw_job()[other]

    def test_empty_dict_yields_all_defaults(self):
        job = extract_job({})

        assert job == Job(**DEFAULTS)


class TestNoneValues:
    @pytest.mark.parametrize("field", FIELDS)
    def test_none_falls_back_to_the_default(self, field):
        job = extract_job(raw_job(**{field: None}))

        assert getattr(job, field) == DEFAULTS[field]

    def test_all_none_yields_all_defaults(self):
        job = extract_job({field: None for field in FIELDS})

        assert job == Job(**DEFAULTS)


class TestEmptyStrings:
    @pytest.mark.parametrize("field", FIELDS)
    def test_empty_string_falls_back_to_the_default(self, field):
        job = extract_job(raw_job(**{field: ""}))

        assert getattr(job, field) == DEFAULTS[field]

    def test_all_empty_strings_yield_all_defaults(self):
        job = extract_job({field: "" for field in FIELDS})

        assert job == Job(**DEFAULTS)


class TestWhitespaceStripping:
    def test_leading_and_trailing_whitespace_is_stripped_from_every_field(self):
        job = extract_job(
            {
                "title": " Software Engineer ",
                "company": " Example GmbH ",
                "location": " Berlin ",
                "description": " Some description ",
            }
        )

        assert job.title == "Software Engineer"
        assert job.company == "Example GmbH"
        assert job.location == "Berlin"
        assert job.description == "Some description"

    def test_tabs_and_newlines_around_values_are_stripped(self):
        job = extract_job(raw_job(title="\n\tSoftware Engineer\t\n"))

        assert job.title == "Software Engineer"

    def test_internal_whitespace_is_left_alone(self):
        job = extract_job(raw_job(title="Senior   Software  Engineer"))

        assert job.title == "Senior   Software  Engineer"


class TestMultilineDescriptions:
    def test_internal_newlines_and_blank_lines_are_preserved(self):
        description = "Berlin, Germany · 1 week ago\n\nPromoted by hirer · Actively reviewing"

        job = extract_job(raw_job(description=description))

        assert job.description == description

    def test_only_the_outer_whitespace_of_a_multiline_description_is_stripped(self):
        job = extract_job(raw_job(description="\n  line one\n\n  line two  \n"))

        assert job.description == "line one\n\n  line two"


class TestSingleSourceOfTruth:
    @pytest.mark.parametrize(
        "raw",
        [
            raw_job(),
            {},
            {field: None for field in FIELDS},
            raw_job(title="  padded  ", description="a\n\nb"),
        ],
    )
    def test_extract_job_agrees_with_job_from_scraped_data(self, raw):
        assert extract_job(raw) == Job.from_scraped_data(raw)


class TestBrowserIndependence:
    @pytest.mark.parametrize("module", ["job_extractor", "job_storage", "models", "job_page_parser"])
    def test_importing_the_layer_does_not_load_selenium(self, module):
        # Fresh interpreter, so this can't be masked by another test importing selenium.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, {module}; "
                "loaded = sorted(m for m in sys.modules if m == 'selenium' or m.startswith('selenium.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
