"""Tests for matching_service: a thin application-level boundary around batch matching (Task 1.9).

match_candidate_against_jobs(candidate, jobs) must be pure delegation to the existing
match_candidate_to_jobs(candidate, jobs): the same arguments go in, the identical return value
comes back, and any error propagates unchanged. The service inspects nothing, transforms nothing,
and has no side effects of its own. All data here is synthetic.
"""

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

import job_batch_matcher
import matching_service
from candidate import CandidateProfile
from job_batch_matcher import match_candidate_to_jobs
from matcher import MatchResult, SkillMatch
from matching_service import match_candidate_against_jobs
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"

PYTHON_DESCRIPTION = "Requirements\n\n- Knowledge of Python"
JAVA_DESCRIPTION = "Requirements\n\n- Knowledge of Java"
NOTHING_DESCRIPTION = "We build software."

PYTHON_RESULT = MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=("Python",)),))
JAVA_RESULT = MatchResult(skills=(SkillMatch(statement="Knowledge of Java", evidence=("Java",)),))


def make_job(**overrides) -> Job:
    fields = {
        "title": "Working Student Software Engineer",
        "company": "Acme GmbH",
        "location": "Berlin, Germany",
        "description": PYTHON_DESCRIPTION,
        "url": "https://www.linkedin.com/jobs/view/3812345678/",
    }
    fields.update(overrides)
    return Job(**fields)


def make_candidate(*skills: str) -> CandidateProfile:
    return CandidateProfile(skills=tuple(skills))


def install_spy(monkeypatch, behavior=None):
    """Replace the batch matcher used by the service; record every (candidate, jobs) call."""
    calls = []

    def spy(candidate, jobs):
        calls.append((candidate, jobs))
        if behavior is not None:
            return behavior(len(calls), candidate, jobs)
        return (MatchResult(unevaluated_experience=(f"call {len(calls)}",)),)

    monkeypatch.setattr(matching_service, "match_candidate_to_jobs", spy)
    return calls


def forbid_calls(monkeypatch):
    def fail(candidate, jobs):
        raise AssertionError("the batch matcher must not be called")

    monkeypatch.setattr(matching_service, "match_candidate_to_jobs", fail)


class TestPublicApi:
    def test_the_function_is_importable_and_callable(self):
        assert callable(match_candidate_against_jobs)
        assert matching_service.match_candidate_against_jobs is match_candidate_against_jobs

    def test_the_public_parameters_are_exactly_candidate_and_jobs(self):
        assert list(inspect.signature(match_candidate_against_jobs).parameters) == ["candidate", "jobs"]

    def test_the_arguments_can_be_passed_by_keyword(self):
        candidate, jobs = make_candidate("Python"), (make_job(),)

        assert match_candidate_against_jobs(candidate=candidate, jobs=jobs) == (PYTHON_RESULT,)

    def test_the_service_uses_the_existing_batch_matcher(self):
        assert matching_service.match_candidate_to_jobs is match_candidate_to_jobs


