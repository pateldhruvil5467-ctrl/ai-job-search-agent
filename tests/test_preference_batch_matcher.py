"""Tests for preference_batch_matcher: one candidate's preferences against many already-loaded Jobs
(Task 1.19), parallel to job_batch_matcher.py for Pipeline B.

match_preferences_to_jobs(preferences, jobs) returns exactly one CandidatePreferenceMatch per Job,
in input order, each obtained by delegating to the existing single-job match_preferences_to_job. It
does no I/O, extraction, scoring, ranking, filtering or recommending, it never coerces an arbitrary
iterable into a list, and it never touches Pipeline A (CandidateProfile/JobRequirements/MatchResult)
or minimum_hours_per_week. All data here is synthetic.
"""

import collections.abc
import dataclasses
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences
from models import Job
from preference_batch_matcher import match_preferences_to_jobs
from preference_matcher import CandidatePreferenceMatch, match_preferences_to_job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"

PREFERENCES_ERROR = "preferences must be a CandidatePreferences"
CONTAINER_ERROR = "jobs must be a sequence of Job objects"
ELEMENT_ERROR = "jobs must contain only Job objects"


def make_preferences(**overrides) -> CandidatePreferences:
    fields = {
        "target_roles": ("Software Engineer",),
        "preferred_locations": ("Berlin",),
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
    }
    fields.update(overrides)
    return CandidatePreferences(**fields)


def make_job(**overrides) -> Job:
    fields = {
        "title": "Software Engineer",
        "company": "Acme GmbH",
        "location": "Berlin, Germany (Hybrid)",
        "description": "Requirements\n\n- Backend Developer experience required",
        "url": "https://www.linkedin.com/jobs/view/3812345678/",
        "employment_type": "Full-time",
    }
    fields.update(overrides)
    return Job(**fields)


class ReadOnlySequence(collections.abc.Sequence):
    """A Sequence that is neither list nor tuple."""

    def __init__(self, items):
        self._items = tuple(items)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)


class TestResultShape:
    def test_the_function_is_importable_and_callable(self):
        assert callable(match_preferences_to_jobs)

    def test_the_public_parameters_are_exactly_preferences_and_jobs(self):
        assert list(inspect.signature(match_preferences_to_jobs).parameters) == ["preferences", "jobs"]

    def test_the_arguments_can_be_passed_by_keyword(self):
        preferences, jobs = make_preferences(), (make_job(),)

        result = match_preferences_to_jobs(preferences=preferences, jobs=jobs)

        assert result == (match_preferences_to_job(preferences, jobs[0]),)

    @pytest.mark.parametrize("container", [tuple, list], ids=["tuple-input", "list-input"])
    def test_the_return_type_is_exactly_a_tuple_of_candidate_preference_matches(self, container):
        results = match_preferences_to_jobs(make_preferences(), container([make_job(), make_job()]))

        assert type(results) is tuple
        assert all(type(result) is CandidatePreferenceMatch for result in results)


class TestEmptyInput:
    def test_empty_jobs_give_an_empty_tuple(self):
        assert match_preferences_to_jobs(make_preferences(), ()) == ()
        assert match_preferences_to_jobs(make_preferences(), []) == ()

    def test_a_default_preferences_object_with_empty_jobs_gives_an_empty_tuple(self):
        assert match_preferences_to_jobs(CandidatePreferences(), ()) == ()

    def test_the_empty_result_is_exactly_a_tuple_not_none_list_or_generator(self):
        result = match_preferences_to_jobs(make_preferences(), ())

        assert result == ()
        assert type(result) is tuple


class TestComposition:
    def test_each_result_equals_matching_that_job_alone(self):
        # The most important test in this suite: proves the batch layer is pure fan-out over the
        # existing single-job matcher, not a reimplementation.
        preferences = make_preferences(
            target_roles=("Backend Developer",),
            preferred_locations=("Munich",),
            work_mode="Remote",
            employment_type="Part-time",
        )
        jobs = [
            make_job(title="Backend Developer", location="Berlin, Germany (Hybrid)", employment_type="Full-time"),
            make_job(title="Frontend Developer", location="Munich, Germany (Remote)", employment_type="Part-time"),
            make_job(),
        ]

        results = match_preferences_to_jobs(preferences, jobs)

        assert results == tuple(match_preferences_to_job(preferences, job) for job in jobs)

    def test_a_single_job_batch_matches_the_direct_single_job_call(self):
        preferences, job = make_preferences(), make_job()

        results = match_preferences_to_jobs(preferences, (job,))

        assert results == (match_preferences_to_job(preferences, job),)


