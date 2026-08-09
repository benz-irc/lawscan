"""The act this instrument was made under, read off its own preamble.

A Thai instrument states where its authority comes from before it states
anything else, in one sentence with a fixed shape:

    อาศัยอำนาจตามความใน มาตรา ๕ วรรคหนึ่ง และมาตรา ๓๒ (๒)
    แห่งพระราชบัญญัติโรคระบาดสัตว์ พ.ศ. ๒๕๕๘
    └── คำประกาศอำนาจ ──┘ └──── มาตราที่อ้าง ────┘ └──── กฎหมายแม่ ────┘

Counted over the whole 3,424-document corpus, that shape covers 59.4% of it
outright. The connectors below add the rest: ``ประกอบกับ`` appears in 481
documents, ``ออกตามความใน`` in 272, ``ประกอบ`` in 288 — none of which the
prompt this replaces ever mentioned.

Two facts about the shape matter more than the words:

* **Sections come before their act, and several can share one.**
  ``มาตรา ๕ … และมาตรา ๓๒ (๒) แห่งพระราชบัญญัติโรคระบาดสัตว์`` is two citations
  of one act, not one citation and one orphan. So the act is found first and
  the sections are read backwards from it.
* **An act ends at its year.** Everything after — ``ซึ่งแก้ไขเพิ่มเติมโดย
  พระราชบัญญัติ… (ฉบับที่ ๘) พ.ศ. ๒๕๕๘`` — is amendment history, and a column
  meant to link documents to each other has to point at the original or the
  links do not meet.

Where it says nothing, the model still answers: an empty return is "this could
not be read", not "there is none". The one place it does answer negatively is
:func:`has_no_parent`, and only for the kinds that provably have none.
"""

from __future__ import annotations

import re

from lawscan.ocr.thai_text import thai_to_arabic_digits
from lawscan.rules import kind

#: Phrases that announce where an instrument's authority comes from, with the
#: share of the 3,424-document corpus each one appears in. Order does not
#: matter — the preamble is taken from the earliest one found.
AUTHORITY = (
    "อาศัยอำนาจตามความใน",   # 59.4%
    "ออกตามความใน",          #  7.9%
    "อาศัยอำนาจ",            #  5.2% in forms other than the first
    "โดยอาศัยอำนาจ",         #  2.9%
    "ประกอบกับ",             # 14.0%
)

#: The words an act's name can begin with. ``ของ`` belongs beside ``แห่ง``:
#: a parent need not be an Act, and when it is a ระเบียบ or a ประกาศ the
#: preamble writes ``ของ`` and cites ``ข้อ`` rather than ``มาตรา``. 399
#: documents do this, and the prompt taught only the ``แห่ง`` form.
_LAW = (
    "พระราชบัญญัติประกอบรัฐธรรมนูญ", "พระราชบัญญัติ", "พระราชกำหนด",
    "พระราชกฤษฎีกา", "กฎกระทรวง", "ระเบียบ", "ประกาศ", "ข้อบังคับ",
    "ประมวลกฎหมาย", "ประมวลรัษฎากร", "กฎ",
)
_STARTS_LAW = re.compile(
    r"(?:แห่ง|ของ)\s*(" + "|".join(re.escape(w) for w in _LAW) + r")"
)

#: Where an act's name stops: its own year. ``พุทธศักราช`` is the older form
#: and appears in the corpus's oldest parents (``พระราชบัญญัติการชลประทานหลวง
#: พุทธศักราช ๒๔๘๕`` is cited 89 times).
_LAW_ENDS = re.compile(r"(?:พ\.ศ\.|พุทธศักราช)\s*[\d๐-๙]{4}")

#: A cited place inside an act, with whatever address follows it.
_SECTION = re.compile(
    r"(มาตรา|ข้อ)\s*([\d๐-๙]+(?:/[\d๐-๙]+)?)"
    r"((?:\s*วรรค[ก-๙]+)?(?:\s*\([\d๐-๙]+\))?)"
)