class TestDelegation:
    def test_a_call_delegates_to_the_batch_matcher_exactly_once_with_the_same_arguments(self, monkeypatch):
        calls = install_spy(monkeypatch)
        candidate, jobs = make_candidate("Python"), (make_job(), make_job(description=JAVA_DESCRIPTION))

        match_candidate_against_jobs(candidate, jobs)

        assert len(calls) == 1
        called_candidate, called_jobs = calls[0]
        assert called_candidate is candidate
        assert called_jobs is jobs

    def test_the_candidate_is_forwarded_unchanged(self, monkeypatch):
        calls = install_spy(monkeypatch)
        candidate = make_candidate("Python", "SQL", "Java")

        match_candidate_against_jobs(candidate, (make_job(),))

        assert calls[0][0] is candidate
        assert calls[0][0].skills == ("Python", "SQL", "Java")

    def test_the_jobs_sequence_is_forwarded_unchanged_not_copied_or_coerced(self, monkeypatch):
        calls = install_spy(monkeypatch)
        jobs = (make_job(), make_job(description=JAVA_DESCRIPTION), make_job(description=NOTHING_DESCRIPTION))

        match_candidate_against_jobs(make_candidate("Python"), jobs)

        assert calls[0][1] is jobs
        assert type(calls[0][1]) is tuple

    def test_a_list_of_jobs_is_forwarded_as_the_identical_list_object(self, monkeypatch):
        calls = install_spy(monkeypatch)
        jobs = [make_job(), make_job(description=JAVA_DESCRIPTION)]

        match_candidate_against_jobs(make_candidate("Python"), jobs)

        assert calls[0][1] is jobs

    def test_the_returned_value_is_exactly_the_object_the_batch_matcher_returned(self, monkeypatch):
        sentinel = (MatchResult(unevaluated_experience=("sentinel",)),)
        install_spy(monkeypatch, lambda number, candidate, jobs: sentinel)

        result = match_candidate_against_jobs(make_candidate("Python"), (make_job(),))

        assert result is sentinel

    def test_the_individual_match_results_are_not_copied(self, monkeypatch):
        first_result = MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=("Python",)),))
        second_result = MatchResult()
        install_spy(monkeypatch, lambda number, candidate, jobs: (first_result, second_result))

        result = match_candidate_against_jobs(make_candidate("Python"), (make_job(), make_job()))

        assert result[0] is first_result
        assert result[1] is second_result

    def test_empty_jobs_still_delegates_exactly_once(self, monkeypatch):
        calls = install_spy(monkeypatch, lambda number, candidate, jobs: ())

        result = match_candidate_against_jobs(make_candidate("Python"), ())

        assert len(calls) == 1
        assert result == ()

    def test_no_second_delegation_happens_for_any_input(self, monkeypatch):
        calls = install_spy(monkeypatch)

        match_candidate_against_jobs(make_candidate("Python"), (make_job(), make_job(), make_job()))

        assert len(calls) == 1


class TestExpectedResults:
    def test_the_result_equals_calling_the_batch_matcher_directly(self):
        candidate = make_candidate("Python", "Java")
        jobs = (make_job(description=PYTHON_DESCRIPTION), make_job(description=JAVA_DESCRIPTION), make_job(description=NOTHING_DESCRIPTION))

        assert match_candidate_against_jobs(candidate, jobs) == match_candidate_to_jobs(candidate, jobs)

    def test_one_job_gives_the_same_single_element_tuple_as_the_batch_matcher(self):
        candidate, job = make_candidate("Python"), make_job()

        assert match_candidate_against_jobs(candidate, (job,)) == (PYTHON_RESULT,)

    def test_empty_jobs_gives_an_empty_tuple(self):
        assert match_candidate_against_jobs(make_candidate("Python"), ()) == ()

    def test_job_order_is_preserved_exactly_as_the_batch_matcher_preserves_it(self):
        jobs = [make_job(description=JAVA_DESCRIPTION), make_job(description=PYTHON_DESCRIPTION), make_job(description=NOTHING_DESCRIPTION)]

        result = match_candidate_against_jobs(make_candidate("Python", "Java"), jobs)

        assert result == (JAVA_RESULT, PYTHON_RESULT, MatchResult())

    def test_no_score_rank_filter_or_sort_is_applied(self):
        jobs = [make_job(description=NOTHING_DESCRIPTION), make_job(description=PYTHON_DESCRIPTION)]

        result = match_candidate_against_jobs(make_candidate("Python"), jobs)

        assert result == (MatchResult(), PYTHON_RESULT)
        assert len(result) == len(jobs)
        assert not hasattr(result, "ranked")
        assert not hasattr(result, "score")


