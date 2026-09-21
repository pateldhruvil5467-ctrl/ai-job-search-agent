"""The Selenium adapter, exercised through a fake WebDriver.

The fake records every driver call, and sleep() is recorded instead of executed, so these tests
pin down the browser mechanics (selector, click/scroll/extract order, pause lengths, where the URL
comes from) with no Chrome, no LinkedIn and no waiting.
"""

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from selenium.webdriver.common.by import By

import browser as browser_module
import linkedin_scraper
from browser import SeleniumJobBrowser

FIXTURES = Path(__file__).parent / "fixtures" / "linkedin"
CARD_HREF = "/jobs/view/3812345678/?eBP=NOT_ELIGIBLE_FOR_CHARGING&refId=abc&trackingId=xyz&trk=flagship3_search_srp_jobs"
JOB_URL = "https://www.linkedin.com/jobs/view/3812345678/"


def fixture_html(name: str) -> str:
    return (FIXTURES / f"job_detail_{name}.html").read_text(encoding="utf-8")


class FakeCard:
    """A job-card link. Reading its href is recorded, like every other browser interaction."""

    def __init__(self, name: str, href: str | None = CARD_HREF, events: list | None = None):
        self.name = name
        self._href = href
        self._events = events if events is not None else []

    def get_attribute(self, attribute: str):
        self._events.append(("get_attribute", attribute))
        return self._href if attribute == "href" else None

    def __repr__(self) -> str:
        return f"FakeCard({self.name})"


class FakeDriver:
    """Records driver calls in order; the JS extraction script returns the next scripted page data."""

    def __init__(self):
        self.cards: list[FakeCard] = []
        self.extractions: list = []
        self.events: list[tuple] = []

    def card(self, name: str, href: str | None = CARD_HREF) -> FakeCard:
        return FakeCard(name, href, self.events)

    def get(self, url):
        self.events.append(("get", url))

    def find_elements(self, by, value):
        self.events.append(("find_elements", by, value))
        return list(self.cards)

    def execute_script(self, script, *args):
        self.events.append(("script", script, args))
        if "const result" not in script:
            return None
        result = self.extractions.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    @property
    def sleeps(self) -> list[float]:
        return [e[1] for e in self.events if e[0] == "sleep"]


@pytest.fixture
def driver(monkeypatch) -> FakeDriver:
    fake = FakeDriver()
    fake_time = SimpleNamespace(sleep=lambda seconds: fake.events.append(("sleep", seconds)))
    monkeypatch.setattr(browser_module, "time", fake_time)
    return fake


def page_data(title: str = "Working Student Software Engineer", company: str = "Acme Logistics GmbH", html: str | None = None) -> dict:
    """What the page JavaScript returns: title and company, plus the page HTML for Python to read."""
    return {"title": title, "company": company, "html": fixture_html("berlin") if html is None else html}


class TestOpenPage:
    def test_loads_the_url_then_pauses_for_five_seconds(self, driver):
        SeleniumJobBrowser(driver).open_page("https://example.test/jobs")

        assert driver.events == [("get", "https://example.test/jobs"), ("sleep", 5)]


class TestFindJobCards:
    def test_looks_up_job_card_links_by_css_selector_and_returns_them(self, driver):
        driver.cards = [driver.card("card-0"), driver.card("card-1"), driver.card("card-2")]

        found = SeleniumJobBrowser(driver).find_job_cards()

        assert driver.events == [("find_elements", By.CSS_SELECTOR, "a.job-card-container__link")]
        assert list(found) == driver.cards

    # Not covered on purpose: with no cards, Selenium's WebDriverWait polls for 20 real seconds
    # before raising TimeoutException, which would slow the suite for no extra insight.


