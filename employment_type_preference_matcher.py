"""Deterministic single employment-type preference vs Job employment_type matcher. Lexical only: no I/O.

Unlike role/location/work-mode matching, this is never a phrase-search inside a larger prose field:
job.employment_type is already a short, already-canonicalized label (from job_page_parser.py's chip
vocabulary), not prose a preference could be embedded in. So the candidate's employment_type (a
single str | None) is compared to Job.employment_type (also a single str | None) by WHOLE-VALUE
equality, not substring/boundary search; a preference is never judged "satisfied" and no other
CandidatePreferences or Job field is read. No synonyms or aliases: "PT" is not "Part-time".
"""

from dataclasses import dataclass

from candidate_preferences import CandidatePreferences
from models import Job


@dataclass(frozen=True)
class EmploymentTypePreferenceMatch:
    """A Job's employment type and the candidate's employment-type preference, if it matches.

    evidence holds the candidate's trimmed employment_type value when it equals job.employment_type,
    in a one-item tuple; an empty tuple means no match, not that the job is unsuitable — including
    when job.employment_type is None (the job's employment type is unknown, not "any").
    """

    job_employment_type: str | None
    evidence: tuple[str, ...] = ()


def match_employment_type_to_job(preferences: CandidatePreferences, job: Job) -> EmploymentTypePreferenceMatch:
    """Compare the candidate's employment_type preference to job.employment_type by whole-value equality.

    Pure and deterministic; neither argument is modified. Raises TypeError, with a static message
    that never includes any preference or job data, if an argument has the wrong type.
    """
    if not isinstance(preferences, CandidatePreferences):
        raise TypeError("preferences must be a CandidatePreferences")
    if not isinstance(job, Job):
        raise TypeError("job must be a Job")

    employment_type = preferences.employment_type
    trimmed = employment_type.strip() if employment_type is not None else ""

    evidence: tuple[str, ...] = ()
    if trimmed and job.employment_type is not None and _key(trimmed) == _key(job.employment_type):
        evidence = (trimmed,)

    return EmploymentTypePreferenceMatch(job_employment_type=job.employment_type, evidence=evidence)


def _key(text: str) -> str:
    """Identity for comparing: whitespace collapsed, case-folded."""
    return " ".join(text.split()).casefold()
