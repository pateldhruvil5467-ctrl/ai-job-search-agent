"""Tests for location_preference_matcher: candidate preferred locations vs a Job location (Task 1.12).

match_preferred_locations_to_job(preferences, job) searches Job.location, literally and
case-insensitively with a word/punctuation boundary rule, for each distinct candidate preferred
location. It never reads any other Job field, never interprets Remote/Hybrid/On-site as a work
mode, never infers geography, and never scores or ranks. All data here is synthetic.
"""

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences
from location_preference_matcher import LocationPreferenceMatch, match_preferred_locations_to_job
from models import Job

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"


def make_preferences(**overrides) -> CandidatePreferences:
    fields = {"preferred_locations": ("Berlin", "Munich")}
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


def evidence_for(preferred_locations, location) -> tuple[str, ...]:
    result = match_preferred_locations_to_job(
        CandidatePreferences(preferred_locations=tuple(preferred_locations)), make_job(location=location)
    )
    assert result.job_location == location
    return result.evidence


class TestConstructionAndPositiveMatching:
    def test_an_exact_location_match_is_found(self):
        assert evidence_for(("Berlin, Germany",), "Berlin, Germany") == ("Berlin, Germany",)

    def test_matching_is_case_insensitive(self):
        assert evidence_for(("berlin",), "Berlin, Germany") == ("berlin",)
        assert evidence_for(("BERLIN",), "berlin, germany") == ("BERLIN",)

    def test_a_double_space_in_the_job_location_does_not_prevent_a_match(self):
        assert evidence_for(("Berlin Germany",), "Berlin  Germany") == ("Berlin Germany",)

    def test_multiple_preferred_locations_can_each_match_the_same_job(self):
        result = match_preferred_locations_to_job(
            CandidatePreferences(preferred_locations=("Munich", "Bavaria")),
            make_job(location="Munich, Bavaria, Germany"),
        )

        assert result.evidence == ("Munich", "Bavaria")

    def test_only_the_preferences_actually_present_are_found(self):
        result = match_preferred_locations_to_job(
            CandidatePreferences(preferred_locations=("Berlin", "Munich")), make_job(location="Berlin, Germany")
        )

        assert result.evidence == ("Berlin",)

    def test_berlin_matches_berlin_germany(self):
        assert evidence_for(("Berlin",), "Berlin, Germany") == ("Berlin",)

    def test_munich_matches_munich_bavaria_germany(self):
        assert evidence_for(("Munich",), "Munich, Bavaria, Germany") == ("Munich",)

    def test_a_region_matches_inside_a_three_part_location(self):
        assert evidence_for(("Bavaria",), "Munich, Bavaria, Germany") == ("Bavaria",)

    def test_a_country_alone_matches_a_country_only_location(self):
        assert evidence_for(("Germany",), "Germany") == ("Germany",)

    def test_a_country_matches_inside_a_multi_part_location(self):
        assert evidence_for(("Germany",), "Berlin, Germany") == ("Germany",)


class TestBoundaries:
    def test_york_does_not_match_inside_newyork(self):
        assert evidence_for(("York",), "NewYork, USA") == ()

    def test_berlin_does_not_match_inside_berliner(self):
        assert evidence_for(("Berlin",), "Berliner Strasse District") == ()

    def test_paris_does_not_match_inside_parish(self):
        assert evidence_for(("Paris",), "Parish County") == ()

    def test_a_location_is_found_when_followed_by_a_word_boundary(self):
        assert evidence_for(("Paris",), "Paris, France") == ("Paris",)

    @pytest.mark.parametrize(
        "location",
        [
            "Berlin, Germany",
            "Berlin (Germany)",
            "Berlin/Germany",
            "Berlin-Mitte, Germany",
            "Berlin; Germany",
        ],
    )
    def test_punctuation_around_the_location_is_a_boundary(self, location):
        assert evidence_for(("Berlin",), location) == ("Berlin",)

    def test_a_parenthetical_suffix_does_not_block_the_base_place_from_matching(self):
        assert evidence_for(("Berlin, Germany",), "Berlin, Germany (Hybrid)") == ("Berlin, Germany",)

    def test_a_slash_separated_location_is_still_matched(self):
        assert evidence_for(("Berlin",), "Berlin/Brandenburg") == ("Berlin",)

    def test_a_hyphenated_location_is_still_matched(self):
        assert evidence_for(("Mitte",), "Berlin-Mitte") == ("Mitte",)

    def test_the_preference_text_is_matched_literally_not_as_a_pattern(self):
        assert evidence_for(("Ber.in",), "Berlin, Germany") == ()

    def test_a_location_is_not_found_when_preceded_by_a_word_character_then_a_dot(self):
        # Mirrors the same "ASP.NET" precedent established in role_preference_matcher.py: a word
        # character followed by a dot does not count as a boundary before the preference.
        assert evidence_for(("Berlin",), "Company.Berlin Office") == ()


