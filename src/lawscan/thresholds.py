"""The numbers that decide whether a law applies to you, and whether they survived.

A regulation banning shops says which shops: ``อาคารพาณิชยกรรมประเภทค้าปลีก
ค้าส่งที่มีพื้นที่ใช้สอยตั้งแต่ 300 ตารางเมตรขึ้นไป``. Drop the 300 and the row
still reads as a sentence about shops, still scores as a near miss, and no
longer tells a small shop that it is exempt. That is the worst kind of error
this pipeline makes and the score cannot see it: one number weighs the same as
one tag.

So this counts them instead. A condition is a quantity with a unit, or a
comparator with a number — the two shapes the operator's own file keeps:

    300 ตารางเมตร      ไม่เกิน 1,000
    หกสิบวัน           ตั้งแต่ 300
    สองเท่า            ร้อยละ 5

Legal Thai writes most of them as words, so :mod:`lawscan.thainum` reads both
spellings and the comparison is done on digits.

Nothing here needs the reference file. The document states the condition and
the row either mentions it or does not, which makes this the one quality check
that works on the 3,184 documents nobody has answers for.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from lawscan.thainum import to_digits

#: Units a threshold is measured in, longest first so ``ตารางเมตร`` wins over
#: ``เมตร``. No boundary is required after them: Thai does not space its words,
#: and requiring one rejected ``300 ตารางเมตรขึ้นไป`` — the phrase this file
#: was written for.
UNITS: tuple[str, ...] = (
    "ลูกบาศก์เมตร", "ตารางกิโลเมตร", "ตารางเมตร", "ตารางวา", "เซนติเมตร",
    "มิลลิเมตร", "กิโลเมตร", "กิโลกรัม", "กิโลวัตต์", "เปอร์เซ็นต์",
    "ชั่วโมง", "แรงม้า", "ที่นั่ง", "สัปดาห์", "เมตร", "กรัม", "ตัน",
    "ลิตร", "บาท", "วัน", "เดือน", "ปี", "นาที", "คน", "ราย", "ตัว",
    "เท่า", "ไร่", "งวด", "ฉบับ",
)

#: Words that make the number after them a limit rather than a quantity. These
#: are the strongest signal that a threshold decides who is in scope.
COMPARATORS: tuple[str, ...] = (
    "ไม่น้อยกว่า", "ไม่ต่ำกว่า", "ไม่เกิน", "เกินกว่า", "อย่างน้อย",
    "อย่างมาก", "ตั้งแต่", "ร้อยละ", "เกิน",
)

#: Words that make the number an address rather than a measurement. A section
#: number and a Gazette volume are not conditions.
_ADDRESS = re.compile(
    r"(มาตรา|ข้อ|วรรค|อนุมาตรา|เล่ม|ตอนที่|ตอนพิเศษ|หน้า|ฉบับที่|ลำดับที่|"
    r"เลขที่|หมายเลข|ครั้งที่)\s*$"
)

_MONTHS = (
    "มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|"
    "กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม"
)

_NUMBER = r"[\d][\d,]*(?:\.\d+)?"
_QUANTITY = re.compile(rf"(?<![\d])({_NUMBER})\s*({'|'.join(UNITS)})")
_LIMIT = re.compile(rf"({'|'.join(COMPARATORS)})\s*({_NUMBER})")
_IS_DATE = re.compile(rf"\s*(?:{_MONTHS}|พ\.ศ\.|พุทธศักราช)")

#: How far into the document to look. The operative provisions are at the
#: front; a schedule of fees at the back states hundreds of amounts and none of
#: them decides who the instrument applies to.
HEAD = 12_000


@dataclass(frozen=True, slots=True)
class Condition:
    """One number the document states, and how it was stated."""

    number: str
    #: The unit or the comparator — whichever shape this was found as.
    word: str
    #: True when a comparator introduced it, which makes it a limit.
    limit: bool
    #: What the number measures, when the sentence says. A limit is only
    #: counted as surviving when its unit survives with it: the digits alone
    #: match any stray number in the cell, and ``เกิน 10`` was scoring as kept
    #: against a ``10`` that belonged to something else.
    unit: str = ""

    def __str__(self) -> str:
        head = f"{self.word} {self.number}" if self.limit else f"{self.number} {self.word}"
        return f"{head} {self.unit}".strip()


def read(text: str) -> list[Condition]:
    """Every numeric condition the document states, each one once, in order."""
    if not text:
        return []
    body = to_digits(" ".join(text[:HEAD].split()))

    found: list[Condition] = []
    seen: set[tuple[str, str]] = set()

    def keep(number: str, word: str, limit: bool, unit: str = "") -> None:
        key = (number.replace(",", ""), word)
        if key not in seen:
            seen.add(key)
            found.append(Condition(number, word, limit, unit))

    for match in _QUANTITY.finditer(body):
        if _ADDRESS.search(body[max(0, match.start() - 14): match.start()]):
            continue
        keep(match.group(1), match.group(2), limit=False)

    for match in _LIMIT.finditer(body):
        # ``ตั้งแต่ 1 มกราคม`` is a date, and the date columns already hold it.
        if _IS_DATE.match(body[match.end(): match.end() + 14]):
            continue
        keep(match.group(2), match.group(1), limit=True,
             unit=_unit_after(body, match.end()))

    return found


#: How far past a comparator to look for what the number measures. Long enough
#: for ``ตั้งแต่ 300 ตารางเมตร`` and short enough not to reach the next clause.
_UNIT_WINDOW = 18


def _unit_after(body: str, position: int) -> str:
    """The unit a limit is measured in, if the sentence gives one nearby."""
    window = body[position: position + _UNIT_WINDOW]
    for unit in UNITS:
        if unit in window:
            return unit
    return ""


def mentioned(condition: Condition, text: str) -> bool:
    """Whether a cell states this condition, in digits or in Thai words.

    The number alone is not enough. A cell holding a year, a section number and
    a count of documents will contain almost any two-digit number by accident,
    so a limit that named a unit has to be found with it.
    """
    if not text:
        return False
    plain = to_digits(text).replace(",", "")
    number = condition.number.replace(",", "")
    if number not in plain:
        return False
    return not condition.unit or condition.unit in plain


@dataclass
class Survey:
    """What the documents stated and what the rows kept."""

    documents: int = 0
    stated: int = 0
    kept: int = 0
    #: Documents that state a limit and mention none of them anywhere.
    silent: list[str] = field(default_factory=list)
    #: (document, condition) for the limits that did not survive.
    lost: list[tuple[str, Condition]] = field(default_factory=list)
    by_unit: Counter = field(default_factory=Counter)

    @property
    def recall(self) -> float:
        return self.kept / self.stated if self.stated else 1.0


def survey(documents, *, columns) -> Survey:
    """Check every document's conditions against the cells a reader opens.

    ``documents`` yields ``(number, text, row)`` where ``row`` maps column to
    value. Only limits are counted: a fee schedule states hundreds of amounts
    and a 250-character summary is not wrong to leave them out, but a threshold
    introduced by ``ตั้งแต่`` or ``ไม่เกิน`` is what decides who must read on.
    """
    result = Survey()
    for number, text, row in documents:
        result.documents += 1
        limits = [c for c in read(text) if c.limit]
        if not limits:
            continue
        cells = " ".join(row.get(column, "") or "" for column in columns)
        survived = [c for c in limits if mentioned(c, cells)]
        result.stated += len(limits)
        result.kept += len(survived)
        for condition in limits:
            result.by_unit[condition.word] += 1
            if condition not in survived:
                result.lost.append((number, condition))
        if not survived:
            result.silent.append(number)
    return result


def report(result: Survey, *, columns) -> str:
    """The survey as a person reads it."""
    if not result.stated:
        return "ไม่มีเอกสารฉบับใดระบุเงื่อนไขเชิงตัวเลข"
    lines = [
        f"เงื่อนไขเชิงตัวเลข · {result.documents} ฉบับ",
        f"  เอกสารระบุไว้ {result.stated} · ไปถึงตาราง {result.kept}"
        f" = {result.recall:.0%}",
        f"  ฉบับที่ระบุเงื่อนไขแต่ตารางไม่พูดถึงเลย {len(result.silent)}",
        "",
        f"  ช่องที่ตรวจ: {' · '.join(c.strip() for c in columns)}",
    ]
    if result.lost:
        lines += ["", "  ที่หายไป เรียงตามคำนำหน้า", "  " + "─" * 56]
        by_word = Counter(c.word for _, c in result.lost)
        for word, count in by_word.most_common():
            sample = [f"{c} ({n})" for n, c in result.lost if c.word == word][:3]
            lines.append(f"  {count:>4}  {word:<12} เช่น {' · '.join(sample)}")
    return "\n".join(lines)
