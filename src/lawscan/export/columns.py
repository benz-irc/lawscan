"""The 33 columns, in the operator's order, spelled their way.

Copied from their sheet character for character — including the trailing spaces
on three of the headers. They look like typos and they are not ours to fix: a
column that silently changes name stops lining up in a diff, and every column
after it then reads as wrong.

``NONE_IS_AN_ANSWER`` is the other half of matching their file. A blank cell in
ours was indistinguishable from a question nobody had reached; theirs never has
that problem because it writes "-". Only the columns where absence is a fact
about the law get the dash — everywhere else a blank still means the system has
nothing to say, and claiming otherwise would be a lie in a spreadsheet.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lawscan.merge import Row

COLUMNS: tuple[str, ...] = (
    "ลำดับ",
    "ชื่อไฟล์ ",
    "ชื่อกฎหมาย",
    "ลิงค์PDF",
    "สถานะกฎหมาย",
    "วันที่ประกาศ",
    "เดือนที่ประกาศ",
    "ปีที่ประกาศ",
    "วันทีมีผลใช้บังคับ",
    "วันที่สิ้นผล",
    "ประเภทกฎหมาย",
    "กฎหมายแม่",
    "หน่วยงานกำกับ",
    "องค์กรปกครองส่วนท้องถิ่น",
    "อำเภอ",
    "จังหวัด",
    "คำอธิบายและสรุปสาระสำคัญ",
    "คำแนะนำสิ่งที่ต้องทำ ",
    "ระดับวามเสี่ยง ",
    "บทลงโทษ",
    "ใบอนุญาต",
    "ข้อมูลแหล่งที่มา",
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
    "ลิงค์เอกสารที่แนะนำ",
    "กลุ่มเป้าหมาย",
    "Activity_Tag",
    "Product_Group_Tag",
    "Legal_Keyword_Tag",
    "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
    "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
    "AI ให้เหตุผล",
    "ระดับความมั่นใจ",
    "หมายเหตุ",
)

NONE = "-"

#: Columns where emptiness is a fact about the law rather than a gap in the
#: record. A regulation with no expiry date has one — none.
NONE_IS_AN_ANSWER: frozenset[str] = frozenset(
    {
        "วันที่สิ้นผล",
        "องค์กรปกครองส่วนท้องถิ่น",
        "อำเภอ",
        "จังหวัด",
        "ใบอนุญาต",
        "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
        "ลิงค์เอกสารที่แนะนำ",
        "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
    }
)

#: Thai legal titles are written with a space before these words, and the
#: Gazette's own text layer routinely closes it up.
_TITLE_BREAKS = ("ว่าด้วย", "เรื่อง")


def _spaced(title: str) -> str:
    import re

    for word in _TITLE_BREAKS:
        title = re.sub(rf"(?<=\S)(?<! ){re.escape(word)}", f" {word}", title)
    return title


def to_dict(row: Row, order: int) -> dict[str, str]:
    """One row as the export writes it."""
    out: dict[str, str] = {}
    for column in COLUMNS:
        value = row.value(column)
        if column == "ชื่อกฎหมาย" and value:
            value = _spaced(value)
        if not value and column in NONE_IS_AN_ANSWER:
            value = NONE
        out[column] = value
    out["ลำดับ"] = str(order)
    return out


def write_csv(rows: list[Row], path: Path) -> None:
    """Rows to CSV, sorted by document number, every cell text.

    ``utf-8-sig`` because the operator opens this in Excel, and Excel reads a
    UTF-8 file without a BOM as Latin-1 and turns every Thai character into
    mojibake.
    """
    ordered = sorted(rows, key=lambda r: r.document)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for position, row in enumerate(ordered, start=1):
            writer.writerow(to_dict(row, position))
