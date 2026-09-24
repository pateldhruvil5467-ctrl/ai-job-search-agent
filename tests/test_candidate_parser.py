"""Tests for candidate_parser: deterministic plain text -> CandidateProfile (Layer 2).

All resume content here is synthetic. The parser supports a small, explicit text format
(labelled SKILLS / EXPERIENCE / EDUCATION sections, pipe-separated entries) and skips what it
cannot structurally interpret instead of inventing candidate facts.
"""

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from candidate import CandidateProfile, Education, Experience
from candidate_parser import parse_candidate_profile

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"


def section(name: str, *lines: str) -> str:
    return "\n".join([name, *lines])


def resume(*sections: str) -> str:
    return "\n\n".join(sections)


FULL_RESUME = resume(
    section("SKILLS", "Java, Spring Boot, Python, React, MySQL"),
    section(
        "EXPERIENCE",
        "Software Engineer | Example GmbH | Jan 2024 - Present",
        "Working Student | Example AG | Jun 2022 - Dec 2023",
    ),
    section(
        "EDUCATION",
        "MSc | University of Example | Software Engineering",
        "BSc | Example University | Computer Science",
    ),
)


class TestEmptyInput:
    @pytest.mark.parametrize("text", ["", "   ", "\n", "\n\n  \n\t\n"])
    def test_empty_or_blank_text_gives_an_empty_profile(self, text):
        assert parse_candidate_profile(text) == CandidateProfile()

    def test_text_with_no_recognised_sections_gives_an_empty_profile(self):
        assert parse_candidate_profile("Just some prose.\nNothing structured here.") == CandidateProfile()


class TestSkills:
    def test_comma_separated_skills_are_extracted_in_order(self):
        profile = parse_candidate_profile(section("SKILLS", "Java, Spring Boot, Python, React"))

        assert profile.skills == ("Java", "Spring Boot", "Python", "React")

    def test_skills_on_several_lines_are_combined_in_order(self):
        profile = parse_candidate_profile(section("SKILLS", "Java, Python", "React, MySQL"))

        assert profile.skills == ("Java", "Python", "React", "MySQL")

    def test_surrounding_whitespace_around_each_skill_is_stripped(self):
        profile = parse_candidate_profile(section("SKILLS", "  Java  ,\tPython ,   Spring Boot   "))

        assert profile.skills == ("Java", "Python", "Spring Boot")

    def test_empty_items_between_commas_are_ignored(self):
        profile = parse_candidate_profile(section("SKILLS", "Java,, ,Python,"))

        assert profile.skills == ("Java", "Python")

    def test_exact_duplicates_are_removed_keeping_the_first(self):
        profile = parse_candidate_profile(section("SKILLS", "Java, Python, Java"))

        assert profile.skills == ("Java", "Python")

    def test_case_variant_duplicates_are_removed_keeping_the_first_spelling(self):
        profile = parse_candidate_profile(section("SKILLS", "Python, python, PYTHON, Java"))

        assert profile.skills == ("Python", "Java")

    def test_original_casing_of_a_skill_is_preserved(self):
        profile = parse_candidate_profile(section("SKILLS", "MySQL, JavaScript, node.js"))

        assert profile.skills == ("MySQL", "JavaScript", "node.js")

    def test_skills_are_a_tuple_of_strings(self):
        profile = parse_candidate_profile(section("SKILLS", "Java"))

        assert isinstance(profile.skills, tuple)
        assert all(isinstance(skill, str) for skill in profile.skills)


