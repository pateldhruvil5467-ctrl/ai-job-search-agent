"""Tests for job_batch_matcher: one candidate against many already-loaded Jobs (Task 1.8).

match_candidate_to_jobs(candidate, jobs) returns exactly one MatchResult per Job, in input order,
each obtained by delegating to the existing single-job matcher. It does no I/O, scoring, ranking or
recommending, and it never coerces an arbitrary iterable into a list. All data here is synthetic.
"""

import collections.abc
import dataclasses
import inspect
import subprocess
import sys
import types
from pathlib import Path

import pytest

import job_batch_matcher
import job_matcher
from candidate import CandidateProfile, Education, Experience
from job_batch_matcher import match_candidate_to_jobs
from job_matcher import match_candidate_to_job
from job_requirements import JobRequirements
from matcher import MatchResult, SkillMatch
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"

CANDIDATE_ERROR = "candidate must be a CandidateProfile"
CONTAINER_ERROR = "jobs must be a sequence of Job objects"
ELEMENT_ERROR = "jobs must contain only Job objects"

PYTHON_DESCRIPTION = "Requirements\n\n- Knowledge of Python"
JAVA_DESCRIPTION = "Requirements\n\n- Knowledge of Java"
NOTHING_DESCRIPTION = "We build software."
EXPERIENCE_EDUCATION_DESCRIPTION = "Requirements\n\n- 3 years of practice\n- Bachelor's degree"

PYTHON_RESULT = MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=("Python",)),))
JAVA_RESULT = MatchResult(skills=(SkillMatch(statement="Knowledge of Java", evidence=("Java",)),))
EXPERIENCE_EDUCATION_RESULT = MatchResult(
    unevaluated_experience=("3 years of practice",), unevaluated_education=("Bachelor's degree",)
)


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


class ReadOnlySequence(collections.abc.Sequence):
    """A Sequence that is neither list nor tuple."""

    def __init__(self, items):
        self._items = tuple(items)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)


def install_spy(monkeypatch, behavior=None):
    """Replace the single-job matcher used by the batch module; record every (candidate, job) call."""
    calls = []

    def spy(candidate, job):
        calls.append((candidate, job))
        if behavior is not None:
            return behavior(len(calls), candidate, job)
        return MatchResult(unevaluated_experience=(f"call {len(calls)}",))

    monkeypatch.setattr(job_batch_matcher, "match_candidate_to_job", spy)
    return calls


def forbid_calls(monkeypatch):
    def fail(candidate, job):
        raise AssertionError("the single-job matcher must not be called")

    monkeypatch.setattr(job_batch_matcher, "match_candidate_to_job", fail)


class TestPublicApi:
    def test_the_function_is_importable_and_callable(self):
        assert callable(match_candidate_to_jobs)
        assert job_batch_matcher.match_candidate_to_jobs is match_candidate_to_jobs

    def test_the_public_parameters_are_exactly_candidate_and_jobs(self):
        assert list(inspect.signature(match_candidate_to_jobs).parameters) == ["candidate", "jobs"]

    def test_the_arguments_can_be_passed_by_keyword(self):
        candidate, jobs = make_candidate("Python"), (make_job(),)

        assert match_candidate_to_jobs(candidate=candidate, jobs=jobs) == (PYTHON_RESULT,)

    @pytest.mark.parametrize("container", [tuple, list], ids=["tuple-input", "list-input"])
    def test_the_return_type_is_exactly_a_tuple_of_match_results(self, container):
        results = match_candidate_to_jobs(make_candidate("Python"), container([make_job(), make_job()]))

        assert type(results) is tuple
        assert all(type(result) is MatchResult for result in results)

    def test_the_batch_module_uses_the_existing_single_job_matcher(self):
        assert job_batch_matcher.match_candidate_to_job is job_matcher.match_candidate_to_job


