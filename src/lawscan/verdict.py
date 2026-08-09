"""Which side of a mismatch is the better cell, where that can be told.

The comparison says two cells disagree. It does not say who is wrong, and for
most of the columns here nobody can say that without reading the document. But
the *shape* of a disagreement is readable, and the operator's own reading of
their file is that ours is usually the fuller cell — except in citations,
where a missing ``วรรคสอง`` or ``(3)`` makes theirs the one to keep.

So this labels shape, and says so: ``ละเอียดกว่า`` is a claim about how much a
cell contains, not about whether it is true. A longer wrong answer is longer.
The one place it does claim accuracy is the citation case, because there the
two cells name the same law and one of them carries an address the other
dropped — and an address is either there or it is not.
"""

import json
import re
from functools import cache
from pathlib import Path

from lawscan.diff import CITED_COLUMNS, address, addresses, items, norm

__all__ = ["CITED_COLUMNS", "better", "why"]

#: ``ำ`` where ``า`` belongs, with or without a tone mark stranded on it. The
#: extraction produces this in a minority of words and cannot be repaired in
#: general — genuine ``ำ`` words sit next to the damaged ones — but two cells
#: that agree once it is folded are two spellings of one answer, not two
#: answers. Spacing goes the same way: the operator's file breaks a long title
#: where the Gazette's line breaks fall, and ours does not.
_OCR_VOWEL = re.compile(r"[่-๋]?ำ")

SAME_TEXT = "ข้อความเดียวกัน (OCR/เว้นวรรคต่าง)"
OURS_FULLER = "ของเราละเอียดกว่า"
THEIRS_FULLER = "เฉลยละเอียดกว่า"
THEIRS_CITATION = "เฉลยแม่นกว่า (เลขมาตรา/วรรค/วงเล็บ)"
OURS_CITATION = "ของเราแม่นกว่า (เลขมาตรา/วรรค/วงเล็บ)"
OURS_ONLY = "เรามี เฉลยเว้นว่าง"
THEIRS_ONLY = "เฉลยมี เราเว้นว่าง"
OVERLAP = "ตรงบางส่วน ที่เหลือต่างกัน"
UNDECIDED = "ต่างกัน ต้องอ่านเอกสารเอง"


def _folded(value: str) -> str:
    """A normalised value with the extraction's own damage taken out."""
    return _OCR_VOWEL.sub("า", value).replace(" ", "")


def better(column: str, theirs: str, ours: str) -> str:
    """A label for one disagreeing cell.

    The ladder is ordered by how much it claims. Emptiness first, because a
    missing cell is not a disagreement about content. Then citations, the one
    case where the operator has said which side wins. Then containment, which
    is a fact about the strings. Anything left is left undecided rather than
    guessed — a wrong label is worse than none, because a label is what stops
    someone looking.
    """
    left, right = norm(theirs), norm(ours)
    if left == right:
        # Includes both blank. Two cells that agree have no side to take.
        return ""
    if not left:
        return OURS_ONLY
    if not right:
        return THEIRS_ONLY

    # Two spellings of one answer. Checked before anything that compares
    # content, because everything below would read a keystroke as a claim.
    if _folded(left) == _folded(right):
        return SAME_TEXT

    # Same law, different address. This is the operator's stated exception and
    # the only place the label claims one side is more accurate.
    if column.strip() in CITED_COLUMNS and address(theirs) == address(ours):
        # Same law, so the disagreement is the address. Whoever carries the
        # finer one carries information the other dropped.
        return (THEIRS_CITATION if len(addresses(theirs)) >= len(addresses(ours))
                else OURS_CITATION)

    mine, yours = items(ours), items(theirs)
    if yours < mine:
        return OURS_FULLER
    if mine < yours:
        return THEIRS_FULLER
    if left in right:
        return OURS_FULLER
    if right in left:
        return THEIRS_FULLER
    if mine & yours:
        return OVERLAP
    return UNDECIDED


