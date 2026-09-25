"""Job-level matching: composition only. Extracts a Job's requirements, then matches a candidate.

Only Job.description is used. All extraction and matching rules live in job_requirements_parser
and matcher; nothing is added, transformed or scored here.
"""

from candidate import CandidateProfile
from job_requirements_parser import extract_job_requirements
from matcher import MatchResult, match_candidate_to_requirements
from models import Job


def match_candidate_to_job(candidate: CandidateProfile, job: Job) -> MatchResult:
    """Match a candidate against the requirements extracted from job.description.

    Equal to match_candidate_to_requirements(candidate, extract_job_requirements(job.description)).
    Raises TypeError with a static message if candidate or job has the wrong type (candidate is
    checked first). A non-str job.description raises the extractor's own TypeError.
    """
    if not isinstance(candidate, CandidateProfile):
        raise TypeError("candidate must be a CandidateProfile")
    if not isinstance(job, Job):
        raise TypeError("job must be a Job")

    requirements = extract_job_requirements(job.description)
    return match_candidate_to_requirements(candidate, requirements)
