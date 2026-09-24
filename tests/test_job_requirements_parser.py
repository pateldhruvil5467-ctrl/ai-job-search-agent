"""Tests for job_requirements_parser: deterministic job description text -> JobRequirements.

All descriptions here are synthetic. The extractor reads only bullet statements inside a small
allowlist of required-requirement sections, stores each statement whole, and classifies it
independently into skills / experience / education (a statement can land in several).
"""

import subprocess
import sys
from pathlib import Path

import pytest

from job_requirements import JobRequirements
from job_requirements_parser import extract_job_requirements

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_12345"

# Each constant classifies into exactly one dimension, so tests can combine them predictably.
SKILL = "Knowledge of Python"
EXPERIENCE = "2+ years of backend development"
EDUCATION = "Bachelor's degree in Computer Science"

REQUIRED_HEADINGS = [
    "Requirements",
    "Qualifications",
    "What you bring",
    "More about you",
    "Was du mitbringen solltest",
    "Wen wir suchen",
]


def block(heading: str, *items: str, marker: str = "- ") -> str:
    """A heading, a blank line, then one bullet per item: the shape parse_job_page produces."""
    return "\n".join([heading, "", *[f"{marker}{item}" for item in items]])


def description(*blocks: str) -> str:
    return "\n\n".join(blocks)


def only_skills(*statements: str) -> JobRequirements:
    return JobRequirements(skills=tuple(statements))


def only_experience(*statements: str) -> JobRequirements:
    return JobRequirements(experience=tuple(statements))


def only_education(*statements: str) -> JobRequirements:
    return JobRequirements(education=tuple(statements))


def statements_under(heading_or_text: str, *items: str, marker: str = "- ") -> JobRequirements:
    return extract_job_requirements(block(heading_or_text, *items, marker=marker))


class TestInputHandling:
    @pytest.mark.parametrize("text", ["", " ", "   ", "\n", "\n\n  \n\t\n", "\r\n\r\n"])
    def test_empty_or_blank_text_gives_empty_requirements(self, text):
        assert extract_job_requirements(text) == JobRequirements()

    def test_the_no_description_sentinel_gives_empty_requirements(self):
        assert extract_job_requirements("No description available") == JobRequirements()

    def test_prose_without_any_recognised_section_gives_empty_requirements(self):
        assert extract_job_requirements("We build software.\nJoin our team.") == JobRequirements()

    def test_bullets_outside_any_required_section_give_empty_requirements(self):
        text = description("About us", "- " + SKILL, block("What we offer", EDUCATION))

        assert extract_job_requirements(text) == JobRequirements()

    def test_a_required_heading_with_no_bullets_gives_empty_requirements(self):
        assert extract_job_requirements("Requirements") == JobRequirements()
        assert extract_job_requirements("Requirements\n\nSome prose only.") == JobRequirements()

    def test_a_description_with_only_optional_sections_gives_empty_requirements(self):
        assert extract_job_requirements(block("Nice to have", SKILL, EDUCATION)) == JobRequirements()

    @pytest.mark.parametrize("value", [None, 123, 1.5, ["Requirements"], b"Requirements", Path("Requirements")])
    def test_non_string_input_raises_type_error(self, value):
        with pytest.raises(TypeError, match=r"^description must be a str$"):
            extract_job_requirements(value)