class TestBatchResults:
    def test_empty_jobs_give_an_empty_tuple(self):
        assert match_candidate_to_jobs(make_candidate("Python"), ()) == ()
        assert match_candidate_to_jobs(make_candidate("Python"), []) == ()

    def test_an_empty_candidate_with_empty_jobs_gives_an_empty_tuple(self):
        assert match_candidate_to_jobs(CandidateProfile(), ()) == ()

    def test_one_job_gives_one_result(self):
        assert match_candidate_to_jobs(make_candidate("Python"), (make_job(),)) == (PYTHON_RESULT,)

    def test_a_job_without_requirements_gives_an_empty_result(self):
        results = match_candidate_to_jobs(make_candidate("Python"), (make_job(description=NOTHING_DESCRIPTION),))

        assert results == (MatchResult(),)

    def test_several_jobs_give_one_exact_result_each(self):
        jobs = [
            make_job(description=PYTHON_DESCRIPTION),
            make_job(description=JAVA_DESCRIPTION),
            make_job(description=NOTHING_DESCRIPTION),
            make_job(description=EXPERIENCE_EDUCATION_DESCRIPTION),
        ]

        results = match_candidate_to_jobs(make_candidate("Python", "Java"), jobs)

        assert results == (PYTHON_RESULT, JAVA_RESULT, MatchResult(), EXPERIENCE_EDUCATION_RESULT)

    @pytest.mark.parametrize(
        "order",
        [(0, 1, 2), (2, 1, 0), (1, 0, 2), (1, 2, 0), (2, 0, 1), (0, 2, 1)],
        ids=lambda order: "".join(map(str, order)),
    )
    def test_the_input_job_order_is_preserved(self, order):
        pool = {0: (PYTHON_DESCRIPTION, PYTHON_RESULT), 1: (JAVA_DESCRIPTION, JAVA_RESULT), 2: (NOTHING_DESCRIPTION, MatchResult())}
        jobs = [make_job(description=pool[index][0]) for index in order]

        results = match_candidate_to_jobs(make_candidate("Python", "Java"), jobs)

        assert results == tuple(pool[index][1] for index in order)

    @pytest.mark.parametrize("field", ["title", "company", "location", "url"])
    @pytest.mark.parametrize("values", [("C", "B", "A"), ("B", "C", "A")], ids=["descending", "rotated"])
    def test_the_input_order_is_kept_whatever_the_field_values_would_sort_to(self, field, values):
        descriptions = (PYTHON_DESCRIPTION, JAVA_DESCRIPTION, NOTHING_DESCRIPTION)
        jobs = [make_job(description=description, **{field: value}) for description, value in zip(descriptions, values)]

        results = match_candidate_to_jobs(make_candidate("Python", "Java"), jobs)

        assert results == (PYTHON_RESULT, JAVA_RESULT, MatchResult())

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("title", ""),
            ("title", "Unknown Title"),
            ("company", ""),
            ("company", "Unknown Company"),
            ("location", ""),
            ("location", "Unknown Location"),
            ("url", ""),
            ("description", ""),
            ("description", "   "),
            ("description", "No description available"),
        ],
    )
    def test_a_job_with_an_empty_or_placeholder_field_still_gets_its_own_result(self, field, value):
        candidate = make_candidate("Python", "Java")
        jobs = [make_job(description=JAVA_DESCRIPTION), make_job(**{field: value}), make_job()]

        results = match_candidate_to_jobs(candidate, jobs)

        assert len(results) == 3
        assert results[0] == JAVA_RESULT
        assert results[2] == PYTHON_RESULT
        assert results == tuple(match_candidate_to_job(candidate, job) for job in jobs)

    def test_a_fully_placeholder_scraped_job_gets_an_empty_result_in_place(self):
        jobs = [make_job(), Job.from_scraped_data({}), make_job(description=JAVA_DESCRIPTION)]

        results = match_candidate_to_jobs(make_candidate("Python", "Java"), jobs)

        assert results == (PYTHON_RESULT, MatchResult(), JAVA_RESULT)

    def test_result_index_corresponds_to_job_index_across_a_larger_batch(self):
        candidate = make_candidate(*[f"Tool{i}" for i in range(60)])
        order = [(index * 17) % 60 for index in range(60)]
        jobs = [make_job(description=f"Requirements\n\n- Knowledge of Tool{i}") for i in order]

        results = match_candidate_to_jobs(candidate, jobs)

        assert len(results) == 60
        assert [result.skills[0].evidence for result in results] == [(f"Tool{i}",) for i in order]

    def test_each_result_equals_matching_that_job_alone(self):
        candidate = make_candidate("Python", "Java")
        jobs = [make_job(description=d) for d in (JAVA_DESCRIPTION, NOTHING_DESCRIPTION, PYTHON_DESCRIPTION, EXPERIENCE_EDUCATION_DESCRIPTION)]

        results = match_candidate_to_jobs(candidate, jobs)

        assert results == tuple(match_candidate_to_job(candidate, job) for job in jobs)

    def test_a_job_result_does_not_depend_on_the_other_jobs_in_the_batch(self):
        candidate = make_candidate("Python", "Java")
        java_job = make_job(description=JAVA_DESCRIPTION)

        alone = match_candidate_to_jobs(candidate, (java_job,))
        among_others = match_candidate_to_jobs(candidate, (make_job(), java_job, make_job(description=NOTHING_DESCRIPTION)))

        assert among_others[1] == alone[0]

    def test_the_same_job_object_twice_gives_two_results_without_deduplication(self):
        job = make_job()

        results = match_candidate_to_jobs(make_candidate("Python"), (job, job))

        assert results == (PYTHON_RESULT, PYTHON_RESULT)

    def test_equal_jobs_with_equal_descriptions_are_not_merged(self):
        results = match_candidate_to_jobs(
            make_candidate("Python"), [make_job(title="A"), make_job(title="B"), make_job(title="A")]
        )

        assert len(results) == 3

    def test_an_empty_candidate_gets_a_result_with_no_evidence_for_every_job(self):
        results = match_candidate_to_jobs(CandidateProfile(), [make_job(), make_job(description=JAVA_DESCRIPTION)])

        assert results == (
            MatchResult(skills=(SkillMatch(statement="Knowledge of Python", evidence=()),)),
            MatchResult(skills=(SkillMatch(statement="Knowledge of Java", evidence=()),)),
        )

    def test_candidate_experience_and_education_records_never_change_the_results(self):
        candidate = CandidateProfile(
            skills=("Python",),
            experience=(Experience(title="Backend Developer", organization="Example", start="2022", end=None),),
            education=(Education(institution="Example University", degree="BSc", field="Computer Science"),),
        )
        jobs = [make_job(description=EXPERIENCE_EDUCATION_DESCRIPTION), make_job()]

        assert match_candidate_to_jobs(candidate, jobs) == match_candidate_to_jobs(make_candidate("Python"), jobs)

    def test_no_score_rank_or_recommendation_is_produced(self):
        results = match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(description=JAVA_DESCRIPTION)])

        assert results == (PYTHON_RESULT, MatchResult(skills=(SkillMatch(statement="Knowledge of Java", evidence=()),)))
        assert not hasattr(results, "ranked")
        assert all(
            [f.name for f in dataclasses.fields(result)] == ["skills", "unevaluated_experience", "unevaluated_education"]
            for result in results
        )


