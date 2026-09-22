# 🤖 LinkedIn Job Search Agent

A local, Selenium-based tool that automates LinkedIn job discovery through a manual, human-in-the-loop login, extracts structured job data from the results, and persists it to CSV for review.

This is **not yet** an AI agent. There is no candidate profile, resume parsing, semantic matching, LLM evaluation, scoring, or autonomous decision-making in the codebase today — those are planned (see [Roadmap](#-roadmap) below) but not implemented.

---

## ✅ Current Functionality

- 🔐 Manual LinkedIn login — the browser opens LinkedIn's login page and waits for you to log in yourself; no credentials are ever entered or stored by the tool
- 🔍 Automated job search for a configured keyword and location
- 🧩 Browser-driven scraping of each result: title, company, location, description and job URL
- 🗂️ A typed, immutable `Job` domain model (`models.py`)
- 📄 CSV persistence — jobs are written to `jobs.csv` (`save_jobs_csv`) and can be read back (`load_jobs_csv`)
- 🔑 A stable `job_key()` identity for each posting, so the same listing can be recognized across separate scrapes
- 🧹 A separate, legacy cleaning/reporting pipeline: `format_jobs.py` → `jobs_formatted.csv`, plus an HTML report (`generate_html_table.py`) and a console summary (`status_report.py`)
- ✅ An offline pytest suite covering the domain model, storage, extraction, and the browser adapter through fakes — no Chrome or LinkedIn access required to run the tests

### Planned, not implemented

The following are part of the intended direction for this project but do **not** exist in the code yet:

- 🧑 Candidate profile (skills, experience, preferences)
- 📄 Resume parsing
- 🎯 Deterministic job/candidate matching rules
- 🧠 LLM-based evaluation of a job against a candidate
- 📊 Job/candidate match scoring
- 🤖 Agent-style decision-making (deciding what to do with a match)
- 🙋 A human-approval workflow before any action is taken on a job

---

## 🏗️ Architecture

```
main.py  ──uses──▶  config.py (ScraperConfig)
   │
   ▼
linkedin_scraper.py        scrape_jobs_incrementally() / scrape_jobs()
   │                       orchestrates the scrape; raises NoJobsExtractedError
   │                       if nothing could be extracted
   ▼
browser.py                 JobBrowser protocol + SeleniumJobBrowser
   │                       the ONLY module that talks to Selenium/Chrome
   ▼
job_page_parser.py         pure, stdlib-only HTML parsing (no Selenium):
   │                       reads location/description from the captured page HTML,
   │                       and derives a canonical job URL from the card link
   ▼
job_extractor.py           extract_job(): raw dict → Job
   ▼
models.py                  Job (frozen dataclass), job_key()
   ▼
job_storage.py             save_jobs_csv() / load_jobs_csv()
   ▼
jobs.csv
```

A second, independent pipeline (older, pre-dates the modules above, and does not use the `Job` model) reformats and reports on the same CSV:

```
jobs.csv → format_jobs.py → jobs_formatted.csv → generate_html_table.py → jobs_table.html
                                                 → status_report.py → console summary
```

`tests/` mirrors this structure with one test file per module (`test_models.py`, `test_job_storage.py`, `test_job_extractor.py`, `test_job_page_parser.py`, `test_browser.py`, `test_linkedin_scraper.py`, `test_main.py`, `test_config.py`, `test_format_jobs.py`) plus `tests/fixtures/linkedin/` — synthetic, hand-written HTML pages used to test `job_page_parser.py` offline. Those fixtures resemble LinkedIn's markup but are **not captures of the real site**, so passing tests confirm the extraction *logic*, not that the selectors match the live DOM.

---

## 🔄 Data flow

```
Browser
  ↓
Raw job data   (dict: title, company, location, description, url — any value may be missing)
  ↓
Job            (typed, immutable; missing/empty values become explicit defaults
  ↓             such as "Unknown Title" or "" for url)
jobs.csv
  ↓
load_jobs_csv()
```

**`job_key(job)`** gives each `Job` a stable identity string:

- If `job.url` contains a recognizable LinkedIn job URL, the key is `linkedin:<numeric id>` — extracted from the URL path, ignoring tracking parameters, slugs, and fragments. This is the preferred, most stable form, since the same posting keeps the same id across scrapes even if its title or description text changes.
- Otherwise, it falls back to `tc:<16 hex characters>`, a SHA-256 hash of the job's title and company, normalized (Unicode NFKC, case-folded, whitespace-collapsed) so trivial formatting differences don't change the key.
- `location` and `description` never affect the key in either case, since those fields are the most likely to change between scrapes of the same posting.

---

## 📄 CSV schema (`jobs.csv`)

Exactly five columns, in this order:

```
title
company
location
description
url
```

Written with `csv.QUOTE_ALL` and `\` as the escape character (see `CSV_ESCAPECHAR` in `job_storage.py`); `load_jobs_csv()` reads with the same settings. `url` is optional on read for backward compatibility with older four-column files (it becomes `""` when absent), but `title`, `company`, `location`, and `description` are required — a file missing any of those raises `ValueError`.

`jobs_formatted.csv` (produced by the separate `format_jobs.py` pipeline) is **not** the same schema: it has only the original four columns and truncated description text, and should not be read with `load_jobs_csv()`.

---

## 🛠️ Setup

Requires **Python 3.10+** (the code uses `X | Y` union type hints).

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 2. Install runtime dependencies
pip install -r requirements.txt

# 3. Install development dependencies (adds pytest on top of the runtime set)
pip install -r requirements-dev.txt

# 4. Run the test suite
pytest

# 5. Run the scraper (opens a real Chrome window and requires you to log in manually)
python main.py
```

> **Note:** these install steps have not been verified against a fresh virtual environment as part of this task. The dependency list in `requirements.txt` was derived by statically checking every `import` in the current source tree, not by running a clean install.

---

## 🧪 Testing

```bash
pytest
```

The suite is designed to run fully **offline**: it does not launch Chrome, does not contact LinkedIn, and makes no network requests. Selenium interaction is tested through a `JobBrowser` fake and a fake WebDriver; `job_page_parser.py` is tested against the synthetic HTML fixtures in `tests/fixtures/linkedin/`. `pytest.ini` sets `testpaths = tests` and `pythonpath = .`, so `pytest` can be run directly from the repository root.

---

## ⚠️ Limitations

- **LinkedIn's DOM can change at any time.** The selectors and page-parsing heuristics in `browser.py` and `job_page_parser.py` were built against a specific snapshot of LinkedIn's markup and may stop matching after a layout change.
- **The live scraper has not been fully re-verified end-to-end** against LinkedIn since the current extraction logic was written; the offline tests validate the parsing logic against fixtures, not the live site.
- **Automated access to LinkedIn may be subject to LinkedIn's Terms of Service and User Agreement.** This project performs browser automation against LinkedIn's pages; you are responsible for reviewing and complying with LinkedIn's terms before running it against your own account.
- **This project does not submit job applications, send messages, or take any action on LinkedIn on your behalf.** It only reads and records publicly visible job listing data after you log in manually.

---

## 🔒 Private data

`private/` is reserved for personal data this project will produce in later phases (resume files, a candidate profile, application records) and is excluded via `.gitignore`. Nothing under `private/` should ever be committed.

---

## 🎯 Use Case

Designed for:
- Working Student applications
- Internship search
- Junior software roles

---

## 📈 Roadmap

```
Foundation
  ✓ Repository cleanup
  ✓ Configuration
  ✓ Job domain model
  ✓ Browser abstraction
  ✓ Extraction/storage separation
  ✓ Job identity + CSV loader
  ✓ Test foundation
  ✓ Documentation & dependency hygiene

Candidate intelligence
  □ CandidateProfile
  □ Resume parsing
  □ Candidate preferences

Matching
  □ Job requirements extraction
  □ Deterministic matching
  □ MatchAnalysis
  □ Explainable scoring

AI
  □ LLM abstraction
  □ AI job evaluation
  □ Hybrid deterministic + LLM matching

Agent
  □ Agent tools
  □ Planning/decision loop
  □ Human approval
  □ Application tracking
```

Everything below "Foundation" is **not implemented**.

---

## 👤 Author

Dhruvil Patel
MSc Software Engineering (Germany)