class TestRequiredSections:
    @pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
    def test_each_allowlisted_heading_is_recognised(self, heading):
        text = description("About us", "We build software.", block(heading, SKILL))

        assert extract_job_requirements(text) == only_skills(SKILL)

    @pytest.mark.parametrize(
        "heading",
        ["REQUIREMENTS", "qualifications", "WHAT YOU BRING", "More About You", "WEN WIR SUCHEN", "was du mitbringen solltest"],
    )
    def test_headings_are_case_insensitive(self, heading):
        assert statements_under(heading, SKILL) == only_skills(SKILL)

    @pytest.mark.parametrize(
        "heading",
        [
            "\u2705 What you bring",
            "\U0001f3af Qualifications",
            "\u2605 Requirements",
            "\u2192 Wen wir suchen",
            "Requirements \U0001f680",
            "## Requirements",
        ],
    )
    def test_leading_and_trailing_emoji_and_symbols_are_ignored(self, heading):
        assert statements_under(heading, SKILL) == only_skills(SKILL)

    @pytest.mark.parametrize("heading", ["Requirements:", "  Requirements  ", "What you bring :", "Requirements:  "])
    def test_trailing_colon_and_surrounding_whitespace_are_ignored(self, heading):
        assert statements_under(heading, SKILL) == only_skills(SKILL)

    def test_bullets_directly_after_the_heading_without_a_blank_line_are_read(self):
        assert extract_job_requirements(f"Requirements\n- {SKILL}\n- {EDUCATION}") == JobRequirements(
            skills=(SKILL,), education=(EDUCATION,)
        )

    def test_a_heading_word_inside_a_sentence_is_not_a_heading(self):
        text = f"Requirements are listed below.\n\n- {SKILL}"

        assert extract_job_requirements(text) == JobRequirements()

    def test_a_heading_that_is_not_on_its_own_paragraph_is_not_recognised(self):
        text = f"Some text\nRequirements\n- {SKILL}"

        assert extract_job_requirements(text) == JobRequirements()

    def test_unlisted_headings_are_not_treated_as_requirement_sections(self):
        for heading in ["Your profile", "What you'll do", "Anforderungen", "About the role", "Benefits"]:
            assert statements_under(heading, SKILL) == JobRequirements(), heading

    def test_several_required_sections_accumulate_in_document_order(self):
        text = description(
            block("Requirements", "Knowledge of Java"),
            block("About the team", "Knowledge of Rust"),
            block("Wen wir suchen", "Kenntnisse in SQL"),
        )

        assert extract_job_requirements(text).skills == ("Knowledge of Java", "Kenntnisse in SQL")


class TestSectionTermination:
    def test_a_following_unlisted_heading_ends_the_section(self):
        text = description(block("Requirements", SKILL), block("Benefits", "Knowledge of Rust"))

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_a_section_at_the_end_of_the_text_runs_to_the_end(self):
        text = description("About us", block("Requirements", SKILL, EDUCATION))

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))

    def test_bullets_before_the_required_heading_are_not_included(self):
        text = description(block("What you'll do", "Knowledge of Rust"), block("Requirements", SKILL))

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_a_short_unlisted_line_between_paragraphs_ends_the_section(self):
        text = f"Requirements\n\n- {SKILL}\n\nBenefits\n\n- Knowledge of Rust"

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_a_long_unpunctuated_line_is_prose_not_a_heading(self):
        url = "https://careers.example.invalid/apply/with/a/very/long/path/segment/here"
        text = f"Requirements\n\n- {SKILL}\n\n{url}\n\n- {EDUCATION}"

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))

    def test_a_line_of_many_short_words_is_prose_not_a_heading(self):
        text = f"Requirements\n\n- {SKILL}\n\na b c d e f g h i\n\n- {EDUCATION}"

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))

    def test_a_truncation_marker_at_the_end_is_ignored(self):
        text = description(block("Requirements", SKILL)) + "\n[truncated]"

        assert extract_job_requirements(text) == only_skills(SKILL)


class TestLeadInLines:
    def test_a_prose_lead_in_ending_with_a_period_does_not_end_the_section(self):
        text = description(
            "Requirements",
            "You are a good match for this position if the points below apply to you.",
            f"- {SKILL}",
        )

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_a_colon_terminated_lead_in_does_not_end_the_section(self):
        text = description("Requirements", "We expect:", f"- {SKILL}", f"- {EDUCATION}")

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))

    def test_a_german_colon_lead_in_with_bullet_dots_does_not_end_the_section(self):
        text = description(
            "Was du mitbringen solltest",
            "Du solltest bereits produktive Systeme gebaut haben.",
            "Wichtig sind uns insbesondere:",
            "\u2022 Erfahrung mit TypeScript\n\u2022 Kenntnisse in SQL",
        )

        assert extract_job_requirements(text).skills == ("Erfahrung mit TypeScript", "Kenntnisse in SQL")

    def test_a_colon_lead_in_outside_a_required_section_does_not_start_one(self):
        text = description("About us", "Wir suchen:", f"- {SKILL}")

        assert extract_job_requirements(text) == JobRequirements()

    def test_a_colon_terminated_optional_heading_inside_a_required_section_ends_collection(self):
        text = description("Requirements", f"- {SKILL}", "Nice to have:", "- Knowledge of Rust")

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_collection_resumes_at_a_later_required_heading_after_an_optional_one(self):
        text = description(
            block("Requirements", SKILL),
            block("Nice to have", "Knowledge of Rust"),
            block("Qualifications", EDUCATION),
        )

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))


