from dataclasses import dataclass


@dataclass(frozen=True)
class Experience:
    """One professional experience entry.

    Dates are kept as opaque strings for now: resume parsing does not exist yet, so no date
    format has been established. Nothing here parses, validates, or normalizes them.
    """

    title: str
    organization: str
    start: str
    end: str | None = None  # None means ongoing/current


@dataclass(frozen=True)
class Education:
    """One education record. Plain strings; no degree enum or validation."""

    institution: str
    degree: str
    field: str


@dataclass(frozen=True)
class CandidateProfile:
    """The structured candidate facts a future matching engine will compare against a Job.

    Immutable, like Job in models.py. Intentionally minimal: no contact details, resume
    provenance, preferences, or matching/LLM output belong here — those are later concerns.
    """

    skills: tuple[str, ...] = ()
    experience: tuple[Experience, ...] = ()
    education: tuple[Education, ...] = ()
