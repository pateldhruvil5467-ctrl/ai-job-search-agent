import dataclasses
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from job_page_parser import canonical_job_url
from models import Job, job_key

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_job(**overrides) -> Job:
    fields = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "Great role",
    }
    fields.update(overrides)
    return Job(**fields)


class TestConstruction:
    def test_holds_the_given_values(self):
        job = make_job()

        assert job.title == "Software Engineer"
        assert job.company == "Acme"
        assert job.location == "Berlin"
        assert job.description == "Great role"

    def test_jobs_with_equal_fields_are_equal(self):
        assert make_job() == make_job()
        assert make_job() != make_job(company="Other")

    def test_field_order_matches_csv_column_contract(self):
        # The scraper turns Jobs into DataFrame rows via dataclasses.asdict, so
        # field order is the column order of jobs.csv. url was appended at the end so the
        # original four columns keep their positions.
        assert list(dataclasses.asdict(make_job())) == [
            "title",
            "company",
            "location",
            "description",
            "url",
        ]


class TestUrl:
    URL = "https://www.linkedin.com/jobs/view/3812345678/"

    def test_holds_the_given_url(self):
        assert make_job(url=self.URL).url == self.URL

    def test_a_job_built_without_a_url_has_an_empty_one(self):
        # Backward compatible: the original four-argument construction still works.
        job = Job("Software Engineer", "Acme", "Berlin", "Great role")

        assert job.url == ""

    def test_the_url_takes_part_in_equality(self):
        assert make_job(url=self.URL) == make_job(url=self.URL)
        assert make_job(url=self.URL) != make_job()


class TestFromScrapedData:
    def test_maps_a_complete_scraped_dict(self):
        job = Job.from_scraped_data(
            {
                "title": "Working Student",
                "company": "Scalable Capital",
                "location": "Remote",
                "description": "Berlin, Germany",
            }
        )

        assert job == Job(
            title="Working Student",
            company="Scalable Capital",
            location="Remote",
            description="Berlin, Germany",
        )

    def test_strips_surrounding_whitespace(self):
        job = Job.from_scraped_data(
            {
                "title": "  Engineer \n",
                "company": "\tAcme  ",
                "location": " Remote ",
                "description": "\n text \n",
            }
        )

        assert job.title == "Engineer"
        assert job.company == "Acme"
        assert job.location == "Remote"
        assert job.description == "text"

    def test_preserves_multiline_description_content(self):
        description = "Berlin, Germany · 1 week ago\n\nPromoted by hirer"

        job = Job.from_scraped_data({"title": "t", "company": "c", "description": description})

        assert job.description == description

    def test_coerces_non_string_values_to_text(self):
        job = Job.from_scraped_data({"title": 42, "company": "c", "location": "l", "description": "d"})

        assert job.title == "42"

    @pytest.mark.parametrize("missing_value", [None, ""])
    def test_falsy_values_fall_back_to_defaults(self, missing_value):
        job = Job.from_scraped_data(
            {
                "title": missing_value,
                "company": missing_value,
                "location": missing_value,
                "description": missing_value,
            }
        )

        assert job == Job(
            title="Unknown Title",
            company="Unknown Company",
            location="Unknown Location",
            description="No description available",
        )

    def test_missing_keys_fall_back_to_defaults(self):
        job = Job.from_scraped_data({})

        assert job.title == "Unknown Title"
        assert job.company == "Unknown Company"
        assert job.location == "Unknown Location"
        assert job.description == "No description available"

    def test_ignores_unrelated_keys(self):
        job = Job.from_scraped_data(
            {"title": "t", "company": "c", "location": "l", "description": "d", "extra": "x"}
        )

        assert job == Job(title="t", company="c", location="l", description="d")

    def test_maps_the_url(self):
        url = "https://www.linkedin.com/jobs/view/3812345678/"

        job = Job.from_scraped_data({"title": "t", "company": "c", "url": url})

        assert job.url == url

    def test_strips_whitespace_around_the_url(self):
        job = Job.from_scraped_data({"url": "  https://www.linkedin.com/jobs/view/1/\n"})

        assert job.url == "https://www.linkedin.com/jobs/view/1/"

    @pytest.mark.parametrize("missing", [None, "", "   "])
    def test_a_missing_url_is_an_empty_string_not_a_placeholder(self, missing):
        assert Job.from_scraped_data({"url": missing}).url == ""

    def test_a_dict_without_a_url_key_gives_an_empty_url(self):
        assert Job.from_scraped_data({"title": "t"}).url == ""


