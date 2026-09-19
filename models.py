from dataclasses import dataclass


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

    @classmethod
    def from_scraped_data(cls, data: dict) -> "Job":
        """Build a Job from the raw dict produced by the scraper.

        Mirrors the sanitization already applied in
        linkedin_scraper.scrape_jobs_incrementally (str() + strip(), with
        the same fallback defaults) so mapping existing scraped data into
        a Job reproduces identical values.
        """
        return cls(
            title=str(data.get("title") or "Unknown Title").strip(),
            company=str(data.get("company") or "Unknown Company").strip(),
            location=str(data.get("location") or "Unknown Location").strip(),
            description=str(data.get("description") or "No description available").strip(),
        )
