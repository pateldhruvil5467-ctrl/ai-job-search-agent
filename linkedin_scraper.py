from selenium.webdriver.remote.webdriver import WebDriver
import urllib.parse

from browser import JobBrowser, SeleniumJobBrowser
from job_extractor import extract_job
from job_storage import save_jobs_csv
from models import Job


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
    """Scrape job cards through any JobBrowser and save the results to jobs.csv."""
    print("🚀 SCRAPER FUNCTION STARTED")

    # ---------- Navigate explicitly to Jobs search ----------
    keyword_encoded = urllib.parse.quote(keyword)
    location_encoded = urllib.parse.quote(location)

    search_url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={keyword_encoded}&location={location_encoded}"
    )

    print("🌍 Navigating to LinkedIn Jobs search page...")
    browser.open_page(search_url)

    # ---------- Wait for job cards to load ----------
    print("👀 Waiting for job cards...")
    job_cards = browser.find_job_cards()

    print(f"🧩 Found {len(job_cards)} visible job cards")

    jobs: list[Job] = []

    for index, job_card in enumerate(job_cards[:max_jobs]):
        try:
            print(f"➡️ Opening job {index + 1}")
            raw_job = browser.read_job(job_card)

            # Map raw extracted values into the Job domain model
            job = extract_job(raw_job)
            jobs.append(job)

            print(f"✅ Saved: {job.title} @ {job.company}")

        except Exception as e:
            print(f"⚠️ Skipped one job: {str(e)[:80]}")
            continue

    df = save_jobs_csv(jobs)

    print("📁 jobs.csv updated with real data")
    print(f"✅ Total jobs saved: {len(df)}")
    print("\n📊 Sample data:")
    print(df.head().to_string(index=False))
