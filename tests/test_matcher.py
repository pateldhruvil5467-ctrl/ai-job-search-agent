"""Tests for matcher: deterministic candidate skills vs job requirement statements (Task 1.6).

The matcher reads only CandidateProfile.skills and JobRequirements. It searches each distinct job
skill statement for candidate skills as literal, case-insensitive phrases with explicit boundaries,
and reports the evidence found. It never splits a statement into concepts, never judges a statement
"satisfied", and never invents synonyms. Experience and education statements are carried through
unevaluated. All data here is synthetic.
"""

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from candidate import CandidateProfile, Education, Experience
from job_requirements import JobRequirements
from matcher import MatchResult, SkillMatch, match_candidate_to_requirements

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"

PYTHON_SQL_DOCKER = "Experience with Python, SQL and Docker"


def match(candidate_skills=(), *, skills=(), experience=(), education=()) -> MatchResult:
    return match_candidate_to_requirements(
        CandidateProfile(skills=tuple(candidate_skills)),
        JobRequirements(skills=tuple(skills), experience=tuple(experience), education=tuple(education)),
    )


def evidence_of(candidate_skills, statement) -> tuple[str, ...]:
    result = match(candidate_skills, skills=(statement,))
    assert [item.statement for item in result.skills] == [statement]
    return result.skills[0].evidence


