"""Deterministic single work-mode preference vs Job location matcher. Lexical only: no I/O.

The candidate's work_mode (a single str | None, unlike the tuple-valued preferences) is searched,
whole, in Job.location only; a match, if found, is reported as the single item of evidence. A
preference is never judged "satisfied" and no other CandidatePreferences or Job field is read.

Matching reuses the same lexical semantics as role_preference_matcher.py and
location_preference_matcher.py (its own small implementation, not imported): the value is found as
a literal phrase, case-insensitively, with whitespace runs treated as one space, and it must be
bounded on both sides so it is never found merely as a substring of a larger word ("Remote" must
not be found in "Remotely"). Remote/Hybrid/On-site are never inferred from one another or from the
absence of a suffix; only the candidate's own literal string is ever searched for.
"""

import re
from dataclasses import dataclass

from candidate_preferences import CandidatePreferences
from models import Job


@dataclass(frozen=True)
class WorkModePreferenceMatch:
    """A Job location and the candidate's work-mode preference, if found inside it.

    evidence holds the candidate's trimmed work_mode value when found, in a one-item tuple; an
    empty tuple means it was not found, not that the job is unsuitable.
    """

    job_location: str
    evidence: tuple[str, ...] = ()


def match_work_mode_to_job(preferences: CandidatePreferences, job: Job) -> WorkModePreferenceMatch:
    """Find the candidate's work-mode preference inside job.location.

    Pure and deterministic; neither argument is modified. Raises TypeError, with a static message
    that never includes any preference or job data, if an argument has the wrong type.
    """
    if not isinstance(preferences, CandidatePreferences):
        raise TypeError("preferences must be a CandidatePreferences")
    if not isinstance(job, Job):
        raise TypeError("job must be a Job")

    work_mode = preferences.work_mode
    trimmed = work_mode.strip() if work_mode is not None else ""

    evidence: tuple[str, ...] = ()
    if trimmed and _work_mode_pattern(trimmed).search(_key(job.location)):
        evidence = (trimmed,)

    return WorkModePreferenceMatch(job_location=job.location, evidence=evidence)


def _key(text: str) -> str:
    """Identity for comparing and matching: whitespace collapsed, case-folded."""
    return " ".join(text.split()).casefold()


def _work_mode_pattern(value: str) -> re.Pattern[str]:
    # re.escape keeps a value such as "on-site" literal, never regex syntax. Applied to a
    # _key()-normalized job location, so no flags or whitespace handling are needed here.
    return re.compile(rf"(?<![\w+#])(?<!\w\.){re.escape(_key(value))}(?![\w+#])(?!\.\w)")