class TestExperience:
    def test_current_position_gives_end_none(self):
        profile = parse_candidate_profile(
            section("EXPERIENCE", "Software Engineer | Example GmbH | Jan 2024 - Present")
        )

        assert profile.experience == (
            Experience(title="Software Engineer", organization="Example GmbH", start="Jan 2024", end=None),
        )

    def test_historical_position_keeps_both_date_strings(self):
        profile = parse_candidate_profile(
            section("EXPERIENCE", "Working Student | Example AG | Jun 2022 - Dec 2023")
        )

        assert profile.experience == (
            Experience(title="Working Student", organization="Example AG", start="Jun 2022", end="Dec 2023"),
        )

    @pytest.mark.parametrize("marker", ["Present", "present", "PRESENT", "Current", "current", "Ongoing", "Now"])
    def test_recognised_current_markers_give_end_none(self, marker):
        profile = parse_candidate_profile(section("EXPERIENCE", f"Engineer | Example GmbH | Jan 2024 - {marker}"))

        assert profile.experience[0].end is None

    @pytest.mark.parametrize("end", ["Presently", "Present day", "Later", "Q4 2023"])
    def test_unrecognised_end_tokens_are_kept_verbatim_not_treated_as_current(self, end):
        profile = parse_candidate_profile(section("EXPERIENCE", f"Engineer | Example GmbH | Jan 2024 - {end}"))

        assert profile.experience[0].end == end

    @pytest.mark.parametrize(
        ("date_range", "start", "end"),
        [
            ("Jun 2022 - Dec 2023", "Jun 2022", "Dec 2023"),
            ("2022-06 - 2023-12", "2022-06", "2023-12"),
            ("06/2022 - 12/2023", "06/2022", "12/2023"),
            ("June 2022 – December 2023", "June 2022", "December 2023"),
            ("June 2022 — December 2023", "June 2022", "December 2023"),
            ("2022–2023", "2022", "2023"),
        ],
    )
    def test_date_strings_are_preserved_as_written_and_never_reformatted(self, date_range, start, end):
        profile = parse_candidate_profile(section("EXPERIENCE", f"Engineer | Example GmbH | {date_range}"))

        assert profile.experience[0].start == start
        assert profile.experience[0].end == end

    def test_dates_stay_strings(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "Engineer | Example GmbH | Jan 2024 - Present"))

        assert isinstance(profile.experience[0].start, str)

    def test_a_current_marker_as_the_start_date_is_not_an_experience(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "Engineer | Example GmbH | Present - Jan 2024"))

        assert profile.experience == ()

    def test_surrounding_whitespace_in_an_entry_is_stripped(self):
        profile = parse_candidate_profile(
            section("EXPERIENCE", "   Software Engineer  |\tExample GmbH   |  Jan 2024   -   Present  ")
        )

        assert profile.experience == (
            Experience(title="Software Engineer", organization="Example GmbH", start="Jan 2024", end=None),
        )

    def test_unicode_text_is_preserved(self):
        profile = parse_candidate_profile(
            section("EXPERIENCE", "Werkstudent Softwareentwicklung | Straße GmbH | Jan 2024 - Present")
        )

        assert profile.experience[0].title == "Werkstudent Softwareentwicklung"
        assert profile.experience[0].organization == "Straße GmbH"

    def test_multiple_entries_keep_their_input_order(self):
        profile = parse_candidate_profile(
            section(
                "EXPERIENCE",
                "Third | C Corp | 2022 - 2023",
                "First | A Corp | 2018 - 2019",
                "Second | B Corp | 2020 - 2021",
            )
        )

        assert [entry.title for entry in profile.experience] == ["Third", "First", "Second"]

    def test_identical_entries_are_not_deduplicated(self):
        line = "Engineer | Example GmbH | 2020 - 2021"

        profile = parse_candidate_profile(section("EXPERIENCE", line, line))

        assert len(profile.experience) == 2


