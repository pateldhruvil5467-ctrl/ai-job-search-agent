"""Deterministic candidate-to-requirements matcher. Lexical only: no synonyms, no NLP, no I/O.

Only skills are evaluated. Each distinct job skill statement is searched, whole, for every
distinct candidate skill; the candidate skills found in it are reported as evidence, in candidate
order. A statement is never split into concepts and never judged "satisfied": "Experience with
Python, SQL and Docker" and a candidate with only Python simply yields evidence ("Python",).
Experience and education statements are carried through unevaluated, because nothing in the
current representations can compare them reliably.

A candidate skill is found in a statement as a literal phrase, case-insensitively, with whitespace
runs treated as one space. It is NOT a plain substring test ("Java" must not be found in
"JavaScript", nor "C" in "C++"), so the skill must be bounded on both sides:
- before it: no word character, "+" or "#", and not a word character followed by "." ("NET" is
  not found in "ASP.NET");
- after it: no word character, "+" or "#", and no "." followed by a word character ("Node" is not
  found in "Node.js", but a sentence-final period is fine).
Any other punctuation, including "-" and "/", is a boundary.

Known, accepted limitations of this lexical baseline: short or common-word skills are found in
ordinary text ("Go" in "go the extra mile", "R" in "R&D", "C" in "C-level"), a hyphen is a boundary
("learn" is found in "Scikit-learn"), and nothing maps aliases ("JS" is not "JavaScript").
Blank skills and blank statements carry no information and are ignored.
"""

import re
from dataclasses import dataclass

from candidate import CandidateProfile
from job_requirements import JobRequirements


@dataclass(frozen=True)
class SkillMatch:
    """One distinct job skill statement and the candidate skills found inside it.

    evidence holds the candidate skills in their first-seen spelling and candidate order; an empty
    tuple means no candidate skill was found, not that the candidate failed anything.
    """

    statement: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class MatchResult:
    """Skill evidence per statement, plus the experience and education statements, unevaluated."""

    skills: tuple[SkillMatch, ...] = ()
    unevaluated_experience: tuple[str, ...] = ()
    unevaluated_education: tuple[str, ...] = ()


def match_candidate_to_requirements(candidate: CandidateProfile, requirements: JobRequirements) -> MatchResult:
    """Find the candidate's skills inside the job's skill requirement statements.

    Pure and deterministic; neither argument is modified. Raises TypeError, with a static message
    that never includes any candidate or requirement text, if an argument has the wrong type.
    """
    if not isinstance(candidate, CandidateProfile):
        raise TypeError("candidate must be a CandidateProfile")
    if not isinstance(requirements, JobRequirements):
        raise TypeError("requirements must be a JobRequirements")

    finders = [(skill, _skill_pattern(skill)) for skill in _distinct(candidate.skills)]

    skills = []
    for statement in _distinct(requirements.skills):
        haystack = _key(statement)
        evidence = tuple(skill for skill, pattern in finders if pattern.search(haystack))
        skills.append(SkillMatch(statement=statement, evidence=evidence))

    return MatchResult(
        skills=tuple(skills),
        unevaluated_experience=_distinct(requirements.experience),
        unevaluated_education=_distinct(requirements.education),
    )


def _key(text: str) -> str:
    """Identity for comparing and matching: whitespace collapsed, case-folded."""
    return " ".join(text.split()).casefold()


def _distinct(texts: tuple[str, ...]) -> tuple[str, ...]:
    """Trimmed texts without blanks or duplicates (by _key), keeping the first spelling and order."""
    first_spelling: dict[str, str] = {}
    for text in texts:
        trimmed = text.strip()
        key = _key(trimmed)
        if key:
            first_spelling.setdefault(key, trimmed)
    return tuple(first_spelling.values())


def _skill_pattern(skill: str) -> re.Pattern[str]:
    # re.escape keeps skills such as "C++" or "Node.js" literal, never regex syntax. Applied to a
    # _key()-normalized statement, so no flags or whitespace handling are needed here.
    return re.compile(rf"(?<![\w+#])(?<!\w\.){re.escape(_key(skill))}(?![\w+#])(?!\.\w)")