class TestDelegation:
    def test_every_job_is_passed_to_the_single_job_matcher_in_order_with_the_same_candidate(self, monkeypatch):
        calls = install_spy(monkeypatch)
        candidate = make_candidate("Python")
        jobs = [make_job(title=f"Job {i}") for i in range(4)]

        match_candidate_to_jobs(candidate, jobs)

        assert len(calls) == 4
        assert all(called_candidate is candidate for called_candidate, _ in calls)
        assert all(called_job is job for (_, called_job), job in zip(calls, jobs))

    def test_the_single_job_matcher_is_called_exactly_once_per_job(self, monkeypatch):
        calls = install_spy(monkeypatch)
        job = make_job()

        match_candidate_to_jobs(make_candidate("Python"), (job, job, make_job()))

        assert len(calls) == 3

    def test_the_results_returned_by_the_single_job_matcher_come_back_unchanged_and_in_order(self, monkeypatch):
        returned = []

        def behavior(number, candidate, job):
            result = MatchResult(unevaluated_experience=(f"result {number}",))
            returned.append(result)
            return result

        install_spy(monkeypatch, behavior)

        results = match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(), make_job()])

        assert len(results) == 3
        assert all(actual is expected for actual, expected in zip(results, returned))

    def test_empty_jobs_never_invoke_the_single_job_matcher(self, monkeypatch):
        forbid_calls(monkeypatch)

        assert match_candidate_to_jobs(make_candidate("Python"), ()) == ()
        assert match_candidate_to_jobs(make_candidate("Python"), []) == ()

    def test_a_later_job_failure_propagates_and_stops_processing(self, monkeypatch):
        boom = RuntimeError("boom")

        def behavior(number, candidate, job):
            if number == 3:
                raise boom
            return MatchResult()

        calls = install_spy(monkeypatch, behavior)

        with pytest.raises(RuntimeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), [make_job() for _ in range(5)])

        assert exc_info.value is boom
        assert len(calls) == 3

    def test_a_failure_on_the_first_job_propagates(self, monkeypatch):
        def behavior(number, candidate, job):
            raise ValueError("first failed")

        install_spy(monkeypatch, behavior)

        with pytest.raises(ValueError, match=r"^first failed$"):
            match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job()])

    def test_no_partial_results_are_returned_when_a_job_fails(self, monkeypatch):
        def behavior(number, candidate, job):
            if number == 2:
                raise KeyError("second")
            return MatchResult()

        install_spy(monkeypatch, behavior)

        with pytest.raises(KeyError):
            match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(), make_job()])

    def test_an_invalid_candidate_never_reaches_the_single_job_matcher(self, monkeypatch):
        forbid_calls(monkeypatch)

        with pytest.raises(TypeError):
            match_candidate_to_jobs("not a CandidateProfile", [make_job()])

    def test_an_invalid_container_never_reaches_the_single_job_matcher(self, monkeypatch):
        forbid_calls(monkeypatch)

        with pytest.raises(TypeError):
            match_candidate_to_jobs(make_candidate("Python"), {make_job()})

    def test_one_invalid_element_stops_everything_before_any_job_is_matched(self, monkeypatch):
        forbid_calls(monkeypatch)

        with pytest.raises(TypeError):
            match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(), "not a Job"])


