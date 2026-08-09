"""Settle a disagreement by going back to the document.

``verdict.better`` compares two cells to each other and stops where the shapes
run out, which leaves the rows that most need an answer marked "read it
yourself". This reads it. The text of every document is already on disk beside
its answers, so the evidence for most of these is a string search away — and a
search that comes back empty is itself evidence, because a cell naming a thing
the document never says is a cell somebody invented.

Two kinds of question get settled here. Some columns copy something printed in
the document — the Gazette volume, the title — and for those the document is
simply right and whoever matches it wins. The rest are summaries, and no search
proves a summary; what it can show is which side's words are in the document at
all, which is worth saying and is not the same as saying who is correct.
"""

import re

from lawscan.diff import items, norm

#: Folding the extraction's own damage, so a search for ``ก่อสร้าง`` still
#: finds the ``ก่อสรำง`` that OCR left in the text. The corruption swallows the
#: tone mark along with the vowel — ``้า`` comes back as ``ำ`` — so both have to
#: go for the two spellings to meet. That makes the search looser than Thai
#: really is, and it is the right trade here: this only ever counts whether a
#: word is present, and a count that misses every damaged document would say
#: those documents source nothing.
_TONE = re.compile(r"[่-๋]")

#: The Gazette's own line: volume, issue, part. Printed on every page, so a
#: cell claiming a different one is checkable without judgement.
_GAZETTE = re.compile(r"เล่ม\s*([\d๐-๙]+)\s*ตอน(ที่|พิเศษ)\s*([\d๐-๙]+)\s*([กงข])")

OURS = "ของเราตรงกับเอกสาร"
THEIRS = "เฉลยตรงกับเอกสาร"
NEITHER = "ไม่ตรงกับเอกสารทั้งคู่"
GROUNDED = "ของเราอ้างคำที่มีในเอกสารมากกว่า"
THEIRS_GROUNDED = "เฉลยอ้างคำที่มีในเอกสารมากกว่า"
EVEN = "ทั้งคู่อ้างคำที่มีในเอกสารพอกัน"

#: Neither cell uses a word the document contains. Kept apart from ``EVEN``
#: because they read as opposites to a reviewer: one says both are fine, the
#: other says nothing here can be defended from the document.
UNGROUNDED = "ไม่มีฝั่งไหนใช้คำจากเอกสารเลย"


def _folded(value: str) -> str:
    return _TONE.sub("", norm(value)).replace("ำ", "า").replace(" ", "")


def _gazette_line(text: str) -> str:
    """``เล่ม 137 ตอนที่ 11 ก`` as the document prints it, or ""."""
    found = _GAZETTE.search(text or "")
    if not found:
        return ""
    volume, kind, number, part = found.groups()
    return f"เล่ม {volume} ตอน{kind} {number} {part}"


#: Below this length a match is not evidence. A two-character item is a
#: substring of half the document by accident — ``ก`` is inside ``ทุก`` — and
#: counting those would report grounding for cells that have none.
_TOO_SHORT = 3


def _present(value: str, text: str) -> int:
    """How many of a cell's items appear in the document, spelling folded."""
    haystack = _folded(text)
    return sum(
        1 for part in items(value)
        if len(part) >= _TOO_SHORT and _folded(part) in haystack
    )


def source_line(theirs: str, ours: str, text: str) -> tuple[str, str]:
    """Who matches the Gazette line the document actually carries."""
    printed = _gazette_line(text)
    if not printed:
        return "", ""
    key = _folded(printed)
    in_theirs, in_ours = key in _folded(theirs), key in _folded(ours)
    if in_ours and not in_theirs:
        return OURS, f"เอกสารพิมพ์ว่า {printed} ตรงกับของเรา เฉลยเขียนต่างไป"
    if in_theirs and not in_ours:
        return THEIRS, f"เอกสารพิมพ์ว่า {printed} ตรงกับเฉลย ของเราเขียนต่างไป"
    if in_theirs and in_ours:
        return "", f"เอกสารพิมพ์ว่า {printed} ตรงกันทั้งคู่ ต่างที่ส่วนอื่น"
    return NEITHER, f"เอกสารพิมพ์ว่า {printed} ซึ่งไม่ตรงกับฝั่งไหนเลย"


def grounding(theirs: str, ours: str, text: str) -> tuple[str, str]:
    """Which side's words the document actually contains.

    Not a proof of correctness — a summary can be right in words the document
    never uses. It is a proof of *sourcing*, and a cell whose every term is
    absent from the document is one nobody can defend from the document.
    """
    mine, yours = _present(ours, text), _present(theirs, text)
    total_mine, total_yours = len(items(ours)), len(items(theirs))
    detail = (f"คำของเราพบในเอกสาร {mine}/{total_mine} รายการ · "
              f"ของเฉลยพบ {yours}/{total_yours} รายการ")
    if mine > yours:
        return GROUNDED, detail
    if yours > mine:
        return THEIRS_GROUNDED, detail
    if mine == 0:
        return UNGROUNDED, detail + " — ทั้งสองฝั่งเรียบเรียงเอง ไม่ได้ยกคำจากตัวบท"
    return EVEN, detail