def assert_only_immutable(value):
    assert not isinstance(value, (list, dict, set, bytearray)), type(value)
    if dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            assert_only_immutable(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:
            assert_only_immutable(item)


class TestSkillMatching:
    @pytest.mark.parametrize(
        ("candidate_skills", "statement", "expected"),
        [
            pytest.param(("Python",), PYTHON_SQL_DOCKER, ("Python",), id="basic-containment"),
            pytest.param(("Python", "SQL", "Docker"), PYTHON_SQL_DOCKER, ("Python", "SQL", "Docker"), id="several-candidate-skills"),
            pytest.param(("Java",), "Knowledge of Java or Kotlin", ("Java",), id="java"),
            pytest.param(
                ("JavaScript", "TypeScript"),
                "Knowledge of TypeScript/JavaScript",
                ("JavaScript", "TypeScript"),
                id="slash-separated-technologies",
            ),
            pytest.param(("C",), "Experience with C, C++ or Rust", ("C",), id="c-before-comma"),
            pytest.param(("C++",), "Experience with C++ or Rust", ("C++",), id="c-plus-plus"),
            pytest.param(("C#",), "Experience with C# and .NET", ("C#",), id="c-sharp"),
            pytest.param((".NET",), "Experience with C# and .NET", (".NET",), id="dot-net"),
            pytest.param(("Node.js",), "Experience with Node.js and React", ("Node.js",), id="node-js"),
            pytest.param(("React.js",), "Experience with React.js.", ("React.js",), id="react-js-with-sentence-period"),
            pytest.param(("Python",), "sehr gute Python-Kenntnisse", ("Python",), id="german-compound-wording"),
            pytest.param(("Spring Boot",), "Experience with spring   boot and Kafka", ("Spring Boot",), id="whitespace-run-in-statement"),
            pytest.param(("Spring   Boot",), "Experience with Spring Boot", ("Spring   Boot",), id="whitespace-run-in-candidate-skill"),
            pytest.param(("Spring Boot",), "Experience with Spring\tBoot", ("Spring Boot",), id="tab-counts-as-whitespace"),
            pytest.param(("python",), "Experience with PYTHON", ("python",), id="case-insensitive-keeps-candidate-spelling"),
            pytest.param(("PYTHON",), "Experience with python", ("PYTHON",), id="case-insensitive-other-direction"),
        ],
    )
    def test_a_candidate_skill_is_found_inside_a_statement(self, candidate_skills, statement, expected):
        assert evidence_of(candidate_skills, statement) == expected

    @pytest.mark.parametrize(
        "statement",
        [
            "Experience with (Python)",
            "Experience with Python; SQL",
            "Skills: Python",
            'Experience with "Python"',
            "Experience with Python/SQL",
            "Experience with Python, ideally in cloud settings",
            "Python",
        ],
    )
    def test_other_punctuation_and_the_statement_edges_are_boundaries(self, statement):
        assert evidence_of(("Python",), statement) == ("Python",)

    def test_a_skill_repeated_inside_one_statement_is_reported_once(self):
        assert evidence_of(("Python",), "Python, Python and more Python") == ("Python",)

    def test_a_skill_that_is_a_phrase_of_another_skill_is_reported_alongside_it(self):
        assert evidence_of(("Spring", "Spring Boot"), "Experience with Spring Boot") == ("Spring", "Spring Boot")

    def test_a_shorter_skill_is_not_reported_inside_a_longer_word_of_another_skill(self):
        assert evidence_of(("Java", "JavaScript"), "Experience with JavaScript") == ("JavaScript",)

    def test_the_skill_text_is_matched_literally_not_as_a_pattern(self):
        assert evidence_of(("Node.js",), "Experience with NodeXjs") == ()
        assert evidence_of(("C++",), "Experience with CCC") == ()


class TestSkillBoundaries:
    @pytest.mark.parametrize(
        ("candidate_skill", "statement"),
        [
            pytest.param("Java", "Experience with JavaScript", id="java-not-in-javascript"),
            pytest.param("C", "Experience with C++", id="c-not-in-c-plus-plus"),
            pytest.param("C", "Experience with C# and .NET", id="c-not-in-c-sharp"),
            pytest.param("C++", "Experience with C", id="c-plus-plus-not-in-c"),
            pytest.param("NET", "Experience with ASP.NET", id="net-not-in-asp-net"),
            pytest.param("Node", "Experience with Node.js", id="node-not-in-node-js"),
            pytest.param("js", "Experience with Node.js", id="js-not-in-node-js"),
            pytest.param("React", "Experience with React.js", id="react-not-in-react-js"),
            pytest.param("React", "Experience with ReactJS", id="react-not-in-reactjs"),
            pytest.param("Python", "Knowledge of Pythonic idioms", id="python-not-in-pythonic"),
            pytest.param("Go", "Experience with Google Cloud", id="go-not-in-google"),
            pytest.param("R", "Experience with Rust", id="r-not-in-rust"),
            pytest.param("AI", "Experience with email tooling", id="ai-not-in-email"),
            pytest.param("Python", "Experience with Python3", id="python-not-in-python3"),
            pytest.param("Python", "Experience with Python.NET", id="python-not-before-a-dot-and-word-character"),
            pytest.param("Python", "Experience with #Python", id="hash-before-the-skill-blocks-it"),
            pytest.param("Python", "Experience with +Python", id="plus-before-the-skill-blocks-it"),
            pytest.param("Python", "Experience with Python#", id="hash-after-the-skill-blocks-it"),
            pytest.param("Python", "Experience with Python+", id="plus-after-the-skill-blocks-it"),
            pytest.param("Python", "Experience with Java and Docker", id="absent-skill"),
        ],
    )
    def test_a_skill_is_not_found_across_a_word_or_symbol_boundary(self, candidate_skill, statement):
        assert evidence_of((candidate_skill,), statement) == ()

    @pytest.mark.parametrize(
        ("candidate_skill", "statement"),
        [
            pytest.param("JS", "Experience with JavaScript", id="js-is-not-javascript"),
            pytest.param("Postgres", "Experience with PostgreSQL", id="postgres-is-not-postgresql"),
            pytest.param("ReactJS", "Experience with React.js", id="reactjs-is-not-react-js"),
            pytest.param("React", "Experience with React.js", id="react-is-not-react-js"),
            pytest.param("JavaScript", "Experience with JS", id="javascript-is-not-js"),
        ],
    )
    def test_no_synonym_or_alias_is_ever_inferred(self, candidate_skill, statement):
        assert evidence_of((candidate_skill,), statement) == ()

    @pytest.mark.parametrize(
        ("candidate_skill", "statement"),
        [
            pytest.param("Go", "We encourage you to go the extra mile", id="go-in-ordinary-english"),
            pytest.param("R", "Experience with R&D", id="r-in-r-and-d"),
            pytest.param("C", "Experience at C-level", id="c-in-c-level"),
        ],
    )
    def test_known_limitation_short_skills_are_found_in_ordinary_text(self, candidate_skill, statement):
        # Accepted, documented lexical behavior: no heuristic prevents these false positives.
        assert evidence_of((candidate_skill,), statement) == (candidate_skill,)

    def test_known_limitation_a_hyphen_is_a_boundary(self):
        # Accepted, documented lexical behavior: "learn" is found inside "Scikit-learn".
        assert evidence_of(("learn",), "Experience with Scikit-learn") == ("learn",)

    def test_a_statement_without_evidence_stays_in_the_result(self):
        result = match(("Python",), skills=("Experience with Java and Docker",))

        assert result.skills == (SkillMatch(statement="Experience with Java and Docker", evidence=()),)


class TestSkillNormalizationAndDeduplication:
    def test_duplicate_candidate_skills_are_evaluated_once_keeping_the_first_spelling(self):
        candidate = CandidateProfile(skills=("Python", "python", " Python "))

        result = match_candidate_to_requirements(candidate, JobRequirements(skills=("Experience with Python",)))

        assert result.skills == (SkillMatch(statement="Experience with Python", evidence=("Python",)),)

    def test_candidate_skills_differing_only_in_whitespace_runs_are_one_skill(self):
        candidate = CandidateProfile(skills=("Spring Boot", "spring   boot"))

        result = match_candidate_to_requirements(candidate, JobRequirements(skills=("Experience with Spring Boot",)))

        assert result.skills[0].evidence == ("Spring Boot",)

    def test_a_candidate_skill_with_surrounding_whitespace_is_found_and_reported_trimmed(self):
        assert evidence_of(("  Python  ",), "Experience with Python") == ("Python",)
        assert evidence_of((" Spring   Boot ",), "Experience with Spring Boot") == ("Spring   Boot",)

    def test_blank_candidate_skills_are_ignored(self):
        assert evidence_of(("", "   ", "\t", "Python"), "Experience with Python") == ("Python",)
        assert evidence_of(("", "   ", "\t"), "Experience with Python") == ()

    def test_blank_job_statements_are_ignored_in_every_dimension(self):
        requirements = JobRequirements(
            skills=("", "   ", "Experience with Python"), experience=("", "\t"), education=("  ",)
        )

        result = match_candidate_to_requirements(CandidateProfile(skills=("Python",)), requirements)

        assert result == MatchResult(skills=(SkillMatch(statement="Experience with Python", evidence=("Python",)),))

    def test_statements_are_reported_trimmed_but_otherwise_verbatim(self):
        result = match(
            ("Python",),
            skills=("  Experience  with Python (e.g., Django).  ",),
            experience=("  3 years  of practice ",),
            education=("\tBachelor's degree\n",),
        )

        assert result.skills[0].statement == "Experience  with Python (e.g., Django)."
        assert result.unevaluated_experience == ("3 years  of practice",)
        assert result.unevaluated_education == ("Bachelor's degree",)

    def test_duplicate_job_statements_keep_only_the_first_spelling(self):
        requirements = JobRequirements(
            skills=("Experience with Python", "experience with python", " Experience with Python ")
        )

        result = match_candidate_to_requirements(CandidateProfile(skills=("Python",)), requirements)

        assert result.skills == (SkillMatch(statement="Experience with Python", evidence=("Python",)),)

    def test_job_statements_differing_only_in_whitespace_runs_are_one_statement(self):
        requirements = JobRequirements(skills=("Experience with Python", "Experience   with   Python"))

        result = match_candidate_to_requirements(CandidateProfile(skills=("Python",)), requirements)

        assert [item.statement for item in result.skills] == ["Experience with Python"]

    def test_distinct_statements_are_not_merged(self):
        result = match(("Python",), skills=("Experience with Python", "Knowledge of Python"))

        assert [item.statement for item in result.skills] == ["Experience with Python", "Knowledge of Python"]

    def test_the_input_objects_are_not_modified_by_deduplication(self):
        candidate = CandidateProfile(skills=("Python", "python", " Python "))
        requirements = JobRequirements(skills=("Experience with Python", "experience with python"))

        match_candidate_to_requirements(candidate, requirements)

        assert candidate.skills == ("Python", "python", " Python ")
        assert requirements.skills == ("Experience with Python", "experience with python")


class TestResultOrdering:
    def test_evidence_follows_candidate_order_not_statement_order(self):
        assert evidence_of(("Docker", "Python", "SQL"), PYTHON_SQL_DOCKER) == ("Docker", "Python", "SQL")

    def test_evidence_order_changes_with_candidate_order(self):
        assert evidence_of(("SQL", "Docker", "Python"), PYTHON_SQL_DOCKER) == ("SQL", "Docker", "Python")

    def test_statements_follow_requirement_order(self):
        statements = ("Knowledge of Rust", "Experience with Python", "Experience with Go", "Knowledge of Java")

        result = match(("Python",), skills=statements)

        assert [item.statement for item in result.skills] == list(statements)

    def test_statement_order_is_kept_when_only_some_statements_have_evidence(self):
        result = match(("Python", "Java"), skills=("Knowledge of Rust", "Knowledge of Java", "Experience with Python"))

        assert [(item.statement, item.evidence) for item in result.skills] == [
            ("Knowledge of Rust", ()),
            ("Knowledge of Java", ("Java",)),
            ("Experience with Python", ("Python",)),
        ]

    def test_the_first_seen_spelling_and_position_of_a_duplicated_candidate_skill_win(self):
        assert evidence_of(("Docker", "PYTHON", "SQL", "python"), PYTHON_SQL_DOCKER) == ("Docker", "PYTHON", "SQL")


class TestStatementEvidenceSemantics:
    def test_a_multi_concept_statement_stays_one_statement(self):
        result = match(("Python", "SQL", "Docker"), skills=(PYTHON_SQL_DOCKER,))

        assert result.skills == (SkillMatch(statement=PYTHON_SQL_DOCKER, evidence=("Python", "SQL", "Docker")),)
        assert [item.statement for item in result.skills] != ["Python", "SQL", "Docker"]

    def test_partial_evidence_is_reported_as_evidence_only(self):
        result = match(("Python",), skills=(PYTHON_SQL_DOCKER,))

        assert result.skills == (SkillMatch(statement=PYTHON_SQL_DOCKER, evidence=("Python",)),)

    def test_no_evidence_is_an_empty_tuple(self):
        result = match(("Python",), skills=("Experience with Java and Docker",))

        assert result.skills[0].evidence == ()

    @pytest.mark.parametrize(
        "name",
        ["score", "percentage", "rank", "qualifies", "recommendation", "winner", "confidence", "satisfied", "matched", "count", "total"],
    )
    def test_the_result_has_no_score_verdict_or_aggregate(self, name):
        result = match(("Python",), skills=(PYTHON_SQL_DOCKER,), experience=("2+ years",), education=("BSc",))

        assert not hasattr(result, name)
        assert not hasattr(result.skills[0], name)

    def test_the_result_exposes_exactly_the_approved_fields(self):
        result = match(("Python",), skills=(PYTHON_SQL_DOCKER,))

        assert [f.name for f in dataclasses.fields(result)] == ["skills", "unevaluated_experience", "unevaluated_education"]
        assert [f.name for f in dataclasses.fields(result.skills[0])] == ["statement", "evidence"]

    def test_the_statement_is_reported_verbatim(self):
        statement = "Experience with  Python  (e.g., Django)."

        assert match(("Python",), skills=(statement,)).skills[0].statement == statement


class TestUnevaluatedDimensions:
    def test_experience_statements_are_carried_through_unevaluated(self):
        candidate = CandidateProfile(
            skills=("Python",),
            experience=(Experience(title="Backend Developer", organization="Example", start="2024", end="2026"),),
        )
        requirements = JobRequirements(experience=("2+ years of backend development",))

        result = match_candidate_to_requirements(candidate, requirements)

        assert result == MatchResult(unevaluated_experience=("2+ years of backend development",))

    def test_candidate_experience_records_never_change_the_result(self):
        requirements = JobRequirements(experience=("2+ years of backend development",))
        with_experience = CandidateProfile(
            experience=(Experience(title="Backend Developer", organization="Example", start="2024", end="2026"),)
        )

        assert match_candidate_to_requirements(with_experience, requirements) == match_candidate_to_requirements(
            CandidateProfile(), requirements
        )

    def test_candidate_skills_are_not_treated_as_experience(self):
        result = match(("Python",), experience=("Experience with Python",))

        assert result == MatchResult(unevaluated_experience=("Experience with Python",))

    def test_education_statements_are_carried_through_unevaluated(self):
        candidate = CandidateProfile(
            education=(
                Education(institution="Example University", degree="Bachelor of Computer Applications", field="Computer Science"),
            )
        )
        requirements = JobRequirements(education=("Master's degree in Computer Science",))

        result = match_candidate_to_requirements(candidate, requirements)

        assert result == MatchResult(unevaluated_education=("Master's degree in Computer Science",))

    def test_candidate_education_records_never_change_the_result(self):
        requirements = JobRequirements(education=("Bachelor's degree in Computer Science",))
        with_education = CandidateProfile(
            education=(Education(institution="Example University", degree="BSc", field="Computer Science"),)
        )

        assert match_candidate_to_requirements(with_education, requirements) == match_candidate_to_requirements(
            CandidateProfile(), requirements
        )

    def test_unevaluated_statements_are_plain_strings_in_requirement_order(self):
        result = match(
            (),
            experience=("3 years of practice", "Experience building REST APIs"),
            education=("Enrolled in a relevant degree program", "Bachelor's degree in Computer Science"),
        )

        assert result.unevaluated_experience == ("3 years of practice", "Experience building REST APIs")
        assert result.unevaluated_education == ("Enrolled in a relevant degree program", "Bachelor's degree in Computer Science")

    def test_duplicate_unevaluated_statements_are_reported_once_keeping_the_first(self):
        result = match(
            (),
            experience=("3 years of practice", "3 YEARS OF PRACTICE", " 3 years of practice "),
            education=("Bachelor's degree", "bachelor's degree"),
        )

        assert result.unevaluated_experience == ("3 years of practice",)
        assert result.unevaluated_education == ("Bachelor's degree",)

    def test_a_statement_in_skills_and_experience_appears_in_both_fields(self):
        result = match(("Python",), skills=("Experience with Python",), experience=("Experience with Python",))

        assert result.skills == (SkillMatch(statement="Experience with Python", evidence=("Python",)),)
        assert result.unevaluated_experience == ("Experience with Python",)
        assert result.unevaluated_education == ()

    def test_a_statement_in_skills_and_education_appears_in_both_fields(self):
        statement = "Knowledge of Python and a Bachelor's degree"

        result = match(("Python",), skills=(statement,), education=(statement,))

        assert result.skills == (SkillMatch(statement=statement, evidence=("Python",)),)
        assert result.unevaluated_education == (statement,)

    def test_a_statement_in_all_three_dimensions_is_never_counted_or_merged(self):
        statement = "3 years of experience with Python and a Bachelor's degree"

        result = match(("Python",), skills=(statement,), experience=(statement,), education=(statement,))

        assert result == MatchResult(
            skills=(SkillMatch(statement=statement, evidence=("Python",)),),
            unevaluated_experience=(statement,),
            unevaluated_education=(statement,),
        )


class TestEmptyInputs:
    def test_an_empty_candidate_with_skill_requirements_has_no_evidence(self):
        result = match_candidate_to_requirements(
            CandidateProfile(), JobRequirements(skills=("Experience with Python",))
        )

        assert result == MatchResult(skills=(SkillMatch(statement="Experience with Python", evidence=()),))

    def test_a_candidate_with_empty_requirements_gives_an_empty_result(self):
        assert match_candidate_to_requirements(CandidateProfile(skills=("Python",)), JobRequirements()) == MatchResult()

    def test_an_empty_candidate_with_empty_requirements_gives_an_empty_result(self):
        assert match_candidate_to_requirements(CandidateProfile(), JobRequirements()) == MatchResult()

    def test_no_skill_requirements_but_experience_requirements_exist(self):
        result = match(("Python",), experience=("2+ years of backend development",))

        assert result.skills == ()
        assert result.unevaluated_experience == ("2+ years of backend development",)
        assert result.unevaluated_education == ()

    def test_no_skill_requirements_but_education_requirements_exist(self):
        result = match(("Python",), education=("Bachelor's degree in Computer Science",))

        assert result.skills == ()
        assert result.unevaluated_education == ("Bachelor's degree in Computer Science",)
        assert result.unevaluated_experience == ()

    def test_empty_requirements_are_not_reported_as_a_candidate_failure(self):
        result = match(("Python",))

        assert result == MatchResult()
        assert result.skills == ()


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidateProfile", None, 123, ["Python"], {"skills": ("Python",)}, JobRequirements()],
        ids=["str", "none", "int", "list", "dict", "job-requirements"],
    )
    def test_a_non_candidate_profile_first_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_requirements(value, JobRequirements())

        assert "candidate" in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "value",
        ["not a JobRequirements", None, 123, ["Experience with Python"], {"skills": ()}, CandidateProfile()],
        ids=["str", "none", "int", "list", "dict", "candidate-profile"],
    )
    def test_a_non_job_requirements_second_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_requirements(CandidateProfile(), value)

        assert "requirements" in str(exc_info.value).lower()

    def test_the_message_is_static_for_the_candidate_argument(self):
        messages = set()
        for value in ["first invalid value", SYNTHETIC_PRIVATE_MARKER, 42]:
            with pytest.raises(TypeError) as exc_info:
                match_candidate_to_requirements(value, JobRequirements())
            messages.add(str(exc_info.value))

        assert len(messages) == 1
        assert SYNTHETIC_PRIVATE_MARKER not in messages.pop()

    def test_the_message_is_static_for_the_requirements_argument(self):
        messages = set()
        for value in ["first invalid value", SYNTHETIC_PRIVATE_MARKER, 42]:
            with pytest.raises(TypeError) as exc_info:
                match_candidate_to_requirements(CandidateProfile(), value)
            messages.add(str(exc_info.value))

        assert len(messages) == 1
        assert SYNTHETIC_PRIVATE_MARKER not in messages.pop()

    def test_the_messages_never_contain_candidate_skills_or_job_requirements(self):
        candidate = CandidateProfile(skills=(SYNTHETIC_PRIVATE_MARKER,))
        requirements = JobRequirements(skills=(SYNTHETIC_PRIVATE_MARKER,))

        with pytest.raises(TypeError) as first:
            match_candidate_to_requirements(requirements, requirements)
        with pytest.raises(TypeError) as second:
            match_candidate_to_requirements(candidate, candidate)

        for exc_info in (first, second):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None

    def test_valid_dataclasses_with_unusual_content_are_accepted_without_field_validation(self):
        candidate = CandidateProfile(skills=("", "   ", "Python"))
        requirements = JobRequirements(skills=("", "Experience with Python"))

        result = match_candidate_to_requirements(candidate, requirements)

        assert isinstance(result, MatchResult)


