from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
import time
import sys

from linkedin_scraper import scrape_jobs_incrementally
from config import ScraperConfig, get_config


def create_driver(config: ScraperConfig) -> WebDriver:
    options = webdriver.ChromeOptions()
    if config.start_maximized:
        options.add_argument("--start-maximized")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )


def wait_for_manual_login(driver: WebDriver, config: ScraperConfig) -> None:
    driver.get("https://www.linkedin.com/login")
    print(f"🔐 Please log in to LinkedIn manually within the next {config.login_wait_seconds} seconds...")
    time.sleep(config.login_wait_seconds)

    # ---------- Verify login ----------
    if "login" in driver.current_url:
        print("❌ Login not detected. Please try again.")
        sys.exit(1)

    print("✅ Login successful. Browser controlled by agent.")


def run(driver: WebDriver, config: ScraperConfig) -> None:
    """Log in and scrape. If anything fails the browser is quit, then the error propagates."""
    try:
        wait_for_manual_login(driver, config)

        # ---------- Run scraper ----------
        scrape_jobs_incrementally(
            driver=driver,
            keyword=config.keyword,
            location=config.location,
            max_jobs=config.max_jobs
        )
    except BaseException:
        driver.quit()
        raise

    print("🎉 Job scraping completed.")


def main() -> None:
    config = get_config()
    run(create_driver(config), config)


if __name__ == "__main__":
    main()