class TestReadJob:
    def test_reads_the_link_then_clicks_scrolls_to_top_then_runs_the_extraction_script_with_pauses(self, driver):
        driver.extractions = [page_data()]
        card = driver.card("card-0")

        SeleniumJobBrowser(driver).read_job(card)

        read_link, click, pause_1, scroll, pause_2, extract = driver.events
        assert read_link == ("get_attribute", "href")
        assert click == ("script", "arguments[0].click();", (card,))
        assert pause_1 == ("sleep", 3)
        assert scroll == ("script", "window.scrollTo(0, 0);", ())
        assert pause_2 == ("sleep", 1)
        kind, script, args = extract
        assert kind == "script"
        assert "const result" in script and "return result;" in script
        assert args == ()

    def test_the_raw_data_combines_the_script_result_the_parsed_page_and_the_card_link(self, driver):
        driver.extractions = [page_data(title="Data Engineer", company="Initech GmbH")]

        raw = SeleniumJobBrowser(driver).read_job(driver.card("card-0"))

        assert raw["title"] == "Data Engineer"
        assert raw["company"] == "Initech GmbH"
        assert raw["location"] == "Berlin, Germany"
        assert raw["description"].startswith("About the role")
        assert raw["description"].endswith("- Available for 15 to 20 hours per week")
        assert raw["url"] == JOB_URL
        assert set(raw) == {"title", "company", "location", "description", "url"}

    def test_the_url_comes_from_the_card_link_without_any_extra_navigation(self, driver):
        driver.extractions = [page_data()]
        card = driver.card("card-0")

        SeleniumJobBrowser(driver).read_job(card)

        assert [e for e in driver.events if e[0] == "get_attribute"] == [("get_attribute", "href")]
        assert not [e for e in driver.events if e[0] == "get"]
        assert len([e for e in driver.events if e[0] == "script"]) == 3  # click, scroll, extraction only

    def test_tracking_parameters_are_not_kept_in_the_url(self, driver):
        driver.extractions = [page_data()]

        raw = SeleniumJobBrowser(driver).read_job(driver.card("card-0"))

        assert "trackingId" not in raw["url"] and "?" not in raw["url"]

    @pytest.mark.parametrize("href", [None, "", "https://www.linkedin.com/company/acme/", "https://example.com/jobs/view/1/"])
    def test_a_card_without_a_usable_job_link_gives_an_empty_url_not_a_guess(self, driver, href):
        driver.extractions = [page_data()]

        raw = SeleniumJobBrowser(driver).read_job(driver.card("card-0", href=href))

        assert raw["url"] == ""

    def test_a_page_without_a_location_gives_no_location_rather_than_a_guess(self, driver):
        driver.extractions = [page_data(html=fixture_html("missing_location"))]

        raw = SeleniumJobBrowser(driver).read_job(driver.card("card-0"))

        assert raw["location"] is None
        assert raw["description"] is not None

    def test_a_remote_filter_elsewhere_on_the_page_does_not_change_the_location(self, driver):
        driver.extractions = [page_data(html=fixture_html("berlin"))]

        raw = SeleniumJobBrowser(driver).read_job(driver.card("card-0"))

        assert raw["location"] == "Berlin, Germany"

    def test_a_script_result_without_page_html_gives_no_location_and_no_description(self, driver):
        driver.extractions = [{"title": "Data Engineer", "company": "Acme"}]

        raw = SeleniumJobBrowser(driver).read_job(driver.card("card-0"))

        assert raw["title"] == "Data Engineer"
        assert raw["location"] is None
        assert raw["description"] is None

    def test_a_driver_error_propagates_so_the_scraper_can_skip_the_card(self, driver):
        driver.extractions = [RuntimeError("stale element")]

        with pytest.raises(RuntimeError, match="stale element"):
            SeleniumJobBrowser(driver).read_job(driver.card("card-0"))


class TestExtractionScript:
    """What the page script still does (title, company) and no longer does (location, description)."""

    @pytest.fixture
    def script(self, driver) -> str:
        driver.extractions = [page_data()]
        SeleniumJobBrowser(driver).read_job(driver.card("card-0"))
        return driver.events[-1][1]

    @pytest.mark.parametrize(
        "retained",
        [
            "h2[data-job-title]",
            ".job-details-jobs-unified-top-card__job-title",
            "a[href*=\"/company/\"]",
            ".job-details-jobs-unified-top-card__company-name",
            "Unknown Title",
            "Unknown Company",
        ],
    )
    def test_the_title_and_company_extraction_is_unchanged(self, script, retained):
        assert retained in script

    def test_it_hands_the_page_html_to_python_for_location_and_description(self, script):
        assert "result.html = document.documentElement.outerHTML;" in script

    @pytest.mark.parametrize(
        "removed",
        [
            "locationPatterns",  # the whole-page "Remote"/"On-site"/"Hybrid" search
            "document.body.innerText",
            "substring(0, 1500)",  # the truncation
            "largestText",  # the page-wide "largest block" fallback
            "show-more-less-html__markup",  # description selection now lives in job_page_parser.py
        ],
    )
    def test_the_old_location_and_description_guesses_are_gone_from_the_script(self, script, removed):
        assert removed not in script


