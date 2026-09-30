"""Tests for employment_type_preference_matcher: a single candidate employment-type preference vs a
Job's own employment_type (Task 1.16).

match_employment_type_to_job(preferences, job) compares preferences.employment_type, a single
str | None, to job.employment_type, also a single str | None, by WHOLE-VALUE equality after
whitespace normalization and case-folding. Unlike role/location/work-mode matching, this is never a
phrase-search inside a larger field: job.employment_type is already a short, already-canonicalized
label (from job_page_parser.py's chip vocabulary), not prose a preference could be embedded in, so
there is no boundary-regex/substring behavior here ("time" must not match "Full-time"). It never
reads any other CandidatePreferences or Job field, never infers employment type from work mode,
minimum hours, title, description, or any other field, and never scores or ranks. All data here is
synthetic.
"""

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences
from employment_type_preference_matcher import EmploymentTypePreferenceMatch, match_employment_type_to_job
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"


def make_preferences(**overrides) -> CandidatePreferences:
    fields = {"employment_type": "Full-time"}
    fields.update(overrides)
    return CandidatePreferences(**fields)


def make_job(**overrides) -> Job:
    fields = {
        "title": "Backend Developer",
        "company": "Acme GmbH",
        "location": "Berlin, Germany (Hybrid)",
        "description": "Requirements\n\n- Backend Developer experience required",
        "url": "https://www.linkedin.com/jobs/view/3812345678/",
        "employment_type": "Full-time",
    }
    fields.update(overrides)
    return Job(**fields)


def evidence_for(preference_value, job_value) -> tuple[str, ...]:
    result = match_employment_type_to_job(
        CandidatePreferences(employment_type=preference_value), make_job(employment_type=job_value)
    )
    assert result.job_employment_type == job_value
    return result.evidence


class TestConstructionAndPositiveMatching:
    def test_an_exact_value_matches(self):
        assert evidence_for("Full-time", "Full-time") == ("Full-time",)

    def test_matching_is_case_insensitive(self):
        assert evidence_for("full-time", "Full-time") == ("full-time",)
        assert evidence_for("FULL-TIME", "full-time") == ("FULL-TIME",)

    def test_surrounding_whitespace_in_the_preference_does_not_prevent_a_match(self):
        assert evidence_for("  Full-time  ", "Full-time") == ("Full-time",)

    def test_internal_whitespace_runs_in_the_preference_are_collapsed_for_matching(self):
        # A synthetic multi-word value: nothing restricts job.employment_type to the parser's own
        # two-value vocabulary at the type level, so this proves internal-whitespace normalization
        # independent of what the real parser happens to produce.
        assert evidence_for("Contract  Basis", "Contract Basis") == ("Contract  Basis",)


class TestNoneAndBlankPreference:
    def test_none_preference_gives_empty_evidence(self):
        result = match_employment_type_to_job(
            CandidatePreferences(employment_type=None), make_job(employment_type="Full-time")
        )

        assert result.job_employment_type == "Full-time"
        assert result.evidence == ()

    def test_none_preference_is_the_default_and_gives_empty_evidence(self):
        result = match_employment_type_to_job(CandidatePreferences(), make_job(employment_type="Full-time"))

        assert result.evidence == ()

    def test_an_empty_string_preference_gives_empty_evidence(self):
        assert evidence_for("", "Full-time") == ()

    def test_a_whitespace_only_preference_gives_empty_evidence(self):
        assert evidence_for("   ", "Full-time") == ()
        assert evidence_for("\t", "Full-time") == ()

    def test_none_preference_gives_empty_evidence_even_against_a_job_with_no_employment_type(self):
        assert evidence_for(None, None) == ()

    def test_none_is_never_converted_into_the_literal_string_none(self):
        # A None preference must never fall through to matching the literal text "None", e.g. via
        # an unguarded str(preference) instead of an explicit None check.
        assert evidence_for(None, "None") == ()

    def test_a_blank_preference_gives_empty_evidence_even_against_a_job_with_an_empty_employment_type(self):
        # Guards against an implementation that drops the "is the preference actually non-blank"
        # check and relies solely on job.employment_type being non-None: without that guard, two
        # blank strings would compare equal (both normalize to "") and produce a false match.
        assert evidence_for("", "") == ()
        assert evidence_for("   ", "") == ()


class TestJobEmploymentTypeIsNone:
    def test_a_none_job_employment_type_gives_empty_evidence_even_with_a_preference_set(self):
        result = match_employment_type_to_job(
            CandidatePreferences(employment_type="Full-time"), make_job(employment_type=None)
        )

        assert result.job_employment_type is None
        assert result.evidence == ()

    def test_both_none_gives_empty_evidence(self):
        result = match_employment_type_to_job(
            CandidatePreferences(employment_type=None), make_job(employment_type=None)
        )

        assert result.job_employment_type is None
        assert result.evidence == ()

    def test_a_none_job_employment_type_is_never_treated_as_any(self):
        # A None job employment type must not behave as "matches everything", even when the
        # preference happens to already be the literal string "None".
        assert evidence_for("None", None) == ()