#: Amendment history. Everything from here to the next act is about when a
#: section was last changed, not about which act it lives in.
_HISTORY = re.compile(r"ซึ่งแก้ไขเพิ่มเติม|แก้ไขเพิ่มเติมโดย")

#: The Constitution is never a parent. Nearly every royal decree opens
#: ``อาศัยอำนาจตามความในมาตรา ๑๗๕ ของรัฐธรรมนูญ… และมาตรา ๐๐ แห่ง
#: พระราชบัญญัติ…`` — that section is the power to issue a decree at all,
#: shared by every decree in the country, and says nothing about which act
#: this one implements.
_CONSTITUTION = re.compile(r"รัฐธรรมนูญแห่งราชอาณาจักรไทย")

#: …and dropping it by name was not enough, because it was never found by
#: name. ``รัฐธรรมนูญ`` is not in :data:`_LAW`, and even added it would not
#: match: the preamble writes it without a year and :func:`_name_at` needs one
#: to know where a name stops. So the clause was invisible to the scan, its
#: ``มาตรา ๑๗๕`` was never consumed, and the next act named picked it up —
#: filing ``พระราชบัญญัติสถานบริการ พ.ศ. ๒๕๐๙ มาตรา ๑๗๕`` and
#: ``พระราชบัญญัติมหาวิทยาลัยราชภัฏ พ.ศ. ๒๕๔๗ มาตรา ๑๗๕`` under two unrelated
#: acts, which is how it was noticed: the same section number under both.
#:
#: 24 of the operator's 240 documents open this way. The clause is cut out of
#: the preamble before anything reads it.
_CONSTITUTIONAL_POWER = re.compile(
    r"(?:มาตรา|ข้อ)\s*[\d๐-๙]+(?:\s*วรรค[ก-๙]+)?(?:\s*\([\d๐-๙]+\))?"
    r"\s*(?:ของ|แห่ง)\s*รัฐธรรมนูญ(?:แห่งราชอาณาจักรไทย)?"
    r"(?:\s*(?:พุทธศักราช|พ\.ศ\.)\s*[\d๐-๙]{4})?"
)

#: ``วรรคหนึ่ง`` is dropped and nothing else is. Every section has a first
#: paragraph, so writing it points at nothing the bare number does not already
#: point at.
_FIRST_PARAGRAPH = re.compile(r"\s*วรรคหนึ่ง")

#: How much of the document can hold a preamble. Past this, a phrase like
#: ``ประกอบกับ`` is an ordinary sentence in the body.
_HEAD = 4_000

#: A citation is written whole: ``มาตรา ๒๕ (๕) วรรคสาม``, brackets and all.
#:
#: Both of these were once ``drop the brackets, keep the วรรค``, measured
#: against a 300-document run that turned out to hold 95 documents whose
#: answers did not come from the pipeline. Re-measured against the operator's
#: 240 answered documents, keeping the brackets is worth 21 exact cells:
#:
#:     วงเล็บ  วรรค    เป๊ะ  บางส่วน  ผิด   คะแนน
#:     ตัด     เก็บ      48     116    55   48.4%
#:     เก็บ    ตัด       55     107    57   49.5%
#:     เก็บ    เก็บ      69      99    51   54.1%
#:
#: It is not that their file prefers brackets — 123 of its citations carry none
#: against 86 that do. It is that the two groups are not symmetric:
#:
#:     เฉลยมีวงเล็บ (86)      ตัด → เป๊ะ  0    เก็บ → เป๊ะ 25
#:     เฉลยไม่มีวงเล็บ (123)   ตัด → เป๊ะ 44    เก็บ → เป๊ะ 40
#:
#: Dropping a bracket the document wrote loses all 86. Keeping a bracket the
#: document never wrote costs nothing, because there is nothing to keep — the
#: 4 lost on the other side are citations that do carry a sub-clause which
#: their file chose not to record. Deleting information to match a file that
#: only sometimes omits it is a losing trade in both directions.
DROP_BRACKETS = False
KEEP_PARAGRAPH = True

