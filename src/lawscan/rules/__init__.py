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

from lawscan.rules import audience, categories, gazette, kind, penalties, places, units
from lawscan.rules.provinces import PROVINCES

if TYPE_CHECKING:
    from lawscan.ocr.read import Document

__all__ = [
    "audience", "categories", "gazette", "kind",
    "penalties", "places", "units", "run_all",
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
PENALTY_TEXT: dict[str, str] = {
    "RED": "มีโทษทางอาญา จำคุกหรือปรับ",
    "ORANGE": "โทษทางปกครอง แพ่ง หรือพินัย",
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

    # A published law is in force. Nothing in a document can say it has since
    # been repealed — that is written in the law that repealed it, which is a
    # different document — so this is stated as the default it is, and the
    # exceptions have to come from the operator's own records.
    found["สถานะกฎหมาย"] = "บังคับใช้"

    header = gazette.parse(text)
    if header:
        published = header.publish_date
        found["วันที่ประกาศ"] = str(published.day)
        found["เดือนที่ประกาศ"] = THAI_MONTHS[published.month - 1]
        found["ปีที่ประกาศ"] = str(published.year + 543)
        found["ข้อมูลแหล่งที่มา"] = (
            f"ราชกิจจานุเบกษา เล่ม {header.volume} "
            f"{header.issue_kind} {header.issue} หน้า {header.page}"
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

    place = places.scope(text, PROVINCES, narrative=stated in kind.NARRATIVE)
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
