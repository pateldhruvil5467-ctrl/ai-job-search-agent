from typing import Any

from models import Job

RawJobData = dict[str, Any]


def extract_job(raw: RawJobData) -> Job:
    """Convert raw values read from a job page into a Job.

    Browser-independent entry point for the extraction layer. Defaults and
    sanitization live in Job.from_scraped_data, the single source of truth;
    nothing is duplicated here.
    """
    return Job.from_scraped_data(raw)