class TestOptionalSections:
    @pytest.mark.parametrize("heading", ["Nice to have", "NICE TO HAVE", "Nice to have:", "\U0001f31f Nice to have"])
    def test_a_nice_to_have_section_is_excluded(self, heading):
        text = description(block("Requirements", SKILL), block(heading, "Knowledge of Rust", EDUCATION))

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_an_optional_section_before_a_required_one_does_not_leak_into_it(self):
        text = description(block("Nice to have", "Knowledge of Rust"), block("Requirements", SKILL))

        assert extract_job_requirements(text) == only_skills(SKILL)

    def test_the_ambiguous_german_helpful_qualities_heading_is_unsupported_and_not_extracted(self):
        # "Was dir bei der Arbeit helfen wird" ("what will help you") is in neither the required
        # nor the optional list: it is ambiguous, so its bullets are not extracted.
        text = description(
            block("Wen wir suchen", "Kenntnisse in SQL"),
            block("Was dir bei der Arbeit helfen wird", "Vertiefte Kenntnisse zu NoSQL-Datenbanken"),
        )

        assert extract_job_requirements(text) == only_skills("Kenntnisse in SQL")


class TestBullets:
    def test_hyphen_bullets_are_read(self):
        assert statements_under("Requirements", SKILL, marker="- ") == only_skills(SKILL)

    def test_bullet_dot_bullets_are_read(self):
        assert statements_under("Requirements", SKILL, marker="\u2022 ") == only_skills(SKILL)

    def test_both_markers_can_be_mixed_within_one_section(self):
        text = f"Requirements\n\n- {SKILL}\n\u2022 {EDUCATION}"

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))

    @pytest.mark.parametrize("separator", [" ", "  ", "\t", "\u00a0"])
    def test_any_whitespace_after_the_marker_is_accepted(self, separator):
        assert extract_job_requirements(f"Requirements\n\n-{separator}{SKILL}") == only_skills(SKILL)

    @pytest.mark.parametrize(
        "line",
        [
            "* Knowledge of Python",
            "\u2013 Knowledge of Python",
            "\u2014 Knowledge of Python",
            "1. Knowledge of Python",
            "-Knowledge of Python",
            "\u2022Knowledge of Python",
            "\u00b7 Knowledge of Python",
            "\u25aa Knowledge of Python",
        ],
    )
    def test_other_bullet_syntaxes_are_not_supported(self, line):
        assert extract_job_requirements(f"Requirements\n\n{SKILL}.\n{line}") == JobRequirements()

    @pytest.mark.parametrize("empty", ["-", "- ", "-   ", "\u2022", "\u2022 ", "\u2022   ", "- -", "-\t"])
    def test_empty_bullets_are_skipped(self, empty):
        text = f"Requirements\n\n- {SKILL}\n{empty}\n- {EDUCATION}"

        assert extract_job_requirements(text) == JobRequirements(skills=(SKILL,), education=(EDUCATION,))

    def test_ordinary_prose_lines_inside_a_section_are_skipped(self):
        text = f"Requirements\n\nKnowledge of Python is required.\n\n- {EDUCATION}\nExperience with Docker is a plus."

        assert extract_job_requirements(text) == only_education(EDUCATION)

    def test_only_the_marker_and_structural_whitespace_are_removed(self):
        statement = "Knowledge of  Python (e.g., NumPy/SciPy); Stra\u00dfe & 100%!"

        assert statements_under("Requirements", statement).skills == (statement,)

    def test_surrounding_whitespace_around_a_bullet_is_stripped(self):
        assert extract_job_requirements(f"Requirements\n\n   -  {SKILL}   ") == only_skills(SKILL)

    @pytest.mark.parametrize("newline", ["\r\n", "\r", "\n"])
    def test_every_line_ending_style_is_handled(self, newline):
        text = description(block("Requirements", SKILL, EDUCATION), block("Nice to have", "Knowledge of Rust"))

        assert extract_job_requirements(text.replace("\n", newline)) == JobRequirements(
            skills=(SKILL,), education=(EDUCATION,)
        )


