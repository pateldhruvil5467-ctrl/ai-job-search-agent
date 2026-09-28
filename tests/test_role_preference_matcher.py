"""Tests for role_preference_matcher: candidate target roles vs a Job title (Task 1.11).

match_target_roles_to_job(preferences, job) searches Job.title, literally and case-insensitively
with the same word/punctuation boundary rule already established by matcher.py, for each distinct
candidate target role. It never reads any other Job field, never scores or ranks, and a role that
is a substring of a larger word in the title must not be reported as evidence. All data here is
synthetic.
"""

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences
from models import Job
from role_preference_matcher import RolePreferenceMatch, match_target_roles_to_job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"


def make_preferences(**overrides) -> CandidatePreferences:
    fields = {"target_roles": ("Backend Developer", "Data Scientist")}
    fields.update(overrides)
    return CandidatePreferences(**fields)


def make_job(**overrides) -> Job:
    fields = {
        "title": "Backend Developer",
        "company": "Acme GmbH",
        "location": "Berlin, Germany",
        "description": "Requirements\n\n- Backend Developer experience required",
        "url": "https://www.linkedin.com/jobs/view/3812345678/",
    }
    fields.update(overrides)
    return Job(**fields)


def evidence_for(target_roles, title) -> tuple[str, ...]:
    result = match_target_roles_to_job(CandidatePreferences(target_roles=tuple(target_roles)), make_job(title=title))
    assert result.job_title == title
    return result.evidence


class TestConstructionAndPositiveMatching:
    def test_an_exact_role_in_the_title_is_found(self):
        assert evidence_for(("Backend Developer",), "Backend Developer") == ("Backend Developer",)

    def test_matching_is_case_insensitive(self):
        assert evidence_for(("backend developer",), "Backend Developer") == ("backend developer",)
        assert evidence_for(("BACKEND DEVELOPER",), "backend developer") == ("BACKEND DEVELOPER",)

    def test_a_role_is_found_as_a_sub_phrase_of_a_longer_title(self):
        assert evidence_for(("Backend Developer",), "Senior Backend Developer (m/f/d)") == ("Backend Developer",)

    def test_a_role_is_found_at_the_start_of_the_title(self):
        assert evidence_for(("Backend Developer",), "Backend Developer II") == ("Backend Developer",)

    def test_a_role_is_found_at_the_end_of_the_title(self):
        assert evidence_for(("Data Scientist",), "Senior Data Scientist") == ("Data Scientist",)

    def test_a_role_is_found_in_the_middle_of_the_title(self):
        assert evidence_for(("Data Scientist",), "Working Student, Data Scientist, Berlin") == ("Data Scientist",)

    def test_a_multi_word_role_matches_across_a_double_space_in_the_title(self):
        assert evidence_for(("Backend Developer",), "Backend  Developer") == ("Backend Developer",)

    def test_multiple_target_roles_can_each_be_found_in_the_same_title(self):
        result = match_target_roles_to_job(
            CandidatePreferences(target_roles=("Backend", "Developer")), make_job(title="Backend Developer")
        )

        assert result.evidence == ("Backend", "Developer")

    def test_only_the_roles_actually_present_are_found(self):
        result = match_target_roles_to_job(
            CandidatePreferences(target_roles=("Backend Developer", "Data Scientist")),
            make_job(title="Backend Developer"),
        )

        assert result.evidence == ("Backend Developer",)


class TestBoundaries:
    def test_java_does_not_match_inside_javascript(self):
        assert evidence_for(("Java",), "JavaScript Developer") == ()

    def test_java_does_match_as_its_own_word(self):
        assert evidence_for(("Java",), "Java Developer") == ("Java",)

    def test_a_role_is_not_found_inside_a_longer_word(self):
        assert evidence_for(("Engineer",), "Engineering Manager") == ()

    def test_a_role_is_found_when_followed_by_a_word_boundary(self):
        assert evidence_for(("Engineer",), "Engineer Manager") == ("Engineer",)

    def test_a_short_role_does_not_match_before_a_plus_sign(self):
        assert evidence_for(("C",), "C++ Developer") == ()

    def test_a_short_role_matches_when_not_followed_by_a_plus_sign(self):
        assert evidence_for(("C",), "C Developer") == ("C",)

    @pytest.mark.parametrize(
        "title",
        [
            "Backend Developer, Payments",
            "Backend Developer (Remote)",
            "Backend Developer / Platform Team",
            "Backend Developer: Platform Team",
            "Backend Developer; Platform Team",
        ],
    )
    def test_punctuation_around_the_role_is_a_boundary(self, title):
        assert evidence_for(("Backend Developer",), title) == ("Backend Developer",)

    def test_a_trailing_sentence_period_is_a_boundary(self):
        assert evidence_for(("Backend Developer",), "Backend Developer.") == ("Backend Developer",)

    def test_the_role_text_is_matched_literally_not_as_a_pattern(self):
        assert evidence_for(("C++",), "C   Developer") == ()

    def test_a_role_is_not_found_when_preceded_by_a_word_character_with_no_boundary(self):
        assert evidence_for(("Engineer",), "SeniorEngineer") == ()

    def test_net_is_not_found_inside_asp_net(self):
        # Mirrors the same accepted precedent already established in matcher.py: a word character
        # followed by a dot does not count as a boundary before the role.
        assert evidence_for(("NET",), "ASP.NET Developer") == ()

    def test_a_hyphen_is_a_boundary_a_role_is_still_found_across_it(self):
        # Mirrors matcher.py's precedent that "-" is a boundary (there demonstrated the other way,
        # by "learn" being found inside "Scikit-learn"): a role adjacent to a hyphen is not blocked.
        assert evidence_for(("Developer",), "Junior-Developer") == ("Developer",)


