"""Shapes the reference asks for, applied to the answer rather than requested.

Every rule here was read off the comparison against the operator's file, and
every one of them describes a difference that is the same in every row it
appears in: a bracket that should not be there, a tag written once per
neighbour, a date that belongs to a measure rather than to the law. A prompt
can ask for these. It cannot guarantee them across hundreds of documents, and
when it fails there is no way to tell from the output whether the model
misread the document or just forgot the instruction.

Doing it here costs nothing to re-run and can be tested without a provider.
"""

import re

#: ``มาตรา 32 (2)`` and ``มาตรา 32`` are the same section; the bracket points
#: at a sentence inside it. The column exists to join documents to the law they
#: were issued under, and two documents citing different sentences of one
#: section still hang off that section.
_SUBSECTION = re.compile(r"\s*\((?:[\d๐-๙]+(?:/[\d๐-๙]+)?)\)\s*$")

#: ``ทางน้ำชลประทาน<ชื่อ>`` out of a title that is otherwise fixed wording.
_WATERWAY = re.compile(
    r"กำหนดให้ทางน้ำชลประทาน\s*(?P<name>.+?)\s*"
    r"เป็นทางน้ำชลประทานที่จะเรียกเก็บค่าชลประทาน"
)

#: A date that closes the law itself, rather than one that closes a measure
#: inside it. The difference is what the sentence is about: a law says when it
#: ceases to be in force; a relief measure says who gets relief and until when.
#: ``ให้ใช้บังคับ ... ถึงวันที่`` is the law stating its own term. The words
#: matter more than the date: a sentence about ``ผู้ที่มาดำเนินการ ... ถึงวันที่``
#: carries the same date and is about who gets relief, not about when the
#: document dies.
_LAW_EXPIRES = re.compile(
    r"(?:พระราชกำหนดนี้|พระราชบัญญัตินี้|กฎกระทรวงนี้|ระเบียบนี้|ประกาศนี้|"
    r"พระราชกฤษฎีกานี้|ให้ใช้บังคับ)"
    r"[^\n]{0,80}?(?:ถึงวันที่|สิ้นสุดลงในวันที่|สิ้นผลในวันที่|ใช้บังคับถึง)"
)


def no_subsection(parents: list[str]) -> list[str]:
    """Parent citations with the sub-section bracket removed, kept in order.

    Not wired in. It was, and it cost กฎหมายแม่ 16 points against the
    reference: that file keeps the bracket in 74 of the 217 rows that cite a
    parent, so stripping it turned a third of the exact matches into misses.
    Kept because the shape is real — the operator drops it in the other
    two-thirds — and whatever eventually decides between the two forms will
    need this to build one of them.
    """
    return once_each(_SUBSECTION.sub("", p).strip() for p in parents)


def once_each(values) -> list[str]:
    """The same list with repeats dropped, first position wins.

    Written for the tag columns, where asking for a broad name beside each
    specific one produces the broad name once per specific one.

    A tab or a line break inside one entry is two entries — the model reaching
    for a separator the schema did not offer — so they are split before the
    repeats are counted. Collapsing them into spaces first, which is what this
    did, hid the join and then made the two look like one long name:
    ``สำนักงาน ก.\tกระทรวง ข.`` reached the sheet as ``สำนักงาน ก. กระทรวง ข.``
    on 77 entries of a 240-document run.
    """
    from lawscan.merge import entries

    seen: set[str] = set()
    kept = []
    for value in values:
        for part in entries(value):
            text = " ".join(part.split())
            if text and text not in seen:
                seen.add(text)
                kept.append(text)
    return kept


def trim_end_date(found: str, text: str) -> str:
    """The date only when the document says the law itself stops.

    Most documents that name an end date are naming the end of something they
    grant — a fee waiver until March, a test exempted until December. Reading
    those as the law's own expiry fills a column that the reference leaves
    blank, and a wrong date there is worse than none: it says a law is dead.

    Not wired in. Blanking the doubtful ones is defensible as data and was
    measured as a loss: cells blank on both sides are not scored, so replacing
    fifteen wrong dates with ``-`` removed them from the count and left only
    the seven rows where the reference names a date — two of which this had
    just blanked. The column went from 10% to 0%.
    """
    if not found:
        return ""
    return found if _LAW_EXPIRES.search(text) else ""


def irrigation_users(title: str) -> list[str]:
    """The audience of a "this waterway now charges" regulation.

    These come in runs of twenty and say one thing, and the operator writes
    that one thing the same way each time. Deriving it from the title costs
    nothing and cannot drift.
    """
    found = _WATERWAY.search(title or "")
    if not found:
        return []
    return [f"ผู้ใช้น้ำจากทางน้ำชลประทาน{found.group('name')}"]


