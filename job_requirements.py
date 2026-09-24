from dataclasses import dataclass


@dataclass(frozen=True)
class JobRequirements:
    """What a job posting asks of a candidate, in three dimensions.

    Each entry is an opaque requirement statement kept exactly as given: nothing here is parsed,
    validated, normalized or classified, and nothing extracts it from a Job yet. Note that
    experience and education are plain strings here, unlike the structured records in
    CandidateProfile. Immutable, like Job and CandidateProfile, and independent of both: it is not
    a field of Job and has no effect on the CSV schema. Intentionally minimal; other kinds of
    requirement are later concerns.
    """

    skills: tuple[str, ...] = ()
    experience: tuple[str, ...] = ()
    education: tuple[str, ...] = ()