class TestNoSynonyms:
    def test_an_abbreviation_does_not_match_its_spelled_out_form(self):
        assert evidence_for(("SWE",), "Software Engineer") == ()

    def test_the_spelled_out_form_does_not_match_the_abbreviation(self):
        assert evidence_for(("Software Engineer",), "SWE") == ()

    def test_a_related_but_different_literal_phrase_does_not_match(self):
        assert evidence_for(("Backend Developer",), "Backend Engineer") == ()

    def test_singular_and_plural_forms_do_not_match_each_other(self):
        assert evidence_for(("Developer",), "Developers Wanted") == ()


class TestEvidence:
    def test_original_candidate_spelling_is_preserved_in_evidence(self):
        assert evidence_for(("bAcKeNd DeVeLoPeR",), "Backend Developer") == ("bAcKeNd DeVeLoPeR",)

    def test_a_role_with_surrounding_whitespace_is_found_and_reported_trimmed(self):
        # Mirrors matcher.py's own established precedent for skills: outer whitespace is stripped
        # from evidence, but internal spacing and casing are otherwise kept exactly as given.
        assert evidence_for(("  Backend Developer  ",), "Backend Developer") == ("Backend Developer",)
        assert evidence_for(("  Backend   Developer  ",), "Backend Developer") == ("Backend   Developer",)

    def test_evidence_follows_candidate_order_not_title_order(self):
        result = match_target_roles_to_job(
            CandidatePreferences(target_roles=("Data Scientist", "Backend Developer")),
            make_job(title="Backend Developer, Data Scientist"),
        )

        assert result.evidence == ("Data Scientist", "Backend Developer")

    def test_duplicate_target_roles_are_evaluated_once_keeping_the_first_spelling(self):
        result = match_target_roles_to_job(
            CandidatePreferences(target_roles=("Backend Developer", "BACKEND DEVELOPER", "backend developer")),
            make_job(title="Backend Developer"),
        )

        assert result.evidence == ("Backend Developer",)

    def test_empty_target_roles_gives_empty_evidence(self):
        assert evidence_for((), "Backend Developer") == ()

    def test_no_matching_target_roles_gives_empty_evidence(self):
        assert evidence_for(("Data Scientist", "Product Manager"), "Backend Developer") == ()

    def test_a_non_matching_title_still_returns_a_result_with_the_title_set(self):
        result = match_target_roles_to_job(make_preferences(), make_job(title="Marketing Intern"))

        assert result.job_title == "Marketing Intern"
        assert result.evidence == ()


class TestJobFieldIsolation:
    def test_a_role_appearing_only_in_the_description_is_not_evidence(self):
        job = make_job(title="Software Engineer", description="Requirements\n\n- Backend Developer experience")

        assert match_target_roles_to_job(CandidatePreferences(target_roles=("Backend Developer",)), job).evidence == ()

    def test_a_role_appearing_only_in_the_company_name_is_not_evidence(self):
        job = make_job(title="Software Engineer", company="Backend Developer GmbH")

        assert match_target_roles_to_job(CandidatePreferences(target_roles=("Backend Developer",)), job).evidence == ()

    def test_a_role_appearing_only_in_the_location_is_not_evidence(self):
        job = make_job(title="Software Engineer", location="Backend Developer Strasse, Berlin")

        assert match_target_roles_to_job(CandidatePreferences(target_roles=("Backend Developer",)), job).evidence == ()

    def test_a_role_appearing_only_in_the_url_is_not_evidence(self):
        job = make_job(title="Software Engineer", url="https://example.invalid/jobs/backend-developer")

        assert match_target_roles_to_job(CandidatePreferences(target_roles=("Backend Developer",)), job).evidence == ()

    def test_a_role_that_would_be_boundary_matched_in_the_url_slug_is_still_not_evidence(self):
        # A single-word role, formatted so a leaked URL slug WOULD satisfy the boundary rule (a
        # hyphen is a boundary): this is the case the earlier URL test cannot distinguish, since
        # its multi-word role/hyphenated-slug combination could never match the pattern either way.
        job = make_job(title="Software Engineer", url="https://example.invalid/jobs/python-developer")

        assert match_target_roles_to_job(CandidatePreferences(target_roles=("Python",)), job).evidence == ()

    def test_matching_uses_only_the_title_even_when_every_other_field_matches(self):
        job = make_job(
            title="Marketing Intern",
            company="Backend Developer GmbH",
            location="Backend Developer Strasse",
            description="Backend Developer",
            url="https://example.invalid/backend-developer",
        )

        assert match_target_roles_to_job(CandidatePreferences(target_roles=("Backend Developer",)), job).evidence == ()