#: How the operator writes a local body: the kind, a space, then its name.
#: Longest first, so ``องค์การบริหารส่วนตำบล`` is not matched as ``เทศบาลตำบล``
#: would be by a shorter prefix sharing its tail.
_LOCAL_KINDS = (
    "องค์การบริหารส่วนจังหวัด",
    "องค์การบริหารส่วนตำบล",
    "เทศบาลตำบล",
    "เทศบาลเมือง",
    "เทศบาลนคร",
    "เมืองพัทยา",
)

#: Documents that name a council without binding one. A ruling against a local
#: politician names the council they served on; the column is for the body the
#: document places a duty on, and a judgment places its duty on a person.
_NOT_A_LOCAL_LAW = ("คำพิพากษา", "คำวินิจฉัย")


def spaced_local_body(value: str) -> str:
    """``เทศบาลตำบลบัวสว่าง`` written the operator's way: kind, space, name."""
    text = " ".join((value or "").split())
    for kind in _LOCAL_KINDS:
        if text.startswith(kind):
            name = text[len(kind):].strip()
            return f"{kind} {name}" if name else kind
    return text


def local_body_of(value: str, law_type: str) -> str:
    """The local body cell, empty where the document only mentions one."""
    if any(mark in (law_type or "") for mark in _NOT_A_LOCAL_LAW):
        return ""
    return spaced_local_body(value)


#: Every "this waterway now charges" regulation is issued by the same two
#: bodies, and the reference names them as one item carrying both short forms.
#: Written out rather than assembled, because the spacing around the slash is
#: part of the string the column is compared against.
_IRRIGATION_AGENCIES = "กรมชลประทาน (ชป.) /กระทรวงเกษตรและสหกรณ์ (กษ.)"


def irrigation_agencies(title: str) -> list[str]:
    """The two bodies behind a waterway regulation, written their way."""
    return [_IRRIGATION_AGENCIES] if _WATERWAY.search(title or "") else []


#: What a waterway regulation does, in the operator's words. Two tags rather
#: than the four their file uses across these rows: adding the other two
#: collected partial credit everywhere and cost nine cells that were exactly
#: right, and an exact cell is one nobody has to open the PDF for.
_IRRIGATION_ACTIVITIES = ["กำหนดทางน้ำชลประทาน", "เรียกเก็บค่าชลประทาน"]


def irrigation_activities(title: str) -> list[str]:
    """What a "this waterway now charges" regulation is doing."""
    return list(_IRRIGATION_ACTIVITIES) if _WATERWAY.search(title or "") else []


#: How much of a name has to appear in the document for the name to be its own.
#: Long enough that ``ใบอนุญาต`` alone does not vouch for
#: ``ใบอนุญาตให้ประกอบกิจการ``, short enough to survive the qualifier the
#: document adds after it.
_ENOUGH = 8

_QUALIFIER = re.compile(r"\(.*?\)")


def _head(name: str) -> str:
    return _QUALIFIER.sub("", name or "").strip()[:_ENOUGH]


def named_in(text: str, items) -> list[str]:
    """The items the document actually names, in the order given.

    ``prompts/summary.md`` illustrates the licence column with five kinds —
    ``ใบอนุญาตให้ประกอบกิจการ``, ``ใบรับแจ้ง``, ``หนังสือแสดงความจำนง`` and two
    more — and the model returned that list, in that order, for 30 documents of
    240. 75% of the non-empty cells named nothing the document contains.

    A licence is a thing a reader has to go and obtain. If the instrument never
    mentions it, the row is sending them after a form that does not exist,
    which is worse than an empty cell. Dropping the unfounded ones removed 12
    wrong cells and cost no right ones.
    """
    return [item for item in items
            if (head := _head(item)) and head in (text or "")]


#: A hand-written list marker at the head of an entry: ``1)`` ``2.`` ``3 -``.
#: Anchored, so the ``1`` in ``บัญชีหมายเลข 1 อัตราค่าเบี้ยเลี้ยง`` is left alone —
#: that digit is part of the document's name, not a position in a list.
_NUMBERED = re.compile(r"^\s*\(?\d{1,2}\s*[).\-]\s+")


def unnumbered(items) -> list[str]:
    """The same entries without the list markers the model wrote into them.

    The column is a list of documents and the sheet joins it with commas, so a
    number in front of each entry is a second numbering on top of the first —
    and an inconsistent one: over twenty-two documents the model numbered
    fourteen of them and left the rest bare, which is worse than either choice
    on its own because a reader cannot tell whether ``1)`` means anything.

    Stripping here rather than asking the prompt for it, because the prompt has
    asked twice and the marker keeps coming back; a list is a list whatever the
    model decides to decorate it with.
    """
    out = []
    for item in items or []:
        if not item:
            continue
        text = _NUMBERED.sub("", str(item)).strip()
        if text:
            out.append(text)
    return out
