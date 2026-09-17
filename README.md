# 🤖 LinkedIn Job Search Agent

A Selenium-based agent that automates LinkedIn job discovery with a human-in-the-loop login, then cleans and formats the scraped results into CSV and HTML reports.

This project demonstrates browser automation and human-in-the-loop agent design. AI-based resume matching and semantic scoring are planned but **not yet implemented** — see [Roadmap](#-roadmap--not-yet-implemented) below.

---

## ✅ Current Functionality

- 🔍 Automated LinkedIn job search (manual, human-in-the-loop login — no credential automation)
- 🧩 Scrapes job title, company, location, and description from search results via Selenium + JavaScript-based DOM extraction
- 🗂️ Saves raw results to `jobs.csv`
- 🧹 Cleans and deduplicates data into `jobs_formatted.csv`
- 📊 Generates a styled HTML report (`jobs_table.html`) and a console summary (`status_report.py`)

---

## 🧠 How It Works (current pipeline)

```
LinkedIn Jobs
   ↓
main.py (browser launch + manual login)
   ↓
linkedin_scraper.py (job card scraping)
   ↓
jobs.csv
   ↓
format_jobs.py (cleaning/dedup)
   ↓
jobs_formatted.csv
   ↓
generate_html_table.py → jobs_table.html
status_report.py → console summary
```

Each stage is run manually as a separate script — there is no scheduler or single "run everything" command yet.

---

## 🛠️ Tech Stack (currently used)

- Python
- Selenium + webdriver-manager (browser automation)
- Pandas (data cleaning/formatting)

`requirements.txt` also lists `pdfplumber`, `sentence-transformers`, and `scikit-learn` for the planned resume-matching feature below — these are not used by any script yet.

---

## 📂 Project Structure (files that exist today)

```
main.py                 → Browser launch, manual login, scraper invocation
linkedin_scraper.py     → Job search + job card scraping logic
format_jobs.py          → Cleans/dedupes jobs.csv → jobs_formatted.csv
generate_html_table.py  → Renders jobs_formatted.csv → jobs_table.html
status_report.py        → Prints a console summary of jobs_formatted.csv
config.py               → Reserved for future configuration (currently empty/unused)
```

---

## ⚠️ Ethical & Safety Notes

- Manual LinkedIn login (no credential automation)
- Read-only scraping
- Human-in-the-loop design
- No ToS-violating automation

---

## 🎯 Use Case

Designed for:
- Working Student applications
- Internship search
- Junior software roles

---

## 📈 Roadmap / Not Yet Implemented

The following were part of the original project vision but do **not** exist in the codebase yet:

- 📄 PDF resume parsing (`resume_reader.py` — not present)
- 🧠 AI-based semantic job matching using embeddings (`matcher.py` — not present)
- 📊 Job relevance scoring
- ⭐ Automatic job shortlisting
- ✉️ Auto-generated cover letters
- 📧 Email outreach automation
- 📈 Job ranking dashboard
- 🌐 Multi-platform support (Indeed, StepStone)

---

## 👤 Author

Dhruvil Patel
MSc Software Engineering (Germany)
