"""Batch preference matching: composition only. One candidate's preferences against many already-
loaded Jobs, parallel to job_batch_matcher.py for Pipeline B.

Each Job goes through preference_matcher.match_preferences_to_job, unchanged and in input order.
Nothing is loaded, extracted, matched, scored or ranked here.
"""

from collections.abc import Sequence

from candidate_preferences import CandidatePreferences
from models import Job
from preference_matcher import CandidatePreferenceMatch, match_preferences_to_job


def match_preferences_to_jobs(
    preferences: CandidatePreferences, jobs: Sequence[Job]
) -> tuple[CandidatePreferenceMatch, ...]:
    """Match a candidate's preferences against every job, returning one CandidatePreferenceMatch
    per Job in input order.

    jobs must be a Sequence (not str, bytes or bytearray) containing only Job objects; it is never
    coerced from another iterable. Everything is validated before any job is matched. Raises
    TypeError with a static message for a wrong preferences, container or element. Errors raised
    while matching a job propagate unchanged.
    """
    if not isinstance(preferences, CandidatePreferences):
        raise TypeError("preferences must be a CandidatePreferences")
    if isinstance(jobs, (str, bytes, bytearray)) or not isinstance(jobs, Sequence):
        raise TypeError("jobs must be a sequence of Job objects")
    if not all(isinstance(job, Job) for job in jobs):
        raise TypeError("jobs must contain only Job objects")

    return tuple(match_preferences_to_job(preferences, job) for job in jobs)
