from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import sys

from linkedin_scraper import scrape_jobs_incrementally
from config import get_config

config = get_config()

# ---------- Browser setup ----------
options = webdriver.ChromeOptions()
if config.start_maximized:
    options.add_argument("--start-maximized")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# ---------- Login ----------
driver.get("https://www.linkedin.com/login")
print(f"🔐 Please log in to LinkedIn manually within the next {config.login_wait_seconds} seconds...")
time.sleep(config.login_wait_seconds)

# ---------- Verify login ----------
if "login" in driver.current_url:
    print("❌ Login not detected. Please try again.")
    driver.quit()
    sys.exit(1)

print("✅ Login successful. Browser controlled by agent.")

# ---------- Run scraper ----------
scrape_jobs_incrementally(
    driver=driver,
    keyword=config.keyword,
    location=config.location,
    max_jobs=config.max_jobs
)

print("🎉 Job scraping completed.")
