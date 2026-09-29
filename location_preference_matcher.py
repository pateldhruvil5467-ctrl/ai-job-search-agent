"""Deterministic candidate preferred-location vs Job location matcher. Lexical only: no I/O.

Each distinct candidate preferred location is searched, whole, in Job.location only. The
preferences found are reported as evidence, in candidate order; a preference is never judged
"satisfied" and no other Job field is read.

Matching reuses the same lexical semantics as role_preference_matcher.py's title matching (its
own small implementation, not imported): a preference is found as a literal phrase, case-
insensitively, with whitespace runs treated as one space, and it must be bounded on both sides so
that it is never found merely as a substring of a larger word ("York" must not be found in
"NewYork"). Remote/Hybrid/On-site are ordinary literal strings here, with no work-mode
interpretation, and no geographic hierarchy or synonym mapping is applied.
"""

import re
from dataclasses import dataclass

from candidate_preferences import CandidatePreferences
from models import Job


@dataclass(frozen=True)
class LocationPreferenceMatch:
    """A Job location and the candidate preferred locations found inside it.

    evidence holds the candidate's preferred locations in their first-seen spelling and candidate
    order; an empty tuple means no preference was found, not that the job is unsuitable.
    """

    job_location: str
    evidence: tuple[str, ...] = ()


def match_preferred_locations_to_job(preferences: CandidatePreferences, job: Job) -> LocationPreferenceMatch:
    """Find the candidate's preferred locations inside job.location.

    Pure and deterministic; neither argument is modified. Raises TypeError, with a static message
    that never includes any preference or job data, if an argument has the wrong type.
    """
    if not isinstance(preferences, CandidatePreferences):
        raise TypeError("preferences must be a CandidatePreferences")
    if not isinstance(job, Job):
        raise TypeError("job must be a Job")

    haystack = _key(job.location)
    evidence = tuple(
        location for location in _distinct(preferences.preferred_locations) if _location_pattern(location).search(haystack)
    )

    return LocationPreferenceMatch(job_location=job.location, evidence=evidence)


def _key(text: str) -> str:
    """Identity for comparing and matching: whitespace collapsed, case-folded."""
    return " ".join(text.split()).casefold()


def _distinct(locations: tuple[str, ...]) -> tuple[str, ...]:
    """Trimmed locations without blanks or duplicates (by _key), keeping first spelling/order."""
    first_spelling: dict[str, str] = {}
    for location in locations:
        trimmed = location.strip()
        key = _key(trimmed)
        if key:
            first_spelling.setdefault(key, trimmed)
    return tuple(first_spelling.values())


def _location_pattern(location: str) -> re.Pattern[str]:
    # re.escape keeps a preference such as "Berlin, Germany" literal, never regex syntax. Applied
    # to a _key()-normalized job location, so no flags or whitespace handling are needed here.
    return re.compile(rf"(?<![\w+#])(?<!\w\.){re.escape(_key(location))}(?![\w+#])(?!\.\w)")
