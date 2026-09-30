"""Pure composition of the four independent preference matchers into one result. No I/O.

Combines match_target_roles_to_job, match_preferred_locations_to_job, match_work_mode_to_job and
match_employment_type_to_job, unchanged, into a single CandidatePreferenceMatch. No matching logic
of its own: normalization, equality, and evidence construction all remain the sibling matchers' own
responsibility. minimum_hours_per_week is deliberately unsupported here (see candidate_preferences.py)
and is never read, interpreted, or exposed.
"""

from dataclasses import dataclass

from candidate_preferences import CandidatePreferences
from employment_type_preference_matcher import EmploymentTypePreferenceMatch, match_employment_type_to_job
from location_preference_matcher import LocationPreferenceMatch, match_preferred_locations_to_job
from models import Job
from role_preference_matcher import RolePreferenceMatch, match_target_roles_to_job
from work_mode_matcher import WorkModePreferenceMatch, match_work_mode_to_job


@dataclass(frozen=True)
class CandidatePreferenceMatch:
    """The four supported preference-match results for one candidate against one Job."""

    role: RolePreferenceMatch
    location: LocationPreferenceMatch
    work_mode: WorkModePreferenceMatch
    employment_type: EmploymentTypePreferenceMatch


def match_preferences_to_job(preferences: CandidatePreferences, job: Job) -> CandidatePreferenceMatch:
    """Match a candidate's supported preferences against a job.

    Equal to calling match_target_roles_to_job, match_preferred_locations_to_job,
    match_work_mode_to_job and match_employment_type_to_job independently and bundling their
    results; nothing is added, transformed or scored here. Raises TypeError, with a static message
    that never includes any preference or job data, if an argument has the wrong type (preferences
    is checked first).
    """
    if not isinstance(preferences, CandidatePreferences):
        raise TypeError("preferences must be a CandidatePreferences")
    if not isinstance(job, Job):
        raise TypeError("job must be a Job")

    return CandidatePreferenceMatch(
        role=match_target_roles_to_job(preferences, job),
        location=match_preferred_locations_to_job(preferences, job),
        work_mode=match_work_mode_to_job(preferences, job),
        employment_type=match_employment_type_to_job(preferences, job),
    )
