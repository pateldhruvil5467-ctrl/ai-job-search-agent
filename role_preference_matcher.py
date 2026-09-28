"""Deterministic candidate target-role vs Job title matcher. Lexical only: no I/O, no synonyms.

Each distinct candidate target role is searched, whole, in Job.title only. The candidate roles
found are reported as evidence, in candidate order; a role is never judged "satisfied" and no
other Job field is read.

Matching reuses the same lexical semantics as matcher.py's skill matching (its own small
implementation, not imported): a role is found as a literal phrase, case-insensitively, with
whitespace runs treated as one space, and it must be bounded on both sides so that a role is never
found merely as a substring of a larger word ("Engineer" must not be found in "Engineering").
Nothing maps aliases, so "SWE" is not "Software Engineer".
"""

import re
from dataclasses import dataclass

from candidate_preferences import CandidatePreferences
from models import Job


@dataclass(frozen=True)
class RolePreferenceMatch:
    """A Job title and the candidate target roles found inside it.

    evidence holds the candidate's target roles in their first-seen spelling and candidate order;
    an empty tuple means no target role was found, not that the job is unsuitable.
    """

    job_title: str
    evidence: tuple[str, ...] = ()


def match_target_roles_to_job(preferences: CandidatePreferences, job: Job) -> RolePreferenceMatch:
    """Find the candidate's target roles inside job.title.

    Pure and deterministic; neither argument is modified. Raises TypeError, with a static message
    that never includes any preference or job data, if an argument has the wrong type.
    """
    if not isinstance(preferences, CandidatePreferences):
        raise TypeError("preferences must be a CandidatePreferences")
    if not isinstance(job, Job):
        raise TypeError("job must be a Job")

    haystack = _key(job.title)
    evidence = tuple(role for role in _distinct(preferences.target_roles) if _role_pattern(role).search(haystack))

    return RolePreferenceMatch(job_title=job.title, evidence=evidence)


def _key(text: str) -> str:
    """Identity for comparing and matching: whitespace collapsed, case-folded."""
    return " ".join(text.split()).casefold()


def _distinct(roles: tuple[str, ...]) -> tuple[str, ...]:
    """Trimmed roles without blanks or duplicates (by _key), keeping the first spelling and order."""
    first_spelling: dict[str, str] = {}
    for role in roles:
        trimmed = role.strip()
        key = _key(trimmed)
        if key:
            first_spelling.setdefault(key, trimmed)
    return tuple(first_spelling.values())


def _role_pattern(role: str) -> re.Pattern[str]:
    # re.escape keeps a role such as "C++" literal, never regex syntax. Applied to a
    # _key()-normalized title, so no flags or whitespace handling are needed here.
    return re.compile(rf"(?<![\w+#])(?<!\w\.){re.escape(_key(role))}(?![\w+#])(?!\.\w)")
