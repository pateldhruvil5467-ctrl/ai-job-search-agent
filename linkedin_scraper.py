from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd
import urllib.parse


def scrape_jobs_incrementally(driver, keyword, location, max_jobs=5):
    """
    Scrapes LinkedIn job listings with robust error handling and multiple fallback selectors.
    
    Key improvements:
    - JavaScript-based extraction for better DOM access
    - Multiple selector strategies for resilience to LinkedIn layout changes
    - Better error handling and data validation
    - Fallback extraction methods when primary selectors fail
    """
    print("🚀 SCRAPER FUNCTION STARTED")

    # ---------- Navigate explicitly to Jobs search ----------
    keyword_encoded = urllib.parse.quote(keyword)
    location_encoded = urllib.parse.quote(location)

    search_url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={keyword_encoded}&location={location_encoded}"
    )

    print("🌍 Navigating to LinkedIn Jobs search page...")
    driver.get(search_url)
    time.sleep(5)

    wait = WebDriverWait(driver, 20)

    # ---------- Wait for job cards to load ----------
    print("👀 Waiting for job cards...")
    job_cards = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "a.job-card-container__link")
        )
    )

    print(f"🧩 Found {len(job_cards)} visible job cards")

    jobs_data = []

    for index, job_card in enumerate(job_cards[:max_jobs]):
        try:
            print(f"➡️ Opening job {index + 1}")
            driver.execute_script("arguments[0].click();", job_card)
            time.sleep(3)

            # Scroll to top to ensure job details are visible
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # ---------- Extract all job data using JavaScript ----------
            job_data = driver.execute_script("""
                const result = {
                    title: 'Unknown Title',
                    company: 'Unknown Company',
                    location: 'Unknown Location',
                    description: 'No description available'
                };
                
                // === EXTRACT JOB TITLE ===
                let titleEl = document.querySelector('h2[data-job-title]') ||
                              document.querySelector('.job-details-jobs-unified-top-card__job-title') ||
                              document.querySelector('h1');
                
                if (!titleEl) {
                    titleEl = Array.from(document.querySelectorAll('h2')).find(el => {
                        let text = el.innerText?.trim();
                        return text && text.length > 5 && !el.className?.includes('show-more');
                    });
                }
                
                if (titleEl) {
                    let text = titleEl.innerText?.trim() || titleEl.textContent?.trim();
                    if (text && text.length > 2 && !text.includes('Sign up')) {
                        result.title = text;
                    }
                }
                
                // === EXTRACT COMPANY NAME ===
                // Strategy 1: Direct company link
                let companyLink = document.querySelector('a[href*="/company/"]');
                if (companyLink) {
                    let text = (companyLink.innerText || companyLink.textContent || '').trim();
                    if (text && text.length > 1) {
                        result.company = text.split('\\n')[0];
                    }
                }
                
                // Strategy 2: Company in class
                if (result.company === 'Unknown Company') {
                    let companyEl = document.querySelector('.job-details-jobs-unified-top-card__company-name');
                    if (companyEl) {
                        let text = (companyEl.innerText || companyEl.textContent || '').trim();
                        if (text && text.length > 1) result.company = text;
                    }
                }
                
                // Strategy 3: Find all company links and use first valid one
                if (result.company === 'Unknown Company') {
                    let links = document.querySelectorAll('a[href*="/company/"]');
                    for (let link of links) {
                        let text = (link.innerText || link.textContent || '').trim();
                        if (text && text.length > 1 && !text.includes('View')) {
                            result.company = text.split('\\n')[0];
                            break;
                        }
                    }
                }
                
                // === EXTRACT LOCATION ===
                // Look through all text for location patterns
                let bodyText = document.body.innerText;
                let locationPatterns = ['Remote', 'On-site', 'Hybrid'];
                for (let pattern of locationPatterns) {
                    if (bodyText.includes(pattern)) {
                        result.location = pattern;
                        break;
                    }
                }
                
                // Look for city, state pattern
                if (result.location === 'Unknown Location') {
                    let allText = document.body.innerText.split('\\n');
                    for (let line of allText) {
                        if (line.includes(',') && line.length < 50 && !line.includes('Search') && !line.includes('Premium')) {
                            result.location = line.trim();
                            break;
                        }
                    }
                }
                
                // === EXTRACT DESCRIPTION ===
                // Primary: show-more-less markup (LinkedIn standard)
                let descEl = document.querySelector('div.show-more-less-html__markup');
                if (descEl) {
                    let text = (descEl.innerText || descEl.textContent || '').trim();
                    if (text && text.length > 50 && !text.includes('Premium')) {
                        result.description = text.substring(0, 1500);
                    }
                }
                
                // Fallback 1: Check all divs for substantial content
                if (result.description === 'No description available') {
                    let divs = document.querySelectorAll('div[class*="description"], div[class*="show-more"]');
                    for (let div of divs) {
                        let text = (div.innerText || div.textContent || '').trim();
                        if (text && text.length > 100 && !text.includes('Premium') && !text.includes('Search')) {
                            result.description = text.substring(0, 1500);
                            break;
                        }
                    }
                }
                
                // Fallback 2: Find largest text block
                if (result.description === 'No description available') {
                    let allDivs = document.querySelectorAll('div');
                    let largestText = '';
                    for (let div of allDivs) {
                        let text = (div.innerText || '').trim();
                        if (text.length > largestText.length && text.length > 100 && text.length < 3000) {
                            if (!text.includes('Search') && !text.includes('Premium') && !text.includes('Sign')) {
                                largestText = text;
                            }
                        }
                    }
                    if (largestText.length > 100) {
                        result.description = largestText.substring(0, 1500);
                    }
                }
                
                return result;
            """)

            # Sanitize extracted data
            title = str(job_data.get('title') or 'Unknown Title').strip()
            company = str(job_data.get('company') or 'Unknown Company').strip()
            location_text = str(job_data.get('location') or 'Unknown Location').strip()
            description = str(job_data.get('description') or 'No description available').strip()

            jobs_data.append({
                "title": title,
                "company": company,
                "location": location_text,
                "description": description
            })

            print(f"✅ Saved: {title} @ {company}")

        except Exception as e:
            print(f"⚠️ Skipped one job: {str(e)[:80]}")
            continue

    # ---------- Save results to CSV ----------
    df = pd.DataFrame(jobs_data)
    
    # Clean up the dataframe
    df['title'] = df['title'].str.strip()
    df['company'] = df['company'].str.strip()
    df['location'] = df['location'].str.strip()
    df['description'] = df['description'].str.strip()
    
    # Remove completely empty rows
    df = df[(df['title'] != 'Unknown Title') & (df['company'] != 'Unknown Company')]
    
    # Save with proper CSV formatting
    df.to_csv("jobs.csv", index=False, quoting=1, escapechar='\\')
    
    print("📁 jobs.csv updated with real data")
    print(f"✅ Total jobs saved: {len(df)}")
    print("\n📊 Sample data:")
    print(df.head().to_string(index=False))