class TestSkills:
    @pytest.mark.parametrize(
        "statement",
        [
            "Experience with APIs and developer tools",
            "Knowledge of common software design and architecture patterns",
            "Strong proficiency in Python",
            "Proficient in Java",
            "Familiar with Docker",
            "Familiarity with Kubernetes",
            "Comfort with at least one modern programming language",
            "Erfahrung mit REST APIs",
            "Erfahrungen mit Git",
            "Kenntnisse in SQL",
            "Vertiefte Kenntnisse zu SQL",
            "sehr gute Python-Kenntnisse",
            "sichere Arbeit mit Git",
            "KNOWLEDGE OF PYTHON",
            "knowledge   of python",
        ],
    )
    def test_skill_trigger_language_classifies_the_statement_as_a_skill(self, statement):
        assert statements_under("Requirements", statement).skills == (statement,)

    def test_the_complete_statement_is_stored_not_extracted_technologies(self):
        statement = "Knowledge of Python, SQL and Docker"

        result = statements_under("Requirements", statement)

        assert result.skills == (statement,)
        assert "Python" not in result.skills
        assert "SQL" not in result.skills

    def test_multiple_technologies_in_one_statement_stay_one_entry(self):
        statement = "Proficiency in Java, Kotlin/Scala or Go"

        assert len(statements_under("Requirements", statement).skills) == 1

    def test_deutschkenntnisse_is_not_matched_by_the_generic_kenntnisse_trigger(self):
        assert statements_under("Wen wir suchen", "Deutschkenntnisse mind. C1") == JobRequirements()

    @pytest.mark.parametrize(
        "statement",
        [
            "Deutschkenntnisse mind. C1",
            "Englischkenntnisse (B2)",
            "Fluent English",
            "Fluent English; German is a plus",
            "Strong communication skills",
            "Good problem-solving skills",
            "Zusammenarbeit mit dem Team",
            "Available for 15 to 20 hours per week",
            "Two days per week in our Berlin office",
        ],
    )
    def test_language_and_generic_statements_are_not_classified_as_skills(self, statement):
        assert statements_under("Requirements", statement).skills == ()

    def test_a_trigger_phrase_inside_a_longer_word_does_not_match(self):
        assert statements_under("Requirements", "Acknowledge of risks and Zusammenarbeit mit Kollegen").skills == ()

    def test_a_statement_with_no_trigger_is_dropped_entirely(self):
        assert statements_under("Requirements", "Great talent only: be among the best") == JobRequirements()


class TestExperience:
    @pytest.mark.parametrize(
        "statement",
        [
            "2+ years of backend development",
            "At least 3 years of Java experience",
            "mind. 3 Jahre Berufserfahrung",
            "3 years in a similar role",
            "2-3 years in a similar role",
            "Two years of professional practice",
            "5+years working with distributed systems",
            "Mindestens drei Jahre in der Entwicklung",
            "seit mehr als 3 Jahren in der Softwareentwicklung",
        ],
    )
    def test_a_duration_classifies_the_statement_as_experience(self, statement):
        assert statements_under("Requirements", statement).experience == (statement,)

    @pytest.mark.parametrize(
        "statement",
        [
            "Experience building REST APIs",
            "Erfahrung in der Softwareentwicklung",
            "Berufserfahrung in der Softwareentwicklung",
            "Hands-on experience shipping production systems",
        ],
    )
    def test_experience_wording_without_a_duration_is_still_experience(self, statement):
        result = statements_under("Requirements", statement)

        assert result.experience == (statement,)
        assert result.skills == ()

    @pytest.mark.parametrize("statement", ["Previous experience with AWS", "Erfahrung mit Softwareentwicklung"])
    def test_experience_with_something_is_both_experience_and_a_skill(self, statement):
        assert statements_under("Requirements", statement) == JobRequirements(
            skills=(statement,), experience=(statement,)
        )

    def test_the_whole_statement_is_stored_not_just_the_duration(self):
        statement = "At least 3 years of Java experience"

        assert statements_under("Requirements", statement).experience == (statement,)
        assert "3 years" not in statements_under("Requirements", statement).experience

    @pytest.mark.parametrize(
        "statement",
        ["Available for 15 to 20 hours per week", "Two days per week in our Berlin office", "Fluent English"],
    )
    def test_unrelated_numbers_and_durations_are_not_experience(self, statement):
        assert statements_under("Requirements", statement).experience == ()