class TestRealJobFailuresPropagate:
    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_a_job_with_a_non_string_description_raises_the_extractors_error(self, position):
        jobs = [make_job(), make_job(), make_job()]
        jobs[position] = make_job(description=None)

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), jobs)

        assert str(exc_info.value) == "description must be a str"

    def test_the_failure_is_not_swallowed_into_an_empty_result(self):
        jobs = [make_job(description=PYTHON_DESCRIPTION), make_job(description=["not", "a", "str"])]

        with pytest.raises(TypeError, match=r"^description must be a str$"):
            match_candidate_to_jobs(make_candidate("Python"), jobs)


class TestCandidateValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidateProfile", None, 123, ["Python"], {"skills": ("Python",)}, make_job(), JobRequirements()],
        ids=["str", "none", "int", "list", "dict", "job", "job-requirements"],
    )
    @pytest.mark.parametrize("jobs", [(), (make_job(),)], ids=["empty-jobs", "one-job"])
    def test_a_non_candidate_profile_raises_the_static_candidate_error(self, value, jobs):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(value, jobs)

        assert str(exc_info.value) == CANDIDATE_ERROR

    def test_the_candidate_is_validated_before_the_jobs(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs("not a CandidateProfile", "not a sequence of Jobs")

        assert str(exc_info.value) == CANDIDATE_ERROR

    def test_an_object_that_only_looks_like_a_candidate_profile_is_rejected(self):
        look_alike = types.SimpleNamespace(skills=("Python",), experience=(), education=())

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(look_alike, [make_job()])

        assert str(exc_info.value) == CANDIDATE_ERROR

    def test_subclasses_of_candidate_profile_are_accepted(self):
        class SpecialCandidate(CandidateProfile):
            pass

        results = match_candidate_to_jobs(SpecialCandidate(skills=("Python",)), [make_job()])

        assert results == (PYTHON_RESULT,)


class TestJobsContainerValidation:
    @pytest.mark.parametrize(
        "container",
        [
            pytest.param(None, id="none"),
            pytest.param(123, id="int"),
            pytest.param(make_job(), id="a-single-job"),
            pytest.param("jobs.csv", id="a-file-name-string"),
            pytest.param(Path("jobs.csv"), id="a-path"),
            pytest.param("abc", id="str"),
            pytest.param(b"abc", id="bytes"),
            pytest.param(bytearray(b"abc"), id="bytearray"),
            pytest.param({make_job()}, id="set"),
            pytest.param(frozenset({make_job()}), id="frozenset"),
            pytest.param({0: make_job()}, id="dict"),
            pytest.param({0: make_job()}.values(), id="dict-values"),
            pytest.param(iter([make_job()]), id="iterator"),
            pytest.param((make_job() for _ in range(2)), id="generator"),
            pytest.param(map(lambda job: job, [make_job()]), id="map-object"),
        ],
    )
    def test_a_non_sequence_jobs_argument_raises_the_static_container_error(self, container):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), container)

        assert str(exc_info.value) == CONTAINER_ERROR

    def test_an_iterable_is_never_silently_coerced_or_consumed(self):
        generator = (job for job in [make_job(), make_job()])

        with pytest.raises(TypeError):
            match_candidate_to_jobs(make_candidate("Python"), generator)

        assert len(list(generator)) == 2

    @pytest.mark.parametrize(
        "make_container",
        [tuple, list, ReadOnlySequence],
        ids=["tuple", "list", "custom-sequence"],
    )
    def test_any_sequence_of_jobs_is_accepted(self, make_container):
        jobs = make_container([make_job(), make_job(description=JAVA_DESCRIPTION)])

        assert match_candidate_to_jobs(make_candidate("Python", "Java"), jobs) == (PYTHON_RESULT, JAVA_RESULT)

    def test_the_container_error_never_contains_the_argument(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
        assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
        assert exc_info.value.__cause__ is None


class TestJobElementValidation:
    @pytest.mark.parametrize(
        "element",
        [
            pytest.param("not a Job", id="str"),
            pytest.param(None, id="none"),
            pytest.param(123, id="int"),
            pytest.param({"description": PYTHON_DESCRIPTION}, id="dict"),
            pytest.param([make_job()], id="nested-list"),
            pytest.param(CandidateProfile(), id="candidate-profile"),
            pytest.param(JobRequirements(), id="job-requirements"),
            pytest.param(MatchResult(), id="match-result"),
            pytest.param(
                types.SimpleNamespace(title="t", company="c", location="l", url="u", description=PYTHON_DESCRIPTION),
                id="duck-typed-job",
            ),
        ],
    )
    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_a_non_job_element_raises_the_static_element_error_wherever_it_sits(self, element, position):
        jobs = [make_job(), make_job(), make_job()]
        jobs[position] = element

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), jobs)

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_a_sequence_that_is_not_made_of_jobs_raises_the_element_error_not_the_container_error(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), range(3))

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_a_tuple_container_is_checked_element_by_element_too(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), (make_job(), "not a Job"))

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_every_element_is_validated_before_any_job_is_matched(self):
        jobs = [make_job(description=None), "not a Job"]

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), jobs)

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_an_invalid_element_is_reported_even_when_the_other_jobs_are_valid_and_numerous(self):
        jobs = [make_job() for _ in range(50)] + [None]

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), jobs)

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_the_element_error_never_contains_the_element_or_its_position(self):
        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), [make_job(), SYNTHETIC_PRIVATE_MARKER])

        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
        assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
        assert exc_info.value.__cause__ is None
        assert str(exc_info.value) == ELEMENT_ERROR

    def test_subclasses_of_job_are_accepted(self):
        class SpecialJob(Job):
            pass

        special = SpecialJob(title="t", company="c", location="l", description=JAVA_DESCRIPTION)

        results = match_candidate_to_jobs(make_candidate("Python", "Java"), [make_job(), special])

        assert results == (PYTHON_RESULT, JAVA_RESULT)