#: A law being cited where a form was asked for. ``summary.md`` tells the
#: model in as many words that a law is not a manual, so a blank here next to
#: a reference cell full of Acts is the instruction working — a different
#: thing entirely from the model failing to find a form that was there.
_A_LAW = re.compile(r"พระราชบัญญัติ|พ\.ร\.บ|พระราชกฤษฎีกา|พระราชกำหนด|กฎกระทรวง")

#: Where a blank is the prompt doing what it was told, keyed by column. Each
#: entry is a test on the *reference* cell and the instruction to quote: the
#: excuse is only offered when their cell holds the thing ours excludes.
_BLANK_BY_DESIGN = {
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ": (
        lambda theirs: bool(_A_LAW.search(theirs)),
        "prompt สั่งว่า กฎหมายไม่ใช่คู่มือ — ชื่อพระราชบัญญัติหรือกฎกระทรวงห้ามลงช่องนี้",
    ),
    "ลิงค์เอกสารที่แนะนำ": (
        lambda theirs: "http" not in theirs.lower(),
        "prompt สั่งให้ใส่ URL เฉพาะที่เอกสารพิมพ์ไว้จริง",
    ),
    "กฎหมายเฉพาะธุรกิจ (Core Business Laws)": (
        lambda theirs: True,
        "prompt สั่งว่า core ว่างคือคำตอบที่พบบ่อยที่สุด ใส่เมื่อมีผู้ประกอบการต้องทำอะไรเพิ่มจริงเท่านั้น",
    ),
    "บทลงโทษ": (
        lambda theirs: True,
        "กฎเติมช่องนี้เฉพาะเอกสารที่มีบทลงโทษของตัวเอง หรือเชื่อมโยงไปกฎหมายแม่ได้",
    ),
}

#: A business-category code on its own. ``เรากรอก BC6`` repeats what the
#: reader can already see in the cell beside it; the name is what tells them
#: whether the code is defensible.
_CODE = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b")

_TAXONOMY = Path(__file__).resolve().parents[2] / "data" / "taxonomy.json"


@cache
def _code_names() -> dict[str, str]:
    if not _TAXONOMY.exists():
        return {}
    groups = json.loads(_TAXONOMY.read_text(encoding="utf-8")).get("groups", [])
    return {c["code"]: c["name"] for g in groups for c in g.get("codes", [])}


def _spelled_out(value: str) -> str:
    """Codes with their names, so a reason can be judged without a lookup."""
    names = _code_names()
    return _CODE.sub(
        lambda m: f"{m.group(1)} ({names[m.group(1)]})" if m.group(1) in names else m.group(1),
        value,
    )


def _quoted(value: str, limit: int) -> str:
    """A cell's text, marked when it had to be cut."""
    text = _spelled_out(" ".join((value or "").split()))
    return text if len(text) <= limit else text[:limit] + "…"


#: How many differing items to name before the sentence stops being readable.
#: Three is enough to recognise the disagreement; the cells themselves are in
#: the next column for anyone who wants all of it.
_SHOWN = 3


def _listed(values: set[str], original: str) -> str:
    """Differing items in the words the cell actually used.

    ``items`` returns normalised text, which is right for comparing and wrong
    for reading back: it strips the brackets and case that make a name look
    like itself. This maps each one to the phrase it came from.
    """
    spoken = {norm(part): part.strip() for part in (original or "").split(",")}
    shown = [spoken.get(v, v) for v in sorted(values)]
    if len(shown) > _SHOWN:
        return ", ".join(shown[:_SHOWN]) + f" และอีก {len(shown) - _SHOWN} รายการ"
    return ", ".join(shown)


def _blank_reason(column: str, theirs: str, origin: str) -> list[str]:
    """Why our cell is empty, as far as the record can say.

    Three separable things, and the fix differs for each: what the reference
    put there, who on our side produced the blank, and whether an instruction
    of ours asked for it. Anything not on the record is left unsaid.
    """
    said = [f"เราเว้นว่าง เฉลยระบุ {_quoted(theirs, 70)}"]
    if origin.startswith("llm"):
        said.append(f"โมเดลตอบว่าไม่มี ({origin.split(':')[-1]})")
    elif origin.startswith("rule"):
        said.append("กฎอ่านเอกสารแล้วไม่พบ")

    rule = _BLANK_BY_DESIGN.get(column.strip())
    if rule and rule[0](theirs):
        said.append(rule[1])
    return said


