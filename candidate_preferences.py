from dataclasses import dataclass


@dataclass(frozen=True)
class CandidatePreferences:
    """What the candidate is looking for, as distinct from CandidateProfile's facts about them.

    Immutable, like CandidateProfile and JobRequirements, and independent of both: it is not a
    field of either and has no matching, scoring, or ranking behavior of its own. No validation,
    normalization, or deduplication; values are stored exactly as given.
    """

    target_roles: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    work_mode: str | None = None
    employment_type: str | None = None
    minimum_hours_per_week: int | None = None