class TestEducation:
    def test_entry_is_read_as_degree_institution_field(self):
        profile = parse_candidate_profile(section("EDUCATION", "MSc | University of Example | Software Engineering"))

        assert profile.education == (
            Education(institution="University of Example", degree="MSc", field="Software Engineering"),
        )

    def test_surrounding_whitespace_in_an_entry_is_stripped(self):
        profile = parse_candidate_profile(section("EDUCATION", "  BSc  |  Example University\t| Computer Science  "))

        assert profile.education == (
            Education(institution="Example University", degree="BSc", field="Computer Science"),
        )

    def test_multiple_entries_keep_their_input_order(self):
        profile = parse_candidate_profile(
            section(
                "EDUCATION",
                "MSc | University of Example | Software Engineering",
                "BSc | Example University | Computer Science",
            )
        )

        assert [entry.institution for entry in profile.education] == ["University of Example", "Example University"]
        assert [entry.degree for entry in profile.education] == ["MSc", "BSc"]

    def test_unicode_text_is_preserved(self):
        profile = parse_candidate_profile(section("EDUCATION", "Diplom | Universität Beispiel | Informatik"))

        assert profile.education[0].institution == "Universität Beispiel"


class TestFullResume:
    def test_all_three_sections_are_parsed_together(self):
        profile = parse_candidate_profile(FULL_RESUME)

        assert profile == CandidateProfile(
            skills=("Java", "Spring Boot", "Python", "React", "MySQL"),
            experience=(
                Experience("Software Engineer", "Example GmbH", "Jan 2024", None),
                Experience("Working Student", "Example AG", "Jun 2022", "Dec 2023"),
            ),
            education=(
                Education(institution="University of Example", degree="MSc", field="Software Engineering"),
                Education(institution="Example University", degree="BSc", field="Computer Science"),
            ),
        )

    def test_windows_line_endings_are_handled(self):
        assert parse_candidate_profile(FULL_RESUME.replace("\n", "\r\n")) == parse_candidate_profile(FULL_RESUME)

    def test_non_breaking_spaces_around_values_are_stripped(self):
        profile = parse_candidate_profile(section("SKILLS", " Java , Python"))

        assert profile.skills == ("Java", "Python")

    def test_sections_may_appear_in_any_order(self):
        reordered = resume(
            section("EDUCATION", "BSc | Example University | Computer Science"),
            section("SKILLS", "Java"),
            section("EXPERIENCE", "Engineer | Example GmbH | 2020 - 2021"),
        )

        profile = parse_candidate_profile(reordered)

        assert profile.skills == ("Java",)
        assert len(profile.experience) == 1
        assert len(profile.education) == 1


class TestSectionHeaders:
    @pytest.mark.parametrize("header", ["SKILLS", "skills", "Skills", "  SkIlLs  ", "SKILLS:", "Skills :"])
    def test_skills_header_is_case_and_whitespace_insensitive(self, header):
        assert parse_candidate_profile(f"{header}\nJava, Python").skills == ("Java", "Python")

    @pytest.mark.parametrize("header", ["EXPERIENCE", "experience", "Experience", "  ExPeRiEnCe  ", "EXPERIENCE:"])
    def test_experience_header_is_case_and_whitespace_insensitive(self, header):
        profile = parse_candidate_profile(f"{header}\nEngineer | Example GmbH | 2020 - 2021")

        assert len(profile.experience) == 1

    @pytest.mark.parametrize("header", ["EDUCATION", "education", "Education", "  EdUcAtIoN  ", "EDUCATION:"])
    def test_education_header_is_case_and_whitespace_insensitive(self, header):
        profile = parse_candidate_profile(f"{header}\nBSc | Example University | Computer Science")

        assert len(profile.education) == 1

    def test_text_before_the_first_header_is_ignored(self):
        text = "Some preamble line\nEngineer | Example GmbH | 2020 - 2021\n\n" + section("SKILLS", "Java")

        assert parse_candidate_profile(text) == CandidateProfile(skills=("Java",))

    def test_a_repeated_section_accumulates_in_document_order(self):
        text = resume(section("SKILLS", "Java"), section("EDUCATION", "BSc | X University | CS"), section("SKILLS", "Python"))

        assert parse_candidate_profile(text).skills == ("Java", "Python")