class TestImmutability:
    @pytest.mark.parametrize("field", ["title", "company", "location", "description", "url"])
    def test_fields_cannot_be_reassigned(self, field):
        job = make_job()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(job, field, "changed")

    def test_jobs_are_hashable_value_objects(self):
        assert len({make_job(), make_job()}) == 1


class TestJobKeyFromLinkedInId:
    ID = "3812345678"
    KEY = "linkedin:3812345678"

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.linkedin.com/jobs/view/3812345678/",
            "https://www.linkedin.com/jobs/view/3812345678",
            "http://www.linkedin.com/jobs/view/3812345678/",
            "HTTPS://WWW.LINKEDIN.COM/jobs/view/3812345678/",
            "https://linkedin.com/jobs/view/3812345678/",
            "https://de.linkedin.com/jobs/view/3812345678/",
            "https://www.linkedin.com/jobs/view/3812345678/?trackingId=abc",
            "https://www.linkedin.com/jobs/view/3812345678/#top",
            "https://www.linkedin.com/jobs/view/3812345678/?trk=x#top",
            "https://www.linkedin.com/jobs/view/3812345678?eBP=NOT_ELIGIBLE&refId=Zb3%2Fq1w%3D%3D&trackingId=Ab12&trk=flagship3_search_srp_jobs",
            "  https://www.linkedin.com/jobs/view/3812345678/  ",
        ],
    )
    def test_the_numeric_job_id_is_taken_from_the_url(self, url):
        assert job_key(make_job(url=url)) == self.KEY

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.linkedin.com/jobs/view/software-engineer-at-acme-3812345678/",
            "https://www.linkedin.com/jobs/view/software-engineer-at-acme-3812345678",
            "https://www.linkedin.com/jobs/view/software-engineer-at-acme-3812345678/?trk=public_jobs",
            "https://de.linkedin.com/jobs/view/werkstudent-m-w-d-bei-acme-gmbh-3812345678?position=1&pageNum=0",
        ],
    )
    def test_slugged_urls_give_the_same_id_as_the_plain_url(self, url):
        assert job_key(make_job(url=url)) == self.KEY

    def test_a_20_plus_digit_id_is_still_accepted_because_the_id_is_text_not_an_integer(self):
        digits = "9" * 25
        assert job_key(make_job(url=f"https://www.linkedin.com/jobs/view/{digits}/")) == f"linkedin:{digits}"

    def test_the_key_has_the_linkedin_prefix_and_only_digits(self):
        assert re.fullmatch(r"linkedin:[0-9]+", job_key(make_job(url="https://www.linkedin.com/jobs/view/4457758762/")))

    def test_leading_zeros_are_kept_because_the_id_is_text(self):
        assert job_key(make_job(url="https://www.linkedin.com/jobs/view/0012345/")) == "linkedin:0012345"

    def test_different_ids_give_different_keys(self):
        first = make_job(url="https://www.linkedin.com/jobs/view/4457758762/")
        second = make_job(url="https://www.linkedin.com/jobs/view/4444078765/")

        assert job_key(first) != job_key(second)

    def test_the_id_wins_over_everything_else_on_the_job(self):
        one = Job("Title A", "Company A", "Berlin", "Description A", "https://www.linkedin.com/jobs/view/3812345678/")
        other = Job("Title B", "Company B", "Munich", "Description B", "https://www.linkedin.com/jobs/view/3812345678/?trk=x")

        assert job_key(one) == job_key(other) == self.KEY

    def test_the_same_title_and_company_with_different_ids_are_different_jobs(self):
        first = make_job(url="https://www.linkedin.com/jobs/view/1000001/")
        second = make_job(url="https://www.linkedin.com/jobs/view/1000002/")

        assert job_key(first) != job_key(second)

    @pytest.mark.parametrize(
        "href",
        [
            "/jobs/view/3812345678/?eBP=NOT_ELIGIBLE_FOR_CHARGING&refId=abc&trackingId=xyz&trk=flagship3_search_srp_jobs",
            "https://www.linkedin.com/jobs/view/3812345678/?trackingId=abc#section",
            "https://de.linkedin.com/jobs/view/software-engineer-at-acme-3812345678?trk=x",
        ],
    )
    def test_a_url_produced_by_the_scraper_always_yields_an_id_key(self, href):
        # job_key carries its own small copy of the URL shape; this ties it to canonical_job_url.
        assert job_key(make_job(url=canonical_job_url(href))) == self.KEY


