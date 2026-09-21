"""Selenium-free knowledge of how a LinkedIn job page is laid out.

The browser adapter hands this module the page's HTML (a live page, or a saved snapshot); every
function here is pure, so it is tested offline against fixtures in tests/fixtures/linkedin/.

The selector lists below are the ONE place to update when LinkedIn's markup changes: save the
page as a snapshot, add it as a fixture, and adjust the lists until the tests pass. Which entries
match the real LinkedIn DOM has NOT been verified offline; the fixtures are synthetic.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterator
from urllib.parse import urlsplit

# Safety ceiling for one description (~3,000 tokens). Typical postings are 2,000-6,000 characters;
# the ceiling only exists to bound CSV size and later LLM cost, never to trim normal postings.
MAX_DESCRIPTION_CHARS = 12_000
TRUNCATION_MARKER = "[truncated]"


@dataclass(frozen=True)
class JobPageDetails:
    """What could be read from a job page. None means "not found", never a guess."""

    location: str | None
    description: str | None


@dataclass(frozen=True)
class _Selector:
    tag: str | None = None
    css_class: str | None = None  # one exact class token
    element_id: str | None = None

    def matches(self, node: "_Node") -> bool:
        if self.tag is not None and node.tag != self.tag:
            return False
        if self.css_class is not None and self.css_class not in node.classes.split():
            return False
        if self.element_id is not None and node.attrs.get("id") != self.element_id:
            return False
        return True


# ---------------------------------------------------------------------------------------------
# LinkedIn-specific configuration
# ---------------------------------------------------------------------------------------------

# Ordered most to least trusted. Only the first entry comes from the original scraper; the rest are
# UNVERIFIED candidates. The first entry that yields enough text wins.
_DESCRIPTION_SELECTORS = (
    _Selector(tag="div", css_class="show-more-less-html__markup"),  # original scraper's primary
    _Selector(css_class="description__text"),  # unverified candidate
    _Selector(element_id="job-details"),  # unverified candidate
    _Selector(css_class="jobs-description__content"),  # unverified candidate
)
_MIN_DESCRIPTION_CHARS = 50

# Original scraper's second tier: any div whose class contains one of these hints. That tier is what
# most likely returned the header line, because LinkedIn's top card has a "...primary-description..."
# container. It is kept, but never inside the top card and never for header-like text.
_FALLBACK_CLASS_HINTS = ("description", "show-more")
_MIN_FALLBACK_DESCRIPTION_CHARS = 100
_HEADER_BLOCK_CLASS_HINTS = ("top-card", "topcard", "primary-description")

# UNVERIFIED candidates for an element that holds only the location; used when no header line exists.
_LOCATION_SELECTORS = (
    _Selector(css_class="topcard__flavor--bullet"),
    _Selector(css_class="job-details-jobs-unified-top-card__bullet"),
    _Selector(css_class="jobs-unified-top-card__bullet"),
)

# The header line seen in every row of a real scrape: "<place> · <posted> · <applicants>", e.g.
# "Berlin, Germany · 1 week ago · Over 100 applicants" or "... · Reposted 2 weeks ago · ...".
_POSTED = r"(?:Reposted\s+)?\d+\s+(?:second|minute|hour|day|week|month)s?\s+ago"
_HEADER_LINE = re.compile(
    rf"^(?P<place>[^·•]{{2,80}}?)\s*[·•]\s*{_POSTED}\b", re.IGNORECASE
)
_NOT_A_PLACE = frozenset({"promoted", "reposted", "viewed", "applied", "saved", "new"})

_WORKPLACE_TYPES = {"remote": "Remote", "hybrid": "Hybrid", "on-site": "On-site", "onsite": "On-site", "on site": "On-site"}
_SHOWN_IN_LOCATION = frozenset({"Remote", "Hybrid"})  # on-site is implied by a plain place name
_UI_LINES = frozenset({"show more", "show less"})

# How far around the header line to look for a workplace-type label (top card only).
_NEIGHBORHOOD_LEVELS = 3
_NEIGHBORHOOD_MAX_CHARS = 1200
_HEADER_MAX_CHARS = 400
_MAX_PLACE_CHARS = 80

# ---------------------------------------------------------------------------------------------
# Minimal HTML tree (stdlib only)
# ---------------------------------------------------------------------------------------------

_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
_RAW_TEXT_TAGS = frozenset({"script", "style"})  # their text is code, never page content
_PARAGRAPH_TAGS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "blockquote", "pre", "table"})
_BLOCK_TAGS = frozenset(
    {"address", "article", "aside", "dd", "details", "div", "dl", "dt", "fieldset", "figcaption", "figure",
     "footer", "form", "header", "hr", "main", "nav", "section", "tr"}
)
_WHITESPACE = re.compile(r"\s+")
_LINE_BREAK, _PARAGRAPH_BREAK = "\x01", "\x02"  # collapsible: adjacent block edges merge into one break
_BREAK_RUN = re.compile(r"[\s\x01\x02]*[\x01\x02][\s\x01\x02]*")  # a block edge plus the whitespace around it


class _Node:
    __slots__ = ("tag", "attrs", "parent", "children", "text")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None") -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[_Node | str] = []
        self.text: str | None = None

    @property
    def classes(self) -> str:
        return self.attrs.get("class", "")


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("[document]", {}, None)
        self._open = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {name: value or "" for name, value in attrs}, self._open)
        self._open.children.append(node)
        if tag not in _VOID_TAGS:
            self._open = node

    def handle_endtag(self, tag: str) -> None:
        node = self._open
        while node is not self.root and node.tag != tag:
            node = node.parent  # tolerate stray or missing closing tags
        if node is not self.root:
            self._open = node.parent

    def handle_data(self, data: str) -> None:
        if self._open.tag not in _RAW_TEXT_TAGS:
            self._open.children.append(data)


def _parse(html: str) -> _Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _iter_elements(root: _Node) -> Iterator[_Node]:
    """Every element below root, in document order."""
    stack = [child for child in reversed(root.children) if isinstance(child, _Node)]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(child for child in reversed(node.children) if isinstance(child, _Node))


def _wrap(tag: str, inner: str) -> str:
    if tag == "br":
        return "\n"  # a real break: <br><br> is a deliberate blank line
    if tag == "li":
        return f"{_LINE_BREAK}- {inner}{_LINE_BREAK}"
    if tag in _PARAGRAPH_TAGS:
        return f"{_PARAGRAPH_BREAK}{inner}{_PARAGRAPH_BREAK}"
    if tag in _BLOCK_TAGS:
        return f"{_LINE_BREAK}{inner}{_LINE_BREAK}"
    return inner


def _text(node: _Node) -> str:
    """The element's text with line breaks where the page would show them (memoized on the node)."""
    stack = [node]
    while stack:
        current = stack[-1]
        pending = [c for c in current.children if isinstance(c, _Node) and c.text is None]
        if pending:
            stack.extend(pending)
            continue
        stack.pop()
        if current.text is None:
            inner = "".join(
                _WHITESPACE.sub(" ", child) if isinstance(child, str) else child.text
                for child in current.children
            )
            current.text = _wrap(current.tag, inner)
    return node.text


