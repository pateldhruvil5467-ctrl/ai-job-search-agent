"""Tests for work_mode_matcher: a single candidate work-mode preference vs a Job location (Task 1.14).

match_work_mode_to_job(preferences, job) compares preferences.work_mode, a single str | None, to
job.location literally and case-insensitively with a word/punctuation boundary rule. It never reads
any other CandidatePreferences or Job field, never infers "On-site" from the absence of Remote or
Hybrid, never infers "On-site" from a location that mentions Remote, and never scores or ranks. All
data here is synthetic.
"""

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences
from models import Job
from work_mode_matcher import WorkModePreferenceMatch, match_work_mode_to_job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"


def make_preferences(**overrides) -> CandidatePreferences:
    fields = {"work_mode": "Hybrid"}
    fields.update(overrides)
    return CandidatePreferences(**fields)


def make_job(**overrides) -> Job:
    fields = {
        "title": "Backend Developer",
        "company": "Acme GmbH",
        "location": "Berlin, Germany (Hybrid)",
        "description": "Requirements\n\n- Backend Developer experience required",
        "url": "https://www.linkedin.com/jobs/view/3812345678/",
    }
    fields.update(overrides)
    return Job(**fields)


def evidence_for(work_mode, location) -> tuple[str, ...]:
    result = match_work_mode_to_job(CandidatePreferences(work_mode=work_mode), make_job(location=location))
    assert result.job_location == location
    return result.evidence


class TestConstructionAndPositiveMatching:
    def test_remote_matches_a_location_carrying_the_remote_suffix(self):
        assert evidence_for("Remote", "Germany (Remote)") == ("Remote",)

    def test_hybrid_matches_a_location_carrying_the_hybrid_suffix(self):
        assert evidence_for("Hybrid", "Berlin, Germany (Hybrid)") == ("Hybrid",)

    def test_on_site_matches_a_location_that_literally_carries_it(self):
        assert evidence_for("On-site", "Berlin, Germany (On-site)") == ("On-site",)

    def test_matching_is_case_insensitive(self):
        assert evidence_for("remote", "Germany (Remote)") == ("remote",)
        assert evidence_for("REMOTE", "germany (remote)") == ("REMOTE",)

    def test_onsite_one_word_matches_its_own_literal_spelling(self):
        assert evidence_for("Onsite", "Berlin (Onsite)") == ("Onsite",)

    def test_on_site_two_words_matches_its_own_literal_spelling(self):
        assert evidence_for("on site", "Berlin (on site)") == ("on site",)

    def test_a_double_space_in_the_job_location_does_not_prevent_a_match(self):
        assert evidence_for("Hybrid", "Berlin, Germany  (Hybrid)") == ("Hybrid",)

    def test_a_bare_work_mode_word_with_no_place_still_matches(self):
        assert evidence_for("Remote", "Remote") == ("Remote",)

    def test_internal_whitespace_in_a_multi_word_value_is_collapsed_for_matching(self):
        assert evidence_for("on site", "Berlin (on  site)") == ("on site",)


class TestNoneAndBlankPreference:
    def test_none_work_mode_gives_empty_evidence(self):
        result = match_work_mode_to_job(CandidatePreferences(work_mode=None), make_job(location="Germany (Remote)"))

        assert result.job_location == "Germany (Remote)"
        assert result.evidence == ()

    def test_none_work_mode_is_the_default_and_gives_empty_evidence(self):
        result = match_work_mode_to_job(CandidatePreferences(), make_job(location="Germany (Remote)"))

        assert result.evidence == ()

    def test_an_empty_string_work_mode_gives_empty_evidence(self):
        assert evidence_for("", "Germany (Remote)") == ()

    def test_a_whitespace_only_work_mode_gives_empty_evidence(self):
        assert evidence_for("   ", "Germany (Remote)") == ()
        assert evidence_for("\t", "Germany (Remote)") == ()

    def test_none_work_mode_gives_empty_evidence_even_against_a_job_with_no_location_suffix(self):
        assert evidence_for(None, "Berlin, Germany") == ()

    def test_none_is_never_converted_into_a_literal_matchable_string(self):
        # A None work_mode must never fall through to matching the literal text "None", e.g. via
        # an unguarded str(work_mode) instead of an explicit None check.
        assert evidence_for(None, "Berlin, Germany (None)") == ()