class TestEducation:
    @pytest.mark.parametrize(
        "statement",
        [
            "Bachelor's degree in Computer Science",
            "Bachelor\u2019s or Master\u2019s Degree in a technical field",
            "Master's in Software Engineering",
            "Master of Science in a related field",
            "MSc or BSc in a technical subject",
            "PhD in Machine Learning",
            "Enrolled in a relevant degree program",
            "Currently enrolled at a German university",
            "Student status at a university in Germany",
            "Enrollment in a STEM programme",
            "abgeschlossenes Studium",
            "Abgeschlossenes Informatikstudium",
            "Hochschulabschluss in Informatik",
            "Immatrikuliert an einer Universit\u00e4t",
            "Studiengang Informatik",
        ],
    )
    def test_degree_and_enrolment_wording_classifies_the_statement_as_education(self, statement):
        assert statements_under("Requirements", statement).education == (statement,)

    @pytest.mark.parametrize(
        "statement",
        [
            "Scrum Master certification",
            "Master data management",
            "A high degree of ownership",
            "Vertragsabschluss verhandeln",
            "Knowledge of Python",
            "Fluent English",
        ],
    )
    def test_unrelated_uses_of_education_words_are_not_education(self, statement):
        assert statements_under("Requirements", statement).education == ()

    def test_the_complete_statement_is_stored(self):
        statement = "Bachelor's degree in Computer Science, Engineering, or a related field"

        assert statements_under("Requirements", statement).education == (statement,)


class TestMultipleDimensions:
    def test_one_bullet_can_be_skills_experience_and_education_at_once(self):
        statement = "At least 3 years of experience with Python and a Bachelor's degree in Computer Science"

        assert statements_under("Requirements", statement) == JobRequirements(
            skills=(statement,), experience=(statement,), education=(statement,)
        )

    def test_a_bullet_without_a_skills_trigger_is_not_a_skills_statement(self):
        statement = "At least 3 years of Python development and a Bachelor's degree in Computer Science."

        assert statements_under("Requirements", statement) == JobRequirements(
            experience=(statement,), education=(statement,)
        )

    def test_a_german_bullet_can_be_experience_and_education(self):
        statement = "Du bringst mind. 3 Jahre Erfahrung in der Entwicklung mit und hast ein abgeschlossenes Studium"

        assert statements_under("Wen wir suchen", statement) == JobRequirements(
            experience=(statement,), education=(statement,)
        )

    def test_each_bullet_is_classified_independently_of_its_neighbours(self):
        result = statements_under("Requirements", SKILL, EXPERIENCE, EDUCATION, "Fluent English")

        assert result == JobRequirements(skills=(SKILL,), experience=(EXPERIENCE,), education=(EDUCATION,))


