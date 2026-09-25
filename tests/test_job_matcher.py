"""Tests for job_matcher: the composition-only orchestration of a Job against a candidate (Task 1.7).

match_candidate_to_job(candidate, job) must equal
match_candidate_to_requirements(candidate, extract_job_requirements(job.description)) and use nothing
of the Job except its description. All data here is synthetic.
"""

import dataclasses
import inspect
import subprocess
import sys
import types
from pathlib import Path

import pytest

import job_matcher
from candidate import CandidateProfile, Education, Experience
from job_matcher import match_candidate_to_job
from job_requirements import JobRequirements
from job_requirements_parser import extract_job_requirements
from matcher import MatchResult, SkillMatch, match_candidate_to_requirements
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"

BULLET_DOT = chr(0x2022)

ENGLISH_DESCRIPTION = "\n".join(
    [
        "About the job",
        "",
        "Acme builds software.",
        "",
        "Requirements",
        "",
        "- Solid experience with Python and SQL",
        "- Currently enrolled in a Computer Science or related degree",
        "- At least 2 years of relevant work experience",
        "- Fluent English",
        "",
        "Nice to have",
        "",
        "- Experience with Docker",
    ]
)

GERMAN_DESCRIPTION = "\n".join(
    [
        "About the job",
        "",
        "Wir bauen Software.",
        "",
        "Was du mitbringen solltest",
        "",
        "Du solltest bereits produktive Systeme gebaut haben.",
        "",
        "Wichtig sind uns insbesondere:",
        "",
        f"{BULLET_DOT} praktische Erfahrung mit TypeScript oder Python",
        f"{BULLET_DOT} Kenntnisse in SQL",
        f"{BULLET_DOT} Deutschkenntnisse mind. C1",
        f"{BULLET_DOT} mindestens 3 Jahre Berufserfahrung",
        f"{BULLET_DOT} abgeschlossenes Informatikstudium",
        "",
        "Was wir dir bieten",
        "",
        f"{BULLET_DOT} Flexible Arbeitszeiten",
    ]
)

PYTHON_ONLY_DESCRIPTION = "Requirements\n\n- Knowledge of Python"


def make_job(**overrides) -> Job:
    fields = {
        "title": "Working Student Software Engineer",
        "company": "Acme GmbH",
        "location": "Berlin, Germany",
        "description": ENGLISH_DESCRIPTION,
        "url": "https://www.linkedin.com/jobs/view/3812345678/",
    }
    fields.update(overrides)
    return Job(**fields)


def make_candidate(*skills: str) -> CandidateProfile:
    return CandidateProfile(skills=tuple(skills))


def composed(candidate: CandidateProfile, job: Job) -> MatchResult:
    return match_candidate_to_requirements(candidate, extract_job_requirements(job.description))


class TestComposition:
    @pytest.mark.parametrize(
        "description",
        [
            ENGLISH_DESCRIPTION,
            GERMAN_DESCRIPTION,
            PYTHON_ONLY_DESCRIPTION,
            "Qualifications\n\n- Experience with Python, SQL and Docker",
            "We build software.\nJoin our team.",
            "",
            "   \n\t ",
            "No description available",
        ],
        ids=["english", "german", "python-only", "multi-skill", "prose", "empty", "whitespace", "sentinel"],
    )
    @pytest.mark.parametrize(
        "candidate",
        [
            CandidateProfile(),
            make_candidate("Python"),
            make_candidate("Docker", "Python", "SQL", "TypeScript", "Java"),
        ],
        ids=["empty-candidate", "one-skill", "many-skills"],
    )
    def test_the_result_equals_extracting_and_then_matching_by_hand(self, candidate, description):
        job = make_job(description=description)

        assert match_candidate_to_job(candidate, job) == composed(candidate, job)

    def test_the_arguments_can_be_passed_by_keyword(self):
        candidate, job = make_candidate("Python"), make_job()

        assert match_candidate_to_job(candidate=candidate, job=job) == composed(candidate, job)

    def test_the_public_parameters_are_exactly_candidate_and_job(self):
        assert list(inspect.signature(match_candidate_to_job).parameters) == ["candidate", "job"]

    def test_the_return_value_is_exactly_a_match_result(self):
        result = match_candidate_to_job(make_candidate("Python"), make_job())

        assert type(result) is MatchResult


