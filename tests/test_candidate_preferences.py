import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from candidate_preferences import CandidatePreferences

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_preferences(**overrides) -> CandidatePreferences:
    fields = {
        "target_roles": ("Working Student Software Engineer", "Backend Developer"),
        "preferred_locations": ("Berlin", "Remote"),
        "work_mode": "Hybrid",
        "employment_type": "Internship",
        "minimum_hours_per_week": 15,
    }
    fields.update(overrides)
    return CandidatePreferences(**fields)


class TestConstruction:
    def test_holds_the_given_values(self):
        preferences = make_preferences()

        assert preferences.target_roles == ("Working Student Software Engineer", "Backend Developer")
        assert preferences.preferred_locations == ("Berlin", "Remote")
        assert preferences.work_mode == "Hybrid"
        assert preferences.employment_type == "Internship"
        assert preferences.minimum_hours_per_week == 15

    def test_all_fields_default_when_constructed_with_no_arguments(self):
        preferences = CandidatePreferences()

        assert preferences.target_roles == ()
        assert preferences.preferred_locations == ()
        assert preferences.work_mode is None
        assert preferences.employment_type is None
        assert preferences.minimum_hours_per_week is None

    def test_each_field_can_be_set_independently_of_the_others(self):
        assert CandidatePreferences(target_roles=("Data Analyst",)).target_roles == ("Data Analyst",)
        assert CandidatePreferences(preferred_locations=("Munich",)).preferred_locations == ("Munich",)
        assert CandidatePreferences(work_mode="Remote").work_mode == "Remote"
        assert CandidatePreferences(employment_type="Full-time").employment_type == "Full-time"
        assert CandidatePreferences(minimum_hours_per_week=20).minimum_hours_per_week == 20

    def test_work_mode_and_employment_type_accept_none_explicitly(self):
        preferences = CandidatePreferences(work_mode=None, employment_type=None)

        assert preferences.work_mode is None
        assert preferences.employment_type is None

    def test_minimum_hours_per_week_accepts_zero(self):
        assert CandidatePreferences(minimum_hours_per_week=0).minimum_hours_per_week == 0

    def test_instances_with_equal_fields_are_equal(self):
        assert make_preferences() == make_preferences()

    @pytest.mark.parametrize(
        "field",
        ["target_roles", "preferred_locations", "work_mode", "employment_type", "minimum_hours_per_week"],
    )
    def test_instances_differing_in_any_single_field_are_not_equal(self, field):
        changed = {
            "target_roles": ("Something Else",),
            "preferred_locations": ("Somewhere Else",),
            "work_mode": "Remote",
            "employment_type": "Full-time",
            "minimum_hours_per_week": 40,
        }
        assert make_preferences() != make_preferences(**{field: changed[field]})


class TestCollections:
    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_the_field_is_stored_as_a_tuple(self, field):
        assert isinstance(getattr(make_preferences(), field), tuple)

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_the_default_is_a_tuple(self, field):
        assert isinstance(getattr(CandidatePreferences(), field), tuple)

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_entry_order_is_preserved(self, field):
        preferences = CandidatePreferences(**{field: ("Third", "First", "Second")})

        assert getattr(preferences, field) == ("Third", "First", "Second")

    def test_multiple_target_roles_keep_their_given_order(self):
        preferences = CandidatePreferences(target_roles=("Data Analyst", "Backend Developer", "Data Analyst"))

        assert preferences.target_roles == ("Data Analyst", "Backend Developer", "Data Analyst")

    def test_multiple_preferred_locations_keep_their_given_order(self):
        preferences = CandidatePreferences(preferred_locations=("Berlin", "Remote", "Munich"))

        assert preferences.preferred_locations == ("Berlin", "Remote", "Munich")


class TestImmutability:
    @pytest.mark.parametrize(
        "field",
        ["target_roles", "preferred_locations", "work_mode", "employment_type", "minimum_hours_per_week"],
    )
    def test_fields_cannot_be_reassigned(self, field):
        preferences = make_preferences()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(preferences, field, None)

    def test_instances_are_hashable_value_objects(self):
        assert len({make_preferences(), make_preferences()}) == 1
        assert len({make_preferences(), CandidatePreferences()}) == 2

    def test_two_default_constructed_instances_are_equal_but_independent_objects(self):
        first, second = CandidatePreferences(), CandidatePreferences()

        assert first == second
        assert first is not second


