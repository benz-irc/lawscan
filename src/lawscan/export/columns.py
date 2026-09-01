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
    # The operator's sheet carries three columns about what an instrument does
    # to other instruments. Nothing fills them yet; they are written out empty
    # so every column after them lands where the sheet expects it — Core
    # Business Laws at AF, Support at AG. A shifted column is worse than a
    # blank one: it reads as an answer to the wrong question.
    "ถูกยกเลิกโดยกฎหมายชื่อ",
    "ยกเลิกกฎหมายอื่นทั้งฉบับ",
    "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
    "วันที่ประกาศ",
    "เดือนที่ประกาศ",
    "ปีที่ประกาศ",
    "วันทีมีผลใช้บังคับ",
    "วันที่สิ้นผล",
    "ประเภทกฎหมาย",
    "กฎหมายแม่",
    "กฎหมายที่อ้างถึง",
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
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
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
    "ข้อความแจ้งเตือน (Smart Prompt)",
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
        "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
        "ลิงค์เอกสารที่แนะนำ",
        "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
        # V16 4.3 and 5.4 say so in as many words: "หากในเอกสารไม่มีคำสั่ง
        # ยกเลิกกฎหมายฉบับอื่นทั้งฉบับ ให้ใส่ -". These were blank because the
        # schema offers null as the way to say "nothing found" and the model
        # used it, which is the right answer to the question this code asked
        # and the wrong shape for the sheet. The dash is added here rather
        # than demanded of the model, because it is a fact about the format,
        # not about the law.
        "ยกเลิกกฎหมายอื่นทั้งฉบับ",
        "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
        # V17 13: "หากสแกนทั้งฉบับแล้วไม่มีการอ้างถึงกฎหมายหรือมติใดๆ ที่เข้า
        # เงื่อนไขเลย ให้ตอบว่า -". Most instruments cite nothing beyond the act
        # they are made under, and that one is excluded by the rule itself.
        "กฎหมายที่อ้างถึง",
        # Same reasoning, other direction: V16 asks for a sentence of standing
        # doubt, their sheet writes a dash. Measured against their sheet.
        "ถูกยกเลิกโดยกฎหมายชื่อ",
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


#: The corpus is numbered from here: document 100001 is the operator's row 1
#: and 103424 is their row 3424, unbroken across all 3,424 of them.
#:
#: ``ลำดับ`` therefore belongs to the document and not to the run. Numbering by
#: position in the output looked identical on a full pass and was wrong on
#: every partial one: a twelve-document rescan numbered them 1–12 against a
#: reference that numbers them by their place in the corpus, losing one exact
#: cell per document. That turned a +8 result into −4 and nearly buried it.
FIRST_DOCUMENT = 100_000


#: Past this the number is not a place in the operator's sheet. Their file
#: runs to 3,424 documents; the ceiling is loose enough to outlast it.
_CORPUS_CEILING = 100_000


def _base_and_suffix(document: str) -> tuple[int, int] | None:
    """A file name as (document number, annexe number), or None.

    An annexe is numbered off the sheet it belongs to: the operator's file
    puts ``1000012.1`` between ``100012`` and ``100013`` and numbers it
    ``12.1``. The leading digits carry one more zero than the document they
    belong to — the file is named that way and the sheet agrees with itself,
    so the extra digit is read as the typo it is rather than propagated.
    """
    number, _, suffix = (document or "").strip().partition(".")
    if not number.isdigit() or (suffix and not suffix.isdigit()):
        return None
    # ``1000012`` is a document of this corpus with a digit too many — the
    # sheet numbers it ``12.1`` and files it between 100012 and 100013, so the
    # number it means is 100012. Rather than encode that one typo, a name too
    # long to be a document number is tried with each single digit removed,
    # and the first result that is a real place in the corpus is the one meant.
    # Nothing shorter or already valid is touched.
    place = int(number) - FIRST_DOCUMENT
    if not 0 < place < _CORPUS_CEILING and len(number) > 6:
        for cut in range(len(number)):
            candidate = int(number[:cut] + number[cut + 1:])
            if 0 < candidate - FIRST_DOCUMENT < _CORPUS_CEILING:
                place = candidate - FIRST_DOCUMENT
                break
    return (place, int(suffix or 0)) if 0 < place < _CORPUS_CEILING else None


#: The operator's own corpus is named 100001 upwards and runs to 103424, so
#: the number carries the place and a partial rescan of it must keep that
#: number rather than count from one. A corpus named otherwise — the 2569 set
#: is named with real Gazette numbers, 91099 to 125393 — carries no place in
#: its names, and the same arithmetic wrote 830, 22839 and a negative where the
#: operator's sheet numbers the rows 1 to 250. Which corpus this is has to be
#: decided over the whole run, not one document at a time: 100830 falls inside
#: the band and still is not the 830th of anything.
_LAST_PLACE = 3_424


def numbered_by_name(documents: list[str]) -> bool:
    """Whether these names carry their own place, as the operator's do."""
    places = [_base_and_suffix(name) for name in documents]
    return bool(places) and all(
        found is not None and 0 < found[0] <= _LAST_PLACE for found in places
    )


def place_in_corpus(document: str, position: int, by_name: bool = True) -> str:
    """The row's number: from the name where the names carry one, else the place.

    The annexe suffix always comes from the name — 1000012.1 is filed behind
    100012 and the sheet numbers it ``12.1``.
    """
    found = _base_and_suffix(document)
    if found is None:
        return str(position)
    place, annexe = found
    head = place if by_name else position
    return f"{head}.{annexe}" if annexe else str(head)


def in_corpus_order(document: str) -> tuple[int, int, str]:
    """Sort key: the sheet's own order, annexes behind the sheet they follow."""
    found = _base_and_suffix(document)
    if found is None:
        return (1 << 30, 0, document or "")
    return (*found, document or "")


def to_dict(row: Row, order: int, by_name: bool = True) -> dict[str, str]:
    """One row as the export writes it."""
    out: dict[str, str] = {}
    for column in COLUMNS:
        value = row.value(column)
        if column == "ชื่อกฎหมาย" and value:
            value = _spaced(value)
        if not value and column in NONE_IS_AN_ANSWER:
            value = NONE
        out[column] = value
    out["ลำดับ"] = place_in_corpus(row.document, order, by_name)
    return out


def write_csv(rows: list[Row], path: Path) -> None:
    """Rows to CSV, sorted by document number, every cell text.

    ``utf-8-sig`` because the operator opens this in Excel, and Excel reads a
    UTF-8 file without a BOM as Latin-1 and turns every Thai character into
    mojibake.
    """
    ordered = sorted(rows, key=lambda r: in_corpus_order(r.document))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS), extrasaction="ignore")
        writer.writeheader()
        # An annexe does not take a number of its own: the operator files
        # 1000012.1 behind 100012 and writes 12.1, so the counter stands still
        # while the annexe is written and moves on at the next document.
        by_name = numbered_by_name([row.document for row in ordered])
        # An annexe takes no number of its own: the operator files 1000012.1
        # behind 100012 and writes 12.1, so the counter stands still while the
        # annexe is written and moves on at the next document.
        place = 0
        for row in ordered:
            found = _base_and_suffix(row.document)
            if not (found and found[1]):
                place += 1
            writer.writerow(to_dict(row, max(place, 1), by_name))
