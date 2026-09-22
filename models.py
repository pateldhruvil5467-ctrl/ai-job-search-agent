import hashlib
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Job:
    """A single scraped LinkedIn job posting.

    Immutable: represents a snapshot of a listing as scraped, not a record
    that is edited in place afterward (cleaning/dedup happens on the
    DataFrame in format_jobs.py, not on Job instances).
    """

    title: str
    company: str
    location: str
    description: str
    url: str = ""  # canonical LinkedIn job URL; "" when the scraper could not read one

    @classmethod
    def from_scraped_data(cls, data: dict) -> "Job":
        """Build a Job from the raw dict produced by the scraper.

        Single source of truth for turning scraped values into a Job:
        str() + strip(), with fallback defaults for missing/falsy values.
        """
        return cls(
            title=str(data.get("title") or "Unknown Title").strip(),
            company=str(data.get("company") or "Unknown Company").strip(),
            location=str(data.get("location") or "Unknown Location").strip(),
            description=str(data.get("description") or "No description available").strip(),
            url=str(data.get("url") or "").strip(),
        )


# /jobs/view/<id>/ or /jobs/view/<slug>-<id>/. The id is kept as text, so there is no length cap.
_JOB_PATH = re.compile(r"/jobs/view/(?:[^/]*-)?([0-9]+)/?")
# Whitespace to str.split(), so it can never survive inside a normalized field.
_FIELD_SEPARATOR = "\x1f"


def job_key(job: Job) -> str:
    """A stable identity for a job posting, safe to use as a dictionary or cache key.

    Uses the numeric LinkedIn job id from job.url when there is one ("linkedin:<id>"), which is
    unchanged by tracking parameters, the title slug, and edits to the location or description.
    Otherwise it hashes the normalized title and company ("tc:<16 hex characters>"); location and
    description are deliberately left out because they change between scrapes.

    Never raises. Two postings with the same title at the same company share a fallback key.
    """
    job_id = _linkedin_job_id(_text(job.url))
    if job_id is not None:
        return f"linkedin:{job_id}"

    identity = _FIELD_SEPARATOR.join((_normalize(_text(job.title)), _normalize(_text(job.company))))
    return "tc:" + hashlib.sha256(identity.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _linkedin_job_id(url: str) -> str | None:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None

    host = parts.hostname or ""
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return None
    match = _JOB_PATH.fullmatch(parts.path)
    return match.group(1) if match else None


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())
