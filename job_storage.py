import csv
from dataclasses import asdict
from os import PathLike
from typing import Sequence

import pandas as pd

from models import Job

JOBS_CSV_PATH = "jobs.csv"


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
    df.to_csv(path, index=False, quoting=csv.QUOTE_ALL, escapechar='\\')
    return df