class TestNoSynonymOrGeographicInference:
    def test_a_city_preference_does_not_match_a_different_city_in_the_same_country(self):
        assert evidence_for(("Munich",), "Berlin, Germany") == ()

    def test_a_country_preference_does_not_match_a_city_without_the_country_text(self):
        assert evidence_for(("Germany",), "Berlin") == ()

    def test_no_geographic_hierarchy_is_assumed_between_region_and_city(self):
        assert evidence_for(("Bavaria",), "Berlin, Germany") == ()

    def test_an_abbreviation_does_not_match_its_spelled_out_form(self):
        assert evidence_for(("NYC",), "New York City, USA") == ()


class TestWorkModeStringsAreLiteralOnly:
    def test_remote_supplied_as_a_preferred_location_matches_only_the_literal_word(self):
        assert evidence_for(("Remote",), "Germany (Remote)") == ("Remote",)

    def test_remote_supplied_as_a_preferred_location_does_not_match_when_absent(self):
        assert evidence_for(("Remote",), "Berlin, Germany") == ()

    def test_hybrid_supplied_as_a_preferred_location_matches_only_the_literal_word(self):
        assert evidence_for(("Hybrid",), "Berlin, Germany (Hybrid)") == ("Hybrid",)

    def test_hybrid_supplied_as_a_preferred_location_does_not_match_when_absent(self):
        assert evidence_for(("Hybrid",), "Berlin, Germany") == ()

    def test_on_site_supplied_as_a_preferred_location_matches_only_the_literal_word(self):
        assert evidence_for(("On-site",), "Berlin (On-site)") == ("On-site",)

    def test_on_site_is_never_inferred_from_a_plain_location_with_no_suffix(self):
        # job_page_parser never writes "On-site" into Job.location (it is implied by the absence of
        # a suffix); this matcher must not compensate for that by inferring on-site itself.
        assert evidence_for(("On-site",), "Berlin, Germany") == ()

    def test_a_bare_work_mode_word_without_a_place_is_still_only_literal_text(self):
        assert evidence_for(("Remote",), "Remote") == ("Remote",)
        assert evidence_for(("Hybrid",), "Remote") == ()

    def test_on_site_text_in_the_job_location_is_never_added_to_evidence_unless_it_was_requested(self):
        # The candidate did not ask for "On-site"; its literal presence in the job location must
        # not be injected into evidence as if it had been requested (that would be work-mode
        # inference, not a match against a stated preference).
        assert evidence_for(("Berlin",), "Berlin, Germany (On-site)") == ("Berlin",)


class TestUnknownLocation:
    def test_the_unknown_location_sentinel_is_treated_as_an_ordinary_string(self):
        assert evidence_for(("Berlin",), "Unknown Location") == ()

    def test_a_preference_literally_equal_to_the_sentinel_text_can_still_match_it(self):
        assert evidence_for(("Unknown Location",), "Unknown Location") == ("Unknown Location",)

    def test_the_sentinel_does_not_special_case_into_empty_or_error(self):
        result = match_preferred_locations_to_job(make_preferences(), make_job(location="Unknown Location"))

        assert result.job_location == "Unknown Location"
        assert result.evidence == ()


