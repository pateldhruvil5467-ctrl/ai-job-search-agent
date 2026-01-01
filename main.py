from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import sys

from linkedin_scraper import scrape_jobs_incrementally


# ---------- Browser setup ----------
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# ---------- Login ----------
driver.get("https://www.linkedin.com/login")
print("🔐 Please log in to LinkedIn manually within the next 60 seconds...")
time.sleep(60)

# ---------- Verify login ----------
if "login" in driver.current_url:
    print("❌ Login not detected. Please try again.")
    driver.quit()
    sys.exit(1)

print("✅ Login successful. Browser controlled by agent.")

# ---------- Run scraper ----------
scrape_jobs_incrementally(
    driver=driver,
    keyword="Working Student Software Engineer",
    location="Berlin",
    max_jobs=5
)

print("🎉 Job scraping completed.")
