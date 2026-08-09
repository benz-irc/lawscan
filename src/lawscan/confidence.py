"""How much to trust one row, decided by evidence rather than by asking.

The model was asked for a confidence figure and returned 0.8 or higher on all
91 documents — including the one where twelve of twenty-three pages were
pictures nothing had read. A number that never varies carries no information,
and a self-report from the thing being judged was never going to.

So confidence is computed here, from facts that can be checked: what the reader
could not read, what the rules and the model disagreed about, what a value
looks like next to the values that column is supposed to hold, and whether the
dates make sense against each other.

Each rule names one specific way a row goes wrong, states what it costs, and
says so in words a reviewer can act on. The point is not the number. The point
is the sentence next to it — a row marked 0.55 with "no Gazette header, so the
publication date came from the model" tells someone what to open and what to
look at, which "0.55" alone does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lawscan.merge import Row
    from lawscan.ocr.read import Document

#: Below this a row should be looked at before it is used.
REVIEW_BELOW = 0.80


@dataclass(frozen=True, slots=True)
class Finding:
    """One reason to trust a row less, and what it costs."""

    rule: str
    penalty: float
    why: str
    columns: tuple[str, ...] = ()


@dataclass
class Verdict:
    findings: list[Finding] = field(default_factory=list)

    @property
    def score(self) -> float:
        """1.0 less what the findings cost, floored at 0.1.

        Never zero. A row this program produced is never worthless — it has a
        document number and whatever the rules read — and a zero would invite
        throwing away work that is mostly right.
        """
        return max(0.1, round(1.0 - sum(f.penalty for f in self.findings), 2))

    @property
    def needs_review(self) -> bool:
        return self.score < REVIEW_BELOW

    @property
    def note(self) -> str:
        return " · ".join(f.why for f in self.findings)

    def touching(self, column: str) -> list[Finding]:
        return [f for f in self.findings if column in f.columns]


# --------------------------------------------------------------- what we read

def _unread_pages(document: Document, row: Row) -> Finding | None:
    """Pages whose content is a picture nothing could read.

    Weighted by how much of the document went missing: two pages of a
    six-page instrument is a different problem from one page of eighty.
    """
    lost = document.unread_pages
    if not lost:
        return None
    share = len(lost) / max(1, len(document.pages))
    return Finding(
        "unread-pages",
        min(0.45, 0.10 + share * 0.5),
        f"อ่านไม่ได้ {len(lost)}/{len(document.pages)} หน้า (เป็นภาพ: "
        f"{', '.join(str(n) for n in lost)})",
        ("คำอธิบายและสรุปสาระสำคัญ", "ใบอนุญาต", "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ"),
    )


def _mostly_recognised(document: Document, row: Row) -> Finding | None:
    """A document read by OCR rather than from a text layer.

    Recognition is good but not perfect, and Thai tone marks are the first
    thing it loses — which is exactly what the rules read dates and section
    numbers from.
    """
    if not document.pages:
        return None
    share = document.scanned_pages / len(document.pages)
    if share < 0.5:
        return None
    return Finding(
        "recognised-not-extracted",
        0.15,
        f"{document.scanned_pages}/{len(document.pages)} หน้ามาจาก OCR ไม่ใช่ชั้นข้อความ",
    )


def _barely_any_text(document: Document, row: Row) -> Finding | None:
    """Too little text to have answered anything from."""
    length = len(document.text())
    if length >= 400:
        return None
    return Finding(
        "almost-no-text", 0.35, f"อ่านข้อความได้เพียง {length} ตัวอักษร"
    )


# ------------------------------------------------------- what the rules found

def _no_gazette_header(document: Document, row: Row) -> Finding | None:
    """No running header, so the dates did not come from one.

    The publication date is the anchor for the commencement date and both are
    printed in the header. Without it the model answered from a date written
    in a sentence — usually the signing date, which is weeks earlier.
    """
    if row.sources().get("วันที่ประกาศ") == "rule":
        return None
    return Finding(
        "no-gazette-header",
        0.20,
        "ไม่พบหัวราชกิจจานุเบกษา วันที่จึงไม่ได้มาจากกฎ",
        ("วันที่ประกาศ", "เดือนที่ประกาศ", "ปีที่ประกาศ", "วันทีมีผลใช้บังคับ",
         "ข้อมูลแหล่งที่มา"),
    )


def _no_law_type(document: Document, row: Row) -> Finding | None:
    """The document never names its own kind.

    Every ordinary Thai instrument opens by saying what it is. One that does
    not is either damaged, an attachment, or something this program has not
    seen before — and the law type decides how three other rules behave.
    """
    if row.value("ประเภทกฎหมาย"):
        return None
    return Finding(
        "no-law-type", 0.25, "เอกสารไม่ได้ระบุว่าตัวเองเป็นกฎหมายประเภทใด",
        ("ประเภทกฎหมาย",),
    )


# ----------------------------------------------------- do the answers hold up

_THAI_TITLE = re.compile(r"^(?:นาย|นาง|นางสาว|ด\.ช\.|ด\.ญ\.|พล\.|ร\.ต\.|พ\.ต\.)")


def _audience_is_a_person(document: Document, row: Row) -> Finding | None:
    """A named individual is never the answer to "who is bound".

    Judgments print the parties' names, and a model reading one answers with
    the person in front of it. The class they belong to is the answer.
    """
    value = row.value("กลุ่มเป้าหมาย")
    if not value or not _THAI_TITLE.match(value.strip()):
        return None
    return Finding(
        "audience-names-a-person", 0.30,
        "ช่องกลุ่มเป้าหมายเป็นชื่อบุคคล ไม่ใช่กลุ่ม", ("กลุ่มเป้าหมาย",),
    )


def _effective_long_after_publication(document: Document, row: Row) -> Finding | None:
    """A commencement date years away from publication is usually a misread.

    Thai instruments commence on publication, the day after, or after a stated
    number of days. A gap of years normally means a date was read out of a
    citation of some older law.
    """
    from lawscan.rules import THAI_MONTHS

    published, effective = row.value("ปีที่ประกาศ"), row.value("วันทีมีผลใช้บังคับ")
    if not published or not effective or effective == "-":
        return None
    year = re.search(r"(\d{4})\s*$", effective)
    if not year:
        return None
    gap = int(year.group(1)) - int(published)
    if -1 <= gap <= 2:
        return None
    return Finding(
        "commencement-far-from-publication", 0.25,
        f"วันบังคับใช้ห่างจากปีที่ประกาศ {gap} ปี",
        ("วันทีมีผลใช้บังคับ",),
    )


def _empty_required(document: Document, row: Row) -> Finding | None:
    """The columns without which the row identifies nothing."""
    missing = [c for c in ("ชื่อกฎหมาย", "ประเภทกฎหมาย") if not row.value(c)]
    if not missing:
        return None
    return Finding(
        "missing-identity", 0.30,
        f"ไม่มีค่าในช่องหลัก: {', '.join(c.strip() for c in missing)}",
        tuple(missing),
    )


def _no_business_codes(document: Document, row: Row) -> Finding | None:
    """Neither code column was filled.

    Not wrong on its own — most instruments bind no private business — but it
    is the shape an answer takes when the model could not read the document,
    so it is worth a small mark rather than none.
    """
    core = row.value("กฎหมายเฉพาะธุรกิจ (Core Business Laws)")
    support = row.value(
        "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)"
    )
    if (core and core != "-") or (support and support != "-"):
        return None
    return Finding(
        "no-business-codes", 0.10, "ไม่มีรหัสหมวดธุรกิจทั้งสองช่อง",
        ("กฎหมายเฉพาะธุรกิจ (Core Business Laws)",),
    )


def _truncated_and_incomplete(document: Document, row: Row) -> Finding | None:
    """The document was cut to a budget and a column that reads the middle is empty."""
    from lawscan.ocr.budget import GAP

    if GAP not in document.text() and len(document.text()) < 12_000:
        return None
    hollow = [
        c for c in ("ใบอนุญาต", "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ")
        if row.value(c) in ("", "-")
    ]
    if len(hollow) < 2:
        return None
    return Finding(
        "long-document-nothing-found", 0.10,
        "เอกสารยาวแต่ไม่พบใบอนุญาตหรือแบบฟอร์มเลย",
        tuple(hollow),
    )


#: Every rule, in the order they are reported. Adding one here is all it takes
#: to add it to the score, the note, and the per-column flags.
RULES = (
    _unread_pages,
    _barely_any_text,
    _mostly_recognised,
    _no_gazette_header,
    _no_law_type,
    _empty_required,
    _audience_is_a_person,
    _effective_long_after_publication,
    _no_business_codes,
    _truncated_and_incomplete,
)


def judge(document: Document, row: Row) -> Verdict:
    """Everything wrong with this row that can be established, and what it costs."""
    verdict = Verdict()
    for rule in RULES:
        found = rule(document, row)
        if found is not None:
            verdict.findings.append(found)
    return verdict


def as_cell(score: float) -> str:
    """The confidence column as the operator writes it: a whole percentage.

    Their first corpus wrote ``1`` and their second writes ``100%``. Both are
    the same number and only one can go in the file; this follows the newer
    one, because that is the convention the corpus is being extended under.
    """
    return f"{score * 100:g}%"
