"""job_page_parser against synthetic LinkedIn-style HTML. No Selenium, no browser, no network.

These tests prove our extraction LOGIC on HTML we wrote ourselves (tests/fixtures/linkedin/). They
do not prove that the selectors match the real LinkedIn DOM; that needs a captured real page.
"""

import html as html_lib
import re
from pathlib import Path

import pytest

from job_page_parser import (
    MAX_DESCRIPTION_CHARS,
    TRUNCATION_MARKER,
    canonical_job_url,
    parse_job_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "linkedin"
DOT = "·"

TEXT_A = "This is a sufficiently long introduction paragraph for testing purposes"
TEXT_B = "A second paragraph that is also comfortably longer than the minimum size"
HEADER_LINE = f"Berlin, Germany {DOT} 1 week ago {DOT} Over 100 applicants"


def fixture_html(name: str) -> str:
    return (FIXTURES / f"job_detail_{name}.html").read_text(encoding="utf-8")


def markup(body: str) -> str:
    """A description container using the selector the original scraper relied on."""
    return f'<div class="show-more-less-html__markup">{body}</div>'


def description_of(page: str) -> str | None:
    return parse_job_page(page).description


def location_of(page: str) -> str | None:
    return parse_job_page(page).location


def top_card(header: str, chips: tuple[str, ...] = (), company_link: bool = True) -> str:
    link = '<a href="https://www.linkedin.com/company/acme/">Acme</a>' if company_link else ""
    items = "".join(f"<li><span>{chip}</span></li>" for chip in chips)
    return (
        f'<div class="top-card"><h1>Working Student</h1><div>{link}</div>'
        f"<div><span>{header}</span></div><ul>{items}</ul></div>"
    )


class TestDescriptionFromPageFixtures:
    def test_returns_the_posting_text_not_the_header_metadata(self):
        description = description_of(fixture_html("berlin"))

        assert description.startswith("About the role")
        assert "route-planning software" in description
        for header_text in ("1 week ago", "Over 100 applicants", "Promoted by hirer", "Actively reviewing"):
            assert header_text not in description

    def test_includes_the_requirements_at_the_end_of_the_posting(self):
        description = description_of(fixture_html("berlin"))

        assert "Requirements" in description
        assert "- Solid experience with Python and SQL" in description
        assert description.endswith("- Available for 15 to 20 hours per week")

    def test_does_not_return_navigation_filters_or_footer_text(self):
        description = description_of(fixture_html("berlin"))

        for page_chrome in ("My Network", "Messaging", "Notifications", "Date posted", "Easy Apply",
                            "Senior Backend Engineer", "Show more", "Privacy", "Help Center"):
            assert page_chrome not in description

    def test_keeps_paragraph_and_bullet_boundaries(self):
        description = description_of(fixture_html("berlin"))

        assert "About the role\n\nAcme Logistics builds" in description
        assert "- Build and test REST endpoints for our route optimisation service\n- Improve the reliability" in description

    def test_text_is_normalized(self):
        description = description_of(fixture_html("berlin"))

        assert description == description.strip()
        assert "  " not in description
        assert "\n\n\n" not in description
        assert all(line == line.strip() for line in description.split("\n"))

    def test_finds_a_description_in_a_job_details_container(self):
        description = description_of(fixture_html("remote"))

        assert description.startswith("Your mission")
        assert "- Experience with Python, SQL and Docker" in description
        assert "25 applicants" not in description

    def test_finds_a_description_in_a_description_text_container(self):
        description = description_of(fixture_html("hybrid"))

        assert description.startswith("Who we are")
        assert "- Two days per week in our Berlin office" in description
        assert "78 people clicked apply" not in description

    def test_a_page_without_a_location_still_yields_its_description(self):
        description = description_of(fixture_html("missing_location"))

        assert "React and TypeScript" in description
        assert "- Experience with React and TypeScript" in description


class TestLongDescriptions:
    @staticmethod
    def long_berlin_page(paragraphs: int) -> str:
        filler = "".join(
            f"<p>Filler paragraph number {i} describing benefits and team culture in some detail.</p>"
            for i in range(paragraphs)
        )
        return fixture_html("berlin").replace("<!-- EXTRA_PARAGRAPHS -->", filler)

    def test_content_beyond_the_old_1500_character_limit_is_kept(self):
        description = description_of(self.long_berlin_page(40))

        assert len(description) > 3000
        assert description.index("Solid experience with Python and SQL") > 1500
        assert "Filler paragraph number 39" in description
        assert description.endswith("- Available for 15 to 20 hours per week")
        assert TRUNCATION_MARKER not in description

    def test_a_posting_far_larger_than_the_old_limit_is_untouched_below_the_ceiling(self):
        body = "".join(f"<p>Paragraph {i}: {TEXT_A}.</p>" for i in range(100))

        description = description_of(markup(body))

        assert 5000 < len(description) < MAX_DESCRIPTION_CHARS
        assert "Paragraph 99" in description
        assert TRUNCATION_MARKER not in description

    def test_the_safety_ceiling_is_far_above_the_old_limit(self):
        assert MAX_DESCRIPTION_CHARS >= 8000

    def test_text_beyond_the_ceiling_is_cut_at_a_boundary_and_visibly_marked(self):
        body = "".join(f"<p>Paragraph {i}: {TEXT_A}.</p>" for i in range(1000))

        description = description_of(markup(body))

        assert description.endswith("\n" + TRUNCATION_MARKER)
        assert len(description) <= MAX_DESCRIPTION_CHARS + len(TRUNCATION_MARKER) + 1
        assert description.startswith("Paragraph 0:")
        body_text = description[: -len(TRUNCATION_MARKER)].rstrip()
        assert body_text.endswith(".")  # cut at the end of a paragraph, not mid-word

    def test_the_ceiling_can_be_lowered_per_call(self):
        body = "".join(f"<p>Paragraph {i}: {TEXT_A}.</p>" for i in range(50))

        description = parse_job_page(markup(body), max_description_chars=500).description

        assert description.endswith(TRUNCATION_MARKER)
        assert len(description) <= 500 + len(TRUNCATION_MARKER) + 1

    def test_a_description_exactly_at_the_ceiling_is_not_marked(self):
        text = " ".join(["word"] * 100)
        limit = len(text)

        description = parse_job_page(markup(f"<p>{text}</p>"), max_description_chars=limit).description

        assert description == text


class TestWhitespaceAndStructure:
    def test_runs_of_whitespace_inside_a_paragraph_become_single_spaces(self):
        page = markup(f"<p>{TEXT_A}   \n\t  extra    words</p>")

        assert description_of(page) == f"{TEXT_A} extra words"

    def test_surrounding_whitespace_is_stripped(self):
        page = markup(f"\n\n   <p>   {TEXT_A}   </p>   \n")

        assert description_of(page) == TEXT_A

    def test_paragraphs_are_separated_by_one_blank_line(self):
        assert description_of(markup(f"<p>{TEXT_A}</p><p>{TEXT_B}</p>")) == f"{TEXT_A}\n\n{TEXT_B}"

    def test_many_empty_paragraphs_do_not_stack_blank_lines(self):
        page = markup(f"<p>{TEXT_A}</p><p></p><p>  </p><br><br><p>{TEXT_B}</p>")

        assert description_of(page) == f"{TEXT_A}\n\n{TEXT_B}"

    @pytest.mark.parametrize("line_break", ["<br>", "<br/>", "<br />"])
    def test_line_breaks_are_kept(self, line_break):
        assert description_of(markup(f"<p>{TEXT_A}{line_break}{TEXT_B}</p>")) == f"{TEXT_A}\n{TEXT_B}"

    def test_list_items_become_dash_bullets_on_consecutive_lines(self):
        page = markup(f"<p>{TEXT_A}</p><ul><li>one</li><li>two</li><li>three</li></ul>")

        assert description_of(page) == f"{TEXT_A}\n\n- one\n- two\n- three"

    def test_empty_list_items_are_dropped(self):
        page = markup(f"<p>{TEXT_A}</p><ul><li></li><li>real</li><li>  </li></ul>")

        assert description_of(page) == f"{TEXT_A}\n\n- real"

    def test_inline_tags_do_not_introduce_line_breaks(self):
        page = markup(f"<p>{TEXT_A} <strong>bold <em>deep</em></strong> and <a href='#'>a link</a>.</p>")

        assert description_of(page) == f"{TEXT_A} bold deep and a link."

    def test_div_blocks_start_new_lines(self):
        assert description_of(markup(f"<div>{TEXT_A}</div><div>{TEXT_B}</div>")) == f"{TEXT_A}\n{TEXT_B}"

    def test_html_entities_are_decoded(self):
        assert description_of(markup(f"<p>{TEXT_A} R&amp;D &lt;3 &euro;5</p>")) == f"{TEXT_A} R&D <3 €5"

    def test_script_and_style_content_is_not_part_of_the_text(self):
        page = markup(f"<p>{TEXT_A}</p><script>var workplace = 'Remote';</script><style>.x {{ color: red }}</style>")

        assert description_of(page) == TEXT_A

    @pytest.mark.parametrize("label", ["Show more", "Show less", "show MORE"])
    def test_show_more_and_show_less_controls_are_removed(self, label):
        assert description_of(markup(f"<p>{TEXT_A}</p><button>{label}</button>")) == TEXT_A

    def test_words_the_old_scraper_used_to_reject_are_kept(self):
        # The old JS discarded any text containing "Premium" or "Search" (and, in one tier, "Sign").
        text = "Our premium customers search for reliable partners; we design robust systems and search for talent"

        assert description_of(markup(f"<p>{text}</p>")) == text


class TestDescriptionSelection:
    def test_the_original_selector_wins_even_when_it_comes_later_in_the_page(self):
        candidate = f'<div class="jobs-description__content">{TEXT_A}</div>'
        original = markup(TEXT_B)

        assert description_of(candidate + original) == TEXT_B

    @pytest.mark.parametrize(
        "container",
        [
            '<div class="description__text">{}</div>',
            '<div id="job-details">{}</div>',
            '<section class="jobs-description__content">{}</section>',
        ],
    )
    def test_each_candidate_container_is_used_when_the_original_selector_is_absent(self, container):
        assert description_of(container.format(TEXT_A)) == TEXT_A

    def test_content_below_the_minimum_size_in_a_known_container_is_skipped(self):
        page = markup("x" * 49) + f'<div class="description__text">{TEXT_A}</div>'

        assert description_of(page) == TEXT_A

    def test_content_at_the_minimum_size_in_a_known_container_is_accepted(self):
        assert description_of(markup("x" * 50)) == "x" * 50

    def test_a_generic_description_div_is_used_when_no_known_container_exists(self):
        page = f'<div class="job-description-body">{TEXT_A}. {TEXT_B}.</div>'

        assert description_of(page) == f"{TEXT_A}. {TEXT_B}."

    def test_a_generic_description_div_below_the_fallback_minimum_is_ignored(self):
        assert description_of(f'<div class="job-description-body">{"y" * 99}</div>') is None

    def test_the_top_card_container_named_description_is_never_mistaken_for_the_posting(self):
        # LinkedIn's top card has a "...primary-description-container" holding "<place> · <age> · <applicants>".
        # A class-contains-"description" fallback matches it; this is the suspected cause of the bad data.
        header = (
            '<div class="job-details-jobs-unified-top-card__primary-description-container">'
            f"<div><span>{HEADER_LINE}</span></div>"
            f"<div>Promoted by hirer {DOT} Actively reviewing applicants</div></div>"
        )

        assert description_of(header) is None

    def test_the_real_posting_is_found_after_a_top_card_container_named_description(self):
        header = (
            '<div class="job-details-jobs-unified-top-card__primary-description-container">'
            f"<div><span>{HEADER_LINE}</span></div>"
            f"<div>Promoted by hirer {DOT} Actively reviewing applicants</div></div>"
        )
        posting = f'<div class="job-description-body">{TEXT_A}. {TEXT_B}.</div>'

        assert description_of(header + posting) == f"{TEXT_A}. {TEXT_B}."

    def test_header_metadata_inside_a_known_container_is_not_returned_as_the_description(self):
        page = markup(f"<p>{HEADER_LINE}</p><p>Promoted by hirer {DOT} Actively reviewing applicants</p>")

        assert description_of(page) is None

    def test_there_is_no_page_wide_fallback(self):
        # The old JS finally took "the largest text block on the page", which can be navigation text.
        page = f'<div class="feed">{"Unrelated navigation and feed text. " * 30}</div>'

        assert description_of(page) is None

    @pytest.mark.parametrize("page", ["", "   ", "plain text, no markup at all", "<div><p>unclosed", "</p></div></span>"])
    def test_pages_without_a_description_yield_none_and_do_not_raise(self, page):
        details = parse_job_page(page)

        assert details.description is None
        assert details.location is None

    def test_very_deep_nesting_does_not_overflow_the_stack(self):
        page = "<div>" * 3000 + markup(TEXT_A) + "</div>" * 3000

        assert description_of(page) == TEXT_A


class TestLocationFromPageFixtures:
    def test_berlin(self):
        assert location_of(fixture_html("berlin")) == "Berlin, Germany"

    def test_remote(self):
        assert location_of(fixture_html("remote")) == "Germany (Remote)"

    def test_hybrid(self):
        assert location_of(fixture_html("hybrid")) == "Berlin, Germany (Hybrid)"

    def test_missing_location_is_none_so_the_job_falls_back_to_unknown(self):
        assert location_of(fixture_html("missing_location")) is None

    def test_a_page_full_of_remote_elsewhere_does_not_make_a_berlin_job_remote(self):
        page = fixture_html("berlin")
        assert page.count("Remote") >= 4  # filter button, another job's card, a script, the footer

        location = location_of(page)

        assert location == "Berlin, Germany"
        assert "remote" not in location.lower()

    def test_remote_elsewhere_does_not_invent_a_location_when_none_is_shown(self):
        page = fixture_html("missing_location")
        assert page.count("Remote") >= 2

        assert location_of(page) is None


class TestLocationRules:
    def test_a_header_line_that_names_remote_as_the_place(self):
        assert location_of(top_card(f"Remote {DOT} 2 days ago {DOT} 12 applicants")) == "Remote"

    def test_hybrid_label_is_appended(self):
        assert location_of(top_card(HEADER_LINE, chips=("Hybrid", "Full-time"))) == "Berlin, Germany (Hybrid)"

    def test_remote_label_is_appended(self):
        assert location_of(top_card(HEADER_LINE, chips=("Remote",))) == "Berlin, Germany (Remote)"

    @pytest.mark.parametrize("label", ["On-site", "Onsite", "on-site"])
    def test_on_site_is_implied_by_a_plain_place(self, label):
        assert location_of(top_card(HEADER_LINE, chips=(label,))) == "Berlin, Germany"

    def test_labels_are_matched_case_insensitively(self):
        assert location_of(top_card(HEADER_LINE, chips=("REMOTE",))) == "Berlin, Germany (Remote)"

    def test_the_label_is_not_repeated_when_the_place_already_carries_it(self):
        header = f"Berlin, Germany (Hybrid) {DOT} 1 week ago {DOT} 5 applicants"

        assert location_of(top_card(header, chips=("Hybrid",))) == "Berlin, Germany (Hybrid)"

    def test_a_label_that_is_only_part_of_a_sentence_does_not_count(self):
        assert location_of(top_card(HEADER_LINE, chips=("Remote work possible", "Not remote"))) == "Berlin, Germany"

    def test_a_remote_label_outside_the_top_card_does_not_count(self):
        far_away = f"<div>{'unrelated page content ' * 80}</div><span>Remote</span>"
        page = f'<div class="pane">{top_card(HEADER_LINE)}{far_away}</div>'

        assert location_of(page) == "Berlin, Germany"

    def test_a_city_line_elsewhere_on_the_page_is_not_taken_as_the_location(self):
        # The old JS took the first page line with a comma and fewer than 50 characters.
        page = "<div><p>Frankfurt, Germany</p><p>Some other text</p></div>"

        assert location_of(page) is None

    @pytest.mark.parametrize("age", ["12 minutes ago", "1 hour ago", "3 days ago", "2 weeks ago", "1 month ago", "Reposted 2 weeks ago"])
    def test_every_posting_age_format_is_recognised(self, age):
        assert location_of(top_card(f"Munich, Bavaria, Germany {DOT} {age} {DOT} 7 applicants")) == "Munich, Bavaria, Germany"

    @pytest.mark.parametrize(
        "header, expected",
        [
            (f"Berlin, Germany {DOT} 1 week ago {DOT} Over 100 applicants", "Berlin, Germany"),
            (f"Berlin, Berlin, Germany {DOT} Reposted 2 weeks ago {DOT} 78 people clicked apply", "Berlin, Berlin, Germany"),
            (f"Berlin, Berlin, Germany {DOT} 3 weeks ago {DOT} Over 100 applicants", "Berlin, Berlin, Germany"),
            (f"Berlin, Berlin, Germany {DOT} 3 weeks ago {DOT} Over 100 people clicked apply", "Berlin, Berlin, Germany"),
            (f"Germany {DOT} 12 minutes ago {DOT} 0 people clicked apply", "Germany"),
        ],
        ids=["berlin", "reposted", "three-weeks", "clicked-apply", "germany-only"],
    )
    def test_header_lines_from_a_real_earlier_scrape_are_recognised(self, header, expected):
        # These five strings are the real "description" values the old scraper stored in jobs.csv.
        assert location_of(top_card(header)) == expected

    @pytest.mark.parametrize("not_a_place", ["Promoted", "Reposted", "Viewed", "New"])
    def test_status_words_before_the_age_are_not_a_place(self, not_a_place):
        assert location_of(top_card(f"{not_a_place} {DOT} 2 days ago {DOT} 5 applicants")) is None

    def test_when_the_header_appears_twice_the_one_in_the_top_card_with_a_company_link_wins(self):
        other = top_card(f"Hamburg, Germany {DOT} 2 days ago {DOT} 9 applicants", company_link=False)
        wanted = top_card(HEADER_LINE, company_link=True)

        assert location_of(other + wanted) == "Berlin, Germany"

    def test_two_ambiguous_headers_without_any_company_link_give_no_location(self):
        first = top_card(f"Hamburg, Germany {DOT} 2 days ago {DOT} 9 applicants", company_link=False)
        second = top_card(HEADER_LINE, company_link=False)

        assert location_of(first + second) is None

    def test_a_single_header_without_a_company_link_is_accepted(self):
        assert location_of(top_card(HEADER_LINE, company_link=False)) == "Berlin, Germany"

    def test_a_dedicated_location_element_is_used_when_there_is_no_header_line(self):
        page = '<span class="topcard__flavor topcard__flavor--bullet">Munich, Bavaria, Germany</span>'

        assert location_of(page) == "Munich, Bavaria, Germany"

    def test_an_implausible_dedicated_element_is_ignored(self):
        page = f'<span class="topcard__flavor--bullet">{"very long text " * 20}</span>'

        assert location_of(page) is None

    def test_the_header_line_takes_precedence_over_a_dedicated_element(self):
        page = top_card(HEADER_LINE) + '<span class="topcard__flavor--bullet">Somewhere Else</span>'

        assert location_of(page) == "Berlin, Germany"


class TestCanonicalJobUrl:
    @pytest.mark.parametrize(
        "href, expected",
        [
            ("https://www.linkedin.com/jobs/view/3812345678/", "https://www.linkedin.com/jobs/view/3812345678/"),
            ("https://www.linkedin.com/jobs/view/3812345678", "https://www.linkedin.com/jobs/view/3812345678/"),
            ("/jobs/view/3812345678/?eBP=NOT_ELIGIBLE&refId=Zb3%2Fq1w%3D%3D&trackingId=Ab12&trk=flagship3", "https://www.linkedin.com/jobs/view/3812345678/"),
            ("https://www.linkedin.com/jobs/view/3812345678/?trackingId=abc#section", "https://www.linkedin.com/jobs/view/3812345678/"),
            ("http://WWW.LinkedIn.com/jobs/view/3812345678/", "https://www.linkedin.com/jobs/view/3812345678/"),
            ("https://de.linkedin.com/jobs/view/software-engineer-at-acme-3812345678?trk=x", "https://de.linkedin.com/jobs/view/software-engineer-at-acme-3812345678/"),
            ("  https://www.linkedin.com/jobs/view/1/  ", "https://www.linkedin.com/jobs/view/1/"),
        ],
    )
    def test_tracking_parameters_and_fragments_are_dropped(self, href, expected):
        assert canonical_job_url(href) == expected

    @pytest.mark.parametrize(
        "href",
        [
            None,
            "",
            "   ",
            "https://example.com/jobs/view/3812345678/",
            "https://notlinkedin.com/jobs/view/3812345678/",
            "https://linkedin.com.evil.test/jobs/view/3812345678/",
            "https://www.linkedin.com/company/acme/",
            "https://www.linkedin.com/jobs/collections/recommended/",
            "https://www.linkedin.com/jobs/search/?currentJobId=3812345678",
            "/feed/",
            "javascript:void(0)",
            "#",
        ],
    )
    def test_anything_that_is_not_a_linkedin_job_link_gives_an_empty_url(self, href):
        assert canonical_job_url(href) == ""

    def test_no_url_is_ever_built_from_a_bare_job_id(self):
        assert canonical_job_url("3812345678") == ""

    def test_the_card_link_in_the_fixture_reduces_to_the_stable_job_url(self):
        page = fixture_html("berlin")
        href = re.search(r'class="job-card-container__link"\s+href="([^"]+)"', page).group(1)

        assert canonical_job_url(html_lib.unescape(href)) == "https://www.linkedin.com/jobs/view/3812345678/"

    @pytest.mark.parametrize(
        "name, expected",
        [("remote", "3800000001"), ("hybrid", "3800000002"), ("missing_location", "3800000003")],
    )
    def test_each_fixture_card_link_reduces_to_its_own_job_url(self, name, expected):
        page = fixture_html(name)
        href = re.search(r'class="job-card-container__link"\s+href="([^"]+)"', page).group(1)

        assert canonical_job_url(html_lib.unescape(href)) == f"https://www.linkedin.com/jobs/view/{expected}/"