class TestNoSilentNormalization:
    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_surrounding_whitespace_in_entries_is_preserved(self, field):
        preferences = CandidatePreferences(**{field: ("  Berlin  ",)})

        assert getattr(preferences, field) == ("  Berlin  ",)

    def test_surrounding_whitespace_in_work_mode_is_preserved(self):
        assert CandidatePreferences(work_mode="  Remote  ").work_mode == "  Remote  "

    def test_surrounding_whitespace_in_employment_type_is_preserved(self):
        assert CandidatePreferences(employment_type="  Internship  ").employment_type == "  Internship  "

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_casing_is_preserved(self, field):
        preferences = CandidatePreferences(**{field: ("BERLIN", "berlin", "Berlin")})

        assert getattr(preferences, field) == ("BERLIN", "berlin", "Berlin")

    def test_work_mode_casing_is_preserved(self):
        assert CandidatePreferences(work_mode="rEmOtE").work_mode == "rEmOtE"

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_duplicate_entries_are_not_removed(self, field):
        preferences = CandidatePreferences(**{field: ("Berlin", "Berlin")})

        assert getattr(preferences, field) == ("Berlin", "Berlin")

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_empty_strings_are_accepted(self, field):
        preferences = CandidatePreferences(**{field: ("",)})

        assert getattr(preferences, field) == ("",)

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_unicode_text_is_accepted_and_preserved(self, field):
        preferences = CandidatePreferences(**{field: ("Straße GmbH", "Zürich")})

        assert getattr(preferences, field) == ("Straße GmbH", "Zürich")

    @pytest.mark.parametrize("field", ["target_roles", "preferred_locations"])
    def test_a_list_is_not_coerced_into_a_tuple(self, field):
        given = ["Backend Developer"]

        preferences = CandidatePreferences(**{field: given})

        assert getattr(preferences, field) is given
        assert isinstance(getattr(preferences, field), list)

    def test_minimum_hours_per_week_is_not_coerced_by_int(self):
        preferences = CandidatePreferences(minimum_hours_per_week=15.5)

        assert preferences.minimum_hours_per_week == 15.5
        assert isinstance(preferences.minimum_hours_per_week, float)


class TestNoMatchingBehavior:
    def test_the_class_defines_no_methods_beyond_the_dataclass_defaults(self):
        own_methods = {
            name
            for name, value in vars(CandidatePreferences).items()
            if callable(value) and not name.startswith("__")
        }

        assert own_methods == set()

    @pytest.mark.parametrize("name", ["score", "rank", "match", "matches", "weight", "priority", "recommend"])
    def test_no_scoring_or_matching_attribute_exists(self, name):
        assert not hasattr(make_preferences(), name)

    @pytest.mark.parametrize("name", ["__lt__", "__le__", "__gt__", "__ge__"])
    def test_no_ordering_comparison_is_defined(self, name):
        # A dataclass with order=True would add these directly to the class; object's own
        # fallback (present on every class) does not count, so this checks the class's own dict.
        assert name not in vars(CandidatePreferences)


class TestDataclassContract:
    def test_is_a_dataclass(self):
        assert dataclasses.is_dataclass(CandidatePreferences)

    def test_is_frozen(self):
        assert CandidatePreferences.__dataclass_params__.frozen is True

    def test_has_exactly_the_agreed_fields_in_order(self):
        assert [f.name for f in dataclasses.fields(CandidatePreferences)] == [
            "target_roles",
            "preferred_locations",
            "work_mode",
            "employment_type",
            "minimum_hours_per_week",
        ]

    def test_the_tuple_fields_default_to_an_empty_tuple(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(CandidatePreferences)}

        assert fields_by_name["target_roles"].default == ()
        assert fields_by_name["preferred_locations"].default == ()

    def test_the_optional_fields_default_to_none(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(CandidatePreferences)}

        assert fields_by_name["work_mode"].default is None
        assert fields_by_name["employment_type"].default is None
        assert fields_by_name["minimum_hours_per_week"].default is None

    def test_the_representation_includes_every_field_and_value(self):
        preferences = make_preferences()

        assert repr(preferences) == (
            "CandidatePreferences(target_roles=('Working Student Software Engineer', 'Backend Developer'), "
            "preferred_locations=('Berlin', 'Remote'), work_mode='Hybrid', employment_type='Internship', "
            "minimum_hours_per_week=15)"
        )


class TestIndependence:
    def test_the_module_imports_only_dataclasses(self):
        import ast

        tree = ast.parse(Path("candidate_preferences.py").read_text(encoding="ascii"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}

        assert imported_modules == {"dataclasses"}

    def test_candidate_preferences_does_not_require_a_candidate_profile_a_job_or_job_requirements(self):
        preferences = CandidatePreferences(
            target_roles=("Backend Developer",), preferred_locations=("Berlin",), work_mode="Remote"
        )

        assert preferences.target_roles == ("Backend Developer",)

    @pytest.mark.parametrize(
        "module",
        ["selenium", "pandas", "webdriver_manager", "pdfplumber", "models", "candidate", "job_requirements"],
    )
    def test_importing_candidate_preferences_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, candidate_preferences; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