def why(column: str, theirs: str, ours: str, *, origin: str = "") -> str:
    """The evidence behind :func:`better`, in the words of the two cells.

    Every branch here names something a reader can check against the columns
    beside it. Where the evidence is only "these do not overlap", it says that
    rather than dressing it up — an explanation that explains nothing is how a
    reviewer learns to stop reading the column.
    """
    label = better(column, theirs, ours)
    if not label:
        return ""

    left, right = norm(theirs), norm(ours)
    if label == OURS_ONLY:
        return f"เฉลยเว้นว่าง เรากรอก {_quoted(ours, 80)}"
    if label == THEIRS_ONLY:
        return " · ".join(_blank_reason(column, theirs, origin))

    if label == SAME_TEXT:
        vowel = _OCR_VOWEL.sub("า", left) != left or _OCR_VOWEL.sub("า", right) != right
        if vowel and left.replace(" ", "") != right.replace(" ", ""):
            return "ข้อความเดียวกัน ต่างที่สระ ำ/า ซึ่ง OCR อ่านเพี้ยน ไม่ใช่คนละคำตอบ"
        return "ข้อความเดียวกัน ต่างแค่เว้นวรรค"

    if label in (THEIRS_CITATION, OURS_CITATION):
        missing = addresses(theirs) - addresses(ours)
        extra = addresses(ours) - addresses(theirs)
        if missing and extra:
            # Each side names something the other does not. Neither is the
            # fuller citation, so calling one of them more precise reads as a
            # verdict where there is only a disagreement about where to look.
            return (f"อ้างกฎหมายฉบับเดียวกัน แต่ชี้คนละที่ — เฉลยระบุ "
                    f"{', '.join(sorted(missing))} เราระบุ {', '.join(sorted(extra))} "
                    "ต้องเปิดตัวบทดูว่าอันไหนคือฐานอำนาจจริง")
        if label == THEIRS_CITATION and missing:
            return (f"อ้างกฎหมายฉบับเดียวกัน แต่เฉลยระบุ {', '.join(sorted(missing))} "
                    "ที่เราไม่ได้เขียน — ที่อยู่ในกฎหมายมีก็คือมี")
        if label == OURS_CITATION and extra:
            return (f"อ้างกฎหมายฉบับเดียวกัน เราระบุ {', '.join(sorted(extra))} "
                    "ที่เฉลยไม่ได้เขียน — ชี้จุดในกฎหมายได้ละเอียดกว่า")
        return "อ้างกฎหมายฉบับเดียวกัน ต่างที่วิธีเขียนเลขมาตรา (เลขไทย/อารบิก)"

    mine, yours = items(ours), items(theirs)
    if label == OURS_FULLER:
        extra = mine - yours
        if extra:
            return f"ของเรามีครบทุกรายการของเฉลย และเพิ่ม {_listed(extra, ours)}"
        return "ข้อความของเราคลุมของเฉลยทั้งหมด และยาวกว่า"
    if label == THEIRS_FULLER:
        missing = yours - mine
        if missing:
            return f"เราขาด {_listed(missing, theirs)} ที่เฉลยระบุไว้"
        return "ข้อความของเฉลยคลุมของเราทั้งหมด และยาวกว่า"

    if label == OVERLAP:
        return (f"ตรงกัน {len(mine & yours)} รายการ · เฉลยมี {_listed(yours - mine, theirs)} "
                f"ที่เราไม่มี · เราเพิ่ม {_listed(mine - yours, ours)}")

    return "ไม่มีรายการใดซ้อนกันเลย ตัดสินจากตัวเลขไม่ได้ ต้องเปิดเอกสารอ่าน"