class TestImmutability:
    def result(self) -> MatchResult:
        return match(
            ("Python", "SQL"),
            skills=(PYTHON_SQL_DOCKER, "Knowledge of Rust"),
            experience=("3 years of practice",),
            education=("Bachelor's degree",),
        )

    @pytest.mark.parametrize("field", ["skills", "unevaluated_experience", "unevaluated_education"])
    def test_result_fields_cannot_be_reassigned(self, field):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(self.result(), field, ())

    @pytest.mark.parametrize("field", ["statement", "evidence"])
    def test_nested_skill_records_cannot_be_reassigned(self, field):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(self.result().skills[0], field, "changed")

    def test_the_result_and_its_records_are_frozen_dataclasses(self):
        result = self.result()

        assert type(result).__dataclass_params__.frozen is True
        assert type(result.skills[0]).__dataclass_params__.frozen is True

    def test_all_collections_are_tuples_and_no_mutable_container_is_exposed(self):
        result = self.result()

        assert isinstance(result.skills, tuple)
        assert isinstance(result.unevaluated_experience, tuple)
        assert isinstance(result.unevaluated_education, tuple)
        assert all(isinstance(item.evidence, tuple) for item in result.skills)
        assert_only_immutable(result)

    def test_the_result_is_hashable_and_equal_results_hash_equally(self):
        assert hash(self.result()) == hash(self.result())
        assert len({self.result(), self.result()}) == 1

    def test_the_inputs_are_not_mutated(self):
        experience = (Experience(title="Backend Developer", organization="Example", start="2024", end=None),)
        education = (Education(institution="Example University", degree="BSc", field="Computer Science"),)
        candidate = CandidateProfile(skills=("Python", "python", " SQL "), experience=experience, education=education)
        requirements = JobRequirements(
            skills=(PYTHON_SQL_DOCKER, "experience with python sql and docker"),
            experience=("3 years of practice", "3 YEARS OF PRACTICE"),
            education=("Bachelor's degree",),
        )
        candidate_skills, requirement_skills = candidate.skills, requirements.skills
        candidate_snapshot = CandidateProfile(skills=candidate.skills, experience=experience, education=education)
        requirements_snapshot = JobRequirements(
            skills=requirements.skills, experience=requirements.experience, education=requirements.education
        )

        match_candidate_to_requirements(candidate, requirements)

        assert candidate == candidate_snapshot
        assert requirements == requirements_snapshot
        assert candidate.skills is candidate_skills and candidate.skills == ("Python", "python", " SQL ")
        assert requirements.skills is requirement_skills
        assert candidate.experience == experience and candidate.education == education


