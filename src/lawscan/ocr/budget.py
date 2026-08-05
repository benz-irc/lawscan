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

#: What a Thai instrument calls the thing you have to obtain or hand in.
#:
#: These name the answers to the ใบอนุญาต and แบบฟอร์ม columns, and they live
#: in the operative sections — which is the middle, which is what a head-plus-
#: tail budget throws away. One document names its form in ข้อ 31, at character
#: 18,962 of 24,892: past the head, before the tail, and the only place in the
#: document it appears.
_NAMED_THING = re.compile(
    r"ใบอนุญาต|ใบรับแจ้ง|ใบสำคัญ|ใบรับรอง|ใบทะเบียน|หนังสือรับรอง|หนังสือแสดง"
    r"|หนังสืออนุญาต|คำขออนุญาต|คำขอรับ|แบบคำขอ|แบบรายงาน|แบบแจ้ง|แบบฟอร์ม"
    r"|เลขทะเบียน|เลขสารบบ|ขึ้นทะเบียน|จดทะเบียน|แบบ\s*[ก-ฮ]{1,3}\s*\."
)

#: Enough either side to carry the whole name and what it is for.
_LEAD, _TRAIL = 120, 260

#: What the rescued sentences may cost. Measured over 91 documents: 1,500
#: characters recovers the form name for 0.8% more text, and raising it to 5,000
#: costs 4.5% and recovers nothing further.
_NAMED_BUDGET = 1_500

#: Says what the block is, so the model reads it as evidence from elsewhere in
#: the document rather than as the passage that follows the cut.
_NAMED_HEADING = "\n\n[ข้อความอื่นในเอกสารที่กล่าวถึงใบอนุญาตหรือแบบฟอร์ม]\n"


def reason(text: str) -> str:
    """The drafter's own reason for the instrument, or nothing."""
    found = _REASON.search(text)
    if not found:
        return ""
    window = text[found.start() : found.start() + _REASON_MAX]
    ends = _REASON_END.search(window)
    return (window[: ends.start()] if ends else window).strip()


def named_things(text: str, budget: int = _NAMED_BUDGET) -> str:
    """Passages that name a licence or a form, wherever they sit."""
    spans: list[list[int]] = []
    for found in _NAMED_THING.finditer(text):
        start = max(0, found.start() - _LEAD)
        end = min(len(text), found.end() + _TRAIL)
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])

    kept: list[str] = []
    used = 0
    for start, end in spans:
        piece = text[start:end]
        if used + len(piece) > budget:
            break
        kept.append(piece)
        used += len(piece)
    return "\n…\n".join(kept)


def fit(text: str, *, head: int | None, tail: int = 0) -> str:
    """The opening, the closing, the reason, and the named things.

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

    rescued = [p for p in named_things(text).split("\n…\n") if p and p not in kept]
    if rescued:
        kept = f"{kept}{_NAMED_HEADING}" + "\n…\n".join(rescued)
    return kept
