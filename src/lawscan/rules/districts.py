"""Which province a district belongs to, from a table rather than a guess.

The place rule reads what the document writes. That is not always enough: a
notice giving ``สำนักงานประจำศาลแขวงเชียงดาว`` a new office is 812 characters
long and never writes เชียงใหม่ anywhere, yet the operator's row has both cells
filled — because a person reading it knows which province เชียงดาว is in.

That knowledge is a list, so it is kept as one. ``data/districts.txt`` holds
872 districts against their province, one pair per line, tab separated; it is
derived from the operator's own register of local authorities, which is where
the pairing is authoritative.

Two things are deliberately left out. Bangkok has เขต rather than อำเภอ and
none of them are here, which is what keeps จตุจักร in a court judgment from
being read as a place the judgment applies to. And a name two provinces share
— there is exactly one, เฉลิมพระเกียรติ — names neither, because a table that
answers ambiguously is worse than one that declines.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

TABLE_FILE = Path(__file__).resolve().parents[3] / "data" / "districts.txt"

#: How long a name must be to be recognised without the word ``อำเภอ`` in front
#: of it. Thai runs words together, so a short district name is a substring of
#: ordinary sentences: ปาย appears inside ปายังคง, ลี้ inside มิได้ลี้ภัย. Six
#: characters is where the test set stops producing false matches.
DISTINCTIVE = 6


#: Some embedded fonts collapse ``้า`` into ``ำ``: ``หนองหญ้าปล้อง`` extracts
#: as ``หนองหญำปล้อง``. In running text that cannot be undone — ``สำนัก`` and
#: ``กำหนด`` are spelt with a real ``ำ`` and a blanket rewrite would break
#: them — but a name is being matched against a register here, and a register
#: is a dictionary. The damaged spelling is added as an alias only where the
#: real one exists and the damaged one is not itself a district.
_DAMAGE = ("้า", "ำ")


@cache
def _load() -> dict[str, str]:
    if not TABLE_FILE.exists():
        return {}
    pairs = {}
    for line in TABLE_FILE.read_text(encoding="utf-8").splitlines():
        district, _, province = line.partition("\t")
        if district.strip() and province.strip():
            pairs[district.strip()] = province.strip()
    for district, province in list(pairs.items()):
        damaged = district.replace(*_DAMAGE)
        if damaged != district and damaged not in pairs:
            pairs[damaged] = province
            CANONICAL[damaged] = district
    return pairs


class _Table(dict):
    """The pairs, loaded once, readable as a plain mapping."""

    def __missing__(self, key: str) -> str:
        raise KeyError(key)


#: Damaged spelling -> the spelling that goes in the file. Reading a name the
#: font broke is only half the job; the column has to carry the real one.
CANONICAL: dict[str, str] = {}

TABLE = _Table()
TABLE.update(_load())


def spell(district: str) -> str:
    """The name as it should be written, whatever the PDF did to it."""
    return CANONICAL.get(district, district)


def province_of(district: str) -> str | None:
    """The province a district is in, or None if the table cannot say."""
    return TABLE.get((district or "").strip().removeprefix("อำเภอ").strip())


def read(text: str) -> tuple[str, str] | None:
    """The first district named in the text, with its province.

    Longest name first, so ``เชียงดาว`` is preferred over a shorter name that
    happens to sit inside it. Names below ``DISTINCTIVE`` are not looked for at
    all — they match ordinary words far more often than they match places.
    """
    if not text:
        return None
    for district in _by_length():
        if district in text:
            return spell(district), TABLE[district]
    return None


@cache
def _by_length() -> tuple[str, ...]:
    return tuple(sorted(
        (name for name in TABLE if len(name) >= DISTINCTIVE),
        key=lambda name: (-len(name), name),
    ))


#: Words that mark what follows as a place rather than as a word that happens
#: to spell one. Without them ``สมเด็จ`` — a district of กาฬสินธุ์ and the first
#: word of a royal title — put three documents in the wrong province.
MARKERS = (
    "ที่ว่าการอำเภอ",
    "เขตอำเภอ",
    "อำเภอ",
    "ศาลแขวง",
    "ศาลจังหวัด",
)


def read_marked(text: str) -> tuple[str, str] | None:
    """A district written behind a word that says it is one, with its province.

    Longest name first so ``เมืองปทุมธานี`` wins over ``ปทุมธานี``, and longest
    marker first so ``ที่ว่าการอำเภอ`` is not read as a bare ``อำเภอ``.
    """
    if not text:
        return None
    for district in _by_length():
        for marker in MARKERS:
            if marker + district in text:
                return district, TABLE[district]
    return None


def read_all(text: str) -> list[tuple[str, str]]:
    """Every district named behind a marker, in the order they appear.

    The register does the finding rather than vetting what a regular
    expression found: an instrument listing ``อำเภอปากพนัง อำเภอเชียรใหญ่``
    without repeating the province after each one gave the old pattern nothing
    to anchor on, and filtering its output afterwards could only remove names,
    never add the two it had missed.

    OCR noise falls out for free — ``ลถานที่ราชการ`` and ``เขียรใหญ่`` are not
    districts, so they are not found. That is the same property that makes
    this safe: a name has to exist to be read.
    """
    strong: list[tuple[str, str]] = []
    weak: list[tuple[str, str]] = []
    for match in re.finditer(r"(?:ที่ว่าการอำเภอ|เขตอำเภอ|อำเภอ|ศาลแขวง|ศาลจังหวัด)\s*", text or ""):
        rest = text[match.end():]
        # Every name, not only the distinctive ones: the marker in front of it
        # is what makes a four-letter name safe here, and นาดี is a district.
        for district in _all_by_length():
            if not rest.startswith(district):
                continue
            pair = (spell(district), TABLE[district])
            # A district the operative text names says จังหวัด straight after
            # it. The same name inside the map bound to the back of the
            # instrument does not, and that map is where OCR damage lives —
            # ``อำเภอเมืองนครศรีธรรมราช`` appears only in a legend reading
            # ``มาดราสวน @: @00,000``. Preferring the operative mentions keeps
            # the legend out without having to recognise a map.
            # A window rather than the very next word, because an instrument
            # lists several districts before naming the province they share:
            # "อำเภอ ก. อำเภอ ข. และอำเภอ ค. จังหวัด ง.".
            here = strong if "จังหวัด" in rest[len(district):len(district) + 60] else weak
            if pair not in here:
                here.append(pair)
            break
    return strong or weak


@cache
def _all_by_length() -> tuple[str, ...]:
    """Every name in the register, longest first.

    Longest first so ``เมืองนครศรีธรรมราช`` is preferred over ``เมือง`` — a
    district named after its province is a prefix of nothing useful, and the
    shorter reading would file the document in the wrong place.
    """
    return tuple(sorted(TABLE, key=lambda name: (-len(name), name)))
