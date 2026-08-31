"""The document's own name, copied off its first page.

A Gazette instrument prints its title before it prints anything else, and the
title ends where the body begins. That is a fixed format, which makes it a rule
rather than a question for a model — and it was being asked as a question:
``ชื่อกฎหมาย`` came from ``identity`` on all 300 documents of the last run, at
16% of the bill.

Measured against the operator's 240 answered documents: this reads 226 of them
exactly (94.2%) where the model reads 216 (90.0%). Getting past the model took
two things — not truncating the title at a word that also sits inside it, and
composing the court documents' titles instead of giving up on them. Both are in
the constants below, with the numbers each one moved.

Two things end a title, and both are needed:

* **A body word.** ``อาศัยอำนาจ`` ``พระบาทสมเด็จ`` ``โดยที่`` ``ตามที่`` and
  their neighbours open the operative text. Whichever appears first is where
  the title stopped.
* **The year.** Most titles end ``พ.ศ. ๒๕๖๓``. Cutting there as well removes
  the run-on that the body word alone leaves behind on documents that carry no
  ``ด้วย``-style opener.

The year test is the one with a trap in it. ``กฎกระทรวง ฉบับที่ ๔ (พ.ศ. ๒๕๖๓)
ออกตามความในพระราชบัญญัติ… พ.ศ. ๒๔๙๗`` holds two years, and the title runs to
the *second*: the first is the amendment's number, in brackets, and stopping
there would name a law that does not exist. So a year inside brackets is not an
ending, and the last year that is not in brackets is.
"""

from __future__ import annotations

import re

from lawscan.rules import kind

#: Words that open the operative text. A title has ended by the time one of
#: these appears.
#:
#: ``ด้วย`` is deliberately not in this list, and the reason is worth keeping:
#: it is a substring of ``ว่าด้วย``, which appears in the *middle* of most
#: titles this rule exists to read. Matching it as a bare word cut
#: ``ระเบียบผู้ตรวจการแผ่นดิน ว่าด้วยค่าใช้จ่าย…`` down to
#: ``ระเบียบผู้ตรวจการแผ่นดิน ว่า`` on 113 of 240 documents — 44% of the
#: corpus, from one word in one tuple. It is handled by :data:`_OPENS_A_CLAUSE`
#: instead, which requires it to start a word.
_BODY_WORDS = (
    "อาศัยอำนาจ",
    "พระบาทสมเด็จ",
    "โดยที่",
    "ตามที่",
    "เพื่อให้",
    "สมเด็จพระ",
    "ในพระปรมาภิไธย",
    "เนื่องจาก",
)

#: Openers that are also common inside titles, so they only count at the start
#: of a word. ``ด้วยศาลแรงงานภาค ๖ ได้ย้าย…`` opens a body; the ``ด้วย`` in
#: ``ว่าด้วย`` does not.
#:
#: ``ตาม`` was here and had to come out. It opens a body clause often enough to
#: look like it belongs, and it also sits inside titles —
#: ``…ใบอนุญาตขายไพ่ ตามกฎหมายว่าด้วยภาษีสรรพสามิต`` — where cutting at it
#: names a narrower instrument than the one on the page. Four of the five
#: documents this rule got wrong were that, and the same mistake as ``ด้วย``
#: one size up: a word that opens a sentence is not a word that ends a title.
_OPENS_A_CLAUSE = re.compile(r"(?<= )(?:ด้วย|เนื่องด้วย|อนุสนธิ)(?=[ก-๙])")

#: A case number in the opening line. A judgment whose Thai the extraction
#: damaged — ``คำพิพำกษำ`` for ``คำพิพากษา`` — is one ``kind.read`` cannot
#: recognise, so the abstention below would not fire and this rule would put a
#: docket number in the title column. The number itself survives the damage.
_CASE_NUMBER = re.compile(r"คดีหม[าำ]ยเลข|อม\.\s*\d+/\d{4}")

#: ``พ.ศ. ๒๕๖๓`` — but not one closed by a bracket, which is an amendment
#: number rather than the instrument's own year.
_YEAR = re.compile(r"พ\.ศ\.\s*[\d๐-๙]{4}(?!\s*\))")