class TestImmutabilityAndDeterminism:
    def test_the_candidate_the_jobs_and_the_container_are_not_modified(self):
        candidate = CandidateProfile(
            skills=("Python", "python", " Java "),
            experience=(Experience(title="Backend Developer", organization="Example", start="2022", end=None),),
            education=(Education(institution="Example University", degree="BSc", field="Computer Science"),),
        )
        jobs = [make_job(), make_job(description=JAVA_DESCRIPTION), make_job(description=EXPERIENCE_EDUCATION_DESCRIPTION)]
        candidate_snapshot = dataclasses.replace(candidate)
        job_snapshots = [dataclasses.replace(job) for job in jobs]
        container_snapshot = list(jobs)

        match_candidate_to_jobs(candidate, jobs)

        assert candidate == candidate_snapshot
        assert jobs == job_snapshots
        assert len(jobs) == 3
        assert all(current is original for current, original in zip(jobs, container_snapshot))

    def test_the_result_is_a_new_tuple_not_the_callers_container(self):
        jobs = (make_job(), make_job())

        results = match_candidate_to_jobs(make_candidate("Python"), jobs)

        assert results is not jobs
        assert type(results) is tuple

    def test_the_results_are_immutable(self):
        results = match_candidate_to_jobs(make_candidate("Python"), [make_job()])

        with pytest.raises(TypeError):
            results[0] = MatchResult()
        with pytest.raises(dataclasses.FrozenInstanceError):
            results[0].skills = ()
        assert isinstance(hash(results), int)

    def test_repeated_calls_give_equal_results(self):
        candidate = make_candidate("Python", "Java")
        jobs = [make_job(description=d) for d in (PYTHON_DESCRIPTION, JAVA_DESCRIPTION, NOTHING_DESCRIPTION)]

        results = [match_candidate_to_jobs(candidate, jobs) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_equal_but_separately_built_inputs_give_equal_results(self):
        first = match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(description=JAVA_DESCRIPTION)])
        second = match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(description=JAVA_DESCRIPTION)])

        assert first == second


