"""Our CSV against theirs, column by column.

The point of this file is that it is boring and it never flatters us. A cell
counts as right when it matches after normalisation, half-right when the two
sides overlap but disagree on the edges, and wrong otherwise. Nothing here
rounds in our favour, because a score that moves when the code has not is worse
than no score at all.

The per-column table is the part that pays. A single number says "69.8%" and
tells you nothing to do next; the table says the codes column is losing forty
cells and the province column is losing two, which is where the next hour goes.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

csv.field_size_limit(10**8)

#: Values both files use to mean "nothing here". Compared as equals, so a dash
#: against an empty cell is agreement, not a miss.
BLANK = {"", "-", "–", "—", "N/A", "n/a", "ไม่มี", "None", "nan"}

#: Long free text — a summary, a recommendation, the model's reasoning. Two
#: correct answers here are almost never the same string, so scoring them as
#: exact matches would drag the number down for no fault. Reported separately.
PROSE = {
    "คำอธิบายและสรุปสาระสำคัญ",
    "คำแนะนำสิ่งที่ต้องทำ ",
    "AI ให้เหตุผล",
    "หมายเหตุ",
}

#: Columns written as a set of items rather than a sentence. Order carries no
#: meaning in them, so they are compared as sets and can be partially right.
LISTS = {
    "หน่วยงานกำกับ",
    "อำเภอ",
    "กลุ่มเป้าหมาย",
    "Activity_Tag",
    "Product_Group_Tag",
    "Legal_Keyword_Tag",
    "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
    "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
    "ใบอนุญาต",
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
}

_SPLIT = re.compile(r"[,،;·|\n]+")
_PUNCT = re.compile(r"[\s​\"'()\[\]．.।]+")

#: ๑๓๗ and 137 are one number written two ways, and the operator's own file
#: writes it both ways — of the forty rows, some source cells use Thai digits
#: and some use Arabic. Comparing the script instead of the value would score
#: those as disagreements when nothing disagrees.
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

#: The Gazette's name and the operator's abbreviation of it.
_SAME_WORD = {"ราชกิจจาฯ": "ราชกิจจานุเบกษา"}


def norm(value: str) -> str:
    """One spelling of a value, so two spellings of the same answer agree."""
    text = unicodedata.normalize("NFC", value or "").strip()
    if text in BLANK:
        return ""
    # A document number arrives from Numbers as a float.
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    text = text.translate(_THAI_DIGITS)
    for short, full in _SAME_WORD.items():
        text = text.replace(short, full)
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split()).casefold()


def items(value: str) -> set[str]:
    return {part for part in (norm(p) for p in _SPLIT.split(value or "")) if part}


@dataclass
class Column:
    name: str
    exact: int = 0
    partial: int = 0
    wrong: int = 0
    both_blank: int = 0
    #: (document, theirs, ours) for the first few misses, so the report can show
    #: what a failure actually looks like rather than only how many there were.
    examples: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def scored(self) -> int:
        return self.exact + self.partial + self.wrong

    @property
    def credit(self) -> float:
        return self.exact + 0.5 * self.partial


def compare_cell(column: str, theirs: str, ours: str) -> str:
    """One of: blank, exact, partial, wrong."""
    a, b = norm(theirs), norm(ours)
    if not a and not b:
        return "blank"
    if a == b:
        return "exact"
    if not a or not b:
        # One side has an answer and the other does not. That is a real miss in
        # both directions: a cell we left empty, or one we invented.
        return "wrong"
    if column in LISTS:
        left, right = items(theirs), items(ours)
        return "partial" if left & right else "wrong"
    # A title that gained or lost a trailing clause is closer than a wrong one.
    return "partial" if a in b or b in a else "wrong"


def _rows(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        table = list(csv.reader(handle))
    header, body = table[0], table[1:]
    try:
        key_at = header.index("ชื่อไฟล์ ")
    except ValueError:
        key_at = 1
    by_document: dict[str, list[str]] = {}
    for row in body:
        key = norm(row[key_at]) if len(row) > key_at else ""
        if key:
            by_document.setdefault(key, row)
    return header, by_document


@dataclass
class Result:
    columns: dict[str, Column]
    per_document: dict[str, tuple[int, int]]  # document -> (credit*2, scored)
    documents: int
    missing: list[str]
    extra: list[str]

    @property
    def scored(self) -> int:
        return sum(c.scored for c in self.columns.values() if c.name not in PROSE)

    @property
    def credit(self) -> float:
        return sum(c.credit for c in self.columns.values() if c.name not in PROSE)

    @property
    def exact(self) -> int:
        return sum(c.exact for c in self.columns.values() if c.name not in PROSE)


def compare(expected: Path, ours: Path) -> Result:
    their_header, theirs = _rows(expected)
    our_header, mine = _rows(ours)

    shared = sorted(set(theirs) & set(mine))
    columns = {name: Column(name) for name in their_header if name in our_header}

    per_document: dict[str, tuple[int, int]] = {}
    for document in shared:
        credit = scored = 0
        for name, column in columns.items():
            a = their_header.index(name)
            b = our_header.index(name)
            left = theirs[document][a] if a < len(theirs[document]) else ""
            right = mine[document][b] if b < len(mine[document]) else ""
            verdict = compare_cell(name, left, right)
            if verdict == "blank":
                column.both_blank += 1
                continue
            setattr(column, verdict, getattr(column, verdict) + 1)
            if verdict != "exact" and len(column.examples) < 3:
                column.examples.append((document, left.strip()[:60], right.strip()[:60]))
            if name in PROSE:
                continue
            scored += 1
            credit += 2 if verdict == "exact" else 1 if verdict == "partial" else 0
        per_document[document] = (credit, scored)

    return Result(
        columns=columns,
        per_document=per_document,
        documents=len(shared),
        missing=sorted(set(theirs) - set(mine)),
        extra=sorted(set(mine) - set(theirs)),
    )


def write_comparison(expected: Path, ours: Path, out: Path) -> int:
    """Every cell of both files side by side, one row per cell that differs.

    A per-column tally says where to look; this says what to look at. Rows are
    ordered worst-first within each document so the first screenful is the work
    to do, and both values are written in full — a comparison that truncates is
    a comparison you have to leave to check.
    """
    their_header, theirs = _rows(expected)
    our_header, mine = _rows(ours)
    shared = sorted(set(theirs) & set(mine))
    columns = [c for c in their_header if c in our_header]

    rank = {"wrong": 0, "partial": 1, "exact": 2, "blank": 3}
    written = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["เอกสาร", "คอลัมน์", "ผล", "ของผู้ดูแล", "ของระบบ", "ชนิด"])
        for document in shared:
            lines = []
            for name in columns:
                left = theirs[document][their_header.index(name)]
                right = mine[document][our_header.index(name)]
                verdict = compare_cell(name, left, right)
                if verdict in ("exact", "blank"):
                    continue
                lines.append((rank[verdict], name, verdict, left.strip(), right.strip()))
            for _, name, verdict, left, right in sorted(lines):
                kind = "ข้อความยาว" if name in PROSE else "รายการ" if name in LISTS else "ค่าเดียว"
                writer.writerow([
                    document, name.strip(),
                    {"wrong": "ไม่ตรง", "partial": "ตรงบางส่วน"}[verdict],
                    left, right, kind,
                ])
                written += 1
    return written


def report(result: Result, *, examples: bool = False) -> str:
    """The table, worst column first."""
    lines: list[str] = []
    scored, credit, exact = result.scored, result.credit, result.exact
    lines.append(f"เทียบ {result.documents} ฉบับ · ช่องที่นับ {scored:,}")
    if scored:
        lines.append(
            f"ตรงเป๊ะ {exact:,} ({exact / scored:.1%}) · "
            f"รวมตรงบางส่วน {credit / scored:.1%} · "
            f"ผิด {scored - exact - sum(c.partial for c in result.columns.values() if c.name not in PROSE):,}"
        )
    if result.missing:
        lines.append(f"เราไม่มี: {', '.join(result.missing)}")
    if result.extra:
        lines.append(f"เกินมา: {', '.join(result.extra)}")

    lines.append("")
    lines.append(f"{'คอลัมน์':<48}{'เป๊ะ':>6}{'บางส่วน':>9}{'ผิด':>6}{'ว่างทั้งคู่':>12}")
    lines.append("─" * 84)
    ranked = sorted(
        result.columns.values(),
        key=lambda c: (-(c.wrong + 0.5 * c.partial), c.name),
    )
    for column in ranked:
        if not column.scored and not column.both_blank:
            continue
        tag = " (ข้อความยาว)" if column.name in PROSE else ""
        name = (column.name.strip() + tag)[:47]
        lines.append(
            f"{name:<48}{column.exact:>6}{column.partial:>9}"
            f"{column.wrong:>6}{column.both_blank:>12}"
        )
        if examples and column.examples:
            for document, left, right in column.examples:
                lines.append(f"      {document}  เขา: {left or '—'}")
                lines.append(f"      {'':<6}  เรา: {right or '—'}")

    worst = sorted(
        ((d, c, s) for d, (c, s) in result.per_document.items() if s),
        key=lambda x: x[1] / (2 * x[2]),
    )[:8]
    if worst:
        lines.append("")
        lines.append("ฉบับที่ห่างที่สุด: " + ", ".join(
            f"{d} {c / (2 * s):.0%}" for d, c, s in worst
        ))
    return "\n".join(lines)