class TestSectionIsolation:
    def test_experience_lines_do_not_become_skills(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "Engineer | Example GmbH | 2020 - 2021"))

        assert profile.skills == ()

    def test_education_lines_do_not_become_skills(self):
        profile = parse_candidate_profile(section("EDUCATION", "BSc | Example University | Computer Science"))

        assert profile.skills == ()

    def test_education_lines_do_not_become_experience(self):
        profile = parse_candidate_profile(section("EDUCATION", "BSc | Example University | Computer Science"))

        assert profile.experience == ()

    def test_experience_lines_do_not_become_education(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "Engineer | Example GmbH | 2020 - 2021"))

        assert profile.education == ()

    def test_skills_do_not_become_experience_or_education(self):
        profile = parse_candidate_profile(section("SKILLS", "Java, Python"))

        assert profile.experience == ()
        assert profile.education == ()

    def test_a_line_shaped_like_experience_inside_education_is_not_an_education_entry(self):
        # Three pipe parts, but the third part is a date range: still read positionally as
        # degree | institution | field, since the section decides the meaning, not the line.
        profile = parse_candidate_profile(section("EDUCATION", "Engineer | Example GmbH | 2020 - 2021"))

        assert profile.experience == ()
        assert profile.education == (
            Education(institution="Example GmbH", degree="Engineer", field="2020 - 2021"),
        )


class TestUnknownSections:
    def test_unknown_section_content_creates_no_data(self):
        profile = parse_candidate_profile(section("SUMMARY", "I am a software engineer with a passion for testing."))

        assert profile == CandidateProfile()

    def test_unknown_section_between_known_ones_does_not_disturb_them(self):
        text = resume(
            section("SKILLS", "Java"),
            section("SUMMARY", "I am a software engineer."),
            section("EDUCATION", "BSc | Example University | Computer Science"),
        )

        profile = parse_candidate_profile(text)

        assert profile.skills == ("Java",)
        assert len(profile.education) == 1

    @pytest.mark.parametrize("header", ["SUMMARY", "PROJECTS", "CERTIFICATIONS", "LANGUAGES", "PERSONAL DETAILS"])
    def test_an_unknown_all_caps_header_ends_the_previous_known_section(self, header):
        text = resume(
            section("SKILLS", "Java"),
            section(header, "Python, React"),
        )

        assert parse_candidate_profile(text).skills == ("Java",)

    def test_entry_shaped_lines_under_an_unknown_header_are_not_experience(self):
        text = resume(
            section("EXPERIENCE", "Engineer | Example GmbH | 2020 - 2021"),
            section("PROJECTS", "Side Project | Example Lab | 2019 - 2020"),
        )

        profile = parse_candidate_profile(text)

        assert [entry.title for entry in profile.experience] == ["Engineer"]

    def test_entry_shaped_lines_under_an_unknown_header_are_not_education(self):
        text = resume(
            section("EDUCATION", "BSc | Example University | Computer Science"),
            section("CERTIFICATIONS", "Cert | Example Body | Cloud"),
        )

        assert len(parse_candidate_profile(text).education) == 1

    def test_all_caps_skill_lines_containing_commas_are_not_mistaken_for_headers(self):
        profile = parse_candidate_profile(section("SKILLS", "JAVA, SQL, AWS"))

        assert profile.skills == ("JAVA", "SQL", "AWS")

    def test_all_caps_entries_containing_pipes_are_not_mistaken_for_headers(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "ENGINEER | EXAMPLE GMBH | 2020 - 2021"))

        assert len(profile.experience) == 1


