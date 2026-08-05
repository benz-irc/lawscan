"""Split a Thai legal document into its numbered units, by rule.

Thai drafting opens every unit with its own name at the start of a line —
``มาตรา ๘``, ``ข้อ ๑๒``, ``หมวด ๓`` — which is a fixed format, and reading a
fixed format is what code is for. The same argument as the Gazette header, and
the same outcome when measured: asked to read out the sections of a 52-page
act, the model returned 25 of 158; asked again with a different provider it
returned 158 headings and no text under any of them. On the 140-document test
set this splitter finds units in 119, and the 21 it finds none in are single
paragraph announcements that genuinely have none — "พรรค… สิ้นสภาพความเป็น
พรรคการเมือง" is one sentence with no ข้อ in it.

What it will not do is guess. A line that does not open a unit is body text of
whichever unit precedes it, and a document with no unit openers yields nothing
rather than one unit holding the whole page.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from lawscan.ocr.thai_text import thai_to_arabic_digits
from lawscan.rules.unit_types import StructureUnit, StructureUnitType

#: The openers that count, and what each one is. Ordered longest-first so
#: ``ส่วนที่`` is not read as ``ส่วน`` with a stray "ที่". Every one of these
#: carries a number, always — and the number is what tells an opener from an
#: ordinary word that starts the same way. Without it, "ข้อ" matched the front
#: of "ข้อเสนอแนะ" and of "ข้อมูลข่าวสาร", and two documents gained a clause
#: made out of a noun.
_NUMBERED: tuple[tuple[str, StructureUnitType], ...] = (
    ("ส่วนที่", StructureUnitType.PART),
    ("มาตรา", StructureUnitType.SECTION),
    ("หมวด", StructureUnitType.CHAPTER),
    ("ข้อ", StructureUnitType.CLAUSE),
)

#: Openers that carry no number. They name a block of the document rather than
#: counting within it, which is why they are also the words a หมวด uses as its
#: own title — "หมวด ๖" on one line, "บทเฉพาะกาล" on the next.
_UNNUMBERED: tuple[tuple[str, StructureUnitType], ...] = (
    ("บทเฉพาะกาล", StructureUnitType.TRANSITIONAL),
    ("บทกำหนดโทษ", StructureUnitType.PENALTY),
)

_OPENERS = _UNNUMBERED + _NUMBERED

#: A unit number, including the two forms that carry a second part: the ทวิ/ตรี
#: suffixes, and the slash form an amendment inserts with — ``ข้อ ๓๕/๒`` sits
#: between ๓๕ and ๓๖ and is a clause in its own right. Both belong to the
#: number: dropping either merges the inserted unit into the one before it.
_NUMBER = r"\d+(?:/\d+)?(?:\s*(?:ทวิ|ตรี|จัตวา|เบญจ|ฉ|สัตต|อัฏฐ|นว|ทศ))?"

_UNIT = re.compile(
    r"(?m)^[ \t]*(?:(?P<kind>"
    + "|".join(re.escape(word) for word, _ in _NUMBERED)
    + r")[ \t]*(?P<no>"
    + _NUMBER
    + r")|(?P<plain>"
    + "|".join(re.escape(word) for word, _ in _UNNUMBERED)
    + r"))(?=[\s฀-๿]|$)"
)
_KIND = dict(_OPENERS)
_UNNUMBERED_WORDS = frozenset(word for word, _ in _UNNUMBERED)


def _kind(match: re.Match[str]) -> str:
    """The opener word, whichever of the two shapes matched."""
    return match.group("kind") or match.group("plain")


#: Text between quotation marks is a passage the document is quoting from
#: another law, and the units named inside it belong to that law. Reading them
#: as units of this one produced a "มาตรา 18" inside a regulation whose own
#: clauses are numbered ข้อ 1 to ข้อ 8.
_QUOTED = re.compile(r"[“\"][^”\"]{0,4000}[”\"]", re.DOTALL)


@dataclass(frozen=True, slots=True)
class PageBreak:
    """Where a page starts in the joined text, so a unit can name its page."""

    offset: int
    page_number: int


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTED.finditer(text)]


def _page_of(offset: int, breaks: list[PageBreak]) -> int:
    page = 1
    for brk in breaks:
        if brk.offset > offset:
            break
        page = brk.page_number
    return page


def _absorb_titles(text: str, matches: list[re.Match[str]]) -> list[re.Match[str]]:
    """Drop an unnumbered heading that is the line right after a numbered one.

    ``หมวด ๖ / บทเฉพาะกาล / ข้อ ๗๗`` is one chapter named "บทเฉพาะกาล", not a
    chapter followed by a sibling. Read as two units the chapter kept only its
    own number — a heading with no text under it — and validation refused the
    whole document rather than accept a unit the document does not have.

    Only the line immediately below counts. An unnumbered heading standing on
    its own, which is how an act with no หมวด at all opens its penalties, is
    still a unit of its own.
    """
    kept: list[re.Match[str]] = []
    for index, match in enumerate(matches):
        if index and _kind(match) in _UNNUMBERED_WORDS:
            previous = matches[index - 1]
            between = text[previous.end() : match.start()]
            # Exactly one newline between them, and nothing else: the heading
            # is on the line directly below, so it is that heading's name.
            if between.strip() == "" and between.count("\n") == 1:
                continue
        kept.append(match)
    return kept


#: The ordinals a unit number uses for its inserted part. ทวิ is second, ตรี
#: third, and so on — the same position the slash form writes as /2, /3.
_ORDINALS: dict[str, int] = {
    "ทวิ": 2,
    "ตรี": 3,
    "จัตวา": 4,
    "เบญจ": 5,
    "ฉ": 6,
    "สัตต": 7,
    "อัฏฐ": 8,
    "นว": 9,
    "ทศ": 10,
}


def _one_scheme(matches: list[re.Match[str]]) -> list[re.Match[str]]:
    """Drop the numbering scheme this document does not use for itself.

    มาตรา and ข้อ are alternatives for the same level, and a document uses one
    or the other: primary legislation numbers in มาตรา, while a ระเบียบ,
    ประกาศ or กฎกระทรวง numbers in ข้อ. Where both appear, the rarer one is
    this document citing a law written in the other scheme — a ประกาศ with
    twenty-eight ข้อ of its own cited "มาตรา ๑๐๘/๔ แห่งพระราชบัญญัติ
    ประกันวินาศภัย" and gained two sections that belong to an act it is not.

    The majority wins, with no threshold: there is no count at which a
    document starts using two schemes. On a tie neither is dropped, because
    nothing here says which is the document's own — that leaves the two
    citations in a court ruling that cites both, which is where this lands on
    the one document in the test set that ties.
    """
    counts = Counter(_kind(match) for match in matches)
    section, clause = counts.get("มาตรา", 0), counts.get("ข้อ", 0)
    if not section or not clause or section == clause:
        return matches
    cited = "ข้อ" if section > clause else "มาตรา"
    return [match for match in matches if _kind(match) != cited]


def _order_key(raw: str | None) -> tuple[int, int] | None:
    """A unit number as the pair it is: the number, then what was inserted at it.

    ``มาตรา ๘``, ``มาตรา ๘ ทวิ`` and ``มาตรา ๙`` run in that order, and so do
    ``ข้อ ๓๕``, ``ข้อ ๓๕/๒`` and ``ข้อ ๓๖``. Compared as plain integers the
    inserted unit is not greater than the one it follows, so the ordering check
    read it as a repeat and dropped it — losing a clause the document has and
    merging its text into the clause before it.
    """
    if not raw:
        return None
    text = raw.strip()
    digits = ""
    for char in text:
        if not char.isdigit():
            break
        digits += char
    if not digits:
        return None

    rest = text[len(digits) :].strip()
    minor = 0
    if rest.startswith("/"):
        tail = rest[1:].strip()
        minor = int(tail) if tail.isdigit() else 0
    elif rest:
        minor = _ORDINALS.get(rest, 0)
    return int(digits), minor


def _ascending(matches: list[re.Match[str]]) -> list[re.Match[str]]:
    """Keep only the openers that continue their kind's numbering.

    A document numbers each kind of unit upward: มาตรา 1, มาตรา 2, มาตรา 3.
    A มาตรา that repeats or goes backwards is not a new unit of this document
    — it is this document citing another law's section, and a court ruling
    does that dozens of times, at the start of a line, without quotation
    marks. Left in, one ruling produced มาตรา 49 three times and the duplicate
    blocked its own import.

    Each kind is tracked separately, because มาตรา and หมวด count
    independently of each other.
    """
    highest: dict[str, tuple[int, int]] = {}
    kept: list[re.Match[str]] = []
    for match in matches:
        kind = _kind(match)
        number = _order_key(match.group("no"))
        if number is None:
            # บทเฉพาะกาล and บทกำหนดโทษ carry no number and appear once.
            kept.append(match)
            continue
        if kind in highest and number <= highest[kind]:
            continue
        highest[kind] = number
        kept.append(match)
    return kept


def split(pages: list[str]) -> list[StructureUnit]:
    """The document's units in reading order, or an empty list if it has none.

    ``pages`` is the text of each page, in order, so a unit can report the page
    it begins on without the caller reconstructing offsets.
    """
    if not pages:
        return []

    breaks: list[PageBreak] = []
    offset = 0
    parts: list[str] = []
    for number, page in enumerate(pages, start=1):
        breaks.append(PageBreak(offset=offset, page_number=number))
        parts.append(page)
        offset += len(page) + 1
    text = "\n".join(parts)

    quoted = _quoted_spans(text)

    def inside_quote(position: int) -> bool:
        return any(start <= position < end for start, end in quoted)

    matches = _absorb_titles(
        text,
        _ascending(
            _one_scheme(
                [
                    m
                    for m in _UNIT.finditer(thai_to_arabic_digits(text))
                    if not inside_quote(m.start())
                ]
            )
        ),
    )
    if not matches:
        return []

    units: list[StructureUnit] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start() : end].strip()
        if not body:
            continue
        units.append(
            StructureUnit(
                unit_type=_KIND[_kind(match)],
                section_no=(match.group("no") or "").strip() or None,
                order_no=len(units),
                content=body,
                page_number=_page_of(match.start(), breaks),
                # The opener line is the evidence: it is what the rule matched,
                # and it is what a reviewer compares against the page image.
                source_text=body.splitlines()[0][:300],
                # Read rather than recognised. Not 1.0: the split is certain,
                # the OCR under it is not, and a reviewer should still look.
                confidence=0.9,
            )
        )
    return units