#: The Gazette's running header, when it survived onto the front of the text.
#:
#: This used to be a shape — ``หน้า ๑๕ เล่ม ๑๕๑ ตอนที่ ๓๑ ราชกิจจานุเบกษา …``
#: — and the shape never once matched, on clean text or damaged: the real
#: masthead puts the section letter between the issue and the paper's name
#: (``ตอนพิเศษ ๒๕๑ ง ราชกิจจานุเบกษา``). Nobody saw it because page one of a
#: clean PDF carries no masthead. OCR reads the printed one, so 591 documents
#: arrived with a title that opened ``หน้า ๑๕ เล่ม ๑๕๑ …``.
#:
#: What replaced it does not try to describe the masthead — OCR renders it a
#: different way on every page (``ตอนที``, ``Maun al``, ``๒ ตุลา``). It uses
#: the one thing that holds: a title begins at the word the instrument calls
#: itself, and :func:`kind.position` already reads that vocabulary through the
#: same damage.
_MASTHEAD = "ราชกิจจานุเบกษา"

#: How far in the masthead can be and still be the masthead rather than a
#: mention of the Gazette inside the title.
_MASTHEAD_WINDOW = 160

#: What a scanner leaves behind where a crest, a seal or a signature was:
#: ``ประกาศสำนักงานศาลปกครอง a 17 6 aa al 17 a 0 1 al A vy 17 Ca vy เรื่อง …``.
#: Only runs are removed, and only runs carrying a letter — a lone ``3`` is
#: ``ฉบับที่ ๓`` and ``GHPs`` is the name of a standard. 122 titles in the
#: corpus carry one; none of the operator's 240 do, because their front pages
#: were never scanned.
_SCANNER_NOISE = re.compile(
    r"(?<![^\s])(?:[^\sก-๙]{1,3}\s+){1,}[^\sก-๙]{1,3}(?![^\s])"
)

#: A run has to hold a letter to be noise. Digits alone are a date or an
#: amendment number.
_HAS_A_LETTER = re.compile(r"[A-Za-z]")

#: How far in to look. A title that has not ended within this many characters
#: is not a title this rule can read.
_HEAD = 1_200

#: Past this, a "title" is a paragraph that never met an ending. The longest
#: real title in the operator's 240 is 232 characters; this leaves room for a
#: longer one without accepting half a page.
_TOO_LONG = 400

#: Below this it is a fragment — a stray line above the real heading.
_TOO_SHORT = 12

#: A court document does not print its name; it prints a docket number. The
#: operator's file writes a composed one:
#:
#:     คำพิพากษาของ‹ศาล› เรื่อง ‹หัวข้อคดี› [คดีหมายเลขดำที่ … คดีหมายเลขแดงที่ …]
#:
#: Every piece of that is on the page, in three different places — the kind and
#: the court in the masthead, the docket numbers beside them, and the subject
#: further in, on the ``เรื่อง`` line that opens the recital. So this is still
#: copying; it just copies from three places instead of one.
_COURT = re.compile(r"(คำพิพากษา|คำวินิจฉัย)")
#: The court's name as printed, and as recognition mangles it. A page that
#: had to be recognised is exactly the page whose name arrives damaged —
#: ``ศาลรฐธ5รรมนูญ`` for ``ศาลรัฐธรรมนูญ``, a dropped vowel and a stray digit
#: — and matching the clean spelling only meant abstaining on the documents
#: this composer exists for. Each pattern is loose in the middle, where the
#: damage lands, and anchored at both ends, where it does not; the title is
#: written with the canonical spelling whichever form matched.
_COURTS = (
    ("ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง",
     re.compile(r"ศาลฎีกาแผนกคดีอาญา\S{0,6}ผู้ดำรง\S{0,4}แหน่งทางการเมือง")),
    ("ศาลรัฐธรรมนูญ", re.compile(r"ศาล[ก-๙\d]{0,4}รรมนูญ")),
    ("ศาลปกครองสูงสุด", re.compile(r"ศาลปกครอง\S{0,3}สุด")),
    ("ศาลฎีกา", re.compile(r"ศาลฎีกา")),
)


def _court_name(head: str) -> str:
    """The court this document belongs to, spelled the way the operator spells it."""
    for name, pattern in _COURTS:
        if pattern.search(head):
            return name
    return ""