class TestExpectedResults:
    def test_a_candidate_with_skills_against_a_job_with_recognised_requirements(self):
        result = match_candidate_to_job(make_candidate("Python", "SQL", "Java"), make_job())

        assert result == MatchResult(
            skills=(SkillMatch(statement="Solid experience with Python and SQL", evidence=("Python", "SQL")),),
            unevaluated_experience=(
                "Solid experience with Python and SQL",
                "At least 2 years of relevant work experience",
            ),
            unevaluated_education=("Currently enrolled in a Computer Science or related degree",),
        )

    def test_an_empty_candidate_against_a_valid_job_has_no_evidence(self):
        result = match_candidate_to_job(CandidateProfile(), make_job())

        assert result == MatchResult(
            skills=(SkillMatch(statement="Solid experience with Python and SQL", evidence=()),),
            unevaluated_experience=(
                "Solid experience with Python and SQL",
                "At least 2 years of relevant work experience",
            ),
            unevaluated_education=("Currently enrolled in a Computer Science or related degree",),
        )

    def test_a_german_description_is_read_and_matched(self):
        result = match_candidate_to_job(make_candidate("TypeScript", "Python", "SQL", "Java"), make_job(description=GERMAN_DESCRIPTION))

        assert result == MatchResult(
            skills=(
                SkillMatch(statement="praktische Erfahrung mit TypeScript oder Python", evidence=("TypeScript", "Python")),
                SkillMatch(statement="Kenntnisse in SQL", evidence=("SQL",)),
            ),
            unevaluated_experience=("praktische Erfahrung mit TypeScript oder Python", "mindestens 3 Jahre Berufserfahrung"),
            unevaluated_education=("abgeschlossenes Informatikstudium",),
        )

    def test_experience_and_education_statements_stay_unevaluated_whatever_the_candidate_records_say(self):
        candidate = CandidateProfile(
            skills=("Python",),
            experience=(Experience(title="Backend Developer", organization="Example", start="2022", end="2026"),),
            education=(Education(institution="Example University", degree="BSc", field="Computer Science"),),
        )
        description = "Requirements\n\n- 3 years of practice\n- Bachelor's degree in Computer Science"

        result = match_candidate_to_job(candidate, make_job(description=description))

        assert result == MatchResult(
            unevaluated_experience=("3 years of practice",),
            unevaluated_education=("Bachelor's degree in Computer Science",),
        )

    def test_one_statement_matching_several_candidate_skills_keeps_candidate_order_in_its_evidence(self):
        description = "Qualifications\n\n- Experience with Python, SQL and Docker"

        result = match_candidate_to_job(make_candidate("Docker", "Python", "SQL"), make_job(description=description))

        assert result == MatchResult(
            skills=(
                SkillMatch(statement="Experience with Python, SQL and Docker", evidence=("Docker", "Python", "SQL")),
            ),
            unevaluated_experience=("Experience with Python, SQL and Docker",),
        )

    def test_duplicate_requirement_statements_are_reported_once(self):
        description = "Requirements\n\n- Knowledge of Python\n- knowledge of python\n- Knowledge of Python"

        result = match_candidate_to_job(make_candidate("Python"), make_job(description=description))

        assert result == MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=("Python",)),))