class TestNonMatchingValues:
    def test_part_time_preference_does_not_match_a_full_time_job(self):
        assert evidence_for("Part-time", "Full-time") == ()

    def test_full_time_preference_does_not_match_a_part_time_job(self):
        assert evidence_for("Full-time", "Part-time") == ()

    def test_internship_preference_does_not_match_a_full_time_job(self):
        assert evidence_for("Internship", "Full-time") == ()

    def test_internship_preference_does_not_match_a_part_time_job(self):
        assert evidence_for("Internship", "Part-time") == ()

    def test_internship_preference_does_not_match_a_job_with_no_employment_type(self):
        assert evidence_for("Internship", None) == ()


class TestNoSynonymsOrCanonicalization:
    def test_the_pt_abbreviation_does_not_match_part_time(self):
        assert evidence_for("PT", "Part-time") == ()

    def test_the_ft_abbreviation_does_not_match_full_time(self):
        assert evidence_for("FT", "Full-time") == ()

    def test_internship_receives_no_fuzzy_or_partial_matching_against_a_real_substring_relationship(self):
        assert evidence_for("Intern", "Internship") == ()


class TestNoSubstringLeakage:
    def test_time_does_not_match_full_time(self):
        assert evidence_for("time", "Full-time") == ()

    def test_full_does_not_match_full_time(self):
        assert evidence_for("Full", "Full-time") == ()

    def test_part_does_not_match_part_time(self):
        assert evidence_for("Part", "Part-time") == ()

    def test_full_time_does_not_match_a_job_value_that_merely_contains_it(self):
        # Proves whole-value equality, not "contains": a phrase-search matcher (like the siblings
        # use for prose fields) would wrongly find "Full-time" inside this longer job value.
        assert evidence_for("Full-time", "Full-time Contractor") == ()


class TestEvidence:
    def test_evidence_holds_the_candidates_trimmed_spelling_not_the_jobs(self):
        assert evidence_for("  full-time  ", "Full-time") == ("full-time",)

    def test_internal_spacing_and_casing_are_preserved_beyond_outer_trimming(self):
        assert evidence_for("  FuLl-TiMe  ", "full-time") == ("FuLl-TiMe",)

    def test_evidence_is_a_tuple(self):
        result = match_employment_type_to_job(make_preferences(), make_job())

        assert isinstance(result.evidence, tuple)

    def test_evidence_contains_at_most_one_item(self):
        result = match_employment_type_to_job(make_preferences(), make_job())

        assert len(result.evidence) <= 1

    def test_a_non_matching_pair_still_returns_the_jobs_employment_type(self):
        result = match_employment_type_to_job(
            CandidatePreferences(employment_type="Part-time"), make_job(employment_type="Full-time")
        )

        assert result.job_employment_type == "Full-time"
        assert result.evidence == ()