class TestNoInference:
    def test_on_site_does_not_match_a_location_with_no_suffix_at_all(self):
        # job_page_parser never writes "On-site" into Job.location (it is implied by the absence
        # of a suffix); this matcher must not compensate for that by inferring on-site itself.
        assert evidence_for("On-site", "Berlin, Germany") == ()

    def test_on_site_does_not_match_a_location_that_says_remote(self):
        assert evidence_for("On-site", "Berlin, Germany (Remote)") == ()

    def test_on_site_does_not_match_a_location_that_says_hybrid(self):
        assert evidence_for("On-site", "Berlin, Germany (Hybrid)") == ()

    def test_remote_does_not_match_a_plain_location_with_no_suffix(self):
        assert evidence_for("Remote", "Berlin, Germany") == ()

    def test_hybrid_does_not_match_a_location_that_says_remote(self):
        assert evidence_for("Hybrid", "Berlin, Germany (Remote)") == ()

    def test_remote_does_not_match_a_location_that_says_hybrid(self):
        assert evidence_for("Remote", "Berlin, Germany (Hybrid)") == ()

    def test_no_absence_of_a_suffix_is_ever_read_as_evidence_for_any_value(self):
        for work_mode in ("Remote", "Hybrid", "On-site", "Onsite", "on site"):
            assert evidence_for(work_mode, "Unknown Location") == ()


class TestBoundaries:
    def test_the_word_home_does_not_match_inside_remotehome(self):
        assert evidence_for("Home", "RemoteHome, Germany") == ()

    def test_remote_does_not_match_inside_a_larger_word(self):
        assert evidence_for("Remote", "Germany (Remotely)") == ()

    def test_a_value_is_found_when_followed_by_a_word_boundary(self):
        assert evidence_for("Remote", "Germany, Remote Team") == ("Remote",)

    @pytest.mark.parametrize(
        "location",
        [
            "Berlin, Germany (Hybrid)",
            "Berlin, Germany [Hybrid]",
            "Berlin, Germany/Hybrid",
            "Berlin, Germany; Hybrid",
            "Berlin, Germany - Hybrid",
        ],
    )
    def test_punctuation_around_the_value_is_a_boundary(self, location):
        assert evidence_for("Hybrid", location) == ("Hybrid",)

    def test_the_preference_is_matched_literally_not_as_a_pattern(self):
        assert evidence_for("Rem.te", "Germany (Remote)") == ()

    def test_a_value_is_not_found_when_preceded_by_a_word_character_then_a_dot(self):
        # Mirrors the same "ASP.NET"-style precedent established in role_preference_matcher.py and
        # location_preference_matcher.py: a word character followed by a dot is not a boundary.
        assert evidence_for("Remote", "Company.Remote Office") == ()


class TestEvidence:
    def test_the_evidence_value_is_the_trimmed_candidate_spelling(self):
        assert evidence_for("  Hybrid  ", "Berlin, Germany (Hybrid)") == ("Hybrid",)

    def test_internal_spacing_and_casing_are_preserved_beyond_outer_trimming(self):
        assert evidence_for("  oN sItE  ", "Berlin (oN sItE)") == ("oN sItE",)

    def test_a_non_matching_location_still_returns_a_result_with_the_location_set(self):
        result = match_work_mode_to_job(make_preferences(), make_job(location="Vienna, Austria"))

        assert result.job_location == "Vienna, Austria"
        assert result.evidence == ()

    def test_evidence_is_a_tuple_of_at_most_one_item(self):
        result = match_work_mode_to_job(make_preferences(), make_job())

        assert isinstance(result.evidence, tuple)
        assert len(result.evidence) <= 1