class TestMissingSections:
    def test_skills_only(self):
        assert parse_candidate_profile(section("SKILLS", "Java, Python")) == CandidateProfile(skills=("Java", "Python"))

    def test_experience_only(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "Engineer | Example GmbH | 2020 - 2021"))

        assert profile.skills == ()
        assert profile.education == ()
        assert len(profile.experience) == 1

    def test_education_only(self):
        profile = parse_candidate_profile(section("EDUCATION", "BSc | Example University | Computer Science"))

        assert profile.skills == ()
        assert profile.experience == ()
        assert len(profile.education) == 1

    @pytest.mark.parametrize("name", ["SKILLS", "EXPERIENCE", "EDUCATION"])
    def test_a_header_with_no_content_gives_an_empty_profile(self, name):
        assert parse_candidate_profile(name) == CandidateProfile()

    @pytest.mark.parametrize("name", ["SKILLS", "EXPERIENCE", "EDUCATION"])
    def test_a_header_followed_only_by_blank_lines_gives_an_empty_profile(self, name):
        assert parse_candidate_profile(f"{name}\n\n   \n") == CandidateProfile()


class TestMalformedEntries:
    @pytest.mark.parametrize(
        "line",
        [
            "Software Engineer",
            "Software Engineer | Example GmbH",
            "Software Engineer | Example GmbH | Jan 2024",
            "Software Engineer | Example GmbH | Jan 2024 - Present | Extra",
            " | Example GmbH | Jan 2024 - Present",
            "Software Engineer |  | Jan 2024 - Present",
            "Software Engineer | Example GmbH | ",
            "Software Engineer | Example GmbH |  - Present",
            "Software Engineer | Example GmbH | Jan 2024 - ",
            "Software Engineer | Example GmbH | 2020-2022",
            "|||",
            "just free text without any structure",
        ],
    )
    def test_malformed_experience_lines_are_skipped(self, line):
        assert parse_candidate_profile(section("EXPERIENCE", line)).experience == ()

    @pytest.mark.parametrize(
        "line",
        [
            "MSc",
            "MSc | University of Example",
            "MSc | University of Example | Software Engineering | Extra",
            " | University of Example | Software Engineering",
            "MSc |  | Software Engineering",
            "MSc | University of Example | ",
            "|||",
            "just free text without any structure",
        ],
    )
    def test_malformed_education_lines_are_skipped(self, line):
        assert parse_candidate_profile(section("EDUCATION", line)).education == ()

    def test_valid_experience_entries_around_a_malformed_one_are_kept_in_order(self):
        profile = parse_candidate_profile(
            section(
                "EXPERIENCE",
                "First | A Corp | 2018 - 2019",
                "this line is not an entry",
                "Second | B Corp | 2020 - 2021",
            )
        )

        assert [entry.title for entry in profile.experience] == ["First", "Second"]

    def test_valid_education_entries_around_a_malformed_one_are_kept_in_order(self):
        profile = parse_candidate_profile(
            section(
                "EDUCATION",
                "BSc | A University | CS",
                "MSc | B University",
                "PhD | C University | CS",
            )
        )

        assert [entry.degree for entry in profile.education] == ["BSc", "PhD"]

    def test_a_malformed_entry_is_never_completed_with_invented_fields(self):
        profile = parse_candidate_profile(section("EXPERIENCE", "Software Engineer | Example GmbH"))

        assert profile == CandidateProfile()

    def test_malformed_content_never_raises(self):
        text = "\x00\x01 | | | - - -\n" + section("EXPERIENCE", "| - |", "|") + "\n" + section("EDUCATION", "||", "|")

        assert parse_candidate_profile(text) == CandidateProfile()


class TestImmutabilityAndDeterminism:
    def test_result_is_the_existing_candidate_profile_type(self):
        assert type(parse_candidate_profile(FULL_RESUME)) is CandidateProfile

    def test_nested_entries_are_the_existing_frozen_types(self):
        profile = parse_candidate_profile(FULL_RESUME)

        assert all(type(entry) is Experience for entry in profile.experience)
        assert all(type(entry) is Education for entry in profile.education)

    def test_collections_are_tuples(self):
        profile = parse_candidate_profile(FULL_RESUME)

        assert isinstance(profile.skills, tuple)
        assert isinstance(profile.experience, tuple)
        assert isinstance(profile.education, tuple)

    def test_result_cannot_be_mutated(self):
        profile = parse_candidate_profile(FULL_RESUME)

        with pytest.raises(dataclasses.FrozenInstanceError):
            profile.skills = ()
        with pytest.raises(dataclasses.FrozenInstanceError):
            profile.experience[0].title = "changed"

    def test_input_text_is_not_modified(self):
        original = FULL_RESUME
        text = str(original)

        parse_candidate_profile(text)

        assert text == original

    def test_parsing_is_deterministic(self):
        assert parse_candidate_profile(FULL_RESUME) == parse_candidate_profile(FULL_RESUME)

    def test_separate_calls_return_independent_results(self):
        first = parse_candidate_profile(section("SKILLS", "Java"))
        second = parse_candidate_profile(section("SKILLS", "Python"))

        assert first.skills == ("Java",)
        assert second.skills == ("Python",)


