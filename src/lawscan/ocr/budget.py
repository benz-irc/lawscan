"""How much of a document one question gets, and which parts of it.

Every question was sent the whole document and the whole document is the wrong
unit. Measured over 91: thirteen run past 20,000 characters and hold 56% of all
the text in the corpus, and nothing reads most of it — the longest is a
138,000-character act of which 120,000 is schedules.

The cut is by position, not by parsing. Splitting on structure was tried first
and got it wrong twice: a citation of another instrument's schedule emptied a
whole act's body, and "ให้ไว้ ณ วันที่" turned out to sit at the *top* of an act
and the bottom of a notification. Guessing at the shape of a document nobody
has read is how content disappears quietly. Head plus tail keeps the parts that
are structurally guaranteed — a Thai instrument states its subject in the first
paragraph and its commencement in the last — and cannot empty anything.

One part is worth finding by name: the drafter's own statement of why the
instrument exists, printed at the end of 36 of the 91. It is an official
summary in the words of the people who wrote the law, and it is always kept.
"""

from __future__ import annotations

import re

#: "หมายเหตุ :- เหตุผลในการประกาศใช้…"
_REASON = re.compile(r"หมายเหตุ\s*:?-?\s*เหตุผลในการ|เหตุผลในการประกาศใช้")

#: The reason paragraph ends where the next page's running header begins.
_REASON_END = re.compile(r"\n\s*(?:หน้า\s*\d|เล่ม\s)")
_REASON_MAX = 1_500

#: Marks the join, so a reader of the saved text can see something was cut and
#: the model is not told a truncated document is a whole one.
GAP = "\n\n[…ตัดเนื้อหาส่วนกลางออก…]\n\n"


def reason(text: str) -> str:
    """The drafter's own reason for the instrument, or nothing."""
    found = _REASON.search(text)
    if not found:
        return ""
    window = text[found.start() : found.start() + _REASON_MAX]
    ends = _REASON_END.search(window)
    return (window[: ends.start()] if ends else window).strip()


def fit(text: str, *, head: int | None, tail: int = 0) -> str:
    """The opening, the closing, and the reason — within a budget.

    ``head=None`` means no limit, which is what a short document gets anyway:
    nothing is cut unless the document is longer than the budget allows.
    """
    if head is None or len(text) <= head + tail:
        return text

    why = reason(text)
    kept = text[:head]
    if tail:
        kept = f"{kept}{GAP}{text[-tail:]}"
    if why and why not in kept:
        kept = f"{kept}\n\n{why}"
    return kept
