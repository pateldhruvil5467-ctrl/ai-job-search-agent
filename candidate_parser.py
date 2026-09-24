"""Plain text -> CandidateProfile. Layer 2 only: deterministic, no PDF, no LLM, no I/O.

Supports one small, explicit resume-text format and skips whatever it cannot structurally
interpret rather than inventing candidate facts:

    SKILLS
    Java, Spring Boot, Python              comma-separated, may span several lines

    EXPERIENCE
    <title> | <organization> | <start> - <end>

    EDUCATION
    <degree> | <institution> | <field>

Section headers are matched case-insensitively on a line of their own (optional trailing colon).
Any other ALL-CAPS line without "|" or "," is treated as an unknown header: it ends the previous
section and its content is ignored, as is any text before the first header. A date range is split
on a spaced hyphen or an en/em dash; the date strings are kept exactly as written. An end date of
Present/Current/Ongoing/Now becomes None. Entries that don't have exactly the expected non-empty
fields are skipped, never completed with guesses.
"""

import re

from candidate import CandidateProfile, Education, Experience

_SKILLS = "skills"
_EXPERIENCE = "experience"
_EDUCATION = "education"
_KNOWN_SECTIONS = frozenset({_SKILLS, _EXPERIENCE, _EDUCATION})

_CURRENT_MARKERS = frozenset({"present", "current", "ongoing", "now"})
_DATE_RANGE_SEPARATOR = re.compile(r"\s*[\u2013\u2014]\s*|\s+-\s+")


def parse_candidate_profile(text: str) -> CandidateProfile:
    """Interpret plain resume text as a CandidateProfile.

    Never raises for malformed content (it is skipped); raises TypeError, with a static message
    that never includes the input, if text is not a str.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    sections = _split_sections(text)
    return CandidateProfile(
        skills=_parse_skills(sections[_SKILLS]),
        experience=_parse_experience(sections[_EXPERIENCE]),
        education=_parse_education(sections[_EDUCATION]),
    )


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {name: [] for name in _KNOWN_SECTIONS}
    current: list[str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if _is_header(line):
            current = sections.get(_header_name(line))
        elif current is not None:
            current.append(line)

    return sections


def _header_name(line: str) -> str:
    return line.removesuffix(":").strip().casefold()


def _is_header(line: str) -> bool:
    if _header_name(line) in _KNOWN_SECTIONS:
        return True
    return "|" not in line and "," not in line and line.isupper()


def _split_fields(line: str, count: int) -> list[str] | None:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) != count or not all(parts):
        return None
    return parts


def _parse_skills(lines: list[str]) -> tuple[str, ...]:
    skills: dict[str, str] = {}
    for line in lines:
        for item in line.split(","):
            skill = item.strip()
            if skill:
                skills.setdefault(skill.casefold(), skill)
    return tuple(skills.values())


def _parse_experience(lines: list[str]) -> tuple[Experience, ...]:
    entries = []
    for line in lines:
        fields = _split_fields(line, 3)
        if fields is None:
            continue
        title, organization, date_range = fields

        dates = [date.strip() for date in _DATE_RANGE_SEPARATOR.split(date_range)]
        if len(dates) != 2 or not all(dates):
            continue
        start, end = dates
        if start.casefold() in _CURRENT_MARKERS:
            continue

        entries.append(
            Experience(
                title=title,
                organization=organization,
                start=start,
                end=None if end.casefold() in _CURRENT_MARKERS else end,
            )
        )
    return tuple(entries)


def _parse_education(lines: list[str]) -> tuple[Education, ...]:
    entries = []
    for line in lines:
        fields = _split_fields(line, 3)
        if fields is None:
            continue
        degree, institution, field = fields
        entries.append(Education(institution=institution, degree=degree, field=field))
    return tuple(entries)