class TestFieldIsolation:
    def test_other_candidate_preference_fields_do_not_affect_matching(self):
        preferences = CandidatePreferences(
            target_roles=("Full-time",),
            preferred_locations=("Full-time",),
            work_mode="Full-time",
            employment_type=None,
            minimum_hours_per_week=20,
        )

        assert match_employment_type_to_job(preferences, make_job(employment_type="Full-time")).evidence == ()

    def test_other_preference_fields_do_not_suppress_a_real_employment_type_match(self):
        preferences = CandidatePreferences(
            target_roles=("Software Engineer",),
            preferred_locations=("Munich",),
            work_mode="Remote",
            employment_type="Full-time",
            minimum_hours_per_week=20,
        )

        result = match_employment_type_to_job(preferences, make_job(employment_type="Full-time"))

        assert result.evidence == ("Full-time",)

    def test_a_preferred_value_appearing_only_in_the_title_is_not_evidence(self):
        job = make_job(employment_type=None, title="Full-time Backend Engineer")

        assert match_employment_type_to_job(CandidatePreferences(employment_type="Full-time"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_company_name_is_not_evidence(self):
        job = make_job(employment_type=None, company="Full-time Software GmbH")

        assert match_employment_type_to_job(CandidatePreferences(employment_type="Full-time"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_location_is_not_evidence(self):
        job = make_job(employment_type=None, location="Berlin, Germany (Full-time)")

        assert match_employment_type_to_job(CandidatePreferences(employment_type="Full-time"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_description_is_not_evidence(self):
        job = make_job(employment_type=None, description="Requirements\n\n- Full-time commitment expected")

        assert match_employment_type_to_job(CandidatePreferences(employment_type="Full-time"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_url_is_not_evidence(self):
        job = make_job(employment_type=None, url="https://example.invalid/jobs/full-time-role")

        assert match_employment_type_to_job(CandidatePreferences(employment_type="Full-time"), job).evidence == ()

    def test_matching_uses_only_job_employment_type_even_when_every_other_field_matches(self):
        job = make_job(
            employment_type=None,
            title="Full-time Software Engineer",
            company="Full-time Software GmbH",
            location="Berlin, Germany (Full-time)",
            description="Full-time",
            url="https://example.invalid/full-time",
        )

        assert match_employment_type_to_job(CandidatePreferences(employment_type="Full-time"), job).evidence == ()


class TestNoScoreOrVerdict:
    @pytest.mark.parametrize(
        "name", ["score", "rank", "percentage", "confidence", "recommendation", "verdict", "qualifies", "matched"]
    )
    def test_the_result_has_no_score_rank_or_verdict_attribute(self, name):
        result = match_employment_type_to_job(make_preferences(), make_job())

        assert not hasattr(result, name)

    def test_the_result_exposes_exactly_the_approved_fields(self):
        result = match_employment_type_to_job(make_preferences(), make_job())

        assert [f.name for f in dataclasses.fields(result)] == ["job_employment_type", "evidence"]

    def test_the_evidence_field_defaults_to_an_empty_tuple(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(EmploymentTypePreferenceMatch)}

        assert fields_by_name["evidence"].default == ()

    def test_the_result_carries_no_attribute_beyond_the_two_approved_fields(self):
        result = match_employment_type_to_job(make_preferences(), make_job())

        assert vars(result) == {"job_employment_type": result.job_employment_type, "evidence": result.evidence}


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidatePreferences", None, 123, ["Full-time"], {"employment_type": "Full-time"}, make_job()],
        ids=["str", "none", "int", "list", "dict", "job"],
    )
    def test_a_non_candidate_preferences_first_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_employment_type_to_job(value, make_job())

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    @pytest.mark.parametrize(
        "value",
        ["not a Job", None, 123, ["Full-time"], {"employment_type": "Full-time"}, make_preferences()],
        ids=["str", "none", "int", "list", "dict", "candidate-preferences"],
    )
    def test_a_non_job_second_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_employment_type_to_job(make_preferences(), value)

        assert str(exc_info.value) == "job must be a Job"

    def test_preferences_are_validated_before_job_when_both_are_invalid(self):
        with pytest.raises(TypeError) as exc_info:
            match_employment_type_to_job("not a CandidatePreferences", "not a Job")

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_preferences = CandidatePreferences(employment_type=SYNTHETIC_PRIVATE_MARKER)
        secret_job = make_job(employment_type=SYNTHETIC_PRIVATE_MARKER)

        with pytest.raises(TypeError) as preferences_error:
            match_employment_type_to_job([SYNTHETIC_PRIVATE_MARKER], secret_job)
        with pytest.raises(TypeError) as job_error:
            match_employment_type_to_job(secret_preferences, {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        for exc_info in (preferences_error, job_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestImmutabilityAndDeterminism:
    def test_the_result_is_frozen(self):
        result = match_employment_type_to_job(make_preferences(), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.job_employment_type = "Somewhere Else"
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.evidence = ()

    def test_the_result_is_hashable(self):
        first = match_employment_type_to_job(make_preferences(), make_job())
        second = match_employment_type_to_job(make_preferences(), make_job())

        assert hash(first) == hash(second)
        assert len({first, second}) == 1

    def test_repeated_calls_with_the_same_inputs_are_equal(self):
        preferences, job = make_preferences(), make_job()

        results = [match_employment_type_to_job(preferences, job) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_the_result_does_not_depend_on_the_interpreters_hash_seed(self):
        script = (
            "from candidate_preferences import CandidatePreferences; "
            "from employment_type_preference_matcher import match_employment_type_to_job as m; "
            "from models import Job; "
            "r = m(CandidatePreferences(employment_type='Full-time'), "
            "Job(title='t', company='c', location='l', description='d', employment_type='Full-time')); "
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

    def test_the_inputs_are_not_mutated(self):
        preferences = CandidatePreferences(employment_type="  Full-time  ")
        job = make_job(employment_type="Full-time")
        preferences_snapshot = dataclasses.replace(preferences)
        job_snapshot = dataclasses.replace(job)

        match_employment_type_to_job(preferences, job)

        assert preferences == preferences_snapshot
        assert job == job_snapshot
        assert preferences.employment_type == "  Full-time  "
        assert job.employment_type == "Full-time"


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        preferences = CandidatePreferences(employment_type=SYNTHETIC_PRIVATE_MARKER)
        job = make_job(employment_type=SYNTHETIC_PRIVATE_MARKER)

        match_employment_type_to_job(preferences, job)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_employment_type_to_job(make_preferences(), make_job())

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
    # models is a legitimate dependency (it brings urllib.parse for job_key), so it is not forbidden.
    @pytest.mark.parametrize(
        "module",
        [
            "matcher",
            "job_matcher",
            "job_batch_matcher",
            "matching_service",
            "role_preference_matcher",
            "location_preference_matcher",
            "work_mode_matcher",
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
    def test_importing_employment_type_preference_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, employment_type_preference_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
