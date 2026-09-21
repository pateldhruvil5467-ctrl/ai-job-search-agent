from selenium.webdriver.remote.webdriver import WebDriver
from typing import Sequence
import urllib.parse

from browser import JobBrowser, JobCard, SeleniumJobBrowser
from job_extractor import extract_job
from job_storage import save_jobs_csv
from models import Job


class NoJobsExtractedError(Exception):
    """No job could be extracted from the job cards that were read; jobs.csv was left untouched."""


def scrape_jobs_incrementally(
    driver: WebDriver, keyword: str, location: str, max_jobs: int = 5
) -> None:
    """
    Scrapes LinkedIn job listings with robust error handling and multiple fallback selectors.
    
    Key improvements:
    - JavaScript-based extraction for better DOM access
    - Multiple selector strategies for resilience to LinkedIn layout changes
    - Better error handling and data validation
    - Fallback extraction methods when primary selectors fail
    """
    scrape_jobs(SeleniumJobBrowser(driver), keyword, location, max_jobs)


def scrape_jobs(
    browser: JobBrowser, keyword: str, location: str, max_jobs: int = 5
) -> None:
    """Scrape job cards through any JobBrowser and save the results to jobs.csv.

    Raises NoJobsExtractedError, leaving jobs.csv untouched, if no job could be extracted.
    """
    print("🚀 SCRAPER FUNCTION STARTED")

    # ---------- Navigate explicitly to Jobs search ----------
    search_url = build_search_url(keyword, location)

    print("🌍 Navigating to LinkedIn Jobs search page...")
    browser.open_page(search_url)

    # ---------- Wait for job cards to load ----------
    print("👀 Waiting for job cards...")
    job_cards = browser.find_job_cards()

    print(f"🧩 Found {len(job_cards)} visible job cards")

    cards_to_read = job_cards[:max_jobs]
    jobs = _collect_jobs(browser, cards_to_read)
    if not jobs:
        raise NoJobsExtractedError(
            f"No jobs could be extracted from {len(cards_to_read)} job card(s); "
            "jobs.csv was not updated."
        )

    df = save_jobs_csv(jobs)

    print("📁 jobs.csv updated with real data")
    print(f"✅ Total jobs saved: {len(df)}")
    print("\n📊 Sample data:")
    print(df.head().to_string(index=False))


def build_search_url(keyword: str, location: str) -> str:
    keyword_encoded = urllib.parse.quote(keyword)
    location_encoded = urllib.parse.quote(location)

    return (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={keyword_encoded}&location={location_encoded}"
    )


def _collect_jobs(browser: JobBrowser, job_cards: Sequence[JobCard]) -> list[Job]:
    """Read each card into a Job; a card that fails is skipped without affecting the others."""
    jobs: list[Job] = []

    for index, job_card in enumerate(job_cards):
        print(f"➡️ Opening job {index + 1}")
        try:
            raw_job = browser.read_job(job_card)
            job = extract_job(raw_job)
        except Exception as e:
            print(f"⚠️ Skipped one job: {str(e)[:80]}")
            continue

        jobs.append(job)
        print(f"✅ Saved: {job.title} @ {job.company}")

    return jobs