class TestScrapeJobsIncrementallyEntryPoint:
    """scrape_jobs_incrementally(driver, ...) is what main.py calls: it must still drive Selenium."""

    @pytest.fixture(autouse=True)
    def workdir(self, tmp_path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def saved_rows(self, workdir: Path) -> list[dict[str, str]]:
        with open(workdir / "jobs.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_drives_the_browser_and_saves_the_scraped_jobs(self, driver, workdir):
        driver.cards = [driver.card("card-0"), driver.card("card-1"), driver.card("card-2")]
        driver.extractions = [page_data(title="A"), page_data(title="B")]

        result = linkedin_scraper.scrape_jobs_incrementally(
            driver=driver, keyword="Working Student", location="Berlin", max_jobs=2
        )

        assert result is None
        assert driver.events[0] == (
            "get",
            "https://www.linkedin.com/jobs/search/?keywords=Working%20Student&location=Berlin",
        )
        clicked = [e[2][0] for e in driver.events if e[0] == "script" and e[1] == "arguments[0].click();"]
        assert clicked == driver.cards[:2]
        assert driver.sleeps == [5, 3, 1, 3, 1]
        assert [row["title"] for row in self.saved_rows(workdir)] == ["A", "B"]

    def test_url_location_and_description_travel_from_the_page_into_the_csv(self, driver, workdir):
        driver.cards = [
            driver.card("card-0", href=CARD_HREF),
            driver.card("card-1", href="/jobs/view/3800000002/?trackingId=z"),
        ]
        driver.extractions = [
            page_data(title="Backend Engineer", html=fixture_html("berlin")),
            page_data(title="Data Engineer", html=fixture_html("hybrid")),
        ]

        linkedin_scraper.scrape_jobs_incrementally(driver, "kw", "loc", max_jobs=2)

        first, second = self.saved_rows(workdir)
        assert list(first) == ["title", "company", "location", "description", "url"]
        assert first["url"] == JOB_URL
        assert first["location"] == "Berlin, Germany"
        assert "Solid experience with Python and SQL" in first["description"]
        assert second["url"] == "https://www.linkedin.com/jobs/view/3800000002/"
        assert second["location"] == "Berlin, Germany (Hybrid)"

    def test_a_job_without_a_card_link_is_saved_with_an_empty_url(self, driver, workdir):
        driver.cards = [driver.card("card-0", href=None)]
        driver.extractions = [page_data()]

        linkedin_scraper.scrape_jobs_incrementally(driver, "kw", "loc")

        assert self.saved_rows(workdir)[0]["url"] == ""

    def test_a_job_whose_page_has_no_location_is_saved_as_unknown_not_remote(self, driver, workdir):
        driver.cards = [driver.card("card-0")]
        driver.extractions = [page_data(html=fixture_html("missing_location"))]

        linkedin_scraper.scrape_jobs_incrementally(driver, "kw", "loc")

        assert self.saved_rows(workdir)[0]["location"] == "Unknown Location"

    def test_a_card_whose_extraction_fails_is_skipped(self, driver, workdir, capsys):
        driver.cards = [driver.card("card-0"), driver.card("card-1")]
        driver.extractions = [RuntimeError("boom"), page_data(title="B")]

        linkedin_scraper.scrape_jobs_incrementally(driver, "kw", "loc")

        assert [row["title"] for row in self.saved_rows(workdir)] == ["B"]
        assert "Skipped one job: boom" in capsys.readouterr().out
