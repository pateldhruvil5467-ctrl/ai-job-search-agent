"""Application-level matching service: pure delegation to the existing batch matcher.

Adds no behavior of its own; it exists only as the stable boundary an application would call.
"""

from collections.abc import Sequence

from candidate import CandidateProfile
from job_batch_matcher import match_candidate_to_jobs
from matcher import MatchResult
from models import Job


def match_candidate_against_jobs(candidate: CandidateProfile, jobs: Sequence[Job]) -> tuple[MatchResult, ...]:
    """Match a candidate against many jobs. Exactly match_candidate_to_jobs(candidate, jobs)."""
    return match_candidate_to_jobs(candidate, jobs)
