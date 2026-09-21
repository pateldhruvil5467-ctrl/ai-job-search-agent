import dataclasses

import pytest

from models import Job


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
