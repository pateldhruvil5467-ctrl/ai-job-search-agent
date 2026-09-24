"""Job description text -> JobRequirements. Deterministic: no NLP, no LLM, no I/O.

Reads only bullet statements ("- " or a bullet dot) inside a small allowlist of required-
requirement sections, keeps each statement whole, and classifies it independently into skills,
experience and education. A statement can land in several dimensions; one that matches none is
dropped. Nothing is extracted from inside a statement, so "Experience with Python, SQL and Docker"
stays one entry.

Known limitations, all deliberate (skip rather than guess):
- Prose requirements are skipped; only bullets are read.
- The heading allowlists are small and come from a handful of postings; extend the data below.
- A section heading must be a short standalone line. A colon-terminated line that is not a known
  heading is a lead-in and does not end the section, so a genuinely colon-terminated heading that
  is not listed would let its bullets leak into the previous required section.
- Optional sections are excluded because JobRequirements has no required/optional distinction.
  Headings that are neither listed as required nor as optional, such as the ambiguous "Was dir
  bei der Arbeit helfen wird", are unsupported: their bullets are not extracted.
- Classification is by keyword, so "experience with X" is both experience and a skill, a degree
  that may be replaced by "equivalent practical experience" is also experience, and a language
  requirement phrased with a trigger ("proficiency in English") counts as a skill.
"""

import re

from job_requirements import JobRequirements

# Normalized (case-folded, symbols and trailing colon removed) headings, as data: the one place to
# update when postings use other wording.
_REQUIRED_HEADINGS = frozenset(
    {
        "requirements",
        "qualifications",
        "what you bring",
        "more about you",
        "was du mitbringen solltest",
        "wen wir suchen",
    }
)
_OPTIONAL_HEADINGS = frozenset({"nice to have"})

_MAX_HEADING_CHARS = 60
_MAX_HEADING_WORDS = 8
_SENTENCE_END = (".", ";", ",", "!", "?")

_BULLET = re.compile(r"(?:-|\u2022)\s+(.+)")
_SYMBOLS_AROUND_HEADING = re.compile(r"^[\W_]+|[\W_]+$")


def _phrases(*phrases: str) -> str:
    return "|".join(r"\s+".join(re.escape(word) for word in phrase.split()) for phrase in phrases)


def _whole_word(alternatives: str) -> re.Pattern[str]:
    # (?<!\w) / (?!\w) so "Kenntnisse" never matches inside "Deutschkenntnisse".
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


_SKILL = _whole_word(
    _phrases(
        "experience with",
        "knowledge of",
        "proficiency in",
        "proficient in",
        "familiar with",
        "familiarity with",
        "comfort with",
        "erfahrung mit",
        "erfahrungen mit",
        "kenntnisse",
        "arbeit mit",
    )
)

_NUMBER_WORDS = _phrases(
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "ein", "einem", "zwei", "drei", "vier", "f\u00fcnf", "sechs", "sieben", "acht", "neun", "zehn",
)
_EXPERIENCE = _whole_word(
    rf"(?:\d+|{_NUMBER_WORDS})\s*\+?\s*(?:years?|yrs?|jahr(?:e|en)?)"
    r"|experience|erfahrung(?:en)?|berufserfahrung(?:en)?"
)

_EDUCATION = _whole_word(
    r"bachelor(?:['\u2019]?s)?|master['\u2019]s|masters|master\s+(?:degree|of)"
    r"|m\.?sc|b\.?sc|ph\.?d|doctorate|diplom(?:a)?"
    r"|degrees?(?!\s+of\b)|enrolled|enrol{1,2}ment|immatrikuliert"
    r"|universit(?:y|ies|\u00e4t)|hochschule|student(?:s|en|in|innen)?"
    r"|\w*studium|studiengang|(?:hochschul|studien|bachelor|master)?abschluss"
)


def extract_job_requirements(description: str) -> JobRequirements:
    """Extract the required skills, experience and education statements from a job description.

    Returns JobRequirements() when nothing can be extracted (empty text, no recognised required
    section, only optional sections). Unsupported or malformed lines are skipped, never raised on.
    Raises TypeError, with a static message that never includes the input, if description is not
    a str.
    """
    if not isinstance(description, str):
        raise TypeError("description must be a str")

    skills: dict[str, str] = {}
    experience: dict[str, str] = {}
    education: dict[str, str] = {}

    for statement in _required_statements(description):
        for pattern, found in ((_SKILL, skills), (_EXPERIENCE, experience), (_EDUCATION, education)):
            if pattern.search(statement):
                found.setdefault(statement.casefold(), statement)

    return JobRequirements(
        skills=tuple(skills.values()),
        experience=tuple(experience.values()),
        education=tuple(education.values()),
    )


def _required_statements(description: str) -> list[str]:
    statements: list[str] = []
    collecting = False
    after_blank_line = True

    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            after_blank_line = True
            continue

        if after_blank_line and _is_heading_shaped(line):
            key = _heading_key(line)
            if key in _REQUIRED_HEADINGS:
                collecting = True
            elif key in _OPTIONAL_HEADINGS or not line.endswith(":"):
                collecting = False
            # Any other colon-terminated line is a lead-in: the section continues.
        elif collecting and (bullet := _BULLET.fullmatch(line)):
            statements.append(bullet.group(1).strip())

        after_blank_line = False

    return statements


def _is_heading_shaped(line: str) -> bool:
    return (
        len(line) <= _MAX_HEADING_CHARS
        and len(line.split()) <= _MAX_HEADING_WORDS
        and not line.endswith(_SENTENCE_END)
        and _BULLET.fullmatch(line) is None
    )


def _heading_key(line: str) -> str:
    return " ".join(_SYMBOLS_AROUND_HEADING.sub("", line).split()).casefold()