#: The docket line, both numbers together. Kept in the order the page prints
#: them because the operator's file keeps it.
_DOCKET = re.compile(
    r"(คดีหมายเลขดำที่\s*\S+\s*\S+\s*คดีหมายเลขแดงที่\s*\S+\s*\S+)"
)
#: A ruling numbers itself instead of carrying a docket.
_RULING_NUMBER = re.compile(r"(คำวินิจฉัยที่\s*[\d๐-๙]+/[\d๐-๙]+)")
#: The subject, on its own line. ``เรื่องพิจารณาที่`` is the internal file
#: reference that sits above it and is not a subject; ``เรื่อง`` followed by a
#: space and a phrase is.
#: ``เรื่อง`` as printed and as recognition returns it. The tone mark is the
#: first thing OCR drops from Thai, and this word carries one: a recognised
#: page says ``เรือง`` where the paper says ``เรื่อง``. Insisting on the mark
#: meant abstaining on exactly the documents that had to be recognised.
#: ``เรือง`` alone is a real word, so the space after it still has to be there
#: — which is also what keeps ``เรื่องพิจารณาที่``, the internal file
#: reference printed above the subject, from being read as one.
_SUBJECT = re.compile(
    r"เรื่?อง\s+([^\n]{6,90}?)\s*(?:\n|ผู้ร้อง|ผู้ถูกกล่าวหา|นาย|นาง|คณะกรรมการ)"
)

#: Whether to compose a title for court documents rather than abstain. Left as
#: a switch because it is the one place this file writes a name the page does
#: not print, and a reader who disagrees should be able to turn it off and get
#: the model's answer back.
COMPOSE_COURT_TITLES = True


def read(text: str) -> str:
    """The instrument's own title, or "" when this cannot read it.

    Empty is a real answer here, not a failure: it hands the column back to the
    model, which is right for court documents and for anything whose first page
    does not follow the Gazette's layout.
    """
    if not text:
        return ""

    head = _without_noise(_after_masthead(" ".join(text[:_HEAD].split())))
    if kind.read(text) in kind.NARRATIVE or _CASE_NUMBER.search(head):
        return _court_title(text, head) if COMPOSE_COURT_TITLES else ""

    # The earliest body word wins. Searched from a small offset so a title that
    # legitimately begins with one of them is not cut to nothing.
    end = len(head)
    for word in _BODY_WORDS:
        at = head.find(word, _TOO_SHORT)
        if _TOO_SHORT < at < end:
            end = at
    clause = _OPENS_A_CLAUSE.search(head, _TOO_SHORT)
    if clause and clause.start() < end:
        end = clause.start()
    head = head[:end]

    years = list(_YEAR.finditer(head))
    if years:
        head = head[: years[-1].end()]

    title = head.strip(" .,")
    if len(title) < _TOO_SHORT:
        return ""
    # The cap is for a paragraph that never met an ending, so it does not apply
    # to one that ended at its own year. 100236 names eight things a permit can
    # be issued for and runs to 408 characters, closing properly with พ.ศ. 2564
    # — a real title that the cap alone threw away, and nothing else fills the
    # column when this rule declines.
    if len(title) > _TOO_LONG and not years:
        return ""
    return title


def _after_masthead(head: str) -> str:
    """``head`` with the Gazette's own furniture taken off the front."""
    printed = head.find(_MASTHEAD)
    if not 0 <= printed < _MASTHEAD_WINDOW:
        return head
    begins = kind.position(head)
    return head[begins:] if begins > printed else head


def _without_noise(head: str) -> str:
    """``head`` with the marks a scanner made around a crest taken out."""
    cleaned = _SCANNER_NOISE.sub(
        lambda m: "" if _HAS_A_LETTER.search(m.group()) else m.group(), head
    )
    return " ".join(cleaned.split())


def _court_title(text: str, head: str) -> str:
    """A judgment's name, composed from the three places the page prints it.

    Returns "" the moment any piece is missing. A half-composed title is worse
    than none: it would still take precedence over the model, which reads all
    three pieces at once and does not need them to be where this expects.
    """
    kinds = _COURT.search(head)
    court = _court_name(head)
    if not kinds or not court:
        return ""
    # Spaces collapse, line breaks do not. Flattening the whole passage first
    # and re-inserting a break before each ``เรื่อง`` looked equivalent and was
    # not: the subject ends at the end of its line, and flattening removed the
    # only marker of that. With every break gone the pattern had to run on to
    # the *next* ``เรื่อง``, which is past its ninety-character limit, so it
    # matched nothing and the composer abstained on documents whose subject was
    # sitting there in plain sight.
    lines = "\n".join(" ".join(l.split()) for l in text[:_HEAD * 3].splitlines())
    subject = _SUBJECT.search(lines)
    if not subject:
        return ""

    name = f"{kinds.group(1)}ของ{court}"
    number = _RULING_NUMBER.search(head)
    if number:
        name += f" {number.group(1)}"
    name += f" เรื่อง {subject.group(1).strip()}"
    docket = _DOCKET.search(head)
    if docket:
        name += f" [{' '.join(docket.group(1).split())}]"
    return name