class TestEvidence:
    def test_original_candidate_spelling_is_preserved_in_evidence(self):
        assert evidence_for(("bErLiN",), "Berlin, Germany") == ("bErLiN",)

    def test_a_preference_with_surrounding_whitespace_is_found_and_reported_trimmed(self):
        assert evidence_for(("  Berlin  ",), "Berlin, Germany") == ("Berlin",)
        assert evidence_for(("  Berlin   Germany  ",), "Berlin Germany") == ("Berlin   Germany",)

    def test_a_blank_preference_is_ignored(self):
        assert evidence_for(("", "   ", "Berlin"), "Berlin, Germany") == ("Berlin",)

    def test_only_blank_preferences_give_empty_evidence(self):
        assert evidence_for(("", "  ", "\t"), "Berlin, Germany") == ()

    def test_duplicate_preferences_are_evaluated_once_keeping_the_first_spelling(self):
        result = match_preferred_locations_to_job(
            CandidatePreferences(preferred_locations=("Berlin", "BERLIN", "berlin")),
            make_job(location="Berlin, Germany"),
        )

        assert result.evidence == ("Berlin",)

    def test_evidence_follows_candidate_order_not_location_text_order(self):
        result = match_preferred_locations_to_job(
            CandidatePreferences(preferred_locations=("Germany", "Berlin")), make_job(location="Berlin, Germany")
        )

        assert result.evidence == ("Germany", "Berlin")

    def test_empty_preferred_locations_gives_empty_evidence(self):
        assert evidence_for((), "Berlin, Germany") == ()

    def test_no_matching_preferences_gives_empty_evidence(self):
        assert evidence_for(("Munich", "Hamburg"), "Berlin, Germany") == ()

    def test_a_non_matching_location_still_returns_a_result_with_the_location_set(self):
        result = match_preferred_locations_to_job(make_preferences(), make_job(location="Vienna, Austria"))

        assert result.job_location == "Vienna, Austria"
        assert result.evidence == ()


class TestJobFieldIsolation:
    def test_a_preference_appearing_only_in_the_title_is_not_evidence(self):
        job = make_job(location="Munich, Germany", title="Software Engineer Berlin")

        assert match_preferred_locations_to_job(CandidatePreferences(preferred_locations=("Berlin",)), job).evidence == ()

    def test_a_preference_appearing_only_in_the_company_name_is_not_evidence(self):
        job = make_job(location="Munich, Germany", company="Berlin Software GmbH")

        assert match_preferred_locations_to_job(CandidatePreferences(preferred_locations=("Berlin",)), job).evidence == ()

    def test_a_preference_appearing_only_in_the_description_is_not_evidence(self):
        job = make_job(location="Munich, Germany", description="Requirements\n\n- Relocation to Berlin possible")

        assert match_preferred_locations_to_job(CandidatePreferences(preferred_locations=("Berlin",)), job).evidence == ()

    def test_a_preference_appearing_only_in_the_url_is_not_evidence(self):
        job = make_job(location="Munich, Germany", url="https://example.invalid/jobs/berlin-office")

        assert match_preferred_locations_to_job(CandidatePreferences(preferred_locations=("Berlin",)), job).evidence == ()

    def test_matching_uses_only_the_location_even_when_every_other_field_matches(self):
        job = make_job(
            location="Munich, Germany",
            title="Berlin Software Engineer",
            company="Berlin Software GmbH",
            description="Berlin",
            url="https://example.invalid/berlin",
        )

        assert match_preferred_locations_to_job(CandidatePreferences(preferred_locations=("Berlin",)), job).evidence == ()


class TestNoScoreOrVerdict:
    @pytest.mark.parametrize(
        "name", ["score", "rank", "percentage", "confidence", "recommendation", "verdict", "qualifies", "matched"]
    )
    def test_the_result_has_no_score_rank_or_verdict_attribute(self, name):
        result = match_preferred_locations_to_job(make_preferences(), make_job())

        assert not hasattr(result, name)

    def test_the_result_exposes_exactly_the_approved_fields(self):
        result = match_preferred_locations_to_job(make_preferences(), make_job())

        assert [f.name for f in dataclasses.fields(result)] == ["job_location", "evidence"]

    def test_the_evidence_field_defaults_to_an_empty_tuple(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(LocationPreferenceMatch)}

        assert fields_by_name["evidence"].default == ()

    def test_the_result_carries_no_attribute_beyond_the_two_approved_fields(self):
        result = match_preferred_locations_to_job(make_preferences(), make_job())

        assert vars(result) == {"job_location": result.job_location, "evidence": result.evidence}


