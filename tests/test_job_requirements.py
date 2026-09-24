import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from job_requirements import JobRequirements

REPO_ROOT = Path(__file__).resolve().parent.parent

FIELDS = ["skills", "experience", "education"]


def make_requirements(**overrides) -> JobRequirements:
    fields = {
        "skills": ("Python", "SQL"),
        "experience": ("Solid experience with Python and SQL",),
        "education": ("Currently enrolled in a Computer Science or related degree",),
    }
    fields.update(overrides)
    return JobRequirements(**fields)


class TestConstruction:
    def test_default_instance_has_empty_collections(self):
        requirements = JobRequirements()

        assert requirements.skills == ()
        assert requirements.experience == ()
        assert requirements.education == ()

    def test_holds_explicit_skills(self):
        requirements = JobRequirements(skills=("Python", "SQL"))

        assert requirements.skills == ("Python", "SQL")
        assert requirements.experience == ()
        assert requirements.education == ()

    def test_holds_explicit_experience(self):
        requirements = JobRequirements(experience=("Solid experience with Python",))

        assert requirements.experience == ("Solid experience with Python",)
        assert requirements.skills == ()
        assert requirements.education == ()

    def test_holds_explicit_education(self):
        requirements = JobRequirements(education=("Degree in Computer Science",))

        assert requirements.education == ("Degree in Computer Science",)
        assert requirements.skills == ()
        assert requirements.experience == ()

    def test_holds_all_fields_together(self):
        requirements = make_requirements()

        assert requirements.skills == ("Python", "SQL")
        assert requirements.experience == ("Solid experience with Python and SQL",)
        assert requirements.education == ("Currently enrolled in a Computer Science or related degree",)

    def test_instances_with_equal_fields_are_equal(self):
        assert make_requirements() == make_requirements()

    @pytest.mark.parametrize("field", FIELDS)
    def test_instances_differing_in_any_field_are_not_equal(self, field):
        assert make_requirements() != make_requirements(**{field: ("Something else",)})


class TestCollections:
    @pytest.mark.parametrize("field", FIELDS)
    def test_each_field_is_stored_as_a_tuple(self, field):
        requirements = make_requirements()

        assert isinstance(getattr(requirements, field), tuple)

    @pytest.mark.parametrize("field", FIELDS)
    def test_default_of_each_field_is_a_tuple(self, field):
        assert isinstance(getattr(JobRequirements(), field), tuple)

    @pytest.mark.parametrize("field", FIELDS)
    def test_entry_order_is_preserved(self, field):
        requirements = JobRequirements(**{field: ("Third", "First", "Second")})

        assert getattr(requirements, field) == ("Third", "First", "Second")


class TestImmutability:
    @pytest.mark.parametrize("field", FIELDS)
    def test_fields_cannot_be_reassigned(self, field):
        requirements = make_requirements()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(requirements, field, ())

    def test_instances_are_hashable_value_objects(self):
        assert len({make_requirements(), make_requirements()}) == 1
        assert len({make_requirements(), make_requirements(skills=("Java",))}) == 2


class TestNoSilentNormalization:
    @pytest.mark.parametrize("field", FIELDS)
    def test_surrounding_whitespace_is_preserved(self, field):
        requirements = JobRequirements(**{field: ("  Python  ", "\tSQL\n")})

        assert getattr(requirements, field) == ("  Python  ", "\tSQL\n")

    @pytest.mark.parametrize("field", FIELDS)
    def test_casing_is_preserved(self, field):
        requirements = JobRequirements(**{field: ("PYTHON", "python", "Python")})

        assert getattr(requirements, field) == ("PYTHON", "python", "Python")

    @pytest.mark.parametrize("field", FIELDS)
    def test_unicode_text_is_preserved(self, field):
        entries = ("Softwareentwicklung in Straße GmbH", "Erfahrung mit Übersetzung \U0001f680")

        requirements = JobRequirements(**{field: entries})

        assert getattr(requirements, field) == entries

    @pytest.mark.parametrize("field", FIELDS)
    def test_empty_strings_are_accepted_and_preserved(self, field):
        requirements = JobRequirements(**{field: ("", "Python", "")})

        assert getattr(requirements, field) == ("", "Python", "")

    @pytest.mark.parametrize("field", FIELDS)
    def test_duplicate_entries_are_not_removed(self, field):
        requirements = JobRequirements(**{field: ("Python", "Python")})

        assert getattr(requirements, field) == ("Python", "Python")


class TestDataclassContract:
    def test_is_a_dataclass(self):
        assert dataclasses.is_dataclass(JobRequirements)

    def test_is_frozen(self):
        assert JobRequirements.__dataclass_params__.frozen is True

    def test_has_exactly_the_agreed_fields_in_order(self):
        assert [f.name for f in dataclasses.fields(JobRequirements)] == ["skills", "experience", "education"]

    @pytest.mark.parametrize("field", FIELDS)
    def test_every_field_defaults_to_an_empty_tuple(self, field):
        fields_by_name = {f.name: f for f in dataclasses.fields(JobRequirements)}

        assert fields_by_name[field].default == ()


class TestIndependence:
    @pytest.mark.parametrize("module", ["selenium", "pandas", "webdriver_manager", "pdfplumber", "models", "candidate"])
    def test_importing_job_requirements_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, job_requirements; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
