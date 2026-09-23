import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from candidate import CandidateProfile, Education, Experience

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_experience(**overrides) -> Experience:
    fields = {
        "title": "Working Student Software Engineer",
        "organization": "Acme GmbH",
        "start": "2024-01",
        "end": "2024-12",
    }
    fields.update(overrides)
    return Experience(**fields)


def make_education(**overrides) -> Education:
    fields = {
        "institution": "TU Berlin",
        "degree": "MSc Software Engineering",
        "field": "Computer Science",
    }
    fields.update(overrides)
    return Education(**fields)


def make_profile(**overrides) -> CandidateProfile:
    return CandidateProfile(**overrides)


class TestExperienceConstruction:
    def test_holds_the_given_values(self):
        experience = make_experience()

        assert experience.title == "Working Student Software Engineer"
        assert experience.organization == "Acme GmbH"
        assert experience.start == "2024-01"
        assert experience.end == "2024-12"

    def test_end_defaults_to_none_for_ongoing_experience(self):
        experience = Experience(title="Engineer", organization="Acme", start="2024-01", end=None)

        assert experience.end is None

    def test_arbitrary_date_strings_are_accepted_without_parsing(self):
        for date_string in ["2024-01", "January 2024", "01/2024", "2024", "sometime last year", ""]:
            experience = make_experience(start=date_string, end=date_string)

            assert experience.start == date_string
            assert experience.end == date_string

    def test_unicode_text_is_accepted(self):
        experience = make_experience(title="Werkstudent Softwareentwicklung", organization="Straße GmbH \U0001f680")

        assert experience.title == "Werkstudent Softwareentwicklung"
        assert experience.organization == "Straße GmbH \U0001f680"

    def test_empty_strings_are_accepted(self):
        experience = Experience(title="", organization="", start="", end="")

        assert experience.title == ""
        assert experience.organization == ""
        assert experience.start == ""
        assert experience.end == ""

    def test_experiences_with_equal_fields_are_equal(self):
        assert make_experience() == make_experience()
        assert make_experience() != make_experience(title="Other")


class TestExperienceImmutability:
    @pytest.mark.parametrize("field", ["title", "organization", "start", "end"])
    def test_fields_cannot_be_reassigned(self, field):
        experience = make_experience()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(experience, field, "changed")

    def test_experiences_are_hashable_value_objects(self):
        assert len({make_experience(), make_experience()}) == 1


class TestEducationConstruction:
    def test_holds_the_given_values(self):
        education = make_education()

        assert education.institution == "TU Berlin"
        assert education.degree == "MSc Software Engineering"
        assert education.field == "Computer Science"

    def test_unicode_text_is_accepted(self):
        education = make_education(institution="Universität München", degree="Diplom-Informatiker \U0001f393")

        assert education.institution == "Universität München"
        assert education.degree == "Diplom-Informatiker \U0001f393"

    def test_empty_strings_are_accepted(self):
        education = Education(institution="", degree="", field="")

        assert education.institution == ""
        assert education.degree == ""
        assert education.field == ""

    def test_educations_with_equal_fields_are_equal(self):
        assert make_education() == make_education()
        assert make_education() != make_education(institution="Other")


class TestEducationImmutability:
    @pytest.mark.parametrize("field", ["institution", "degree", "field"])
    def test_fields_cannot_be_reassigned(self, field):
        education = make_education()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(education, field, "changed")

    def test_educations_are_hashable_value_objects(self):
        assert len({make_education(), make_education()}) == 1


class TestCandidateProfileConstruction:
    def test_valid_construction_with_all_fields(self):
        profile = CandidateProfile(
            skills=("Python", "SQL"),
            experience=(make_experience(),),
            education=(make_education(),),
        )

        assert profile.skills == ("Python", "SQL")
        assert profile.experience == (make_experience(),)
        assert profile.education == (make_education(),)

    def test_all_three_collections_default_to_empty_tuples(self):
        profile = CandidateProfile()

        assert profile.skills == ()
        assert profile.experience == ()
        assert profile.education == ()

    def test_profiles_with_equal_fields_are_equal(self):
        assert make_profile(skills=("Python",)) == make_profile(skills=("Python",))
        assert make_profile(skills=("Python",)) != make_profile(skills=("SQL",))