class TestJobKeyFallback:
    GOLDEN = "tc:5adbeede98a0bbc0"  # sha256("working student software engineer" + US + "acme gmbh")[:16]

    UNUSABLE_URLS = [
        "",
        "   ",
        "not a url",
        "/jobs/view/3812345678/",  # relative: no host to trust
        "www.linkedin.com/jobs/view/3812345678/",  # no scheme
        "https://example.com/jobs/view/3812345678/",
        "https://notlinkedin.com/jobs/view/3812345678/",
        "https://linkedin.com.evil.test/jobs/view/3812345678/",
        "https://www.linkedin.com/company/acme/",
        "https://www.linkedin.com/jobs/view/",
        "https://www.linkedin.com/jobs/view/abc/",
        "https://www.linkedin.com/jobs/view/software-engineer-at-acme/",
        "https://www.linkedin.com/jobs/view/3812345678/apply/",
        "https://www.linkedin.com/jobs/search/?currentJobId=3812345678",
        "https://www.linkedin.com/jobs/collections/recommended/?jobs/view/3812345678/",
        "https://www.linkedin.com/jobs/view/٣٨١/",  # non-ASCII digits are not an id
        "http://[::1",  # not even a valid URL
        "javascript:void(0)",
    ]

    @staticmethod
    def job(title="Working Student Software Engineer", company="Acme GmbH", **overrides):
        return make_job(title=title, company=company, **overrides)

    def test_a_job_without_a_url_uses_the_title_and_company_hash(self):
        assert job_key(self.job()) == self.GOLDEN

    def test_the_hash_value_is_pinned_so_the_algorithm_cannot_drift_unnoticed(self):
        assert job_key(Job("Developer Relations", "OrcaRouter.ai", "x", "y")) == "tc:ef95516114f53a73"
        assert job_key(Job("", "", "", "")) == "tc:ffe679bb831c95b6"

    def test_the_key_is_tc_followed_by_16_lowercase_hex_characters(self):
        assert re.fullmatch(r"tc:[0-9a-f]{16}", job_key(self.job()))

    @pytest.mark.parametrize("url", UNUSABLE_URLS)
    def test_an_empty_or_unusable_url_falls_back_to_title_and_company(self, url):
        assert job_key(self.job(url=url)) == self.GOLDEN

    @pytest.mark.parametrize("seed", ["0", "1", "12345"])
    def test_the_key_does_not_depend_on_python_hash_randomization(self, seed):
        code = "from models import Job, job_key; print(job_key(Job('Working Student Software Engineer', 'Acme GmbH', 'x', 'y')))"

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == self.GOLDEN

    def test_the_same_job_always_gives_the_same_key(self):
        assert job_key(self.job()) == job_key(self.job())

    @pytest.mark.parametrize(
        "title, company",
        [
            ("WORKING STUDENT SOFTWARE ENGINEER", "ACME GMBH"),
            ("working student software engineer", "acme gmbh"),
            ("  Working   Student\tSoftware\nEngineer  ", " Acme  GmbH "),
            ("Working Student Software Engineer", "Acme  GmbH"),
        ],
        ids=["upper-case", "lower-case", "whitespace", "inner-spaces"],
    )
    def test_case_and_whitespace_do_not_change_the_key(self, title, company):
        assert job_key(self.job(title=title, company=company)) == self.GOLDEN

    def test_unicode_compatibility_forms_are_normalized(self):
        fullwidth = job_key(self.job(title="Ｗorking Ｓtudent Software Engineer", company="Ａcme GmbH"))

        assert fullwidth == self.GOLDEN

    @pytest.mark.parametrize(
        "composed, decomposed",
        [("Müller GmbH", "Müller GmbH"), ("Café AG", "Café AG")],
    )
    def test_composed_and_decomposed_accents_give_the_same_key(self, composed, decomposed):
        assert job_key(self.job(company=composed)) == job_key(self.job(company=decomposed))

    def test_case_folding_handles_german_sharp_s(self):
        assert job_key(self.job(company="Straße GmbH")) == job_key(self.job(company="STRASSE GmbH"))

    def test_a_ligature_is_folded_by_compatibility_normalization(self):
        assert job_key(self.job(title="ﬁrmware Engineer")) == job_key(self.job(title="firmware Engineer"))

    def test_a_different_title_or_company_gives_a_different_key(self):
        assert job_key(self.job(title="Data Engineer")) != self.GOLDEN
        assert job_key(self.job(company="Globex")) != self.GOLDEN

    def test_title_and_company_are_not_interchangeable_or_blurred_together(self):
        assert job_key(Job("ab", "c", "x", "y")) != job_key(Job("a", "bc", "x", "y"))
        assert job_key(Job("a", "b", "x", "y")) != job_key(Job("b", "a", "x", "y"))

    def test_location_and_description_do_not_take_part(self):
        base = self.job()
        moved = self.job(location="Munich, Germany (Hybrid)", description="A completely different, much longer description.")

        assert job_key(moved) == job_key(base) == self.GOLDEN

    def test_the_url_query_string_does_not_take_part_in_the_fallback(self):
        assert job_key(self.job(url="https://example.com/?a=1")) == job_key(self.job(url="https://example.com/?a=2"))

    def test_id_keys_and_fallback_keys_can_never_be_confused(self):
        assert job_key(self.job(url="https://www.linkedin.com/jobs/view/1/")).startswith("linkedin:")
        assert job_key(self.job()).startswith("tc:")