class TestPrivacy:
    def test_matching_a_batch_produces_no_console_output_or_log_records(self, capsys, caplog):
        description = f"Requirements\n\n- Experience with {SYNTHETIC_PRIVATE_MARKER} and Python\n\n{SYNTHETIC_PRIVATE_MARKER}"
        jobs = [make_job(description=description), make_job(), make_job(description=NOTHING_DESCRIPTION)]

        match_candidate_to_jobs(make_candidate(SYNTHETIC_PRIVATE_MARKER, "Python"), jobs)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_jobs = [make_job(title=SYNTHETIC_PRIVATE_MARKER, description=SYNTHETIC_PRIVATE_MARKER)]

        with pytest.raises(TypeError) as candidate_error:
            match_candidate_to_jobs([SYNTHETIC_PRIVATE_MARKER], secret_jobs)
        with pytest.raises(TypeError) as container_error:
            match_candidate_to_jobs(make_candidate(SYNTHETIC_PRIVATE_MARKER), SYNTHETIC_PRIVATE_MARKER.encode())
        with pytest.raises(TypeError) as element_error:
            match_candidate_to_jobs(make_candidate(SYNTHETIC_PRIVATE_MARKER), secret_jobs + [{SYNTHETIC_PRIVATE_MARKER: 1}])

        for exc_info in (candidate_error, container_error, element_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_candidate_to_jobs(make_candidate("Python"), [make_job(), make_job(description=JAVA_DESCRIPTION)])

        assert list(tmp_path.iterdir()) == []

    def test_a_csv_file_name_is_rejected_not_loaded_even_when_the_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "jobs.csv").write_text("title,company,location,description\n", encoding="utf-8")

        with pytest.raises(TypeError) as exc_info:
            match_candidate_to_jobs(make_candidate("Python"), "jobs.csv")

        assert str(exc_info.value) == CONTAINER_ERROR

    def test_the_module_holds_no_mutable_module_level_state(self):
        mutable = [
            name
            for name, value in vars(job_batch_matcher).items()
            if not name.startswith("__") and isinstance(value, (list, dict, set, bytearray))
        ]

        assert mutable == []


class TestDependencyIsolation:
    # models and urllib are legitimate transitive dependencies (through job_matcher), so neither is forbidden.
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
    def test_importing_job_batch_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, job_batch_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