class TestOrderPreservation:
    ALPHA = make_job(title="Alpha Engineer")
    BETA = make_job(title="Beta Engineer")
    GAMMA = make_job(title="Gamma Engineer")
    PREFERENCES = make_preferences(target_roles=("Alpha Engineer", "Beta Engineer", "Gamma Engineer"))
    POOL = {"alpha": ALPHA, "beta": BETA, "gamma": GAMMA}

    @pytest.mark.parametrize(
        "order",
        [
            ("alpha", "beta", "gamma"),
            ("gamma", "beta", "alpha"),
            ("beta", "alpha", "gamma"),
            ("beta", "gamma", "alpha"),
            ("gamma", "alpha", "beta"),
            ("alpha", "gamma", "beta"),
        ],
        ids=lambda order: "".join(name[0] for name in order),
    )
    def test_the_input_job_order_is_preserved(self, order):
        jobs = [self.POOL[name] for name in order]

        results = match_preferences_to_jobs(self.PREFERENCES, jobs)

        assert [result.role.evidence for result in results] == [(self.POOL[name].title,) for name in order]

    @pytest.mark.parametrize("field", ["company", "location", "url"])
    @pytest.mark.parametrize("values", [("C", "B", "A"), ("B", "C", "A")], ids=["descending", "rotated"])
    def test_the_input_order_is_kept_whatever_the_field_values_would_sort_to(self, field, values):
        titles = ("Alpha Engineer", "Beta Engineer", "Gamma Engineer")
        jobs = [make_job(title=title, **{field: value}) for title, value in zip(titles, values)]

        results = match_preferences_to_jobs(self.PREFERENCES, jobs)

        assert [result.role.evidence for result in results] == [("Alpha Engineer",), ("Beta Engineer",), ("Gamma Engineer",)]


class TestMultipleJobs:
    def test_several_jobs_give_one_exact_result_each(self):
        preferences = make_preferences(target_roles=("Backend Developer", "Frontend Developer"))
        jobs = [make_job(title="Backend Developer"), make_job(title="Frontend Developer"), make_job(title="Designer")]

        results = match_preferences_to_jobs(preferences, jobs)

        assert len(results) == 3
        assert results[0].role.evidence == ("Backend Developer",)
        assert results[1].role.evidence == ("Frontend Developer",)
        assert results[2].role.evidence == ()

    def test_a_job_result_does_not_depend_on_the_other_jobs_in_the_batch(self):
        preferences = make_preferences(target_roles=("Backend Developer",))
        target_job = make_job(title="Backend Developer")

        alone = match_preferences_to_jobs(preferences, (target_job,))
        among_others = match_preferences_to_jobs(
            preferences, (make_job(title="Designer"), target_job, make_job(title="Other"))
        )

        assert among_others[1] == alone[0]

    def test_the_same_job_object_twice_gives_two_equal_results_without_deduplication(self):
        job = make_job()

        results = match_preferences_to_jobs(make_preferences(), (job, job))

        assert len(results) == 2
        assert results[0] == results[1]

    def test_result_index_corresponds_to_job_index_across_a_larger_batch(self):
        titles = [f"Role {i}" for i in range(20)]
        preferences = make_preferences(target_roles=tuple(titles))
        jobs = [make_job(title=title) for title in titles]

        results = match_preferences_to_jobs(preferences, jobs)

        assert len(results) == 20
        assert [result.role.evidence for result in results] == [(title,) for title in titles]


