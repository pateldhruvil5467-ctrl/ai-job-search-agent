"""Scraper orchestration, exercised through a fake JobBrowser.

No Selenium calls, no Chrome, no LinkedIn, no sleeping. Every test runs in a temp working
directory, so the real storage layer writes a real jobs.csv there and the repository's own
jobs.csv is never touched.
"""

import csv
from pathlib import Path

import pytest

import linkedin_scraper
from linkedin_scraper import NoJobsExtractedError, build_search_url, scrape_jobs
from models import Job

COLUMNS = ["title", "company", "location", "description"]


def raw(**overrides) -> dict:
    data = {
        "title": "Software Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "Some description",
    }
    data.update(overrides)
    return data


class FakeBrowser:
    """Scripted JobBrowser: one entry per card, either raw data to return or an Exception to raise."""

    def __init__(
        self,
        results,
        find_error: Exception | None = None,
        open_error: Exception | None = None,
    ):
        self._results = list(results)
        self._find_error = find_error
        self._open_error = open_error
        self.cards = [f"card-{i}" for i in range(len(self._results))]
        self.events: list[str] = []

    def open_page(self, url: str) -> None:
        self.events.append(f"open {url}")
        if self._open_error is not None:
            raise self._open_error

    def find_job_cards(self):
        self.events.append("find_job_cards")
        if self._find_error is not None:
            raise self._find_error
        return list(self.cards)

    def read_job(self, job_card):
        self.events.append(f"read {job_card}")
        result = self._results[self.cards.index(job_card)]
        if isinstance(result, Exception):
            raise result
        return result

    @property
    def cards_read(self) -> list[str]:
        return [e.split(" ", 1)[1] for e in self.events if e.startswith("read ")]


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def saved_rows(workdir: Path) -> list[dict[str, str]]:
    with open(workdir / "jobs.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def saved_titles(workdir: Path) -> list[str]:
    return [row["title"] for row in saved_rows(workdir)]


class TestNavigation:
    def test_opens_the_linkedin_jobs_search_for_the_keyword_and_location(self):
        browser = FakeBrowser([raw()])

        scrape_jobs(browser, "Working Student Software Engineer", "Berlin")

        assert browser.events[0] == (
            "open https://www.linkedin.com/jobs/search/"
            "?keywords=Working%20Student%20Software%20Engineer&location=Berlin"
        )

    def test_keyword_and_location_are_url_encoded(self):
        url = build_search_url("C++ & Data", "München")

        assert url == (
            "https://www.linkedin.com/jobs/search/"
            "?keywords=C%2B%2B%20%26%20Data&location=M%C3%BCnchen"
        )

    def test_page_is_opened_then_cards_are_found_then_cards_are_read(self):
        browser = FakeBrowser([raw()])

        scrape_jobs(browser, "kw", "loc")

        assert [e.split(" ")[0] for e in browser.events] == ["open", "find_job_cards", "read"]


class TestMaxJobs:
    @pytest.mark.parametrize(
        "cards_available, max_jobs, expected_reads",
        [
            (5, 5, 5),  # exactly as many cards as max_jobs
            (3, 5, 3),  # fewer cards than max_jobs
            (8, 5, 5),  # more cards than max_jobs
            (4, 2, 2),
            (1, 1, 1),
        ],
    )
    def test_at_most_max_jobs_cards_are_read_in_page_order(
        self, workdir, cards_available, max_jobs, expected_reads
    ):
        browser = FakeBrowser([raw(title=f"Job {i}") for i in range(cards_available)])

        scrape_jobs(browser, "kw", "loc", max_jobs=max_jobs)

        assert browser.cards_read == [f"card-{i}" for i in range(expected_reads)]
        assert saved_titles(workdir) == [f"Job {i}" for i in range(expected_reads)]

    def test_max_jobs_defaults_to_five(self, workdir):
        browser = FakeBrowser([raw(title=f"Job {i}") for i in range(7)])

        scrape_jobs(browser, "kw", "loc")

        assert len(browser.cards_read) == 5

    def test_max_jobs_limits_the_cards_attempted_not_the_jobs_saved(self, workdir):
        # A failed card is not replaced by the next one, so fewer than max_jobs jobs can be saved.
        browser = FakeBrowser(
            [raw(title="A"), RuntimeError("boom"), raw(title="C"), raw(title="D"), raw(title="E")]
        )

        scrape_jobs(browser, "kw", "loc", max_jobs=3)

        assert browser.cards_read == ["card-0", "card-1", "card-2"]
        assert saved_titles(workdir) == ["A", "C"]


class TestSuccessfulScrape:
    def test_scraped_jobs_are_saved_in_card_order_with_sanitized_values(self, workdir):
        browser = FakeBrowser(
            [
                raw(title="  Backend Engineer ", company=" Acme ", location=" Remote ", description=" First "),
                raw(title="Data Engineer", company="Globex", location="Berlin", description="Second"),
            ]
        )

        scrape_jobs(browser, "kw", "loc")

        assert saved_rows(workdir) == [
            {"title": "Backend Engineer", "company": "Acme", "location": "Remote", "description": "First"},
            {"title": "Data Engineer", "company": "Globex", "location": "Berlin", "description": "Second"},
        ]

    def test_csv_has_the_expected_columns(self, workdir):
        scrape_jobs(FakeBrowser([raw()]), "kw", "loc")

        assert list(saved_rows(workdir)[0].keys()) == COLUMNS

    def test_returns_nothing(self):
        assert scrape_jobs(FakeBrowser([raw()]), "kw", "loc") is None

    def test_each_raw_result_from_the_browser_is_passed_to_extract_job(self, monkeypatch):
        raws = [raw(title="A"), raw(title="B")]
        seen = []
        real_extract_job = linkedin_scraper.extract_job

        def spy(raw_job):
            seen.append(raw_job)
            return real_extract_job(raw_job)

        monkeypatch.setattr(linkedin_scraper, "extract_job", spy)

        scrape_jobs(FakeBrowser(raws), "kw", "loc")

        assert len(seen) == 2
        assert seen[0] is raws[0]
        assert seen[1] is raws[1]

    def test_the_extracted_jobs_are_handed_to_storage_in_order(self, monkeypatch):
        handed_over = []
        real_save = linkedin_scraper.save_jobs_csv

        def spy(jobs):
            handed_over.append(list(jobs))
            return real_save(jobs)

        monkeypatch.setattr(linkedin_scraper, "save_jobs_csv", spy)

        scrape_jobs(FakeBrowser([raw(title="A"), raw(title="B", company="Globex")]), "kw", "loc")

        assert handed_over == [
            [
                Job("A", "Acme", "Berlin", "Some description"),
                Job("B", "Globex", "Berlin", "Some description"),
            ]
        ]

    def test_progress_is_reported_for_each_job_and_for_the_total(self, capsys):
        scrape_jobs(FakeBrowser([raw(title="A"), raw(title="B", company="Globex")]), "kw", "loc")

        out = capsys.readouterr().out
        assert "Saved: A @ Acme" in out
        assert "Saved: B @ Globex" in out
        assert "Total jobs saved: 2" in out


class TestSkippedCards:
    def test_a_failing_card_is_skipped_and_scraping_continues(self, workdir, capsys):
        browser = FakeBrowser([raw(title="A"), RuntimeError("boom"), raw(title="C")])

        scrape_jobs(browser, "kw", "loc")

        assert saved_titles(workdir) == ["A", "C"]
        assert browser.cards_read == ["card-0", "card-1", "card-2"]
        assert "Skipped one job: boom" in capsys.readouterr().out

    def test_several_failing_cards_are_each_skipped(self, workdir, capsys):
        browser = FakeBrowser(
            [RuntimeError("one"), raw(title="B"), RuntimeError("two"), RuntimeError("three"), raw(title="E")]
        )

        scrape_jobs(browser, "kw", "loc")

        out = capsys.readouterr().out
        assert saved_titles(workdir) == ["B", "E"]
        assert out.count("Skipped one job") == 3
        assert "Total jobs saved: 2" in out

    def test_the_skip_message_shows_at_most_the_first_80_characters_of_the_error(self, capsys):
        scrape_jobs(FakeBrowser([RuntimeError("x" * 200), raw()]), "kw", "loc")

        out = capsys.readouterr().out
        assert "Skipped one job: " + "x" * 80 in out
        assert "x" * 81 not in out

    @pytest.mark.parametrize(
        "error", [ValueError("bad"), KeyError("missing"), TimeoutError("slow"), Exception("generic")]
    )
    def test_any_ordinary_exception_from_the_browser_skips_the_card(self, workdir, capsys, error):
        scrape_jobs(FakeBrowser([error, raw(title="Survivor")]), "kw", "loc")

        assert saved_titles(workdir) == ["Survivor"]
        assert "Skipped one job" in capsys.readouterr().out

    def test_a_card_that_yields_no_data_at_all_is_skipped(self, workdir, capsys):
        scrape_jobs(FakeBrowser([None, raw(title="B")]), "kw", "loc")

        assert saved_titles(workdir) == ["B"]
        assert "Skipped one job" in capsys.readouterr().out


class TestIncompleteData:
    def test_missing_optional_values_are_saved_with_their_defaults(self, workdir):
        browser = FakeBrowser(
            [
                raw(title="Real Job", company="Real Co", location=None, description=None),
                {"title": "Sparse", "company": "Sparse Co"},
            ]
        )

        scrape_jobs(browser, "kw", "loc")

        assert saved_rows(workdir) == [
            {
                "title": "Real Job",
                "company": "Real Co",
                "location": "Unknown Location",
                "description": "No description available",
            },
            {
                "title": "Sparse",
                "company": "Sparse Co",
                "location": "Unknown Location",
                "description": "No description available",
            },
        ]

    def test_a_job_without_title_or_company_is_reported_as_saved_but_dropped_from_the_csv(
        self, workdir, capsys
    ):
        # Current behavior: the per-job progress line is printed as soon as the Job exists;
        # the "Unknown" filter only runs later, inside storage.
        blank = {"title": None, "company": None, "location": None, "description": None}

        scrape_jobs(FakeBrowser([blank, raw(title="B")]), "kw", "loc")

        out = capsys.readouterr().out
        assert "Saved: Unknown Title @ Unknown Company" in out
        assert saved_titles(workdir) == ["B"]
        assert "Total jobs saved: 1" in out

    @pytest.mark.parametrize(
        "incomplete", [raw(title=None), raw(company=None), raw(title=""), raw(company="")]
    )
    def test_a_job_missing_its_title_or_company_never_reaches_the_csv(self, workdir, incomplete):
        scrape_jobs(FakeBrowser([incomplete, raw(title="Keeper")]), "kw", "loc")

        assert saved_titles(workdir) == ["Keeper"]

    def test_when_every_job_is_unknown_the_csv_is_written_with_only_its_header(self, workdir, capsys):
        blank = {"title": None, "company": None, "location": None, "description": None}

        scrape_jobs(FakeBrowser([blank, blank]), "kw", "loc")

        assert (workdir / "jobs.csv").read_text(encoding="utf-8").strip() == '"title","company","location","description"'
        assert "Total jobs saved: 0" in capsys.readouterr().out


class TestZeroJobsExtracted:
    """When not a single job can be extracted the scrape fails loudly and clearly.

    This used to surface as a cryptic KeyError('title') from the storage layer. Both the loud
    failure and the untouched jobs.csv are unchanged; only the error is now explicit.
    (Different from "every job is Unknown", which still writes a header-only CSV; see above.)
    """

    @pytest.mark.parametrize(
        "results, max_jobs, cards_attempted",
        [
            pytest.param([], 5, 0, id="no-cards-found"),
            pytest.param([RuntimeError("a"), RuntimeError("b")], 5, 2, id="every-card-fails"),
            pytest.param([raw(), raw()], 0, 0, id="max-jobs-is-zero"),
        ],
    )
    def test_raises_a_clear_error_naming_how_many_cards_were_tried(
        self, workdir, results, max_jobs, cards_attempted
    ):
        expected = rf"from {cards_attempted} job card\(s\); jobs\.csv was not updated"

        with pytest.raises(NoJobsExtractedError, match=expected):
            scrape_jobs(FakeBrowser(results), "kw", "loc", max_jobs=max_jobs)

        assert not (workdir / "jobs.csv").exists()

    def test_a_previous_jobs_csv_is_not_overwritten(self, workdir):
        previous = '"title","company","location","description"\n"Old","Old Co","Remote","kept"\n'
        (workdir / "jobs.csv").write_text(previous, encoding="utf-8")

        with pytest.raises(NoJobsExtractedError):
            scrape_jobs(FakeBrowser([RuntimeError("boom")]), "kw", "loc")

        assert (workdir / "jobs.csv").read_text(encoding="utf-8") == previous

    def test_storage_is_not_called(self, monkeypatch):
        def storage_must_not_run(jobs):
            raise AssertionError("save_jobs_csv must not be called when there are no jobs")

        monkeypatch.setattr(linkedin_scraper, "save_jobs_csv", storage_must_not_run)

        with pytest.raises(NoJobsExtractedError):
            scrape_jobs(FakeBrowser([RuntimeError("boom")]), "kw", "loc")


class TestPageLevelFailures:
    """Failures outside the per-card loop are not skipped: they abort the scrape."""

    def test_failure_to_open_the_page_propagates_and_nothing_is_read_or_saved(self, workdir):
        browser = FakeBrowser([raw()], open_error=ConnectionError("network unreachable"))

        with pytest.raises(ConnectionError, match="network unreachable"):
            scrape_jobs(browser, "kw", "loc")

        assert "find_job_cards" not in browser.events
        assert browser.cards_read == []
        assert not (workdir / "jobs.csv").exists()

    def test_failure_to_find_cards_propagates_and_nothing_is_read_or_saved(self, workdir):
        browser = FakeBrowser([raw()], find_error=TimeoutError("no job cards appeared"))

        with pytest.raises(TimeoutError, match="no job cards appeared"):
            scrape_jobs(browser, "kw", "loc")

        assert browser.cards_read == []
        assert not (workdir / "jobs.csv").exists()


class TestStorageFailure:
    def test_a_storage_error_propagates_and_is_not_mistaken_for_a_skipped_card(
        self, monkeypatch, capsys
    ):
        def failing_save(jobs):
            raise PermissionError("jobs.csv is open in another program")

        monkeypatch.setattr(linkedin_scraper, "save_jobs_csv", failing_save)
        browser = FakeBrowser([raw(title="A"), raw(title="B")])

        with pytest.raises(PermissionError, match="open in another program"):
            scrape_jobs(browser, "kw", "loc")

        out = capsys.readouterr().out
        assert browser.cards_read == ["card-0", "card-1"]
        assert "Skipped one job" not in out
        assert "Total jobs saved" not in out
