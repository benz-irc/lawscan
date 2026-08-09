"""Thai numbers written as words, read as numbers.

Legal Thai writes a quantity in words far more often than in digits — a
regulation says ``ภายในหกสิบวัน`` where the operator's file records ``60 วัน``,
and ``เป็นจำนวนสองเท่า`` where the file records ``2 เท่า``. Anything that
compares the two has to read both.

The grammar is positional and small:

    หก สิบ    →  6 × 10
    ยี่ สิบ   →  2 × 10      ``ยี่`` is two, and only ever before ``สิบ``
    สิบ เอ็ด  →  10 + 1      ``เอ็ด`` is one, and only ever in the ones place
    สอง พัน หนึ่ง ร้อย ยี่สิบ ห้า  →  2,125

A bare place word carries an implied one: ``สิบ`` is ten and ``ร้อย`` is a
hundred. ``ล้าน`` multiplies everything before it rather than adding, which is
what separates ``สองล้านห้าแสน`` from a list of two numbers.
"""

from __future__ import annotations

import re

#: The ones. ``เอ็ด`` and ``ยี่`` are positional variants and are read the
#: same as ``หนึ่ง`` and ``สอง``.
DIGITS: dict[str, int] = {
    "ศูนย์": 0, "หนึ่ง": 1, "เอ็ด": 1, "สอง": 2, "ยี่": 2, "สาม": 3,
    "สี่": 4, "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9,
}

#: The places, smallest first. ``ล้าน`` is handled apart because it scales
#: what came before it instead of taking its place in the column.
PLACES: dict[str, int] = {
    "สิบ": 10, "ร้อย": 100, "พัน": 1_000, "หมื่น": 10_000, "แสน": 100_000,
}

MILLION = "ล้าน"

_TOKEN = re.compile("|".join(sorted(
    [*DIGITS, *PLACES, MILLION], key=len, reverse=True
)))

#: The longest run of number words this will read as one number. A legal
#: threshold is never longer, and a longer run is almost always two numbers
#: that happen to be adjacent.
_WORDS = re.compile(
    r"(?:" + "|".join(sorted([*DIGITS, *PLACES, MILLION], key=len, reverse=True)) + r"){1,12}"
)


def value(words: str) -> int | None:
    """The number a run of Thai number words spells, or None if it spells none.

    Returns None rather than 0 for text that is not a number, so a caller can
    tell "not a number" from "the number zero" — ``ศูนย์`` is legal Thai and
    does appear.
    """
    tokens = _TOKEN.findall(words or "")
    if not tokens or "".join(tokens) != (words or ""):
        return None

    total = 0     # everything before the last ``ล้าน``
    section = 0   # the current group of six places
    pending = 0   # a digit waiting for the place word that scales it
    seen = False

    for token in tokens:
        if token == MILLION:
            # ``ล้าน`` scales everything accumulated so far, including a bare
            # ``ล้าน`` with nothing in front of it, which is one million.
            total = (total + section + pending or 1) * 1_000_000
            section = pending = 0
            seen = True
        elif token in PLACES:
            section += (pending or 1) * PLACES[token]
            pending = 0
            seen = True
        else:
            pending = DIGITS[token]
            seen = True

    return total + section + pending if seen else None


def to_digits(text: str) -> str:
    """The same text with every run of Thai number words written as digits.

    ``ภายในหกสิบวัน`` becomes ``ภายใน60วัน``. The spacing is not repaired,
    because this exists to be searched and compared rather than read.
    """
    if not text:
        return text

    def swap(match: re.Match[str]) -> str:
        number = value(match.group(0))
        return match.group(0) if number is None else str(number)

    return _WORDS.sub(swap, text)