class TestErrorPropagation:
    def test_a_type_error_from_the_batch_matcher_propagates_unchanged(self):
        with pytest.raises(TypeError) as from_batch:
            match_candidate_to_jobs("not a CandidateProfile", ())
        with pytest.raises(TypeError) as from_service:
            match_candidate_against_jobs("not a CandidateProfile", ())

        assert str(from_service.value) == str(from_batch.value)
        assert type(from_service.value) is type(from_batch.value)

    def test_an_invalid_jobs_container_propagates_the_batch_matchers_error(self):
        with pytest.raises(TypeError) as from_batch:
            match_candidate_to_jobs(make_candidate("Python"), "not a sequence")
        with pytest.raises(TypeError) as from_service:
            match_candidate_against_jobs(make_candidate("Python"), "not a sequence")

        assert str(from_service.value) == str(from_batch.value)

    def test_a_non_job_element_propagates_the_batch_matchers_error(self):
        with pytest.raises(TypeError) as from_batch:
            match_candidate_to_jobs(make_candidate("Python"), [make_job(), "not a Job"])
        with pytest.raises(TypeError) as from_service:
            match_candidate_against_jobs(make_candidate("Python"), [make_job(), "not a Job"])

        assert str(from_service.value) == str(from_batch.value)

    def test_a_non_string_description_propagates_the_extractors_error(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_against_jobs(make_candidate("Python"), [make_job(description=None)])

        assert str(exc_info.value) == "description must be a str"

    def test_an_arbitrary_exception_raised_while_matching_propagates_unchanged(self, monkeypatch):
        boom = RuntimeError("boom")
        install_spy(monkeypatch, lambda number, candidate, jobs: (_ for _ in ()).throw(boom))

        with pytest.raises(RuntimeError) as exc_info:
            match_candidate_against_jobs(make_candidate("Python"), (make_job(),))

        assert exc_info.value is boom

    def test_the_service_adds_no_exception_chaining_of_its_own(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_against_jobs("not a CandidateProfile", ())

        assert exc_info.value.__cause__ is None

    def test_error_messages_never_contain_the_arguments(self):
        secret_jobs = [make_job(title=SYNTHETIC_PRIVATE_MARKER, description=SYNTHETIC_PRIVATE_MARKER)]

        with pytest.raises(TypeError) as exc_info:
            match_candidate_against_jobs([SYNTHETIC_PRIVATE_MARKER], secret_jobs)

        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
        assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)


class TestNoIndependentLogic:
    def test_the_service_module_defines_no_matching_helper_functions(self):
        import ast

        tree = ast.parse(Path("matching_service.py").read_text(encoding="ascii"))
        names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]

        assert names == ["match_candidate_against_jobs"]

    def test_the_service_module_defines_no_classes(self):
        import ast

        tree = ast.parse(Path("matching_service.py").read_text(encoding="ascii"))

        assert [node.name for node in tree.body if isinstance(node, ast.ClassDef)] == []

    def test_the_service_does_not_import_the_single_job_matcher_or_the_requirements_parser(self):
        # Importing CandidateProfile/Job/MatchResult for type hints is fine; what must not happen is
        # reaching past job_batch_matcher into the layers it already composes.
        import ast

        tree = ast.parse(Path("matching_service.py").read_text(encoding="ascii"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }

        assert imported_modules & {"job_matcher", "job_requirements_parser"} == set()
        assert "job_batch_matcher" in imported_modules

    def test_the_service_result_is_identical_across_repeated_calls_with_the_same_objects(self):
        candidate, jobs = make_candidate("Python", "Java"), (make_job(), make_job(description=JAVA_DESCRIPTION))

        first = match_candidate_against_jobs(candidate, jobs)
        second = match_candidate_against_jobs(candidate, jobs)

        assert first == second


class TestPrivacy:
    def test_the_service_produces_no_console_output_or_log_records(self, capsys, caplog):
        description = f"Requirements\n\n- Experience with {SYNTHETIC_PRIVATE_MARKER} and Python\n\n{SYNTHETIC_PRIVATE_MARKER}"

        match_candidate_against_jobs(make_candidate(SYNTHETIC_PRIVATE_MARKER, "Python"), [make_job(description=description)])

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_the_service_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_candidate_against_jobs(make_candidate("Python"), [make_job(), make_job(description=JAVA_DESCRIPTION)])

        assert list(tmp_path.iterdir()) == []

    def test_the_module_holds_no_mutable_module_level_state(self):
        mutable = [
            name
            for name, value in vars(matching_service).items()
            if not name.startswith("__") and isinstance(value, (list, dict, set, bytearray))
        ]

        assert mutable == []


class TestDependencyIsolation:
    # job_batch_matcher (and, transitively, models/urllib) is a legitimate dependency, so it is not forbidden.
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
    def test_importing_matching_service_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, matching_service; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr

    def test_the_service_can_be_used_in_a_fresh_interpreter_without_importing_job_batch_matcher_directly(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from candidate import CandidateProfile; "
                "from matching_service import match_candidate_against_jobs; "
                "assert match_candidate_against_jobs(CandidateProfile(), ()) == ()",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