#: Where the preamble stops and the instrument begins. Sections cited after
#: this are the document's own, not its parent's — ``ข้อ ๑ ในกฎกระทรวงนี้…``
#: was being read as a citation of the act named above it.
_OPERATIVE = re.compile(r"ดังต่อไปนี้|ต่อไปนี้|(?:ข้อ|มาตรา)\s*1\s+[ก-๙]")


def is_constitution(law: str) -> bool:
    """Whether a named act is the Constitution, which is nobody's parent.

    Exposed because the model needs the same answer the preamble scan already
    has: it named the Constitution for two documents where the reference row is
    a dash, and nothing between the answer and the cell knew any better.
    """
    return bool(_CONSTITUTION.search(law or ""))


def has_no_parent(text: str) -> bool:
    """Kinds that are nobody's child, so silence here is a real answer.

    Judgments and rulings cite sections throughout and have no parent at all:
    of the 17 in the operator's answered documents, the reference names a
    parent for none. Their citations are grounds of offence, not grants of
    power, and a model reading them without this told to look for authority
    finds plenty.
    """
    return kind.read(text) in kind.NARRATIVE


def read(text: str) -> list[str]:
    """Every act this instrument cites as its authority, sections included.

    One entry per section cited, formatted as the export writes it —
    ``พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5`` — because each section
    grants a different power and whoever checks the citation opens them one at
    a time.

    Returns an empty list both for "this has no parent" and for "this could not
    be read"; :func:`has_no_parent` is what separates the two.
    """
    if not text or has_no_parent(text):
        return []

    head = " ".join(thai_to_arabic_digits(text[:_HEAD]).split())
    start = min(
        (head.find(phrase) for phrase in AUTHORITY if phrase in head),
        default=-1,
    )
    if start < 0:
        return []

    preamble = head[start:]
    # The power to issue the instrument at all, which every instrument of its
    # kind cites and none is made under. Cut before anything else reads the
    # preamble, so its section cannot be picked up by the act named after it.
    preamble = _CONSTITUTIONAL_POWER.sub(" ", preamble)
    # The preamble ends where the instrument's own text begins. Without this,
    # a document's ``ข้อ ๑`` was read as another citation of the act above it.
    stops = _OPERATIVE.search(preamble)
    if stops:
        preamble = preamble[: stops.start()]
    found: list[str] = []
    previous_end = 0
    for law in _STARTS_LAW.finditer(preamble):
        name = _name_at(preamble, law)
        if not name:
            continue
        sections = _sections_in(preamble[previous_end : law.start()])
        previous_end = law.end()
        if _CONSTITUTION.search(name):
            # Its sections belong to it, so they leave with it — not to the
            # act named after it.
            continue
        found.extend(f"{name} {s}".strip() for s in (sections or [""]))

    return _once_each(found)


def _name_at(preamble: str, law: re.Match[str]) -> str:
    """The act's name, from ``แห่ง`` to its own year."""
    rest = preamble[law.start(1) :]
    stop = _LAW_ENDS.search(rest)
    if not stop:
        return ""
    name = rest[: stop.end()]
    # An act cited with its amendment history attached is still that act.
    cut = _HISTORY.search(name)
    return (name[: cut.start()] if cut else name).strip(" ,")


def _sections_in(span: str) -> list[str]:
    """The sections cited in the run of text before an act's name."""
    out: list[str] = []
    for match in _SECTION.finditer(span):
        word, number, address = match.groups()
        if DROP_BRACKETS:
            address = re.sub(r"\s*\([\d๐-๙]+\)", "", address)
        if not KEEP_PARAGRAPH:
            address = re.sub(r"\s*วรรค[ก-๙]+", "", address)
        address = _FIRST_PARAGRAPH.sub("", address)
        out.append(" ".join(f"{word} {number}{address}".split()))
    return out


def _once_each(items: list[str]) -> list[str]:
    """The same list with repeats dropped, in the order they were cited."""
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            kept.append(item)
    return kept