class TestNoScoreOrVerdict:
    @pytest.mark.parametrize(
        "name", ["score", "rank", "percentage", "confidence", "recommendation", "verdict", "qualifies", "matched"]
    )
    def test_the_result_has_no_score_rank_or_verdict_attribute(self, name):
        result = match_target_roles_to_job(make_preferences(), make_job())

        assert not hasattr(result, name)

    def test_the_result_exposes_exactly_the_approved_fields(self):
        result = match_target_roles_to_job(make_preferences(), make_job())

        assert [f.name for f in dataclasses.fields(result)] == ["job_title", "evidence"]

    def test_the_evidence_field_defaults_to_an_empty_tuple(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(RolePreferenceMatch)}

        assert fields_by_name["evidence"].default == ()

    def test_the_result_carries_no_attribute_beyond_the_two_approved_fields(self):
        result = match_target_roles_to_job(make_preferences(), make_job())

        assert vars(result) == {"job_title": result.job_title, "evidence": result.evidence}


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidatePreferences", None, 123, ["Backend Developer"], {"target_roles": ("Backend Developer",)}, make_job()],
        ids=["str", "none", "int", "list", "dict", "job"],
    )
    def test_a_non_candidate_preferences_first_argument_raises_type_error(self, value):
        with pytest.raises(TypeError):
            match_target_roles_to_job(value, make_job())

    @pytest.mark.parametrize(
        "value",
        ["not a Job", None, 123, ["Backend Developer"], {"title": "Backend Developer"}, make_preferences()],
        ids=["str", "none", "int", "list", "dict", "candidate-preferences"],
    )
    def test_a_non_job_second_argument_raises_type_error(self, value):
        with pytest.raises(TypeError):
            match_target_roles_to_job(make_preferences(), value)

    def test_the_candidate_argument_is_validated_before_the_job_argument(self):
        with pytest.raises(TypeError) as exc_info:
            match_target_roles_to_job("not a CandidatePreferences", "not a Job")

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_preferences = CandidatePreferences(target_roles=(SYNTHETIC_PRIVATE_MARKER,))
        secret_job = make_job(title=SYNTHETIC_PRIVATE_MARKER)

        with pytest.raises(TypeError) as candidate_error:
            match_target_roles_to_job([SYNTHETIC_PRIVATE_MARKER], secret_job)
        with pytest.raises(TypeError) as job_error:
            match_target_roles_to_job(secret_preferences, {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        for exc_info in (candidate_error, job_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestImmutabilityAndDeterminism:
    def test_the_result_is_frozen(self):
        result = match_target_roles_to_job(make_preferences(), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.job_title = "Something Else"
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.evidence = ()

    def test_the_result_is_hashable(self):
        first = match_target_roles_to_job(make_preferences(), make_job())
        second = match_target_roles_to_job(make_preferences(), make_job())

        assert hash(first) == hash(second)
        assert len({first, second}) == 1

    def test_repeated_calls_with_the_same_inputs_are_equal(self):
        preferences, job = make_preferences(), make_job()

        results = [match_target_roles_to_job(preferences, job) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_the_inputs_are_not_mutated(self):
        preferences = CandidatePreferences(target_roles=("Backend Developer", "backend developer", " Data Scientist "))
        job = make_job(title="Backend Developer")
        preferences_snapshot = dataclasses.replace(preferences)
        job_snapshot = dataclasses.replace(job)

        match_target_roles_to_job(preferences, job)

        assert preferences == preferences_snapshot
        assert job == job_snapshot
        assert preferences.target_roles == ("Backend Developer", "backend developer", " Data Scientist ")
        assert job.title == "Backend Developer"


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        preferences = CandidatePreferences(target_roles=(SYNTHETIC_PRIVATE_MARKER, "Backend Developer"))
        job = make_job(title=f"Backend Developer, {SYNTHETIC_PRIVATE_MARKER}")

        match_target_roles_to_job(preferences, job)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_target_roles_to_job(make_preferences(), make_job())

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
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
        ],
    )
    def test_importing_role_preference_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, role_preference_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
