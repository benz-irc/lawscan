"""What the document states in a fixed format, read by code.

Nothing here calls a model, opens a network connection, or reads a database.
Give it text, it gives the same answer every time — which is what makes
``lawscan rules <pdf>`` worth running when a cell looks wrong.

``run_all`` is the whole deterministic side in one call, returning the export
columns it can fill. What it leaves out is exactly what the model is for.
Fields beginning with ``_`` are not export columns; they are what the rules
noticed, shown so a person can see why a column came out the way it did.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from lawscan.rules import (
    audience, categories, gazette, kind, parent, penalties, places, title, units,
)
from lawscan.rules.provinces import PROVINCES

if TYPE_CHECKING:
    from lawscan.ocr.read import Document

__all__ = [
    "audience", "categories", "gazette", "kind", "parent",
    "penalties", "places", "title", "units", "run_all",
]

THAI_MONTHS: tuple[str, ...] = (
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
)

#: How the expected export writes each severity band. The emoji is part of the
#: value, not decoration — it is what makes a column of them scannable.
BANDS: dict[str, str] = {
    "RED": "🔴 แดง",
    "ORANGE": "🟠 ส้ม",
    "YELLOW": "🟡 เหลือง",
    "GREEN": "🟢 เขียว",
    "BLUE": "🔵 ฟ้า",
    "GREY": "⚪️ เทา",
}

#: What each band means in the penalty column, where it means anything. GREEN
#: is guidance and GREY is a pure amendment; neither is a consequence, and the
#: expected file leaves the cell empty for both. Measured over forty documents:
#: filling this for anything issued under a parent act scored 9, staying quiet
#: scores 25.
#:
#: The wording is the operator's, not a paraphrase of it. This column is
#: compared whole, so ``มีโทษทางอาญา จำคุกหรือปรับ`` and ``โทษทางอาญา`` score
#: as a disagreement about the law when they are a disagreement about phrasing.
PENALTY_TEXT: dict[str, str] = {
    "RED": "โทษทางอาญา",
    "ORANGE": "โทษทางปกครอง / โทษทางแพ่ง",
    "YELLOW": "เสียสิทธิประโยชน์ / ผลทางนิติกรรม",
    "BLUE": "ระเบียบภาครัฐ",
}

NONE = "-"


def thai_date(value: date | None) -> str:
    """22 กุมภาพันธ์ 2563 — day, Thai month, Buddhist year."""
    if value is None:
        return NONE
    return f"{value.day} {THAI_MONTHS[value.month - 1]} {value.year + 543}"


def run_all(document: Document, *, law_type: str | None = None) -> dict[str, str]:
    """Every column the rules can fill for one document.

    ``law_type`` comes from the model when it is available and is genuinely
    optional: the one rule that wants it also recognises a judgment from its
    opening words, so a missing type costs nothing.
    """
    text = document.text()
    found: dict[str, str] = {"ชื่อไฟล์ ": document.number}

    stated = kind.read(text)
    if stated:
        found["ประเภทกฎหมาย"] = stated

    # The instrument prints its own name before it prints anything else, so
    # this is a copy rather than a reading — and it was being paid for as a
    # reading. ``title.read`` returns "" for the documents it cannot copy from
    # (judgments name themselves with a case number), and an empty value never
    # displaces the model's answer.
    named = title.read(text)
    if named:
        found["ชื่อกฎหมาย"] = named

    # A published law is in force. Nothing in a document can say it has since
    # been repealed — that is written in the law that repealed it, which is a
    # different document — so this is the default, and repeals have to come
    # from the operator's own records.
    #
    # An instrument that runs for a stated period is the exception it can state
    # itself: "ตั้งแต่วันที่ ๑ มกราคม ถึงวันที่ ๓๑ มีนาคม" ends on that day
    # whatever anyone else records, and that day is often in the past by the
    # time the corpus is read.
    # Not from a judgment: it recites the period the conduct happened in, and
    # reading that as the document's own expiry filed a 2013 ruling as lapsed.
    narrative = (stated or law_type) in kind.NARRATIVE
    end = None if narrative else gazette.stated_end_date(text)
    found["วันที่สิ้นผล"] = thai_date(end) if end else NONE
    found["สถานะกฎหมาย"] = gazette.status(end)

    # A judgment is not made under an act; it applies one. Asked anyway, the
    # model returned an empty list on all six court documents of the last run,
    # and the reference file writes a dash for eleven of the seventeen it holds
    # and leaves the other six blank — so the answer is settled by the type and
    # the call buys nothing. Written here rather than skipped in the pipeline
    # because a column the rules can fill is a rule, and ``pipeline`` drops the
    # question on its own once every column it fills is already filled.
    if narrative:
        found["กฎหมายแม่"] = NONE
    else:
        # The instrument names the act it was made under, in a fixed sentence,
        # before it says anything else. Reading it beats asking: the model was
        # answering ``พระราชบัญญัติควบคุมรัฐธรรมนูญ…`` for a document whose
        # own evidence field quoted ``พระราชบัญญัติประกอบรัฐธรรมนูญ…`` — a word
        # that appears nowhere in it — and dropping the two sections it cited.
        #
        # On the 240 answered documents: 43.2% asked, 54.1% read, and the rule
        # is silent on 35 of them, which is where the question still gets put.
        cited = parent.read(text)
        if cited:
            found["กฎหมายแม่"] = ", ".join(cited)

    # Read from the text layer where OCR replaced it: the header is numerals,
    # a broken font leaves numerals alone, and OCR is the one that gets them
    # wrong — it read the Gazette year as ๒๕๒๐ on every document it misread.
    header = gazette.parse(document.header_text)
    if header:
        published = header.publish_date
        found["วันที่ประกาศ"] = str(published.day)
        found["เดือนที่ประกาศ"] = THAI_MONTHS[published.month - 1]
        found["ปีที่ประกาศ"] = str(published.year + 543)
        # The pages the instrument occupies, not only the one it starts on:
        # every page carries its own number in the footer, and the operator
        # cites the span. The footer is Gazette furniture like the header, so
        # it is read the same way — 100087's footers run 1..7 in the text
        # layer and 1,2,3,5,5,2,3 once OCR has been over them, which turns a
        # seven-page instrument into a five-page one.
        span = gazette.page_span(
            gazette.pages_of([page.layer or page.text for page in document.pages])
        ) or str(header.page)
        found["ข้อมูลแหล่งที่มา"] = (
            f"ราชกิจจานุเบกษา เล่ม {header.volume} "
            f"{header.issue_kind} {header.issue} หน้า {span}"
        )
        # A derived rule first — it is the document's own arithmetic. Then a
        # date written out. Only if it says neither does publication stand in.
        effective = (
            gazette.effective_date_from_rule(text, published)
            or gazette.stated_effective_date(text)
        )
        if effective is None and gazette.commences_on_publication(text):
            effective = published
        found["วันทีมีผลใช้บังคับ"] = thai_date(effective)

    # A judgment's audience is the jurisdiction of the court that gave it —
    # a fact about which court, not a reading of the parties.
    bound = audience.read(text)
    if bound:
        found["กลุ่มเป้าหมาย"] = bound

    # Read from the body only: a map annex prints the districts around the
    # area rather than the ones in it.
    place = places.scope(document.body_text, PROVINCES,
                         narrative=stated in kind.NARRATIVE)
    found["จังหวัด"] = place.province or NONE
    # Their sheet writes the district bare and never puts a Bangkok เขต here.
    found["อำเภอ"] = (
        ", ".join(
            name.removeprefix("อำเภอ").strip()
            for name in place.districts
            if not name.startswith("เขต")
        )
        or NONE
    )

    found["_มาตรา/ข้อ"] = str(len(units.split([page.text for page in document.pages])))

    # The document's own word for itself is preferred over the caller's: it is
    # read from the page rather than reported by a model, and it is right on
    # every document measured.
    reading = penalties.read(text, stated or law_type)
    band = reading.band.value
    found["ระดับวามเสี่ยง "] = BANDS[band] if band in PENALTY_TEXT else BANDS["GREY"]
    found["บทลงโทษ"] = PENALTY_TEXT.get(band, NONE)
    found["_แถบสี"] = f"{band} · {reading.evidence or 'ไม่พบคำบ่งชี้'}"

    # Written into the row itself, not only the log. A document that lost
    # pages to pictures reaches the CSV looking exactly like one that lost
    # none, and the person reading the CSV is the one who needs to know.
    lost = document.unread_pages
    found["_หน้าที่เป็นภาพ"] = (
        f"{len(lost)}/{len(document.pages)} หน้า ({', '.join(str(n) for n in lost)})"
        if lost else NONE
    )
    if lost:
        found["หมายเหตุ"] = (
            f"เอกสารมี {len(lost)} จาก {len(document.pages)} หน้าเป็นภาพที่ยังอ่านไม่ได้ "
            f"(หน้า {', '.join(str(n) for n in lost)}) ข้อมูลอาจไม่ครบ"
        )

    found["_รหัสจากกฎ"] = ", ".join(categories.read(text)) or NONE
    found["_ตัดรหัสบริหาร"] = ", ".join(sorted(categories.suppressed(text))) or NONE
    return found