class TestDefaultPreferences:
    def test_default_preferences_gives_the_four_corresponding_no_evidence_results_for_every_job(self):
        jobs = [make_job(), make_job(title="Something Else")]

        results = match_preferences_to_jobs(CandidatePreferences(), jobs)

        assert all(result.role.evidence == () for result in results)
        assert all(result.location.evidence == () for result in results)
        assert all(result.work_mode.evidence == () for result in results)
        assert all(result.employment_type.evidence == () for result in results)

    def test_the_same_preferences_object_is_applied_unchanged_to_every_job(self):
        preferences = make_preferences(target_roles=("Backend Developer",))
        jobs = [make_job(title="Backend Developer"), make_job(title="Backend Developer")]

        results = match_preferences_to_jobs(preferences, jobs)

        assert results[0] == results[1] == match_preferences_to_job(preferences, jobs[0])


class TestFieldIsolation:
    def test_changing_one_jobs_fields_does_not_affect_another_jobs_result(self):
        preferences = make_preferences(
            target_roles=("Backend Developer",),
            preferred_locations=("Munich",),
            work_mode="Remote",
            employment_type="Part-time",
        )
        unrelated_job = make_job(
            title="Frontend Developer", location="Hamburg, Germany", employment_type="Full-time"
        )
        target_job = make_job(
            title="Backend Developer", location="Munich, Germany (Remote)", employment_type="Part-time"
        )

        results = match_preferences_to_jobs(preferences, [unrelated_job, target_job])

        assert results[0] == match_preferences_to_job(preferences, unrelated_job)
        assert results[1] == match_preferences_to_job(preferences, target_job)
        assert results[0] != results[1]


