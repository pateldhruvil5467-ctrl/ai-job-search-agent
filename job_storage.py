import csv
from dataclasses import asdict
from os import PathLike
from typing import Sequence

import pandas as pd

from models import Job

JOBS_CSV_PATH = "jobs.csv"
# Shared by the writer and the reader: the writer doubles every backslash, so reading must undo it.
CSV_ESCAPECHAR = "\\"
# The original schema. "url" was added later, so it stays optional for files written before it existed.
_REQUIRED_COLUMNS = ("title", "company", "location", "description")


def jobs_to_dataframe(jobs: Sequence[Job]) -> pd.DataFrame:
    return pd.DataFrame([asdict(job) for job in jobs])


def clean_jobs_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['title'] = df['title'].str.strip()
    df['company'] = df['company'].str.strip()
    df['location'] = df['location'].str.strip()
    df['description'] = df['description'].str.strip()

    # Remove completely empty rows
    return df[(df['title'] != 'Unknown Title') & (df['company'] != 'Unknown Company')]


def save_jobs_csv(
    jobs: Sequence[Job], path: str | PathLike[str] = JOBS_CSV_PATH
) -> pd.DataFrame:
    """Write jobs to a CSV file and return the cleaned DataFrame that was written."""
    df = clean_jobs_dataframe(jobs_to_dataframe(jobs))
    df.to_csv(path, index=False, quoting=csv.QUOTE_ALL, escapechar=CSV_ESCAPECHAR)
    return df


def load_jobs_csv(path: str | PathLike[str] = JOBS_CSV_PATH) -> list[Job]:
    """Read jobs from a CSV file written by save_jobs_csv, in file order.

    Rows are converted with Job.from_scraped_data; nothing is deduplicated, filtered or repaired.
    The header must contain title, company, location and description (url is optional, so files
    from before it existed still load); other columns are ignored. Raises FileNotFoundError if
    the file is missing and ValueError if required columns are absent.

    Load jobs.csv, not jobs_formatted.csv: the formatted file has truncated descriptions and no url.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, escapechar=CSV_ESCAPECHAR)
        present = reader.fieldnames or []
        missing = [column for column in _REQUIRED_COLUMNS if column not in present]
        if missing:
            raise ValueError(f"{path} is missing required column(s): {', '.join(missing)}")
        return [Job.from_scraped_data(row) for row in reader]
