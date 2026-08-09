"""Wrong cells grouped by what made them wrong, so the pattern is visible.

A column score says a column is wrong. It does not say whether it is wrong
because the model read the document differently or because the pipeline broke
the answer on the way to the cell — and those need opposite work. The first is
a prompt or a rule; the second is a bug that is usually one line and usually
affects dozens of cells at once.

The two that prompted this file were found by a person reading the spreadsheet:

* ``…พ.ศ. 2560 None`` — an f-string interpolating a nullable field, which cost
  32 cells and silently dropped 83 section citations.
* ``สำนักงาน ก. กระทรวง ข.`` — one array slot holding two agencies joined by a
  tab, which cost 30 cells and read as one office with a long name.

Both have a signature. Neither needed a model to spot. Finding them by eye is
the failure this replaces: run :func:`scan` after every run and the mechanical
ones come out sorted by how many cells they cost.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Defect:
    """One signature, and whether code or a prompt is what fixes it."""

    name: str
    #: True when the shape alone proves the pipeline did it. These are the ones
    #: worth stopping for; the rest are disagreements about the document.
    mechanical: bool
    test: object

    def matches(self, expected: str, got: str) -> bool:
        try:
            return bool(self.test(expected, got))
        except Exception:  # noqa: BLE001 — a bad signature must not stop the sweep
            return False


_FENCE = re.compile(r"```|\{\"|\"\}|\\\"")
_THINKING = re.compile(
    r"\b(I need to|Let'?s |I should|wait|actually,|there is a formatting|"
    r"as an AI|sorry|apolog)", re.IGNORECASE
)
_EMPTY_WORD = re.compile(r"(?:^|[\s,])(None|null|nan|undefined|NaN)\s*(?:,|$)")
_BREAK = re.compile(r"[\t\r\n\v\f]")
_LOOSE_COMMA = re.compile(r",\s*,|,\s*$|^\s*,")
_BRACKETED = re.compile(r"(?:^|[\s,])<[^<>]{1,60}>")


def _items(value: str) -> list[str]:
    return sorted(part.strip() for part in value.split(",") if part.strip())


#: Ordered most specific first — a cell is reported under the first that fits,
#: so a cell holding both a code fence and a stray comma is a code fence.
SIGNATURES: tuple[Defect, ...] = (
    Defect("โค้ดเฟนซ์หรือ JSON ดิบหลุดเข้าเซลล์", True,
           lambda e, g: _FENCE.search(g)),
    Defect("โมเดลคิดออกมาเป็นข้อความ แล้วหลุดเข้าเซลล์", True,
           lambda e, g: _THINKING.search(g)),
    Defect("None/null ห้อยอยู่ในค่า", True,
           lambda e, g: _EMPTY_WORD.search(g)),
    Defect("tab หรือขึ้นบรรทัดคั่นอยู่กลางค่า", True,
           lambda e, g: _BREAK.search(g)),
    Defect("ค่ายังใส่วงเล็บแหลมของตัวอย่างใน prompt", True,
           lambda e, g: _BRACKETED.search(g)),
    Defect("จุลภาคลอย — คั่นแล้วไม่มีอะไรตาม", True,
           lambda e, g: _LOOSE_COMMA.search(g)),
    Defect("เว้นวรรคซ้อนหรือเว้นวรรคหัวท้าย", True,
           lambda e, g: g != g.strip() or "  " in g),
    Defect("รายการเดียวกัน คนละลำดับ", True,
           lambda e, g: e.strip() and g.strip() and _items(e) == _items(g)),
    Defect("เราตอบครอบเฉลย — มีของเกิน", False,
           lambda e, g: e.strip() and e.strip() in g),
    Defect("เฉลยครอบเรา — เราตอบไม่ครบ", False,
           lambda e, g: g.strip() and g.strip() in e),
    Defect("เราเขียน - แต่เฉลยมีเนื้อหา", False,
           lambda e, g: g.strip() == "-" and e.strip() not in ("", "-")),
    Defect("เฉลยเขียน - แต่เราตอบเนื้อหา", False,
           lambda e, g: e.strip() == "-" and g.strip() not in ("", "-")),
    Defect("เราว่าง เฉลยตอบ", False,
           lambda e, g: e.strip() and not g.strip()),
    Defect("เฉลยว่าง เราตอบ", False,
           lambda e, g: not e.strip() and g.strip()),
)

OTHER = "อ่านเอกสารคนละอย่าง"


@dataclass
class Found:
    """Every wrong cell of one run, grouped."""

    counts: Counter = field(default_factory=Counter)
    columns: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    examples: dict[str, list] = field(default_factory=lambda: defaultdict(list))
    mechanical: set[str] = field(default_factory=set)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def mechanical_cells(self) -> int:
        return sum(n for tag, n in self.counts.items() if tag in self.mechanical)


def classify(expected: str, got: str) -> tuple[str, bool]:
    """Which signature this pair fits, and whether code is what fixes it."""
    for defect in SIGNATURES:
        if defect.matches(expected or "", got or ""):
            return defect.name, defect.mechanical
    return OTHER, False


def scan(reference: dict, ours: dict, columns, *, skip=frozenset(), verdict=None) -> Found:
    """Group every wrong cell of a run by signature.

    ``verdict`` is :func:`lawscan.diff.compare_cell`, passed in rather than
    imported so this module stays about shapes and the comparison stays in one
    place.
    """
    if verdict is None:
        from lawscan.diff import compare_cell as verdict

    found = Found(mechanical={d.name for d in SIGNATURES if d.mechanical})
    for number in sorted(set(reference) & set(ours)):
        for column in columns:
            if column in skip or column.strip() in skip:
                continue
            expected = reference[number].get(column, "") or ""
            got = ours[number].get(column, "") or ""
            if verdict(column, expected, got) != "wrong":
                continue
            tag, _ = classify(expected, got)
            found.counts[tag] += 1
            found.columns[tag][column.strip()] += 1
            if len(found.examples[tag]) < 3:
                found.examples[tag].append((number, column.strip(), expected, got))
    return found


def report(found: Found, *, width: int = 96) -> str:
    """The sweep as a person reads it: fixable first, biggest first."""
    if not found.total:
        return "ไม่มีช่องที่ผิด"

    lines = [
        f"ช่องที่ผิด {found.total:,} ช่อง · เป็นบั๊กเชิงกล {found.mechanical_cells:,} ช่อง"
        f" ({found.mechanical_cells / found.total:.1%})",
        "",
        "แก้ที่โค้ดได้ — ลายเซ็นบอกว่าท่อทำพัง ไม่ใช่โมเดลอ่านผิด",
        "─" * width,
    ]

    def rows(tags):
        out = []
        for tag in tags:
            n = found.counts[tag]
            top = " · ".join(f"{c}({k})" for c, k in found.columns[tag].most_common(3))
            out.append(f"  {tag:<42}{n:>5}   {top[: width - 52]}")
        return out

    fixable = [t for t, _ in found.counts.most_common() if t in found.mechanical]
    lines += rows(fixable) or ["  ไม่พบ"]
    lines += ["", "ต้องแก้ที่ prompt หรือเขียนกฎ", "─" * width]
    lines += rows([t for t, _ in found.counts.most_common()
                   if t not in found.mechanical and t != OTHER])
    lines += ["", f"  {OTHER:<42}{found.counts[OTHER]:>5}"]

    if fixable:
        lines += ["", "ตัวอย่างของบั๊กเชิงกล", "═" * width]
        for tag in fixable:
            lines.append(f"\n▸ {tag}  ({found.counts[tag]} ช่อง)")
            for number, column, expected, got in found.examples[tag]:
                lines.append(f"   [{number}] {column}")
                lines.append(f"      เฉลย {expected[:80]!r}")
                lines.append(f"      เรา  {got[:80]!r}")
    return "\n".join(lines)