def _normalize(text: str) -> str:
    """Trim every line, drop empty list items, and keep at most one blank line between paragraphs."""
    text = _BREAK_RUN.sub(lambda run: "\n\n" if _PARAGRAPH_BREAK in run.group() else "\n", text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    kept: list[str] = []
    for line in lines:
        if line == "-":
            continue
        if line or (kept and kept[-1]):
            kept.append(line)
    return "\n".join(kept).strip()


def _lines(node: _Node) -> list[str]:
    return _normalize(_text(node)).split("\n")


def _ancestors_and_self(node: _Node) -> Iterator[_Node]:
    current: _Node | None = node
    while current is not None:
        yield current
        current = current.parent


# ---------------------------------------------------------------------------------------------
# Description
# ---------------------------------------------------------------------------------------------

def _description_text(node: _Node) -> str:
    text = _normalize(_text(node))
    text = "\n".join(line for line in text.split("\n") if line.casefold() not in _UI_LINES)
    return _normalize(text)


def _place_from_header_line(line: str) -> str | None:
    match = _HEADER_LINE.match(line)
    if match is None:
        return None
    place = match.group("place").strip()
    if place.casefold() in _NOT_A_PLACE or not any(ch.isalpha() for ch in place):
        return None
    return place


def _looks_like_header(text: str) -> bool:
    first_lines = [line for line in text.split("\n") if line][:3]
    return any(_place_from_header_line(line) is not None for line in first_lines)


def _limit(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    boundary = max(cut.rfind("\n"), cut.rfind(" "))
    if boundary > max_chars * 0.8:
        cut = cut[:boundary]
    return f"{cut.rstrip()}\n{TRUNCATION_MARKER}"


def _extract_description(root: _Node, max_chars: int) -> str | None:
    for selector in _DESCRIPTION_SELECTORS:
        for node in _iter_elements(root):
            if selector.matches(node):
                text = _description_text(node)
                if len(text) >= _MIN_DESCRIPTION_CHARS and not _looks_like_header(text):
                    return _limit(text, max_chars)

    for node in _iter_elements(root):
        if node.tag != "div" or not any(hint in node.classes for hint in _FALLBACK_CLASS_HINTS):
            continue
        if any(hint in n.classes for n in _ancestors_and_self(node) for hint in _HEADER_BLOCK_CLASS_HINTS):
            continue
        text = _description_text(node)
        if len(text) >= _MIN_FALLBACK_DESCRIPTION_CHARS and not _looks_like_header(text):
            return _limit(text, max_chars)

    return None


# ---------------------------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------------------------

def _header_candidates(root: _Node) -> list[tuple[str, _Node]]:
    """Smallest elements whose text contains a header line, with the place named in it."""
    found: list[tuple[str, _Node]] = []
    for node in _iter_elements(root):
        if len(_text(node)) > _HEADER_MAX_CHARS * 2:
            continue
        lines = _lines(node)
        if not 20 <= len(" ".join(lines)) <= _HEADER_MAX_CHARS:
            continue
        for line in lines:
            place = _place_from_header_line(line)
            if place is not None:
                found.append((place, node))
                break

    has_candidate_below: set[int] = set()
    for _, node in found:
        for ancestor in list(_ancestors_and_self(node))[1:]:
            has_candidate_below.add(id(ancestor))
    return [(place, node) for place, node in found if id(node) not in has_candidate_below]


def _neighborhood(node: _Node) -> _Node:
    """The node plus up to a few enclosing elements, as long as they stay small (the top card)."""
    top = node
    for _ in range(_NEIGHBORHOOD_LEVELS):
        parent = top.parent
        if parent is None or parent.tag == "[document]" or len(_text(parent)) > _NEIGHBORHOOD_MAX_CHARS:
            break
        top = parent
    return top


def _has_company_link(scope: _Node) -> bool:
    stack = [scope]
    while stack:
        node = stack.pop()
        if node.tag == "a" and "/company/" in node.attrs.get("href", ""):
            return True
        stack.extend(child for child in node.children if isinstance(child, _Node))
    return False


def _workplace_type(scope: _Node) -> str | None:
    """A label that is, by itself, exactly Remote / Hybrid / On-site inside the top card."""
    stack = [scope]
    while stack:
        node = stack.pop()
        if len(_text(node)) <= 40:
            label = _normalize(_text(node)).removeprefix("- ").casefold()
            if label in _WORKPLACE_TYPES:
                return _WORKPLACE_TYPES[label]
        stack.extend(reversed([child for child in node.children if isinstance(child, _Node)]))
    return None


def _compose_location(place: str, workplace: str | None) -> str:
    if workplace not in _SHOWN_IN_LOCATION:
        return place
    if place.casefold() == workplace.casefold() or place.rstrip().endswith(")"):
        return place
    return f"{place} ({workplace})"


def _is_plausible_place(text: str) -> bool:
    return 2 <= len(text) <= _MAX_PLACE_CHARS and "\n" not in text and any(ch.isalpha() for ch in text)


def _extract_location(root: _Node) -> str | None:
    candidates = _header_candidates(root)
    chosen = next((c for c in candidates if _has_company_link(_neighborhood(c[1]))), None)
    if chosen is None and len(candidates) == 1:
        chosen = candidates[0]
    if chosen is not None:
        place, node = chosen
        return _compose_location(place, _workplace_type(_neighborhood(node)))

    for selector in _LOCATION_SELECTORS:
        for node in _iter_elements(root):
            if selector.matches(node):
                text = _normalize(_text(node))
                if _is_plausible_place(text):
                    return text
    return None


# ---------------------------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------------------------

def parse_job_page(html: str, max_description_chars: int = MAX_DESCRIPTION_CHARS) -> JobPageDetails:
    """Read the location and the posting text from a job page's HTML."""
    root = _parse(html)
    return JobPageDetails(
        location=_extract_location(root),
        description=_extract_description(root, max_description_chars),
    )


def canonical_job_url(href: str | None) -> str:
    """The stable LinkedIn job URL for a card link, or "" when it is not a LinkedIn job link.

    Tracking parameters and fragments are dropped; nothing is ever constructed from an id.
    """
    if not href or not href.strip():
        return ""
    parts = urlsplit(href.strip())
    host = parts.netloc.lower() if parts.netloc else "www.linkedin.com" if href.strip().startswith("/") else ""
    if parts.scheme not in ("", "http", "https"):
        return ""
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return ""
    if not re.match(r"^/jobs/view/[^/]+", parts.path):
        return ""
    return f"https://{host}{parts.path.rstrip('/')}/"
