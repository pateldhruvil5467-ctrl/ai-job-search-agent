"""Batch matching: composition only. One candidate against many already-loaded Jobs.

Each Job goes through job_matcher.match_candidate_to_job, unchanged and in input order. Nothing is
loaded, extracted, matched, scored or ranked here.
"""

from collections.abc import Sequence

from candidate import CandidateProfile
from job_matcher import match_candidate_to_job
from matcher import MatchResult
from models import Job


def match_candidate_to_jobs(candidate: CandidateProfile, jobs: Sequence[Job]) -> tuple[MatchResult, ...]:
    """Match a candidate against every job, returning one MatchResult per job in input order.

    jobs must be a Sequence (not str, bytes or bytearray) containing only Job objects; it is never
    coerced from another iterable. Everything is validated before any job is matched. Raises
    TypeError with a static message for a wrong candidate, container or element. Errors raised
    while matching a job propagate unchanged.
    """
    if not isinstance(candidate, CandidateProfile):
        raise TypeError("candidate must be a CandidateProfile")
    if isinstance(jobs, (str, bytes, bytearray)) or not isinstance(jobs, Sequence):
        raise TypeError("jobs must be a sequence of Job objects")
    if not all(isinstance(job, Job) for job in jobs):
        raise TypeError("jobs must contain only Job objects")

    return tuple(match_candidate_to_job(candidate, job) for job in jobs)
