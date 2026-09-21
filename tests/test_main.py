"""main.py's browser lifecycle: manual login, scraping, and cleanup when something goes wrong.

Importing main starts nothing (no Chrome). run() receives a fake driver and sleep() is recorded
instead of executed, so the 60-second manual-login wait never happens.
"""

from types import SimpleNamespace

import pytest

import main
from config import ScraperConfig
from linkedin_scraper import NoJobsExtractedError

CONFIG = ScraperConfig(keyword="Data Engineer", location="Hamburg", max_jobs=3, login_wait_seconds=7)
LOGGED_IN_URL = "https://www.linkedin.com/feed/"
LOGIN_PAGE_URL = "https://www.linkedin.com/login?session_redirect=%2Ffeed%2F"


class FakeDriver:
    def __init__(self, current_url: str = LOGGED_IN_URL):
        self.current_url = current_url
        self.events: list[tuple] = []

    def get(self, url: str) -> None:
        self.events.append(("get", url))

    def quit(self) -> None:
        self.events.append(("quit",))

    @property
    def quit_calls(self) -> int:
        return self.events.count(("quit",))


@pytest.fixture
def driver(monkeypatch) -> FakeDriver:
    fake = FakeDriver()
    fake_time = SimpleNamespace(sleep=lambda seconds: fake.events.append(("sleep", seconds)))
    monkeypatch.setattr(main, "time", fake_time)
    return fake


@pytest.fixture
def scrape_calls(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(main, "scrape_jobs_incrementally", lambda **kwargs: calls.append(kwargs))
    return calls


class TestSuccessfulRun:
    def test_opens_the_login_page_waits_then_scrapes_with_the_configured_search(
        self, driver, scrape_calls
    ):
        main.run(driver, CONFIG)

        assert driver.events == [("get", "https://www.linkedin.com/login"), ("sleep", 7)]
        assert scrape_calls == [
            {"driver": driver, "keyword": "Data Engineer", "location": "Hamburg", "max_jobs": 3}
        ]

    def test_the_browser_is_left_open_after_a_successful_run(self, driver, scrape_calls):
        main.run(driver, CONFIG)

        assert driver.quit_calls == 0

    def test_reports_login_and_completion(self, driver, scrape_calls, capsys):
        main.run(driver, CONFIG)

        out = capsys.readouterr().out
        assert "Please log in to LinkedIn manually within the next 7 seconds" in out
        assert "Login successful" in out
        assert "Job scraping completed" in out


class TestLoginNotDetected:
    def test_exits_with_status_1_quits_the_browser_once_and_does_not_scrape(
        self, driver, scrape_calls, capsys
    ):
        driver.current_url = LOGIN_PAGE_URL

        with pytest.raises(SystemExit) as exit_info:
            main.run(driver, CONFIG)

        assert exit_info.value.code == 1
        assert driver.quit_calls == 1
        assert scrape_calls == []
        out = capsys.readouterr().out
        assert "Login not detected" in out
        assert "Job scraping completed" not in out


class TestFailuresQuitTheBrowser:
    @pytest.mark.parametrize(
        "error",
        [
            NoJobsExtractedError("no jobs"),
            TimeoutError("no job cards appeared"),
            RuntimeError("unexpected"),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_a_scraping_error_quits_the_browser_once_and_propagates(
        self, driver, monkeypatch, error
    ):
        def failing_scrape(**kwargs):
            raise error

        monkeypatch.setattr(main, "scrape_jobs_incrementally", failing_scrape)

        with pytest.raises(type(error)) as raised:
            main.run(driver, CONFIG)

        assert raised.value is error
        assert driver.quit_calls == 1
        assert driver.events[-1] == ("quit",)

    def test_an_unexpected_error_while_opening_the_login_page_quits_the_browser(
        self, driver, scrape_calls, monkeypatch
    ):
        def failing_get(url):
            raise RuntimeError("browser crashed")

        monkeypatch.setattr(driver, "get", failing_get)

        with pytest.raises(RuntimeError, match="browser crashed"):
            main.run(driver, CONFIG)

        assert driver.quit_calls == 1
        assert scrape_calls == []

    def test_interrupting_the_login_wait_quits_the_browser(self, driver, scrape_calls, monkeypatch):
        def interrupted_sleep(seconds):
            raise KeyboardInterrupt

        monkeypatch.setattr(main, "time", SimpleNamespace(sleep=interrupted_sleep))

        with pytest.raises(KeyboardInterrupt):
            main.run(driver, CONFIG)

        assert driver.quit_calls == 1
        assert scrape_calls == []


class TestMain:
    def test_builds_the_driver_from_the_configuration_and_runs_it(
        self, driver, scrape_calls, monkeypatch
    ):
        created_with = []
        monkeypatch.setattr(main, "get_config", lambda: CONFIG)
        monkeypatch.setattr(main, "create_driver", lambda config: created_with.append(config) or driver)

        main.main()

        assert created_with == [CONFIG]
        assert [call["keyword"] for call in scrape_calls] == ["Data Engineer"]


class TestCreateDriver:
    @pytest.fixture
    def chrome_calls(self, monkeypatch) -> list[dict]:
        calls: list[dict] = []
        monkeypatch.setattr(main.webdriver, "Chrome", lambda **kwargs: calls.append(kwargs) or "driver")
        monkeypatch.setattr(main, "ChromeDriverManager", lambda: SimpleNamespace(install=lambda: "chromedriver-path"))
        return calls

    def test_starts_chrome_maximized_by_default(self, chrome_calls):
        result = main.create_driver(ScraperConfig())

        assert result == "driver"
        assert "--start-maximized" in chrome_calls[0]["options"].arguments
        assert chrome_calls[0]["service"].path == "chromedriver-path"

    def test_maximizing_can_be_switched_off_in_the_configuration(self, chrome_calls):
        main.create_driver(ScraperConfig(start_maximized=False))

        assert "--start-maximized" not in chrome_calls[0]["options"].arguments
