"""Repair the name of a law the document cites.

``ชื่อกฎหมาย`` is the document's own name and comes from the catalogue by
number. The other columns here name *other* documents — the parent act, laws
referred to, laws repealed or amended — and there is no number to look those up
by. They arrive as the model read them off a page the scanner damaged, and the
damage takes two shapes.

Junk inside the name: ``พระราชบัญญัติจัดตั้งศาลปกครอง owe 1 aaa a a a a และ
วิธีพิจารณาคดีปกครอง``. Short Latin runs stranded between Thai words, left by
marginal marks and the emblem. Nothing in Thai law is spelled that way.

The year: ``พ.ศ. 2552`` where the act reads 2542, ``2520`` for 2560, ``2500``
for 2560. The glyph table maps ๖ to 2, to 0 and to 20 in different documents,
and ๕ and ๙ both to 5, so no rule turns the printed digits back into a year.
What does settle it is the name: strip the year, look the rest up in the
catalogue, and where exactly one year is listed under that name, that is the
year. 305 of 9,882 names are listed under more than one — ``พระราชกฤษฎีกาปิด
ประชุมสมัยวิสามัญแห่งรัฐสภา`` is issued most years — and those are left as they
came, because choosing between two real answers is a guess wearing a fact's
clothes.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from functools import cache

from lawscan.rules import manifest

#: Columns that hold the name of some *other* law. ``ชื่อกฎหมาย`` is not among
#: them: that is this document's own name, already settled by its number.
COLUMNS = (
    "กฎหมายแม่",
    "กฎหมายที่อ้างถึง",
    "ถูกยกเลิกโดยกฎหมายชื่อ",
    "ยกเลิกกฎหมายอื่นทั้งฉบับ",
    "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
)

_THAI = r"฀-๿"
#: A short run with Thai on both sides. Four characters a token at most, so
#: ``COVID 19`` and ``ISO 9001`` survive, and Thai must sit on both sides so
#: ``ฉบับที่ 2 (พ.ศ. …)`` is untouched. Bare numbers may ride along inside a
#: run — ``owe 1 aaa a a`` is one piece of noise — but a run of only numbers is
#: never junk: ``มาตรา 5 วรรคหนึ่ง`` is a citation, and the first version of
#: this pattern deleted that 5.
_JUNK = re.compile(
    rf"(?<=[{_THAI}])\s+(?:[A-Za-z]{{1,4}}\d*|\d{{1,2}})"
    rf"(?:\s+(?:[A-Za-z]{{1,4}}\d*|\d{{1,2}})){{0,8}}\s+(?=[{_THAI}])"
)
_HAS_LETTER = re.compile(r"[A-Za-z]")

#: ``พ.ศ.`` and the spellings the scanner returns instead of it. The Thai
#: letters fall in the Latin range of the broken font, so the abbreviation that
#: introduces every year comes back as ``W.A.``, ``we.`` or ``WA,``.
_PHOR_SOR = re.compile(r"(?:พ\.?\s?ศ\.?|W\.?\s?A\.?|we\.?|wa\.?)[\s,.]*(?=\d{3,6})",
                       re.IGNORECASE)

#: The year and whatever the citing document wrote after it. The tail is where
#: ``มาตรา 5 และมาตรา 33`` lives — the citer's own pinpoint, not part of the
#: name and not the catalogue's to overwrite.
_YEAR_AND_TAIL = re.compile(r"\s*พ\.ศ\.\s*\d{3,6}(?P<tail>.*)$")
_SPACES = re.compile(r"[\s ]+")


def tidy(name: str) -> str:
    """The name with the scanner's stray marks taken out."""
    swept = _JUNK.sub(
        lambda m: " " if _HAS_LETTER.search(m.group(0)) else m.group(0), name or "")
    return _SPACES.sub(" ", _PHOR_SOR.sub("พ.ศ. ", swept)).strip()


def _split(name: str) -> tuple[str, str]:
    """The name up to its year, and everything the citer wrote after it."""
    found = _YEAR_AND_TAIL.search(name or "")
    if not found:
        return (name or "").strip(), ""
    return name[: found.start()].strip(), (found.group("tail") or "").strip()


def _key(name: str) -> str:
    """Spacing and the year removed, so two spellings of one law agree."""
    return _SPACES.sub("", unicodedata.normalize("NFC", _split(name)[0]))


@cache
def _unambiguous() -> dict[str, str]:
    """Year-less name -> the one full name listed under it, where there is one."""
    seen: dict[str, set[str]] = defaultdict(set)
    for full in manifest.names():
        seen[_key(full)].add(full.strip())
    return {key: next(iter(names)) for key, names in seen.items() if len(names) == 1}


def settle(name: str) -> str:
    """One cited name, tidied and — where the catalogue is certain — corrected.

    Whatever follows the year is kept and put back. An earlier version dropped
    it, taking ``มาตรา 5 และมาตรา 33`` out of twenty-one penalty cells with it.
    """
    cleaned = tidy(name)
    if not cleaned:
        return cleaned
    head, tail = _split(cleaned)
    listed = _unambiguous().get(_SPACES.sub("", unicodedata.normalize("NFC", head)))
    if not listed:
        return cleaned
    return f"{listed} {tail}".strip() if tail else listed


def settle_all(cell: str) -> str:
    """Every name in a comma-joined cell, each settled on its own.

    The scanner's spelling of ``พ.ศ.`` is repaired before the split, not after.
    One of those spellings is ``WA,`` — with the comma — so splitting first cut
    ``…แผ่นดิน WA, 2535 มาตรา 5`` into two halves, neither of which was a law.
    """
    if not cell or cell.strip() == "-":
        return cell
    joined = _PHOR_SOR.sub("พ.ศ. ", cell)
    return ", ".join(part for part in (settle(x) for x in joined.split(",")) if part)