class TestDuplicates:
    def test_case_insensitive_duplicates_within_a_dimension_are_removed(self):
        result = statements_under("Requirements", "Knowledge of Python", "KNOWLEDGE OF PYTHON", "knowledge of python")

        assert result.skills == ("Knowledge of Python",)

    def test_the_first_spelling_is_kept(self):
        result = statements_under("Requirements", "KNOWLEDGE OF PYTHON", "Knowledge of Python")

        assert result.skills == ("KNOWLEDGE OF PYTHON",)

    def test_duplicates_across_separate_required_sections_are_removed(self):
        text = description(block("Requirements", SKILL), block("Qualifications", SKILL.upper()))

        assert extract_job_requirements(text).skills == (SKILL,)

    def test_statements_that_differ_beyond_case_are_kept_apart(self):
        result = statements_under("Requirements", "Knowledge of Python", "Knowledge of Java")

        assert result.skills == ("Knowledge of Python", "Knowledge of Java")

    def test_the_same_statement_may_appear_in_more_than_one_dimension(self):
        statement = "Previous experience with AWS"

        result = statements_under("Requirements", statement, statement.upper())

        assert result.skills == (statement,)
        assert result.experience == (statement,)

    def test_duplicates_are_removed_per_dimension_independently(self):
        both = "Experience with Docker"

        result = statements_under("Requirements", both, "EXPERIENCE WITH DOCKER", "Knowledge of Python")

        assert result.skills == (both, "Knowledge of Python")
        assert result.experience == (both,)


class TestOrdering:
    def test_each_dimension_keeps_document_order(self):
        result = statements_under(
            "Requirements",
            "Knowledge of Zig",
            "Master's degree in Physics",
            "3 years of practice",
            "Knowledge of Ada",
            "Bachelor's degree in Chemistry",
            "1 year of research",
        )

        assert result.skills == ("Knowledge of Zig", "Knowledge of Ada")
        assert result.education == ("Master's degree in Physics", "Bachelor's degree in Chemistry")
        assert result.experience == ("3 years of practice", "1 year of research")

    def test_order_holds_across_several_required_sections(self):
        text = description(
            block("Requirements", "Knowledge of Zig"),
            block("Benefits", "Knowledge of Rust"),
            block("Wen wir suchen", "Kenntnisse in Ada"),
            block("Qualifications", "Proficiency in Lua"),
        )

        assert extract_job_requirements(text).skills == ("Knowledge of Zig", "Kenntnisse in Ada", "Proficiency in Lua")


ENGLISH_POSTING = description(
    "About the job",
    "Acme builds route-planning software.",
    block("What you'll do", "Build REST endpoints", "Review code"),
    block(
        "Requirements",
        "Currently enrolled in a Computer Science or related degree",
        "Solid experience with Python and SQL",
        "At least 2 years of relevant work experience",
        "Fluent English; German is a plus",
        "Available for 15 to 20 hours per week",
    ),
    block("Nice to have", "Experience with Docker"),
    block("What we offer", "Flexible hours"),
)

GERMAN_POSTING = description(
    "About the job",
    "Wir bauen Software.",
    "Was du mitbringen solltest",
    "Du solltest bereits produktive Systeme gebaut haben.",
    "Wichtig sind uns insbesondere:",
    "\n".join(
        [
            "\u2022 praktische Erfahrung mit TypeScript oder Python",
            "\u2022 Kenntnisse in SQL",
            "\u2022 Deutschkenntnisse mind. C1",
            "\u2022 mindestens 3 Jahre Berufserfahrung",
            "\u2022 abgeschlossenes Informatikstudium",
        ]
    ),
    "Von Vorteil sind Erfahrungen mit Shopify.",
    block("Was wir dir bieten", "Flexible Arbeitszeiten", marker="\u2022 "),
)


class TestWholeDescriptions:
    def test_a_realistic_english_posting_gives_the_exact_expected_requirements(self):
        assert extract_job_requirements(ENGLISH_POSTING) == JobRequirements(
            skills=("Solid experience with Python and SQL",),
            experience=("Solid experience with Python and SQL", "At least 2 years of relevant work experience"),
            education=("Currently enrolled in a Computer Science or related degree",),
        )

    def test_a_realistic_german_posting_gives_the_exact_expected_requirements(self):
        assert extract_job_requirements(GERMAN_POSTING) == JobRequirements(
            skills=("praktische Erfahrung mit TypeScript oder Python", "Kenntnisse in SQL"),
            experience=("praktische Erfahrung mit TypeScript oder Python", "mindestens 3 Jahre Berufserfahrung"),
            education=("abgeschlossenes Informatikstudium",),
        )

    def test_a_posting_that_went_through_a_csv_round_trip_with_crlf_gives_the_same_result(self):
        assert extract_job_requirements(GERMAN_POSTING.replace("\n", "\r\n")) == extract_job_requirements(GERMAN_POSTING)
        assert extract_job_requirements(ENGLISH_POSTING.replace("\n", "\r\n")) == extract_job_requirements(ENGLISH_POSTING)