class TestDescriptionsWithoutRequirements:
    @pytest.mark.parametrize(
        "description",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="spaces"),
            pytest.param("\n\n \t \n", id="whitespace-only"),
            pytest.param("No description available", id="sentinel-literal"),
            pytest.param("We build software.\nJoin our team.", id="prose-only"),
            pytest.param("Benefits\n\n- Knowledge of Python", id="unlisted-heading"),
            pytest.param("Nice to have\n\n- Knowledge of Python", id="only-optional-section"),
        ],
    )
    def test_a_description_without_recognised_requirements_gives_an_empty_result(self, description):
        result = match_candidate_to_job(make_candidate("Python"), make_job(description=description))

        assert result == MatchResult()

    def test_the_scrapers_missing_description_sentinel_gives_an_empty_result(self):
        job = Job.from_scraped_data({"title": "Engineer", "company": "Acme"})

        assert job.description == "No description available"
        assert match_candidate_to_job(make_candidate("Python"), job) == MatchResult()

    def test_an_empty_candidate_and_an_empty_description_give_an_empty_result(self):
        assert match_candidate_to_job(CandidateProfile(), make_job(description="")) == MatchResult()


class TestDescriptionFormats:
    def test_requirements_after_a_very_long_description_are_still_found(self):
        filler = "We build software for many customers. " * 400
        description = filler + "\n\n" + PYTHON_ONLY_DESCRIPTION

        result = match_candidate_to_job(make_candidate("Python"), make_job(description=description))

        assert len(description) > 12_000
        assert result == MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=("Python",)),))

    def test_the_description_reaches_the_extractor_verbatim_including_a_bullet_dot_inside_a_statement(self):
        statement = f"Knowledge of Python {BULLET_DOT} SQL"

        result = match_candidate_to_job(make_candidate("Python"), make_job(description=f"Requirements\n\n- {statement}"))

        assert result == MatchResult(skills=(SkillMatch(statement=statement, evidence=("Python",)),))

    @pytest.mark.parametrize("newline", ["\r\n", "\r"])
    def test_windows_and_old_mac_line_endings_give_the_same_result_as_unix_ones(self, newline):
        candidate = make_candidate("Python", "SQL")
        unix = make_job(description=ENGLISH_DESCRIPTION)
        other = make_job(description=ENGLISH_DESCRIPTION.replace("\n", newline))

        assert match_candidate_to_job(candidate, other) == match_candidate_to_job(candidate, unix)

    def test_a_german_description_with_windows_line_endings_gives_the_same_result(self):
        candidate = make_candidate("TypeScript", "Python", "SQL")

        assert match_candidate_to_job(candidate, make_job(description=GERMAN_DESCRIPTION.replace("\n", "\r\n"))) == (
            match_candidate_to_job(candidate, make_job(description=GERMAN_DESCRIPTION))
        )

    @pytest.mark.parametrize("marker_separator", ["\n", "\n\n"])
    def test_a_trailing_truncation_marker_does_not_change_the_result(self, marker_separator):
        candidate = make_candidate("Python")
        plain = make_job(description=PYTHON_ONLY_DESCRIPTION)
        truncated = make_job(description=PYTHON_ONLY_DESCRIPTION + marker_separator + "[truncated]")

        expected = MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=("Python",)),))
        assert match_candidate_to_job(candidate, plain) == expected
        assert match_candidate_to_job(candidate, truncated) == expected