class TestFieldIsolation:
    def test_a_preferred_value_appearing_only_in_the_title_is_not_evidence(self):
        job = make_job(location="Munich, Germany", title="Berlin Remote Engineer")

        assert match_work_mode_to_job(CandidatePreferences(work_mode="Remote"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_company_name_is_not_evidence(self):
        job = make_job(location="Munich, Germany", company="Remote Software GmbH")

        assert match_work_mode_to_job(CandidatePreferences(work_mode="Remote"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_description_is_not_evidence(self):
        job = make_job(location="Munich, Germany", description="Requirements\n\n- Occasional remote work possible")

        assert match_work_mode_to_job(CandidatePreferences(work_mode="Remote"), job).evidence == ()

    def test_a_preferred_value_appearing_only_in_the_url_is_not_evidence(self):
        job = make_job(location="Munich, Germany", url="https://example.invalid/jobs/remote-role")

        assert match_work_mode_to_job(CandidatePreferences(work_mode="Remote"), job).evidence == ()

    def test_matching_uses_only_the_location_even_when_every_other_field_matches(self):
        job = make_job(
            location="Munich, Germany",
            title="Remote Software Engineer",
            company="Remote Software GmbH",
            description="Remote",
            url="https://example.invalid/remote",
        )

        assert match_work_mode_to_job(CandidatePreferences(work_mode="Remote"), job).evidence == ()

    def test_other_candidate_preference_fields_do_not_affect_matching(self):
        preferences = CandidatePreferences(
            target_roles=("Remote",),
            preferred_locations=("Remote",),
            work_mode=None,
            employment_type="Remote",
            minimum_hours_per_week=20,
        )

        assert match_work_mode_to_job(preferences, make_job(location="Germany (Remote)")).evidence == ()

    def test_other_preference_fields_do_not_suppress_a_real_work_mode_match(self):
        preferences = CandidatePreferences(
            target_roles=("Software Engineer",),
            preferred_locations=("Munich",),
            work_mode="Remote",
            employment_type="Part-time",
            minimum_hours_per_week=20,
        )

        result = match_work_mode_to_job(preferences, make_job(location="Germany (Remote)"))

        assert result.evidence == ("Remote",)

    def test_a_preference_shaped_like_a_place_does_not_match_through_the_title(self):
        job = make_job(location="Munich, Germany", title="Berlin Software Engineer")

        assert match_work_mode_to_job(CandidatePreferences(work_mode="Berlin"), job).evidence == ()


class TestNoScoreOrVerdict:
    @pytest.mark.parametrize(
        "name", ["score", "rank", "percentage", "confidence", "recommendation", "verdict", "qualifies", "matched"]
    )
    def test_the_result_has_no_score_rank_or_verdict_attribute(self, name):
        result = match_work_mode_to_job(make_preferences(), make_job())

        assert not hasattr(result, name)

    def test_the_result_exposes_exactly_the_approved_fields(self):
        result = match_work_mode_to_job(make_preferences(), make_job())

        assert [f.name for f in dataclasses.fields(result)] == ["job_location", "evidence"]

    def test_the_evidence_field_defaults_to_an_empty_tuple(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(WorkModePreferenceMatch)}

        assert fields_by_name["evidence"].default == ()

    def test_the_result_carries_no_attribute_beyond_the_two_approved_fields(self):
        result = match_work_mode_to_job(make_preferences(), make_job())

        assert vars(result) == {"job_location": result.job_location, "evidence": result.evidence}


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidatePreferences", None, 123, ["Remote"], {"work_mode": "Remote"}, make_job()],
        ids=["str", "none", "int", "list", "dict", "job"],
    )
    def test_a_non_candidate_preferences_first_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_work_mode_to_job(value, make_job())

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    @pytest.mark.parametrize(
        "value",
        ["not a Job", None, 123, ["Remote"], {"location": "Remote"}, make_preferences()],
        ids=["str", "none", "int", "list", "dict", "candidate-preferences"],
    )
    def test_a_non_job_second_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_work_mode_to_job(make_preferences(), value)

        assert str(exc_info.value) == "job must be a Job"

    def test_preferences_are_validated_before_job_when_both_are_invalid(self):
        with pytest.raises(TypeError) as exc_info:
            match_work_mode_to_job("not a CandidatePreferences", "not a Job")

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_preferences = CandidatePreferences(work_mode=SYNTHETIC_PRIVATE_MARKER)
        secret_job = make_job(location=SYNTHETIC_PRIVATE_MARKER)

        with pytest.raises(TypeError) as preferences_error:
            match_work_mode_to_job([SYNTHETIC_PRIVATE_MARKER], secret_job)
        with pytest.raises(TypeError) as job_error:
            match_work_mode_to_job(secret_preferences, {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        for exc_info in (preferences_error, job_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestImmutabilityAndDeterminism:
    def test_the_result_is_frozen(self):
        result = match_work_mode_to_job(make_preferences(), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.job_location = "Somewhere Else"
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.evidence = ()

    def test_the_result_is_hashable(self):
        first = match_work_mode_to_job(make_preferences(), make_job())
        second = match_work_mode_to_job(make_preferences(), make_job())

        assert hash(first) == hash(second)
        assert len({first, second}) == 1

    def test_repeated_calls_with_the_same_inputs_are_equal(self):
        preferences, job = make_preferences(), make_job()

        results = [match_work_mode_to_job(preferences, job) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_the_result_does_not_depend_on_the_interpreters_hash_seed(self):
        script = (
            "from candidate_preferences import CandidatePreferences; "
            "from work_mode_matcher import match_work_mode_to_job as m; "
            "from models import Job; "
            "r = m(CandidatePreferences(work_mode='Hybrid'), "
            "Job(title='t', company='c', location='Berlin, Germany (Hybrid)', description='d')); "
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
        preferences = CandidatePreferences(work_mode="  Hybrid  ")
        job = make_job(location="Berlin, Germany (Hybrid)")
        preferences_snapshot = dataclasses.replace(preferences)
        job_snapshot = dataclasses.replace(job)

        match_work_mode_to_job(preferences, job)

        assert preferences == preferences_snapshot
        assert job == job_snapshot
        assert preferences.work_mode == "  Hybrid  "
        assert job.location == "Berlin, Germany (Hybrid)"


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        preferences = CandidatePreferences(work_mode=SYNTHETIC_PRIVATE_MARKER)
        job = make_job(location=f"Berlin, {SYNTHETIC_PRIVATE_MARKER}")

        match_work_mode_to_job(preferences, job)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_work_mode_to_job(make_preferences(), make_job())

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
    def test_importing_work_mode_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, work_mode_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