class TestMinimumHoursIsUnsupported:
    def test_minimum_hours_per_week_has_no_effect_on_any_batch_result(self):
        jobs = [make_job(), make_job(title="Something Else")]
        with_hours = make_preferences(minimum_hours_per_week=40)
        without_hours = make_preferences(minimum_hours_per_week=None)

        assert match_preferences_to_jobs(with_hours, jobs) == match_preferences_to_jobs(without_hours, jobs)

    def test_no_result_element_has_a_minimum_hours_field(self):
        results = match_preferences_to_jobs(make_preferences(), [make_job()])

        assert not hasattr(results[0], "minimum_hours_per_week")


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidatePreferences", None, 123, ["Software Engineer"], {"target_roles": ()}, make_job()],
        ids=["str", "none", "int", "list", "dict", "job"],
    )
    @pytest.mark.parametrize("jobs", [(), (make_job(),)], ids=["empty-jobs", "one-job"])
    def test_a_non_candidate_preferences_raises_the_static_preferences_error(self, value, jobs):
        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_jobs(value, jobs)

        assert str(exc_info.value) == PREFERENCES_ERROR

    def test_the_preferences_are_validated_before_the_jobs_container(self):
        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_jobs("not a CandidatePreferences", "not a sequence of Jobs")

        assert str(exc_info.value) == PREFERENCES_ERROR

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
            pytest.param({0: make_job()}, id="dict"),
            pytest.param(iter([make_job()]), id="iterator"),
            pytest.param((make_job() for _ in range(2)), id="generator"),
        ],
    )
    def test_a_non_sequence_jobs_argument_raises_the_static_container_error(self, container):
        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_jobs(make_preferences(), container)

        assert str(exc_info.value) == CONTAINER_ERROR

    @pytest.mark.parametrize(
        "make_container",
        [tuple, list, ReadOnlySequence],
        ids=["tuple", "list", "custom-sequence"],
    )
    def test_any_sequence_of_jobs_is_accepted(self, make_container):
        preferences = make_preferences(target_roles=("Backend Developer",))
        jobs = make_container([make_job(title="Backend Developer"), make_job(title="Other")])

        results = match_preferences_to_jobs(preferences, jobs)

        assert [r.role.evidence for r in results] == [("Backend Developer",), ()]

    @pytest.mark.parametrize(
        "element",
        [
            pytest.param("not a Job", id="str"),
            pytest.param(None, id="none"),
            pytest.param(123, id="int"),
            pytest.param({"title": "x"}, id="dict"),
            pytest.param([make_job()], id="nested-list"),
            pytest.param(make_preferences(), id="candidate-preferences"),
        ],
    )
    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_a_non_job_element_raises_the_static_element_error_wherever_it_sits(self, element, position):
        jobs = [make_job(), make_job(), make_job()]
        jobs[position] = element

        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_jobs(make_preferences(), jobs)

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_every_element_is_validated_before_any_job_is_matched(self):
        jobs = [make_job(), "not a Job"]

        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_jobs(make_preferences(), jobs)

        assert str(exc_info.value) == ELEMENT_ERROR

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_jobs = [make_job(title=SYNTHETIC_PRIVATE_MARKER)]

        with pytest.raises(TypeError) as preferences_error:
            match_preferences_to_jobs([SYNTHETIC_PRIVATE_MARKER], secret_jobs)
        with pytest.raises(TypeError) as container_error:
            match_preferences_to_jobs(make_preferences(), SYNTHETIC_PRIVATE_MARKER.encode())
        with pytest.raises(TypeError) as element_error:
            match_preferences_to_jobs(make_preferences(), secret_jobs + [{SYNTHETIC_PRIVATE_MARKER: 1}])

        for exc_info in (preferences_error, container_error, element_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestDeterminism:
    def test_repeated_calls_give_equal_results(self):
        preferences = make_preferences()
        jobs = [make_job(), make_job(title="Other")]

        results = [match_preferences_to_jobs(preferences, jobs) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_equal_but_separately_built_inputs_give_equal_results(self):
        first = match_preferences_to_jobs(make_preferences(), [make_job(), make_job(title="Other")])
        second = match_preferences_to_jobs(make_preferences(), [make_job(), make_job(title="Other")])

        assert first == second

    def test_the_inputs_are_not_mutated(self):
        preferences = make_preferences()
        jobs = [make_job(), make_job(title="Other")]
        preferences_snapshot = dataclasses.replace(preferences)
        job_snapshots = [dataclasses.replace(job) for job in jobs]
        container_snapshot = list(jobs)

        match_preferences_to_jobs(preferences, jobs)

        assert preferences == preferences_snapshot
        assert jobs == job_snapshots
        assert all(current is original for current, original in zip(jobs, container_snapshot))

    def test_the_result_is_a_new_tuple_not_the_callers_container(self):
        jobs = (make_job(), make_job())

        results = match_preferences_to_jobs(make_preferences(), jobs)

        assert results is not jobs
        assert type(results) is tuple


class TestPipelineSeparation:
    def test_result_elements_are_candidate_preference_match_with_exactly_the_four_approved_fields(self):
        results = match_preferences_to_jobs(make_preferences(), [make_job()])

        assert [f.name for f in dataclasses.fields(results[0])] == ["role", "location", "work_mode", "employment_type"]

    @pytest.mark.parametrize(
        "name", ["score", "rank", "percentage", "confidence", "recommendation", "verdict", "qualifies", "matched"]
    )
    def test_no_result_element_has_a_score_or_verdict_attribute(self, name):
        results = match_preferences_to_jobs(make_preferences(), [make_job()])

        assert not hasattr(results[0], name)


class TestPrivacy:
    def test_matching_a_batch_produces_no_console_output_or_log_records(self, capsys, caplog):
        jobs = [make_job(title=SYNTHETIC_PRIVATE_MARKER), make_job()]

        match_preferences_to_jobs(make_preferences(target_roles=(SYNTHETIC_PRIVATE_MARKER,)), jobs)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_preferences_to_jobs(make_preferences(), [make_job(), make_job(title="Other")])

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
    # candidate_preferences, models, and preference_matcher (plus its own sibling matchers) are
    # legitimate dependencies, so none are forbidden here.
    @pytest.mark.parametrize(
        "module",
        [
            "matcher",
            "job_matcher",
            "job_batch_matcher",
            "matching_service",
            "browser",
            "linkedin_scraper",
            "job_extractor",
            "job_page_parser",
            "job_storage",
            "selenium",
            "webdriver_manager",
            "pandas",
            "pdfplumber",
            "resume_pdf",
            "candidate_parser",
            "socket",
            "http",
            "requests",
            "ssl",
        ],
    )
    def test_importing_preference_batch_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first. In
        # particular, matcher/job_matcher/job_batch_matcher/matching_service (Pipeline A) must never
        # load -- this is the boundary this whole module exists to preserve.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, preference_batch_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