class TestOutputContract:
    def test_the_result_is_a_job_requirements_of_tuples(self):
        result = extract_job_requirements(ENGLISH_POSTING)

        assert type(result) is JobRequirements
        assert isinstance(result.skills, tuple)
        assert isinstance(result.experience, tuple)
        assert isinstance(result.education, tuple)

    def test_extraction_is_deterministic(self):
        assert extract_job_requirements(ENGLISH_POSTING) == extract_job_requirements(ENGLISH_POSTING)

    def test_the_input_text_is_not_modified(self):
        text = str(ENGLISH_POSTING)

        extract_job_requirements(text)

        assert text == ENGLISH_POSTING

    def test_malformed_content_never_raises(self):
        text = "\x00\x01 | | -\n\nRequirements\n\n-\n\u2022\n- -\n\u2022 \x00\n" + "x" * 5000 + "\n- " + "y" * 5000

        assert extract_job_requirements(text) == JobRequirements()

    def test_very_long_statements_are_kept_whole(self):
        statement = "Knowledge of " + "Python, " * 500 + "and more"

        assert statements_under("Requirements", statement).skills == (statement,)


class TestPrivacy:
    @pytest.mark.parametrize(
        "value",
        [
            [SYNTHETIC_PRIVATE_MARKER],
            SYNTHETIC_PRIVATE_MARKER.encode(),
            Path(SYNTHETIC_PRIVATE_MARKER),
            {SYNTHETIC_PRIVATE_MARKER: SYNTHETIC_PRIVATE_MARKER},
        ],
        ids=["list", "bytes", "path", "dict"],
    )
    def test_exception_messages_never_contain_the_input(self, value):
        with pytest.raises(TypeError) as exc_info:
            extract_job_requirements(value)

        assert str(exc_info.value) == "description must be a str"
        assert SYNTHETIC_PRIVATE_MARKER not in repr(exc_info.value)

    def test_the_exception_carries_no_cause_or_context_with_the_input(self):
        with pytest.raises(TypeError) as exc_info:
            extract_job_requirements(SYNTHETIC_PRIVATE_MARKER.encode())

        assert exc_info.value.__cause__ is None
        assert SYNTHETIC_PRIVATE_MARKER not in str(exc_info.value.__context__)

    def test_dropped_lines_are_not_carried_into_the_result(self):
        text = description(
            block("Requirements", f"{SYNTHETIC_PRIVATE_MARKER} without any trigger", SKILL),
            f"Prose mentioning {SYNTHETIC_PRIVATE_MARKER}.",
            block("Nice to have", f"Knowledge of {SYNTHETIC_PRIVATE_MARKER}"),
        )

        result = extract_job_requirements(text)

        assert result == only_skills(SKILL)
        assert SYNTHETIC_PRIVATE_MARKER not in repr(result)

    def test_extraction_produces_no_console_output_or_log_records(self, capsys, caplog):
        extract_job_requirements(ENGLISH_POSTING + f"\n\n{SYNTHETIC_PRIVATE_MARKER}")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        assert caplog.records == []

    def test_extraction_writes_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        extract_job_requirements(ENGLISH_POSTING)

        assert list(tmp_path.iterdir()) == []


class TestDependencyIsolation:
    @pytest.mark.parametrize(
        "module",
        ["selenium", "pandas", "webdriver_manager", "pdfplumber", "models", "candidate", "candidate_parser", "resume_pdf"],
    )
    def test_importing_job_requirements_parser_does_not_load(self, module):
        # Fresh interpreter, so this can't be masked by another test importing these first.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys, job_requirements_parser; "
                f"loaded = sorted(m for m in sys.modules if m == '{module}' or m.startswith('{module}.')); "
                "assert not loaded, loaded",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
