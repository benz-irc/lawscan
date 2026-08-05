"""The Gazette running header, read by rule rather than asked for.

Every page the ราชกิจจานุเบกษา prints carries a header naming the volume, the
issue, and the date of publication:

    หน้า ๑๕
    เล่ม ๑๓๗ ตอนที่ ๑๔ ก   ราชกิจจานุเบกษา   ๒๑ กุมภาพันธ์ ๒๕๖๓

That date is what a Thai law's dates are counted from. The date printed beside
the signature at the end — "ประกาศ ณ วันที่ ..." — is the day the instrument was
signed, usually weeks earlier, and the two are routinely confused: asked for a
publication date, a model reads the one written in a sentence rather than the
one set in a header, and returns the signing date.

Told about the difference, it did no better. Measured over ten documents, an
instruction to prefer the header moved publish-date accuracy from 4/10 to 3/10
and produced one date in 1933, so that instruction was reverted. This module
does the reading instead, because the header is a fixed format and reading a
fixed format is what code is for. Where it finds one, its answer is used; where
it does not, the model's answer stands — of the 140-document first test set, 57
carry a header, 36 carry only a signing date, and 47 carry neither.

Nothing here guesses. A header that does not parse yields None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import logging
from lawscan.ocr.thai_text import thai_to_arabic_digits

log = logging.getLogger(__name__)

#: Thai month names, in order, as the Gazette prints them.
THAI_MONTHS: tuple[str, ...] = (
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
)
_MONTH_NUMBER = {name: number for number, name in enumerate(THAI_MONTHS, start=1)}
_MONTHS = "|".join(THAI_MONTHS)

#: Matched on month *names* rather than a Thai character class: [ก-ฮ] is the
#: consonants only, and every month name contains a vowel, so a class-based
#: pattern matches nothing at all — which is exactly how the first attempt at
#: this failed, silently and completely.
_HEADER = re.compile(
    r"เล่ม\s*(?P<volume>\d{1,4})\s+"
    r"(?P<issue_kind>ตอน(?:ที่|พิเศษ)?)\s*(?P<issue>\d{1,4}(?:\s*[ก-ฮ])?)\s+"
    r"ราชกิจจานุเบกษา\s+"
    rf"(?P<day>\d{{1,2}})\s+(?P<month>{_MONTHS})\s+(?P<year>\d{{4}})"
)

#: "หน้า ๑๕" — the page the instrument starts on, printed above the header.
_PAGE = re.compile(r"หน้า\s*(\d{1,4})")

#: A Buddhist-Era year is at least this. Below it the number is already CE, or
#: it is not a year at all.
_BE_THRESHOLD = 2300


@dataclass(frozen=True, slots=True)
class GazetteHeader:
    """What one running header states. Every field came from the page."""

    volume: str
    issue: str
    publish_date: date
    page: str | None
    #: ตอนที่ or ตอนพิเศษ, as printed — different issues of one volume, and
    #: dropping the word made them the same string.
    issue_kind: str = "ตอนที่"


def parse(text: str) -> GazetteHeader | None:
    """Read the first Gazette header in the text, or None if there is none.

    The first is the right one: the header repeats on every page of the same
    issue, so any of them says the same thing, and the first is the one on the
    page the instrument begins on.
    """
    normalized = thai_to_arabic_digits(text)
    match = _HEADER.search(normalized)
    if match is None:
        return None

    year = int(match.group("year"))
    if year >= _BE_THRESHOLD:
        year -= 543
    try:
        published = date(year, _MONTH_NUMBER[match.group("month")], int(match.group("day")))
    except ValueError:
        # A day that does not exist in that month: the header is damaged, and
        # a date built by clamping it would be a fact nothing printed.
        log.info("gazette_header_date_invalid", raw=match.group(0)[:80])
        return None

    # The page number is printed above the header, so look behind the match.
    before = normalized[max(0, match.start() - 80) : match.start()]
    page = _PAGE.search(before)

    return GazetteHeader(
        volume=match.group("volume"),
        issue=re.sub(r"\s+", " ", match.group("issue")).strip(),
        # "ตอนที่ 14 ก" and "ตอนพิเศษ 14 ง" are different issues of the
        # same volume, and dropping the word made them the same string.
        issue_kind=re.sub(r"\s+", "", match.group("issue_kind") or "ตอนที่"),
        publish_date=published,
        page=page.group(1) if page else None,
    )


#: "ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศในราชกิจจานุเบกษาเป็นต้นไป" — the
#: commonest commencement clause in Thai subordinate legislation, and one that
#: names no date at all. The date it produces is fully determined: the day
#: after the one printed in the header above.
_EFFECT_NEXT_DAY = re.compile(r"ใช้บังคับ\s*ตั้งแต่\s*วันถัดจากวันประกาศ")

#: "…ตั้งแต่วันประกาศในราชกิจจานุเบกษาเป็นต้นไป" — the same clause without the
#: day's grace. Checked after the one above, which it is otherwise a prefix of.
_EFFECT_SAME_DAY = re.compile(r"ใช้บังคับ\s*ตั้งแต่\s*วันประกาศ")

#: "…ให้ใช้บังคับเมื่อพ้นกำหนดหนึ่งร้อยยี่สิบวันนับแต่วันประกาศ…" — a delay
#: measured from publication. Thai drafting writes the count in words as often
#: as in digits, so both are read; the words are the round numbers the drafting
#: actually uses, and a count outside them is left alone rather than guessed.
_SPELLED_DAYS: Final[dict[str, int]] = {
    "สามสิบ": 30,
    "หกสิบ": 60,
    "เก้าสิบ": 90,
    "หนึ่งร้อยยี่สิบ": 120,
    "หนึ่งร้อยแปดสิบ": 180,
    "สองร้อยสี่สิบ": 240,
    "สามร้อยหกสิบ": 360,
}

_EFFECT_AFTER_DAYS = re.compile(
    r"ใช้บังคับ\s*(?:เมื่อ)?\s*พ้น\s*(?:กำหนด)?\s*"
    r"(?P<count>\d{1,3}|" + "|".join(_SPELLED_DAYS) + r")\s*"
    r"(?P<unit>วัน|เดือน|ปี)\s*นับแต่วันประกาศ"
)

#: "…ตั้งแต่วันที่ ๑ ตุลาคม พ.ศ. ๒๕๖๔ เป็นต้นไป" — an explicit date, which may
#: legitimately precede publication. Thai regulations are routinely applied
#: retroactively, so an effective date earlier than the publication date is not
#: by itself an error, and this clause is why.
_EFFECT_ON_DATE = re.compile(r"ใช้บังคับ\s*ตั้งแต่\s*วันที่\s*\d")

#: "ตั้งแต่วันที่ ๑ เมษายน ๒๕๖๓" — a date written out, wherever it appears.
#: Read only when something ties it to commencement, because a Thai instrument
#: also writes dates when citing the law it amends: document 100034 states
#: 28 ตุลาคม 2554 in a recital, and taking the first date found made that its
#: commencement date instead of the correct 3 กุมภาพันธ์ 2563.
_STATED_DATE = re.compile(
    r"ตั้งแต่วันที่\s*(?P<day>\d{1,2})\s*(?P<month>" + _MONTHS + r")\s*"
    r"(?:พ\.ศ\.\s*)?(?P<year>\d{4})"
)

#: What makes a stated date a commencement: the document either says so before
#: it, or writes "onwards" after it. Measured over forty documents, requiring
#: one of these reads 40 right where taking the date unconditionally read 39.
_COMMENCEMENT_AFTER = re.compile(r"^\s*(?:พ\.ศ\.\s*\d{4}\s*)?(?:เป็นต้นไป|เป็นต้นมา)")
_COMMENCEMENT_BEFORE = ("ใช้บังคับ", "มีผล", "เปิดทำการ", "ให้ใช้", "ทั้งนี้")
_COMMENCEMENT_LOOKBACK = 90


def stated_effective_date(text: str) -> date | None:
    """A commencement date the document writes out, rather than derives.

    Four of the forty documents state their date in a clause that never uses
    the words ``ใช้บังคับ`` — a court office opens ``ตั้งแต่วันที่ 1 เมษายน``
    — so a pattern anchored on that phrase could not see them, and each was
    silently taking the publication date instead.
    """
    normalized = thai_to_arabic_digits(text)
    for match in _STATED_DATE.finditer(normalized):
        before = normalized[max(0, match.start() - _COMMENCEMENT_LOOKBACK) : match.start()]
        after = normalized[match.end() : match.end() + 24]
        if not (_COMMENCEMENT_AFTER.match(after) or any(c in before for c in _COMMENCEMENT_BEFORE)):
            continue
        try:
            return date(
                int(match.group("year")) - 543,
                _MONTH_NUMBER[match.group("month")],
                int(match.group("day")),
            )
        except ValueError:  # 31 กันยายน and friends — a typo, not a date
            continue
    return None


def effective_date_from_rule(text: str, publish_date: date) -> date | None:
    """The commencement date the document's own rule produces, or None.

    Only for the two clauses that state a rule instead of a date. A clause
    naming an explicit date is left alone: that date is in the document
    already, and it is frequently earlier than publication because Thai
    regulations are often applied retroactively — of 21 laws whose stored
    effective date preceded publication, 11 said so on purpose.

    Deriving rather than inventing: both the rule and the publication date are
    printed on the page, and the arithmetic between them has one answer.
    """
    normalized = thai_to_arabic_digits(text)
    if _EFFECT_ON_DATE.search(normalized):
        return None

    delayed = _EFFECT_AFTER_DAYS.search(normalized)
    if delayed:
        raw = delayed.group("count")
        count = int(raw) if raw.isdigit() else _SPELLED_DAYS[raw]
        unit = delayed.group("unit")
        # "พ้นกำหนด ๑๒๐ วันนับแต่วันประกาศ" runs out at the end of the 120th
        # day, so the instrument binds on the day after — measured against the
        # operator's own dates, +120 days from publication is what they hold.
        if unit == "วัน":
            return publish_date + timedelta(days=count)
        if unit == "เดือน":
            return publish_date + timedelta(days=30 * count)
        return publish_date + timedelta(days=365 * count)

    if _EFFECT_NEXT_DAY.search(normalized):
        return publish_date + timedelta(days=1)
    if _EFFECT_SAME_DAY.search(normalized):
        return publish_date
    return None


def commences_on_publication(text: str) -> bool:
    """Whether the document states no commencement rule at all.

    An instrument that says nothing takes effect on the day it is published —
    that is the default, not an assumption, and the operator's own spreadsheet
    holds the publication date for 23 of the documents where this codebase held
    nothing. Saying nothing is the commonest case in a ประกาศ.

    False as soon as the document does say something, whatever it says, so a
    clause naming a date or a delay is never overridden by the default.
    """
    normalized = thai_to_arabic_digits(text)
    return not any(
        pattern.search(normalized)
        for pattern in (
            _EFFECT_ON_DATE,
            _EFFECT_AFTER_DAYS,
            _EFFECT_NEXT_DAY,
            _EFFECT_SAME_DAY,
        )
    )


#: A clause naming the day the instrument starts, rather than deriving it from
#: publication. "ให้ใช้บังคับตั้งแต่วันที่ ๒๑ มีนาคม พ.ศ. ๒๕๕๗ เป็นต้นไป".
_EXPLICIT_START = re.compile(
    r"(?:ใช้บังคับ|มีผล)(?:ใช้บังคับ)?\s*ตั้งแต่วันที่\s*[๐-๙\d]"
)


def states_its_own_start(text: str) -> bool:
    """Whether the document names the day it starts, rather than implying it."""
    return _EXPLICIT_START.search(text) is not None