class TestJobKeyNeverRaises:
    @pytest.mark.parametrize(
        "title, company, url",
        [
            ("", "", ""),
            ("   ", "\t\n", "   "),
            ("\x00", "\x00\x01\x02", "\x00"),
            ("\ud800", "\udfff", "\ud800"),  # lone surrogates
            ("\U0001f680 Rocket", "C, Inc \U0001f9d1‍\U0001f4bb", ""),
            ("x" * 1_000_000, "y" * 1_000_000, "z" * 100_000),
            ("Title", "Company", "http://[::1"),
            ("Title", "Company", "http://["),
            ("Title", "Company", "://"),
            ("Title", "Company", "%%%"),
            ("Title", "Company", "https://www.linkedin.com:notaport/jobs/view/123/"),
            ("Title", "Company", "https://www.linkedin.com/jobs/view/" + "9" * 5000 + "/"),
        ],
        ids=["empty", "whitespace", "control-chars", "surrogates", "emoji", "huge", "bad-ipv6", "open-bracket", "no-host", "percent", "bad-port", "huge-id"],
    )
    def test_unusual_text_still_gives_a_key(self, title, company, url):
        key = job_key(Job(title, company, "Berlin", "d", url))

        assert re.fullmatch(r"(linkedin:[0-9]+|tc:[0-9a-f]{16})", key)

    @pytest.mark.parametrize("value", [None, 0, 12345, 1.5, b"bytes", ["list"], ("tuple",)])
    def test_values_that_are_not_text_still_give_a_key(self, value):
        job = Job(value, value, value, value, value)

        assert re.fullmatch(r"tc:[0-9a-f]{16}", job_key(job))

    def test_none_is_treated_as_empty_text(self):
        assert job_key(Job(None, None, "x", "y", None)) == job_key(Job("", "", "x", "y", ""))


class TestJobKeyIsNotPartOfTheJob:
    def test_job_has_exactly_the_original_five_fields(self):
        assert [f.name for f in dataclasses.fields(Job)] == ["title", "company", "location", "description", "url"]

    def test_the_key_is_not_a_field_property_or_csv_column(self):
        assert not hasattr(Job, "key")
        assert "key" not in dataclasses.asdict(make_job())