class TestValidation:
    @pytest.mark.parametrize(
        "value",
        ["not a CandidatePreferences", None, 123, ["Berlin"], {"preferred_locations": ("Berlin",)}, make_job()],
        ids=["str", "none", "int", "list", "dict", "job"],
    )
    def test_a_non_candidate_preferences_first_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_preferred_locations_to_job(value, make_job())

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    @pytest.mark.parametrize(
        "value",
        ["not a Job", None, 123, ["Berlin"], {"location": "Berlin"}, make_preferences()],
        ids=["str", "none", "int", "list", "dict", "candidate-preferences"],
    )
    def test_a_non_job_second_argument_raises_type_error(self, value):
        with pytest.raises(TypeError) as exc_info:
            match_preferred_locations_to_job(make_preferences(), value)

        assert str(exc_info.value) == "job must be a Job"

    def test_preferences_are_validated_before_job_when_both_are_invalid(self):
        with pytest.raises(TypeError) as exc_info:
            match_preferred_locations_to_job("not a CandidatePreferences", "not a Job")

        assert str(exc_info.value) == "preferences must be a CandidatePreferences"

    def test_the_error_messages_never_contain_the_arguments(self):
        secret_preferences = CandidatePreferences(preferred_locations=(SYNTHETIC_PRIVATE_MARKER,))
        secret_job = make_job(location=SYNTHETIC_PRIVATE_MARKER)

        with pytest.raises(TypeError) as preferences_error:
            match_preferred_locations_to_job([SYNTHETIC_PRIVATE_MARKER], secret_job)
        with pytest.raises(TypeError) as job_error:
            match_preferred_locations_to_job(secret_preferences, {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER})

        for exc_info in (preferences_error, job_error):
            assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
            assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)
            assert exc_info.value.__cause__ is None


class TestImmutabilityAndDeterminism:
    def test_the_result_is_frozen(self):
        result = match_preferred_locations_to_job(make_preferences(), make_job())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.job_location = "Somewhere Else"
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.evidence = ()

    def test_the_result_is_hashable(self):
        first = match_preferred_locations_to_job(make_preferences(), make_job())
        second = match_preferred_locations_to_job(make_preferences(), make_job())

        assert hash(first) == hash(second)
        assert len({first, second}) == 1

    def test_repeated_calls_with_the_same_inputs_are_equal(self):
        preferences, job = make_preferences(), make_job()

        results = [match_preferred_locations_to_job(preferences, job) for _ in range(5)]

        assert all(result == results[0] for result in results)

    def test_the_result_does_not_depend_on_the_interpreters_hash_seed(self):
        # A same-process "repeated calls are equal" test cannot catch ordering that leaks through a
        # set (stable within one process, but randomized across processes by PYTHONHASHSEED).
        script = (
            "from candidate_preferences import CandidatePreferences; "
            "from location_preference_matcher import match_preferred_locations_to_job as m; "
            "from models import Job; "
            "r = m(CandidatePreferences(preferred_locations=('Germany', 'Berlin', 'Munich', 'Bavaria')), "
            "Job(title='t', company='c', location='Munich, Bavaria, Germany', description='d')); "
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
        preferences = CandidatePreferences(preferred_locations=("Berlin", "berlin", " Munich "))
        job = make_job(location="Berlin, Germany")
        preferences_snapshot = dataclasses.replace(preferences)
        job_snapshot = dataclasses.replace(job)

        match_preferred_locations_to_job(preferences, job)

        assert preferences == preferences_snapshot
        assert job == job_snapshot
        assert preferences.preferred_locations == ("Berlin", "berlin", " Munich ")
        assert job.location == "Berlin, Germany"


class TestPrivacy:
    def test_matching_produces_no_console_output_or_log_records(self, capsys, caplog):
        preferences = CandidatePreferences(preferred_locations=(SYNTHETIC_PRIVATE_MARKER, "Berlin"))
        job = make_job(location=f"Berlin, {SYNTHETIC_PRIVATE_MARKER}")

        match_preferred_locations_to_job(preferences, job)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_matching_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        match_preferred_locations_to_job(make_preferences(), make_job())

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
    def test_importing_location_preference_matcher_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, location_preference_matcher; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
