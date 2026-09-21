"""The Selenium adapter, exercised through a fake WebDriver.

The fake records every driver call, and sleep() is recorded instead of executed, so these tests
pin down the browser mechanics (selector, click/scroll/extract order, pause lengths) with no
Chrome, no LinkedIn and no waiting.
"""

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from selenium.webdriver.common.by import By

import browser as browser_module
import linkedin_scraper
from browser import SeleniumJobBrowser


class FakeDriver:
    """Records driver calls in order; the JS extraction script returns the next scripted result."""

    def __init__(self):
        self.cards: list[str] = []
        self.extractions: list = []
        self.events: list[tuple] = []

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


def raw(**overrides) -> dict:
    data = {"title": "Software Engineer", "company": "Acme", "location": "Berlin", "description": "d"}
    data.update(overrides)
    return data


class TestOpenPage:
    def test_loads_the_url_then_pauses_for_five_seconds(self, driver):
        SeleniumJobBrowser(driver).open_page("https://example.test/jobs")

        assert driver.events == [("get", "https://example.test/jobs"), ("sleep", 5)]


class TestFindJobCards:
    def test_looks_up_job_card_links_by_css_selector_and_returns_them(self, driver):
        driver.cards = ["card-0", "card-1", "card-2"]

        found = SeleniumJobBrowser(driver).find_job_cards()

        assert driver.events == [("find_elements", By.CSS_SELECTOR, "a.job-card-container__link")]
        assert list(found) == ["card-0", "card-1", "card-2"]

    # Not covered on purpose: with no cards, Selenium's WebDriverWait polls for 20 real seconds
    # before raising TimeoutException, which would slow the suite for no extra insight.


class TestReadJob:
    def test_clicks_the_card_scrolls_to_top_then_runs_the_extraction_script_with_pauses(self, driver):
        driver.extractions = [raw()]

        SeleniumJobBrowser(driver).read_job("card-0")

        click, pause_1, scroll, pause_2, extract = driver.events
        assert click == ("script", "arguments[0].click();", ("card-0",))
        assert pause_1 == ("sleep", 3)
        assert scroll == ("script", "window.scrollTo(0, 0);", ())
        assert pause_2 == ("sleep", 1)
        kind, script, args = extract
        assert kind == "script"
        assert "const result" in script and "return result;" in script
        assert args == ()

    def test_returns_exactly_what_the_extraction_script_returned(self, driver):
        scraped = raw(title="Data Engineer")
        driver.extractions = [scraped]

        assert SeleniumJobBrowser(driver).read_job("card-0") is scraped

    def test_a_driver_error_propagates_so_the_scraper_can_skip_the_card(self, driver):
        driver.extractions = [RuntimeError("stale element")]

        with pytest.raises(RuntimeError, match="stale element"):
            SeleniumJobBrowser(driver).read_job("card-0")


class TestScrapeJobsIncrementallyEntryPoint:
    """scrape_jobs_incrementally(driver, ...) is what main.py calls: it must still drive Selenium."""

    @pytest.fixture(autouse=True)
    def workdir(self, tmp_path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def saved_titles(self, workdir: Path) -> list[str]:
        with open(workdir / "jobs.csv", newline="", encoding="utf-8") as f:
            return [row["title"] for row in csv.DictReader(f)]

    def test_drives_the_browser_and_saves_the_scraped_jobs(self, driver, workdir):
        driver.cards = ["card-0", "card-1", "card-2"]
        driver.extractions = [raw(title="A"), raw(title="B")]

        result = linkedin_scraper.scrape_jobs_incrementally(
            driver=driver, keyword="Working Student", location="Berlin", max_jobs=2
        )

        assert result is None
        assert driver.events[0] == (
            "get",
            "https://www.linkedin.com/jobs/search/?keywords=Working%20Student&location=Berlin",
        )
        clicked = [e[2][0] for e in driver.events if e[0] == "script" and e[1] == "arguments[0].click();"]
        assert clicked == ["card-0", "card-1"]
        assert driver.sleeps == [5, 3, 1, 3, 1]
        assert self.saved_titles(workdir) == ["A", "B"]

    def test_a_card_whose_extraction_fails_is_skipped(self, driver, workdir, capsys):
        driver.cards = ["card-0", "card-1"]
        driver.extractions = [RuntimeError("boom"), raw(title="B")]

        linkedin_scraper.scrape_jobs_incrementally(driver, "kw", "loc")

        assert self.saved_titles(workdir) == ["B"]
        assert "Skipped one job: boom" in capsys.readouterr().out
