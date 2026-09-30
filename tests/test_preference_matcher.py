"""Tests for preference_matcher: pure composition of the four independently tested preference
matchers into one CandidatePreferenceMatch (Task 1.18).

match_preferences_to_job(preferences, job) is composition only: it calls match_target_roles_to_job,
match_preferred_locations_to_job, match_work_mode_to_job, and match_employment_type_to_job unchanged
and bundles their results. It implements no matching logic of its own, so these tests prove
composition and the aggregate boundary -- not the individual matchers' lexical semantics, which are
already covered by their own test suites. minimum_hours_per_week is explicitly unsupported: the
aggregate must never read, interpret, or expose it. All data here is synthetic.
"""

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences
from employment_type_preference_matcher import match_employment_type_to_job
from location_preference_matcher import match_preferred_locations_to_job
from models import Job
from preference_matcher import CandidatePreferenceMatch, match_preferences_to_job
from role_preference_matcher import match_target_roles_to_job
from work_mode_matcher import match_work_mode_to_job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"


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


class TestResultConstruction:
    def test_a_valid_call_returns_a_candidate_preference_match(self):
        result = match_preferences_to_job(make_preferences(), make_job())

        assert isinstance(result, CandidatePreferenceMatch)

    def test_the_result_exposes_exactly_the_four_approved_fields_in_order(self):
        result = match_preferences_to_job(make_preferences(), make_job())

        assert [f.name for f in dataclasses.fields(result)] == ["role", "location", "work_mode", "employment_type"]

    def test_the_dataclass_itself_declares_exactly_the_four_fields_in_order(self):
        assert [f.name for f in dataclasses.fields(CandidatePreferenceMatch)] == [
            "role",
            "location",
            "work_mode",
            "employment_type",
        ]

    def test_the_result_is_frozen(self):
        result = match_preferences_to_job(make_preferences(), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.role = match_target_roles_to_job(make_preferences(), make_job())


class TestCompositionCorrectness:
    def test_each_field_equals_the_directly_computed_matcher_result(self):
        # The most important test in this suite: proves the aggregate is pure composition, not a
        # reimplementation. Deliberately uses meaningful, partially-overlapping values for all four
        # supported preferences so each individual matcher has real work to do.
        preferences = make_preferences(
            target_roles=("Software Engineer", "Backend Developer"),
            preferred_locations=("Berlin", "Munich"),
            work_mode="Hybrid",
            employment_type="Full-time",
        )
        job = make_job(
            title="Backend Developer",
            location="Berlin, Germany (Hybrid)",
            employment_type="Full-time",
        )

        result = match_preferences_to_job(preferences, job)

        assert result.role == match_target_roles_to_job(preferences, job)
        assert result.location == match_preferred_locations_to_job(preferences, job)
        assert result.work_mode == match_work_mode_to_job(preferences, job)
        assert result.employment_type == match_employment_type_to_job(preferences, job)


class TestEmptyDefaultPreferences:
    def test_default_preferences_give_the_four_corresponding_direct_results(self):
        job = make_job()

        result = match_preferences_to_job(CandidatePreferences(), job)

        assert result.role == match_target_roles_to_job(CandidatePreferences(), job)
        assert result.location == match_preferred_locations_to_job(CandidatePreferences(), job)
        assert result.work_mode == match_work_mode_to_job(CandidatePreferences(), job)
        assert result.employment_type == match_employment_type_to_job(CandidatePreferences(), job)

    def test_default_preferences_give_empty_evidence_everywhere(self):
        # Not a new aggregate-level meaning: each sub-result's own empty tuple already means
        # "not stated / not found," never "job is unsuitable" -- the aggregate adds nothing here.
        result = match_preferences_to_job(CandidatePreferences(), make_job())

        assert result.role.evidence == ()
        assert result.location.evidence == ()
        assert result.work_mode.evidence == ()
        assert result.employment_type.evidence == ()


class TestMixedMatchState:
    def test_each_sub_result_preserves_its_own_independent_match_or_non_match(self):
        # role matches, location does not, work_mode matches, employment_type does not: proves the
        # aggregate never collapses four independent outcomes into one boolean.
        preferences = make_preferences(
            target_roles=("Backend Developer",),
            preferred_locations=("Munich",),
            work_mode="Hybrid",
            employment_type="Part-time",
        )
        job = make_job(
            title="Backend Developer",
            location="Berlin, Germany (Hybrid)",
            employment_type="Full-time",
        )

        result = match_preferences_to_job(preferences, job)

        assert result.role.evidence == ("Backend Developer",)
        assert result.location.evidence == ()
        assert result.work_mode.evidence == ("Hybrid",)
        assert result.employment_type.evidence == ()


class TestMinimumHoursIsUnsupported:
    def test_minimum_hours_per_week_has_no_effect_on_any_of_the_four_results(self):
        job = make_job()
        with_hours = make_preferences(minimum_hours_per_week=40)
        without_hours = make_preferences(minimum_hours_per_week=None)

        result_with = match_preferences_to_job(with_hours, job)
        result_without = match_preferences_to_job(without_hours, job)

        assert result_with == result_without

    def test_the_result_has_no_minimum_hours_field(self):
        result = match_preferences_to_job(make_preferences(), make_job())

        assert not hasattr(result, "minimum_hours_per_week")


class TestFieldIsolation:
    def test_changing_target_roles_only_affects_the_role_result(self):
        job = make_job(title="Backend Developer")
        base = match_preferences_to_job(make_preferences(target_roles=()), job)
        changed = match_preferences_to_job(make_preferences(target_roles=("Backend Developer",)), job)

        assert base.role != changed.role
        assert base.location == changed.location
        assert base.work_mode == changed.work_mode
        assert base.employment_type == changed.employment_type

    def test_changing_preferred_locations_only_affects_the_location_result(self):
        job = make_job(location="Munich, Germany")
        base = match_preferences_to_job(make_preferences(preferred_locations=()), job)
        changed = match_preferences_to_job(make_preferences(preferred_locations=("Munich",)), job)

        assert base.location != changed.location
        assert base.role == changed.role
        assert base.work_mode == changed.work_mode
        assert base.employment_type == changed.employment_type

    def test_changing_work_mode_only_affects_the_work_mode_result(self):
        job = make_job(location="Berlin, Germany (Remote)")
        base = match_preferences_to_job(make_preferences(work_mode=None), job)
        changed = match_preferences_to_job(make_preferences(work_mode="Remote"), job)

        assert base.work_mode != changed.work_mode
        assert base.role == changed.role
        assert base.location == changed.location
        assert base.employment_type == changed.employment_type

    def test_changing_employment_type_only_affects_the_employment_type_result(self):
        job = make_job(employment_type="Full-time")
        base = match_preferences_to_job(make_preferences(employment_type=None), job)
        changed = match_preferences_to_job(make_preferences(employment_type="Full-time"), job)

        assert base.employment_type != changed.employment_type
        assert base.role == changed.role
        assert base.location == changed.location
        assert base.work_mode == changed.work_mode

    def test_changing_minimum_hours_per_week_affects_none_of_the_four_results(self):
        job = make_job()
        base = match_preferences_to_job(make_preferences(minimum_hours_per_week=None), job)
        changed = match_preferences_to_job(make_preferences(minimum_hours_per_week=40), job)

        assert base == changed

    def test_a_change_in_job_title_only_affects_the_role_result(self):
        preferences = make_preferences(target_roles=("Backend Developer",))
        base = match_preferences_to_job(preferences, make_job(title="Software Engineer"))
        changed = match_preferences_to_job(preferences, make_job(title="Backend Developer"))

        assert base.role != changed.role
        assert base.location == changed.location
        assert base.work_mode == changed.work_mode
        assert base.employment_type == changed.employment_type

    def test_a_change_in_job_company_affects_none_of_the_four_results(self):
        preferences = make_preferences()
        base = match_preferences_to_job(preferences, make_job(company="Acme GmbH"))
        changed = match_preferences_to_job(preferences, make_job(company="Different GmbH"))

        assert base == changed

    def test_a_change_in_job_location_affects_location_and_work_mode_only(self):
        # location.py and work_mode_matcher.py both legitimately read job.location; role and
        # employment_type must stay unaffected by it.
        preferences = make_preferences(preferred_locations=("Munich",), work_mode="Remote")
        base = match_preferences_to_job(preferences, make_job(location="Berlin, Germany (Hybrid)"))
        changed = match_preferences_to_job(preferences, make_job(location="Munich, Germany (Remote)"))

        assert base.location != changed.location
        assert base.work_mode != changed.work_mode
        assert base.role == changed.role
        assert base.employment_type == changed.employment_type

    def test_a_change_in_job_description_affects_none_of_the_four_results(self):
        preferences = make_preferences()
        base = match_preferences_to_job(preferences, make_job(description="Requirements\n\n- A"))
        changed = match_preferences_to_job(preferences, make_job(description="Requirements\n\n- B"))

        assert base == changed

    def test_a_change_in_job_url_affects_none_of_the_four_results(self):
        preferences = make_preferences()
        base = match_preferences_to_job(preferences, make_job(url="https://example.invalid/a"))
        changed = match_preferences_to_job(preferences, make_job(url="https://example.invalid/b"))

        assert base == changed

    def test_a_change_in_job_employment_type_only_affects_the_employment_type_result(self):
        preferences = make_preferences(employment_type="Part-time")
        base = match_preferences_to_job(preferences, make_job(employment_type="Full-time"))
        changed = match_preferences_to_job(preferences, make_job(employment_type="Part-time"))

        assert base.employment_type != changed.employment_type
        assert base.role == changed.role
        assert base.location == changed.location
        assert base.work_mode == changed.work_mode


class TestNoScoreOrVerdict:
    @pytest.mark.parametrize(
        "name",
        [
            "score",
            "rank",
            "percentage",
            "confidence",
            "recommendation",
            "verdict",
            "qualifies",
            "matched",
            "suitable",
            "preferred",
            "minimum_hours_per_week",
        ],
    )
    def test_the_result_has_no_unapproved_attribute(self, name):
        result = match_preferences_to_job(make_preferences(), make_job())

        assert not hasattr(result, name)

    def test_the_result_carries_no_attribute_beyond_the_four_approved_fields(self):
        result = match_preferences_to_job(make_preferences(), make_job())

        assert vars(result) == {
            "role": result.role,
            "location": result.location,
            "work_mode": result.work_mode,
            "employment_type": result.employment_type,
        }


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidatePreferences", None, 123, ["Software Engineer"], {"target_roles": ()}, make_job()],
        ids=["str", "none", "int", "list", "dict", "job"],
    )
    def test_a_non_candidate_preferences_first_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_job(value, make_job())

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    @pytest.mark.parametrize(
        "value",
        ["not a Job", None, 123, ["Software Engineer"], {"title": "x"}, make_preferences()],
        ids=["str", "none", "int", "list", "dict", "candidate-preferences"],
    )
    def test_a_non_job_second_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_job(make_preferences(), value)

        assert str(exc_info.value) == "job must be a Job"

    def test_preferences_are_validated_before_job_when_both_are_invalid(self):
        with pytest.raises(TypeError) as exc_info:
            match_preferences_to_job("not a CandidatePreferences", "not a Job")

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_preferences = CandidatePreferences(target_roles=(SYNTHETIC_PRIVATE_MARKER,))
        secret_job = make_job(title=SYNTHETIC_PRIVATE_MARKER)

        with pytest.raises(TypeError) as preferences_error:
            match_preferences_to_job([SYNTHETIC_PRIVATE_MARKER], secret_job)
        with pytest.raises(TypeError) as job_error:
            match_preferences_to_job(secret_preferences, {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        for exc_info in (preferences_error, job_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestImmutabilityAndDeterminism:
    def test_the_result_is_frozen(self):
        result = match_preferences_to_job(make_preferences(), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.role = match_target_roles_to_job(make_preferences(), make_job())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.employment_type = match_employment_type_to_job(make_preferences(), make_job())

    def test_the_result_is_hashable(self):
        first = match_preferences_to_job(make_preferences(), make_job())
        second = match_preferences_to_job(make_preferences(), make_job())

        assert hash(first) == hash(second)
        assert len({first, second}) == 1

    def test_repeated_calls_with_the_same_inputs_are_equal(self):
        preferences, job = make_preferences(), make_job()

        results = [match_preferences_to_job(preferences, job) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_the_inputs_are_not_mutated(self):
        preferences = make_preferences()
        job = make_job()
        preferences_snapshot = dataclasses.replace(preferences)
        job_snapshot = dataclasses.replace(job)

        match_preferences_to_job(preferences, job)

        assert preferences == preferences_snapshot
        assert job == job_snapshot


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        preferences = CandidatePreferences(target_roles=(SYNTHETIC_PRIVATE_MARKER,))
        job = make_job(title=SYNTHETIC_PRIVATE_MARKER)

        match_preferences_to_job(preferences, job)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_preferences_to_job(make_preferences(), make_job())

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
    # candidate_preferences, models, and the four sibling preference matchers are legitimate
    # dependencies (this module is pure composition over them), so none are forbidden here.
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
    def test_importing_preference_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, preference_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