class TestDeterminism:
    def test_the_same_inputs_give_equal_results(self):
        first = match(("Docker", "Python"), skills=(PYTHON_SQL_DOCKER,), experience=("3 years",), education=("BSc",))
        second = match(("Docker", "Python"), skills=(PYTHON_SQL_DOCKER,), experience=("3 years",), education=("BSc",))

        assert first == second

    def test_repeated_calls_on_the_same_objects_give_equal_results(self):
        candidate = CandidateProfile(skills=("Docker", "Python", "SQL"))
        requirements = JobRequirements(skills=(PYTHON_SQL_DOCKER, "Knowledge of Rust"))

        results = [match_candidate_to_requirements(candidate, requirements) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_the_result_does_not_depend_on_the_interpreters_hash_seed(self):
        script = (
            "from candidate import CandidateProfile; "
            "from job_requirements import JobRequirements; "
            "from matcher import match_candidate_to_requirements as m; "
            "r = m(CandidateProfile(skills=('Docker', 'Python', 'SQL', 'Go', 'C++', 'python')), "
            "JobRequirements(skills=('Experience with Python, SQL and Docker', 'Knowledge of C++ or Go', "
            "'Experience with Rust', 'experience with rust'), experience=('2+ years', '2+ YEARS'), "
            "education=('BSc', 'bsc'))); "
            "print(repr(r))"
        )

        outputs = []
        for seed in ("0", "1", "12345"):
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONHASHSEED": seed},
            )
            assert result.returncode == 0, result.stderr
            outputs.append(result.stdout)

        assert outputs[0] == outputs[1] == outputs[2]


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        match(
            (SYNTHETIC_PRIVATE_MARKER, "Python"),
            skills=(f"Experience with {SYNTHETIC_PRIVATE_MARKER} and Python",),
            experience=(f"2+ years of {SYNTHETIC_PRIVATE_MARKER}",),
            education=(f"Degree in {SYNTHETIC_PRIVATE_MARKER}",),
        )

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match(("Python",), skills=(PYTHON_SQL_DOCKER,), experience=("3 years",), education=("BSc",))

        assert list(tmp_path.iterdir()) == []

    def test_the_result_holds_only_what_the_inputs_provided(self):
        result = match(("Python",), skills=(PYTHON_SQL_DOCKER,))

        assert SYNTHETIC_PRIVATE_MARKER not in repr(result)


class TestDependencyIsolation:
    @pytest.mark.parametrize(
        "module",
        [
            "selenium",
            "pandas",
            "webdriver_manager",
            "pdfplumber",
            "models",
            "candidate_parser",
            "job_requirements_parser",
            "resume_pdf",
            "browser",
            "job_extractor",
            "job_page_parser",
            "job_storage",
            "linkedin_scraper",
            "config",
            "main",
            "socket",
            "urllib",
            "http",
            "requests",
            "ssl",
        ],
    )
    def test_importing_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
