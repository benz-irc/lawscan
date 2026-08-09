"""One document against its row in the reference, cell by cell.

The forty-document table says which column is losing and is the right tool for
choosing what to work on. It is the wrong tool for the work itself: fixing a
prompt means reading one document, changing one sentence, and asking whether
that document got better — and an average over forty rows cannot answer that.
A fix that helps the document in front of you and breaks two others reads as
"no change", which is the least useful sentence a measurement can produce.

So this prints one row, worst cell first, with the operator's answer beside
ours and the verdict between them. Nothing is aggregated except the row's own
score, and the score names its denominator: prose and the columns nothing in
the document can answer are shown but not counted, exactly as ``lawscan diff``
counts them.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from lawscan import sheet
from lawscan.diff import EXTERNAL, PROSE, UNSCORED, compare_cell

csv.field_size_limit(10**8)

#: Worst first. The order is the work queue: a wrong cell needs a change, a
#: partial one needs a wording decision, an exact one needs nothing.
ORDER = {"wrong": 0, "partial": 1, "blank": 2, "exact": 3}

MARK = {"wrong": "✗", "partial": "≈", "exact": "✓", "blank": "·"}


@dataclass(frozen=True, slots=True)
class Cell:
    column: str
    theirs: str
    ours: str
    verdict: str

    @property
    def counted(self) -> bool:
        return self.column not in UNSCORED

    @property
    def note(self) -> str:
        if self.column in PROSE:
            return "ข้อความยาว ไม่นับ"
        if self.column in EXTERNAL:
            return "นอกเอกสาร ไม่นับ"
        return ""


def _rows(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    return sheet.by_document(path)


def compare_row(expected: Path, ours: Path, document: str) -> list[Cell]:
    """Every shared column for one document, worst first.

    Raises ``KeyError`` when either file has no such row, because a silent
    empty result would read as "nothing wrong with it".
    """
    their_header, theirs = _rows(expected)
    our_header, mine = _rows(ours)
    key = sheet.document_of(document)
    if key not in theirs:
        raise KeyError(f"ไฟล์อ้างอิงไม่มีเอกสาร {document}")
    if key not in mine:
        raise KeyError(f"ผลลัพธ์ไม่มีเอกสาร {document}")

    cells = []
    for column in their_header:
        if column not in our_header:
            continue
        left = theirs[key].get(column, "")
        right = mine[key].get(column, "")
        cells.append(Cell(column, left.strip(), right.strip(),
                          compare_cell(column, left, right)))
    return sorted(cells, key=lambda c: (ORDER[c.verdict], c.column))


def score(cells: list[Cell]) -> tuple[float, int]:
    """(credit, cells counted) — the same arithmetic the whole-run table uses."""
    counted = [c for c in cells if c.counted and c.verdict != "blank"]
    credit = sum(1 if c.verdict == "exact" else 0.5 if c.verdict == "partial" else 0
                 for c in counted)
    return credit, len(counted)


def report_rows(expected: Path, ours: Path, documents: list[str], *,
                width: int = 78, show_all: bool = False) -> str:
    """One block per document, worst cell first."""
    lines: list[str] = []
    for document in documents:
        try:
            cells = compare_row(expected, ours, document)
        except KeyError as exc:
            lines += [f"=== {document}", f"  {exc}", ""]
            continue

        credit, counted = score(cells)
        share = f"{credit / counted:.0%}" if counted else "—"
        wrong = sum(1 for c in cells if c.verdict == "wrong" and c.counted)
        partial = sum(1 for c in cells if c.verdict == "partial" and c.counted)
        lines.append(
            f"=== {document}  ได้ {share}  ({credit:g}/{counted} ช่องที่นับ"
            f" · ผิด {wrong} · บางส่วน {partial})"
        )

        shown = [c for c in cells if show_all or c.verdict in ("wrong", "partial")]
        if not shown:
            lines += ["  ตรงทุกช่องที่นับ", ""]
            continue

        for cell in shown:
            note = f"  [{cell.note}]" if cell.note else ""
            lines.append(f"  {MARK[cell.verdict]} {cell.column.strip()}{note}")
            lines.append(f"      เขา: {_short(cell.theirs, width)}")
            lines.append(f"      เรา: {_short(cell.ours, width)}")
        lines.append("")
    return "\n".join(lines)


def _short(value: str, width: int) -> str:
    text = " ".join((value or "").split())
    if not text:
        return "—"
    return text if len(text) <= width else text[:width] + "…"


def worst(expected: Path, ours: Path, limit: int = 5) -> list[tuple[str, float]]:
    """The documents furthest from the reference, worst first."""
    _, theirs = _rows(expected)
    _, mine = _rows(ours)
    ranked = []
    for document in sorted(set(theirs) & set(mine)):
        credit, counted = score(compare_row(expected, ours, document))
        if counted:
            ranked.append((document, credit / counted))
    return sorted(ranked, key=lambda row: row[1])[:limit]