class TestInputTypeContract:
    @pytest.mark.parametrize(
        "value",
        [
            None,
            123,
            [SYNTHETIC_PRIVATE_MARKER],
            SYNTHETIC_PRIVATE_MARKER.encode(),
            Path(SYNTHETIC_PRIVATE_MARKER + ".pdf"),
        ],
        ids=["none", "int", "list", "bytes", "path"],
    )
    def test_non_text_input_raises_type_error(self, value):
        with pytest.raises(TypeError):
            parse_candidate_profile(value)


class TestPrivacy:
    @pytest.mark.parametrize(
        "value",
        [
            [SYNTHETIC_PRIVATE_MARKER],
            SYNTHETIC_PRIVATE_MARKER.encode(),
            Path(SYNTHETIC_PRIVATE_MARKER + ".pdf"),
            {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER},
        ],
        ids=["list", "bytes", "path", "dict"],
    )
    def test_exception_messages_never_contain_the_input(self, value):
        with pytest.raises(TypeError) as exc_info:
            parse_candidate_profile(value)

        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value)
        assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)

    def test_exception_does_not_chain_a_cause_or_context_carrying_the_input(self):
        with pytest.raises(TypeError) as exc_info:
            parse_candidate_profile(SYNTHETIC_PRIVATE_MARKER.encode())

        assert exc_info.value.__cause__ is None
        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value.__context__)

    def test_malformed_lines_are_dropped_rather_than_carried_into_the_result(self):
        text = section(
            "EXPERIENCE",
            f"{SYNTHETIC_PRIVATE_MARKER} | Example GmbH",
            f"Engineer | {SYNTHETIC_PRIVATE_MARKER}",
            f"{SYNTHETIC_PRIVATE_MARKER} without any structure",
        )

        profile = parse_candidate_profile(text)

        assert profile == CandidateProfile()
        assert SYNTHETIC_PRIVATE_MARKER not in repr(profile)

    def test_unknown_section_content_is_dropped_rather_than_carried_into_the_result(self):
        profile = parse_candidate_profile(section("SUMMARY", f"{SYNTHETIC_PRIVATE_MARKER} is my private note"))

        assert SYNTHETIC_PRIVATE_MARKER not in repr(profile)

    def test_parsing_produces_no_console_output_or_log_records(self, capsys, caplog):
        parse_candidate_profile(FULL_RESUME + "\n" + section("SUMMARY", SYNTHETIC_PRIVATE_MARKER))

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_parsing_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        parse_candidate_profile(FULL_RESUME)

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
    @pytest.mark.parametrize(
        "module",
        ["selenium", "pandas", "pdfplumber", "webdriver_manager", "resume_pdf"],
    )
    def test_importing_candidate_parser_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, candidate_parser; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr

    def test_importing_resume_pdf_does_not_load_candidate_parser(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, resume_pdf; "
                "assert 'candidate_parser' not in sys.modules, 'resume_pdf pulled in candidate_parser'",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr

    def test_the_parser_can_be_used_without_the_pdf_layer(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from candidate_parser import parse_candidate_profile; "
                "assert parse_candidate_profile('SKILLS\\nJava').skills == ('Java',)",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