class TestOnlyTheDescriptionIsUsed:
    @pytest.mark.parametrize("field", ["title", "company", "location", "url"])
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "Unknown Title",
            "Some Other Value",
            "Requirements",
            "- Knowledge of Python",
            "Requirements\n\n- Knowledge of Python",
            "https://www.linkedin.com/jobs/view/1/",
        ],
        ids=["empty", "sentinel-like", "other", "heading-text", "bullet-text", "requirement-text", "url-like"],
    )
    def test_changing_any_other_job_field_never_changes_the_result(self, field, value):
        candidate = make_candidate("Python", "SQL", "Java")
        baseline = make_job()

        changed = dataclasses.replace(baseline, **{field: value})

        assert match_candidate_to_job(candidate, changed) == match_candidate_to_job(candidate, baseline)

    @pytest.mark.parametrize("field", ["title", "company", "location", "url"])
    @pytest.mark.parametrize("description", ["", "   ", "\n\t\n"], ids=["empty", "spaces", "whitespace-only"])
    def test_another_field_is_never_used_as_a_fallback_for_an_empty_description(self, field, description):
        job = make_job(description=description)
        job = dataclasses.replace(job, **{field: PYTHON_ONLY_DESCRIPTION})

        assert match_candidate_to_job(make_candidate("Python"), job) == MatchResult()

    def test_requirement_like_text_in_other_fields_is_not_matched_when_the_description_has_none(self):
        job = make_job(
            title="Knowledge of Python",
            company="Requirements",
            location="- Knowledge of Python",
            url="https://example.invalid/Knowledge-of-Python",
            description="We build software.",
        )

        assert match_candidate_to_job(make_candidate("Python"), job) == MatchResult()


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidateProfile", None, 123, ["Python"], {"skills": ("Python",)}, make_job(), JobRequirements()],
        ids=["str", "none", "int", "list", "dict", "job", "job-requirements"],
    )
    def test_a_non_candidate_profile_raises_the_static_candidate_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job(value, make_job())

        assert str(exc_info.value) == "candidate must be a CandidateProfile"

    @pytest.mark.parametrize(
        "value",
        ["not a Job", None, 123, ["description"], {"description": "Requirements"}, CandidateProfile(), JobRequirements()],
        ids=["str", "none", "int", "list", "dict", "candidate-profile", "job-requirements"],
    )
    def test_a_non_job_raises_the_static_job_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job(make_candidate("Python"), value)

        assert str(exc_info.value) == "job must be a Job"

    def test_an_object_that_only_looks_like_a_job_is_rejected(self):
        look_alike = types.SimpleNamespace(
            title="t", company="c", location="l", url="u", description=PYTHON_ONLY_DESCRIPTION
        )

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job(make_candidate("Python"), look_alike)

        assert str(exc_info.value) == "job must be a Job"

    def test_an_object_that_only_looks_like_a_candidate_profile_is_rejected(self):
        look_alike = types.SimpleNamespace(skills=("Python",), experience=(), education=())

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job(look_alike, make_job())

        assert str(exc_info.value) == "candidate must be a CandidateProfile"

    def test_a_candidate_look_alike_is_rejected_before_the_job_is_examined(self):
        look_alike = types.SimpleNamespace(skills=("Python",), experience=(), education=())

        for job in ["not a Job", make_job(description=None)]:
            with pytest.raises(TypeError) as exc_info:
                match_candidate_to_job(look_alike, job)

            assert str(exc_info.value) == "candidate must be a CandidateProfile"

    def test_subclasses_of_candidate_profile_and_job_are_accepted(self):
        class SpecialCandidate(CandidateProfile):
            pass

        class SpecialJob(Job):
            pass

        candidate = SpecialCandidate(skills=("Python", "SQL"))
        job = SpecialJob(title="t", company="c", location="l", description=ENGLISH_DESCRIPTION)

        assert match_candidate_to_job(candidate, job) == composed(candidate, job)
        assert match_candidate_to_job(candidate, job) == match_candidate_to_job(make_candidate("Python", "SQL"), make_job())

    def test_the_candidate_is_validated_before_the_job(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job("not a CandidateProfile", "not a Job")

        assert str(exc_info.value) == "candidate must be a CandidateProfile"

    def test_swapped_arguments_report_the_candidate_first(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job(make_job(), make_candidate("Python"))

        assert str(exc_info.value) == "candidate must be a CandidateProfile"

    def test_an_invalid_candidate_is_rejected_even_when_the_jobs_description_is_also_invalid(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job("not a CandidateProfile", make_job(description=None))

        assert str(exc_info.value) == "candidate must be a CandidateProfile"

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_candidate = CandidateProfile(skills=(SYNTHETIC_PRIVATE_MARKER,))
        secret_job = make_job(title=SYNTHETIC_PRIVATE_MARKER, description=SYNTHETIC_PRIVATE_MARKER)

        with pytest.raises(TypeError) as candidate_error:
            match_candidate_to_job([SYNTHETIC_PRIVATE_MARKER], secret_job)
        with pytest.raises(TypeError) as job_error:
            match_candidate_to_job(secret_candidate, {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        for exc_info in (candidate_error, job_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestNonStringDescriptions:
    @pytest.mark.parametrize(
        "description",
        [None, 123, 1.5, ["Requirements"], b"Requirements", ("Requirements",)],
        ids=["none", "int", "float", "list", "bytes", "tuple"],
    )
    def test_the_extractors_type_error_propagates_unchanged(self, description):
        job = make_job(description=description)

        with pytest.raises(TypeError) as from_extractor:
            extract_job_requirements(description)
        with pytest.raises(TypeError) as from_job_matcher:
            match_candidate_to_job(make_candidate("Python"), job)

        assert str(from_job_matcher.value) == "description must be a str"
        assert str(from_job_matcher.value) == str(from_extractor.value)
        assert type(from_job_matcher.value) is type(from_extractor.value)

    def test_the_propagated_message_never_contains_the_description(self):
        job = make_job(description=[SYNTHETIC_PRIVATE_MARKER])

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_job(make_candidate("Python"), job)

        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
        assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)


class TestImmutabilityAndDeterminism:
    def test_the_candidate_and_the_job_are_not_modified(self):
        candidate = CandidateProfile(
            skills=("Python", "python", " SQL "),
            experience=(Experience(title="Backend Developer", organization="Example", start="2022", end=None),),
            education=(Education(institution="Example University", degree="BSc", field="Computer Science"),),
        )
        job = make_job()
        candidate_snapshot = dataclasses.replace(candidate)
        job_snapshot = dataclasses.replace(job)

        match_candidate_to_job(candidate, job)

        assert candidate == candidate_snapshot
        assert job == job_snapshot
        assert candidate.skills == ("Python", "python", " SQL ")
        assert job.description == ENGLISH_DESCRIPTION

    def test_the_result_is_immutable(self):
        result = match_candidate_to_job(make_candidate("Python", "SQL"), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.skills = ()
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.skills[0].evidence = ()
        assert isinstance(hash(result), int)

    def test_repeated_calls_give_equal_results(self):
        candidate, job = make_candidate("Docker", "Python", "SQL"), make_job()

        results = [match_candidate_to_job(candidate, job) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_equal_but_separately_built_inputs_give_equal_results(self):
        first = match_candidate_to_job(make_candidate("Python", "SQL"), make_job())
        second = match_candidate_to_job(make_candidate("Python", "SQL"), make_job())

        assert first == second
        assert first is not second


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        description = f"Requirements\n\n- Experience with {SYNTHETIC_PRIVATE_MARKER} and Python\n\n{SYNTHETIC_PRIVATE_MARKER}"

        match_candidate_to_job(make_candidate(SYNTHETIC_PRIVATE_MARKER, "Python"), make_job(description=description))

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_the_module_holds_no_mutable_module_level_state(self):
        mutable = [
            name
            for name, value in vars(job_matcher).items()
            if not name.startswith("__") and isinstance(value, (list, dict, set, bytearray))
        ]

        assert mutable == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_candidate_to_job(make_candidate("Python", "SQL"), make_job())

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
    # models is a legitimate dependency (it brings urllib.parse), so neither is forbidden here.
    @pytest.mark.parametrize(
        "module",
        [
            "browser",
            "linkedin_scraper",
            "job_extractor",
            "job_storage",
            "selenium",
            "webdriver_manager",
            "pandas",
            "pdfplumber",
            "resume_pdf",
            "candidate_parser",
        ],
    )
    def test_importing_job_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, job_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
