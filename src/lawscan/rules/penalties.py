"""What happens to you if you do not comply, read off the document's own words.

The operator's specification tags every law with one of six bands, ordered by
how much the consequence hurts, and each band is defined by a list of phrases
rather than by judgement. That makes it a rule, not a question for a model —
"จำคุก" means a criminal penalty whoever is reading, and a model asked to rate
risk on a four-point scale answered MEDIUM for almost everything.

Top-down: the first band whose phrases appear wins, so a law that both jails
people and withdraws licences is filed under the jail. Ordering the checks IS
the severity ranking; there is no scoring.

Two bands carry an exclusion as well as a list, because their phrases are
common enough to catch the wrong documents on their own:

* BLUE is internal government housekeeping, and stops being that the moment the
  text also binds a company.
* GREY is a pure amending instrument, and stops being that the moment it states
  a penalty of its own.

A document matching nothing gets UNKNOWN rather than a guess. The specification
is explicit that those go to a person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class PenaltyBand(StrEnum):
    """Ordered worst first. The order is the severity ranking."""

    RED = "RED"
    ORANGE = "ORANGE"
    YELLOW = "YELLOW"
    BLUE = "BLUE"
    GREEN = "GREEN"
    GREY = "GREY"
    UNKNOWN = "UNKNOWN"


#: Thai in these lists is matched as plain substrings — no word boundaries,
#: because Thai does not write them.
_RED = (
    "ประหารชีวิต",
    "จำคุก",
    "กักขัง",
    "ระวางโทษปรับ",
    "ปรับทางอาญา",
    "ริบทรัพย์สิน",
    "ความผิดทางอาญา",
)

_ORANGE = (
    # ปรับและชดใช้
    "ปรับทางปกครอง",
    "ปรับเป็นพินัย",
    "มาตรการลงโทษทางแพ่ง",
    "ชดใช้ค่าสินไหมทดแทน",
    "ชดใช้ค่าเสียหาย",
    "บังคับชำระหนี้",
    # ธุรกิจและใบอนุญาต
    "เพิกถอนใบอนุญาต",
    "พักใช้ใบอนุญาต",
    "จำกัดการประกอบการ",
    "ระงับการประกอบกิจการ",
    "สั่งปิดสถานประกอบการ",
    "สั่งหยุดกิจการ",
    # ชื่อเสียงและบังคับคดี
    "ภาคทัณฑ์",
    "ตำหนิโดยเปิดเผยต่อสาธารณชน",
    "บุคคลล้มละลาย",
    "ยึดทรัพย์",
    "อายัดเงิน",
    "อายัดบัญชี",
    "ขายทอดตลาด",
)

_YELLOW = (
    # ผลทางนิติกรรม
    "เป็นโมฆะ",
    "โมฆียะ",
    "สิ้นผล",
    # สิทธิประโยชน์
    "เสียสิทธิ",
    "หมดสิทธิ",
    "ไม่ได้รับสิทธิประโยชน์",
    "ตัดสิทธิ",
    # ส่งเสริมการลงทุน
    "ยกเว้นภาษี",
    "ลดหย่อน",
)

_GREEN = (
    "แนวทางปฏิบัติ",
    "คำแนะนำ",
    "เพื่อเป็นการส่งเสริม",
    "มาตรการส่งเสริม",
    "มาตรฐานการปฏิบัติ",
    "ขอความร่วมมือ",
    "ไม่ต้องรับโทษ",
    "ได้รับยกเว้นโทษ",
    "ไม่มีความผิด",
    "ไม่ถือว่ามีความผิด",
    "อำนวยความสะดวก",
)

_BLUE = (
    "ระเบียบสำนักนายกรัฐมนตรี",
    "แบ่งส่วนราชการ",
    "โครงสร้างหน่วยงาน",
    "วินัยข้าราชการ",
    "อัตรากำลัง",
    "เบี้ยเลี้ยง",
)

#: BLUE is government housekeeping only while no private party is bound.
_BLUE_EXCLUDES = ("บริษัท", "นิติบุคคล", "นายจ้าง", "ผู้ประกอบการ", "เอกชน")

_GREY = (
    "ให้ยกเลิกความในมาตรา",
    "ให้เพิ่มความต่อไปนี้",
    "ให้ใช้ความต่อไปนี้แทน",
)

#: Any penalty phrase at all — used to disqualify GREY, which is defined by
#: having none of its own.
_ANY_PENALTY = _RED + _ORANGE + _YELLOW


@dataclass(frozen=True, slots=True)
class Reading:
    """The band, and the phrases that put it there."""

    band: PenaltyBand
    matched: tuple[str, ...] = ()

    @property
    def evidence(self) -> str:
        return ", ".join(self.matched)


#: What turns a penalty phrase into a qualification requirement. A ระเบียบ
#: listing who may hold an office says "ไม่เคยได้รับโทษจำคุก" and "ไม่เป็น
#: บุคคลล้มละลาย" — nobody is being jailed, the opposite is being required.
#: Checked in the characters immediately before the phrase, because Thai puts
#: the negation there and nowhere else.
#: Two windows, because the two kinds of negation carry different distances.
#: A specific one governs its whole clause — "ไม่เคยได้รับโทษจำคุกโดยคำพิพากษา
#: ถึงที่สุดให้จำคุก" negates a จำคุก forty characters later, and a fourteen
#: character window read the second one as a real sentence. Bare ไม่ is far too
#: common in Thai legal prose to be trusted at that range.
_NEGATIONS = ("ไม่เคย", "ไม่เป็น", "ไม่ได้", "มิได้", "มิเคย", "เว้นแต่", "ห้ามมิให้")
_NEGATION_WINDOW = 44

_WEAK_NEGATIONS = ("ไม่",)
_WEAK_WINDOW = 14

#: A judgment records the sentence a court already passed. It states no rule for
#: anyone to comply with, so the sentence in its narrative is not this
#: document's penalty — 100029 and 100030 both recite "จำคุก 2 เดือน" and the
#: operator's own file records no penalty for either.
#: Types that recount a decision rather than impose a duty. Both the model's
#: enum and the words the document uses about itself are listed, because the
#: type now comes from a rule reading the Thai heading and no longer only from
#: the model — and a set that silently stopped matching would turn every
#: judgment back into a scored penalty without anything failing.
_NARRATIVE_TYPES = frozenset(
    {
        "COURT_RULING",
        "CONSTITUTIONAL_COURT_RULING",
        "COURT_ORDER",
        "คำพิพากษา",
        "คำพิพากษาของศาลฎีกาแผนกคดีอาญา",
        "คำวินิจฉัย",
        "คำวินิจฉัยศาลรัฐธรรมนูญ",
        "คำสั่ง",
    }
)


def _negated(text: str, at: int) -> bool:
    wide = text[max(0, at - _NEGATION_WINDOW) : at]
    if any(negation in wide for negation in _NEGATIONS):
        return True
    near = text[max(0, at - _WEAK_WINDOW) : at]
    return any(negation in near for negation in _WEAK_NEGATIONS)


def _found(text: str, phrases: tuple[str, ...]) -> tuple[str, ...]:
    """Phrases that appear and are not being required NOT to happen."""
    matched: list[str] = []
    for phrase in phrases:
        start = 0
        while (at := text.find(phrase, start)) != -1:
            if not _negated(text, at):
                matched.append(phrase)
                break
            start = at + len(phrase)
    return tuple(matched)


#: Thai numerals and spacing vary; nothing here depends on either, but the text
#: is collapsed so a phrase broken across a line break still matches.
_SPACES = re.compile(r"\s+")

#: The chapter a Thai act puts its own penalties in. Everything from the heading
#: to the end of the document, because บทกำหนดโทษ is conventionally last.
_PENALTY_CHAPTER = re.compile(r"(?:หมวด\s*\S*\s*)?บทกำหนดโทษ")


def _own_penalties(flat: str) -> str | None:
    """The document's own penalty chapter, when it has one.

    Read first and alone, because a subordinate instrument routinely quotes the
    penalty of the act that empowers it — "ผู้ใดฝ่าฝืนมาตรา ๘ แห่งพระราชบัญญัติ
    ... ต้องระวางโทษจำคุก" — and scanning the whole text files that document
    under a jail sentence it does not impose. Measured against the operator's
    own file, whole-text scanning called 26 documents criminal and they agreed
    with 5.
    """
    match = _PENALTY_CHAPTER.search(flat)
    return flat[match.start() :] if match else None


def read(text: str, law_type_code: str | None) -> Reading:
    """Which band this document's own words put it in.

    ``law_type_code`` is required, and positional, because it decides whether
    the keywords mean anything at all. A judgment recites the sentence it
    passed; with the type left out, every one of the corpus's judgments came
    back tagged as imposing a criminal penalty. Passing ``None`` says "the type
    is genuinely unknown" and is a decision, not a default.
    """
    if law_type_code in _NARRATIVE_TYPES:
        return Reading(PenaltyBand.UNKNOWN)

    whole = _SPACES.sub("", text)
    # Where the document has a penalty chapter, that chapter is the answer and
    # the rest of the text does not get a vote.
    flat = _own_penalties(whole) or whole

    for band, phrases in (
        (PenaltyBand.RED, _RED),
        (PenaltyBand.ORANGE, _ORANGE),
        (PenaltyBand.YELLOW, _YELLOW),
        (PenaltyBand.GREEN, _GREEN),
    ):
        matched = _found(flat, phrases)
        if matched:
            return Reading(band, matched)

    blue = _found(flat, _BLUE)
    if blue and not _found(flat, _BLUE_EXCLUDES):
        return Reading(PenaltyBand.BLUE, blue)

    grey = _found(flat, _GREY)
    if grey and not _found(flat, _ANY_PENALTY):
        return Reading(PenaltyBand.GREY, grey)

    # A document whose blue phrases were disqualified by naming a company is not
    # blue and is not anything else either. UNKNOWN goes to a person, which is
    # what the specification asks for.
    return Reading(PenaltyBand.UNKNOWN)


#: The operator's sixth band, and the one the scale did not have room for. The
#: five colours rank how much the consequence hurts; this one says the
#: consequence is not written here at all — it is in the act this document was
#: made under. Seven of the forty sit in it, and every one of them carries
#: ``รอเชื่อมโยง:`` in the penalty column. Two columns, one decision.
LINKED_BAND = "โทษเชื่อมโยงจากกฎหมายแม่"

#: Bands that mean "this document states no penalty of its own". A document
#: that does state one is not waiting on anything.
_SILENT = frozenset({"GREEN", "GREY", "UNKNOWN"})


#: Words that make an instrument a relief rather than a duty. A regulation
#: that waives a fee has nothing to punish, so it is not waiting on its parent
#: act for a penalty — the operator files these as no-impact.
_RELIEF = ("ยกเว้น", "ลดหย่อน", "งดเว้น", "คืนเงิน", "ผ่อนผัน")


def amends(text: str) -> bool:
    """Whether this instrument's whole job is editing an earlier one.

    An amendment carries no consequence of its own even when the act above it
    does: it moves words around inside a law that already exists, and whoever
    has to comply was already complying. The operator files these as
    ``⚪️ เทา (Amendment / No Impact)`` — 12 of the 14 that reach this rule.
    """
    return bool(_found(_SPACES.sub("", text), _GREY))


def is_housekeeping(band: str, core: str) -> bool:
    """Government-internal, on the two signals that actually separate it.

    ``_BLUE`` looks for the words a housekeeping instrument uses, and misses
    most of them: of the 39 documents the operator files as 🔵 ฟ้า, 22 contain
    none of those words at all. They are about pay supplements, travel claims,
    recruitment, insignia, grievances — every one of them a different phrase,
    and a list long enough to catch them would catch half the corpus with it.

    What they share is not vocabulary. It is that the instrument reads as
    guidance (the band the phrase-matching already lands on) *and* the business
    codes came back empty — nobody outside the issuing body has anything to do.
    On the 27 documents where both hold, 17 are 🔵 ฟ้า and 7 are ⚪️ เทา, against
    the 7-right/17-wrong the phrase list manages on its own.
    """
    return band == "GREEN" and not _clean(core)


def links_to_parent(*, band: str, parent: str, core: str, title: str = "",
                    amending: bool = False) -> bool:
    """Whether this document's penalty lives in the act above it.

    Four things have to hold. The business codes are what separate these from
    the internal-housekeeping documents that also have a parent and also state
    no penalty — the document must bind a business — which makes this the one
    rule that reads a model answer, so it runs after the questions rather than
    in the first rules pass.

    ``amending`` is the fourth and it is a late addition: an instrument that
    only edits an earlier one passed all three original tests and was being
    filed as waiting on a penalty it will never carry. Twelve of the fourteen
    that reached here were amendments the operator marks as no-impact.
    """
    if amending:
        return False
    if any(word in (title or "")[:60] for word in _RELIEF):
        return False
    return bool(_clean(parent)) and bool(_clean(core)) and band in _SILENT


def link_text(parent: str) -> str:
    """``รอเชื่อมโยง:`` followed by the first act cited, with its sections.

    The parent column is one act-and-section per item; the penalty column names
    a single act and joins its sections with ``และ``, which is how the operator
    writes a duty that one act states in two places.
    """
    parent = _clean(parent)
    if not parent:
        return ""
    items = [_bare(p) for p in parent.split(",") if p.strip()]
    first = items[0]
    act, _, section = first.rpartition(" มาตรา ")
    if not act:
        return f"รอเชื่อมโยง: {first}"
    sections = [section.strip()]
    for item in items[1:]:
        other, _, more = item.rpartition(" มาตรา ")
        if other == act and more.strip() not in sections:
            sections.append(more.strip())
    return f"รอเชื่อมโยง: {act} มาตรา " + " และมาตรา ".join(sections)


#: A section citation carries where in the section the power sits — วรรค for
#: the paragraph, brackets for the sub-clause. The parent column keeps those;
#: this column does not. It names the section a reader has to go and open, and
#: a section is opened whole.
_QUALIFIER = re.compile(r"\s*(วรรค\S+|\([^)]*\))\s*$")


def _bare(item: str) -> str:
    text = item.strip()
    while True:
        shorter = _QUALIFIER.sub("", text)
        if shorter == text:
            return text
        text = shorter


def _clean(value: str) -> str:
    text = (value or "").strip()
    return "" if text in ("", "-") else text