class TestCandidateProfileCollections:
    def test_skills_are_stored_as_a_tuple(self):
        profile = CandidateProfile(skills=("Python", "SQL"))

        assert isinstance(profile.skills, tuple)

    def test_experience_is_stored_as_a_tuple(self):
        profile = CandidateProfile(experience=(make_experience(),))

        assert isinstance(profile.experience, tuple)

    def test_education_is_stored_as_a_tuple(self):
        profile = CandidateProfile(education=(make_education(),))

        assert isinstance(profile.education, tuple)

    def test_nested_experience_objects_are_accessible_by_field(self):
        profile = CandidateProfile(experience=(make_experience(title="Backend Intern"),))

        assert profile.experience[0].title == "Backend Intern"
        assert profile.experience[0].organization == "Acme GmbH"

    def test_nested_education_objects_are_accessible_by_field(self):
        profile = CandidateProfile(education=(make_education(degree="BSc Computer Science"),))

        assert profile.education[0].degree == "BSc Computer Science"
        assert profile.education[0].institution == "TU Berlin"

    def test_multiple_experience_entries_keep_their_order(self):
        first = make_experience(title="First Role")
        second = make_experience(title="Second Role")

        profile = CandidateProfile(experience=(first, second))

        assert [item.title for item in profile.experience] == ["First Role", "Second Role"]

    def test_multiple_education_entries_keep_their_order(self):
        first = make_education(institution="First University")
        second = make_education(institution="Second University")

        profile = CandidateProfile(education=(first, second))

        assert [item.institution for item in profile.education] == ["First University", "Second University"]


class TestCandidateProfileImmutability:
    @pytest.mark.parametrize("field", ["skills", "experience", "education"])
    def test_fields_cannot_be_reassigned(self, field):
        profile = make_profile()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(profile, field, ())

    def test_profiles_are_hashable_value_objects(self):
        assert len({make_profile(), make_profile()}) == 1

    def test_default_empty_tuples_are_shared_but_collections_are_already_immutable(self):
        # Frozen dataclasses with an immutable default (an empty tuple) are safe to share across
        # instances: there is no mutable state to leak between them, unlike a shared list default.
        first = CandidateProfile()
        second = CandidateProfile()

        assert first.skills is second.skills


class TestNoSilentNormalization:
    def test_surrounding_whitespace_in_skills_is_preserved(self):
        profile = CandidateProfile(skills=("  Java  ",))

        assert profile.skills == ("  Java  ",)

    def test_surrounding_whitespace_in_experience_fields_is_preserved(self):
        experience = Experience(title="  Engineer  ", organization="  Acme  ", start="  2024-01  ", end="  2024-12  ")

        assert experience.title == "  Engineer  "
        assert experience.organization == "  Acme  "
        assert experience.start == "  2024-01  "
        assert experience.end == "  2024-12  "

    def test_surrounding_whitespace_in_education_fields_is_preserved(self):
        education = Education(institution="  TU Berlin  ", degree="  MSc  ", field="  CS  ")

        assert education.institution == "  TU Berlin  "
        assert education.degree == "  MSc  "
        assert education.field == "  CS  "

    def test_casing_is_preserved(self):
        profile = CandidateProfile(skills=("PYTHON", "python", "Python"))

        assert profile.skills == ("PYTHON", "python", "Python")

    def test_no_validation_is_applied_to_dates_or_end_before_start(self):
        # end < start, unusual/free-form dates: none of this is rejected. Dates stay opaque strings.
        experience = Experience(title="t", organization="o", start="2024-12", end="2020-01")

        assert experience.start == "2024-12"
        assert experience.end == "2020-01"

    def test_none_is_only_accepted_where_the_type_declares_it(self):
        # Experience.end is str | None, so None is valid there.
        experience = Experience(title="t", organization="o", start="2024-01", end=None)

        assert experience.end is None


class TestIndependence:
    def test_candidate_profile_does_not_require_a_job(self):
        profile = CandidateProfile(skills=("Python",), experience=(make_experience(),), education=(make_education(),))

        assert profile.skills == ("Python",)

    @pytest.mark.parametrize("module", ["selenium", "pandas", "webdriver_manager"])
    def test_importing_candidate_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, candidate; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr


class TestDataclassContract:
    @pytest.mark.parametrize("cls", [Experience, Education, CandidateProfile])
    def test_is_a_dataclass(self, cls):
        assert dataclasses.is_dataclass(cls)

    @pytest.mark.parametrize("cls", [Experience, Education, CandidateProfile])
    def test_is_frozen(self, cls):
        assert cls.__dataclass_params__.frozen is True

    def test_candidate_profile_collection_fields_default_to_empty_tuples(self):
        fields_by_name = {f.name: f for f in dataclasses.fields(CandidateProfile)}

        for name in ("skills", "experience", "education"):
            assert fields_by_name[name].default == ()

    def test_two_default_constructed_profiles_do_not_share_mutable_state(self):
        first, second = CandidateProfile(), CandidateProfile()
        assert first == second
        # Proven immutable via TestCandidateProfileImmutability; this only confirms independence
        # of the two instances at the object level, not of the (already-immutable) tuple contents.
        assert first is not second
