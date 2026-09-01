"""Business categories the document states outright.

Same enforcement point as the Gazette header and the place: where a document
identifies itself in a fixed format, code reads it and the model's answer does
not get a vote.

There is one such format here so far. A judgment of the Supreme Court's Criminal
Division for Persons Holding Political Positions carries a docket numbered
อม. — that prefix is the division's own, printed on every one of them, and it
identifies the category exactly. The model was reading these as NACC cases,
court cases and parliamentary matters, all defensible and none of them the
answer the taxonomy has a code for.

Rules here only add. A code the model found stays; this is the floor, not the
ceiling, because a judgment is genuinely also about whatever it is about.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

_TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy.json"


def _once_each(codes) -> list[str]:
    """The codes in order, each written once."""
    seen: dict[str, None] = {}
    for code in codes:
        seen.setdefault(code, None)
    return list(seen)

#: Only the first stretch of a document is searched, so a docket quoted deep in
#: a judgment's reasoning cannot re-file the document that quotes it.
_HEAD = 1500


@dataclass(frozen=True, slots=True)
class Signal:
    """A category the text names in a form only that category takes."""

    code: str
    pattern: re.Pattern[str]
    why: str


#: คดีหมายเลขดำที่ อม. 77/2561 — the space and the full stop both vary in OCR,
#: and the number is not needed: the prefix alone is the identification.
_SIGNALS: tuple[Signal, ...] = (
    Signal(
        code="CC29",
        pattern=re.compile(r"คดีหมายเลข(?:ดำ|แดง)ที่\s*อม\s*\.?\s*\d"),
        why="เลขคดี อม. คือคดีของศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง",
    ),
)


#: The administrative codes a document collects merely by being issued inside
#: government. They belong on a law ABOUT the courts, the civil service, or the
#: machinery of the state — not on every instrument those bodies produce.
#:
#: Suppressed outright for judgments, where the operator's file is unvarying:
#: four judgments of the political-criminal division, four times CC1 and CC29
#: and nothing else, while the model added CC4, CC6 or CC17 to every one. A
#: judgment of a court is not a law about courts.
_ADMIN_CODES: frozenset[str] = frozenset({"CC4", "CC6", "CC17"})

#: How a document that records rather than legislates opens. Read from the
#: text rather than taken from the extraction, because this runs beside the
#: compliance job and the metadata job's answer is not in scope there — and the
#: opening word of a Thai judgment is as fixed a format as the Gazette header.
_NARRATIVE_OPENING = re.compile(r"(?:คำพิพากษา|คำวินิจฉัย|คำสั่งศาล)")


def suppressed(text: str, *, title: str = "") -> frozenset[str]:
    """Codes this kind of document should never carry."""
    window = f"{title}\n{text[:_HEAD]}"
    return _ADMIN_CODES if _NARRATIVE_OPENING.search(window) else frozenset()


def read(text: str, *, title: str = "") -> dict[str, str]:
    """Codes the document identifies itself as, with the reason for each."""
    window = f"{title}\n{text[:_HEAD]}"
    return {signal.code: signal.why for signal in _SIGNALS if signal.pattern.search(window)}


#: A family without its number — ``AM`` where ``AM19`` was meant. The prompt
#: says "หมวดย่อยเสมอ" and nothing enforced it: ten reached the sheet across
#: 240 documents and the operator's file contains none. A family names a shelf
#: rather than a business, so it tells a reader nothing they can act on.
_FAMILY = re.compile(r"^[A-Z]{1,3}$")


def _is_family(code: str) -> bool:
    return bool(_FAMILY.match((code or "").strip().split(" ")[0]))


#: What a code looks like: a family letter or three, then its number.
_CODE = re.compile(r"\b([A-Z]{1,3}\d{1,3})\b")

#: What the model says when the register has no name for what it found.
SUGGEST_NEW = "[SUGGEST_NEW]"
_SUGGEST_NEW = re.compile(r"\[?\s*SUGGEST_NEW\s*\]?", re.IGNORECASE)


@cache
def _catalogue() -> frozenset[str]:
    """Every code the operator's taxonomy defines."""
    if not _TAXONOMY.exists():
        return frozenset()
    groups = json.loads(_TAXONOMY.read_text(encoding="utf-8")).get("groups", [])
    return frozenset(
        entry["code"] for group in groups for entry in group.get("codes", [])
        if entry.get("code")
    )


def codes_in(answer: str) -> list[str]:
    """The codes inside one answer, with whatever else came along dropped.

    The code columns take codes. The model sometimes writes the line it was
    asked to put in the reasoning column instead — ``เกษตรกร · A1 · มาตรา 8
    (1)``, ``CF3 กฎหมายท้องถิ่น สุขาภิบาล และควบคุมอาคาร`` — and a spreadsheet
    filtering on a code matches none of them. 116 entries of a 240-document run
    carried prose in ``Support``, ten in ``Core``.

    A code the taxonomy does not define is dropped rather than kept: it cannot
    be filtered on either, and it is the shape an invented answer takes.
    """
    text = answer or ""
    # V16 gives the model one thing to say that is not a code: "หากวิเคราะห์
    # เทียบเคียงอย่างถี่ถ้วนแล้วไม่เข้าข่ายหมวดใดเลยใน Master List จริงๆ จึงจะ
    # อนุญาตให้ตอบ [SUGGEST_NEW]". It is the answer to a real question — this
    # business exists and the register has no name for it — and the register
    # is the operator's to extend. Dropping it left the column blank, which
    # reads as "nothing was found" rather than "nothing fits".
    if _SUGGEST_NEW.search(text):
        return [SUGGEST_NEW]
    known = _catalogue()
    found = _CODE.findall(text)
    return [c for c in found if not known or c in known]


def correct(
    text: str, core: list[str], support: list[str], *, title: str = ""
) -> tuple[list[str], list[str]]:
    """The model's two lists, with what the document itself states applied.

    This function exists because for a long time it did not. ``read`` and
    ``suppressed`` were computed on every document and written out as
    diagnostics — visible in ``rules.json``, absent from the CSV. The rule knew
    a judgment was a CC29 and knew CC17 did not belong on it, and said so to
    nobody. Measured over the forty documents, connecting them moves the code
    columns from 44 cells right to 49.

    Order matters and is the whole logic: add what the document identifies
    itself as, then remove what its kind cannot carry. A signal that is also
    an administrative code would otherwise be added and kept.
    """
    dead = suppressed(text, title=title)
    found = read(text, title=title)

    core = _once_each(c for entry in core for c in codes_in(entry))
    support = _once_each(c for entry in support for c in codes_in(entry))

    core = [c for c in core if not _is_family(c)]
    support = [c for c in support if not _is_family(c)]

    kept_core = [c for c in core if c not in dead]
    kept_support = [c for c in support if c not in dead]
    for code in found:
        if code not in dead and code not in kept_core and code not in kept_support:
            kept_support.append(code)
    return kept_core, kept_support

#: ``AB2 = ผู้ค้าส่งและตัวแทนจำหน่าย`` — the register, read the other way round.
#: Built once, from the same file the prompt ships.
def _bare_name(name: str) -> str:
    return re.sub(r"\s+", "", name)


def _by_name(*, bare: bool = False) -> dict[str, str]:
    global _NAMED, _BARE
    if bare:
        if _BARE is None:
            _BARE = {_bare_name(k): v for k, v in _by_name().items()}
        return _BARE
    if _NAMED is None:
        found: dict[str, str] = {}
        listing = _TAXONOMY.with_suffix(".txt")
        for line in listing.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Z]{1,2}\d+)\s*=\s*(.+?)\s*\[", line)
            if match:
                found.setdefault(" ".join(match.group(2).split()), match.group(1))
        _NAMED = found
    return _NAMED


_NAMED: dict[str, str] | None = None
_BARE: dict[str, str] | None = None

#: A code and the name written beside it, anywhere in the reasoning.
_LABELLED = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b[\]\s:·]*([ก-๙][^·\n\[\]<]{3,50})")


#: ``AB2 = ผู้ค้าส่งและตัวแทนจำหน่าย`` as the model is now asked to write it.
_PAIRED = re.compile(r"^\s*([A-Z]{1,2}\d{1,2})\s*(\[[A-Za-z]+\])?\s*=\s*(.+?)\s*$")

#: The register's own tag, which says which column a row may be answered in.
#: Upper case throughout, which is what tells it from a status tag.
_REGISTER_TAG = re.compile(r"\s*\[[A-Z]+\]\s*$")

#: Any bracketed tag the answer carries. V19 asks for two different kinds and
#: the difference matters: ``[Exempted]`` is a status the sheet keeps, while
#: ``[Direct Duty]``, ``[Service Opportunity]`` and the rest are the impact
#: labels rule STEP 2 wants in the reasoning column and nowhere else.
#:
#: Matching only ``[Exempted]`` was not enough — an answer tagged
#: ``[Direct Duty]`` kept the label inside the name, matched no register row,
#: and was dropped. On 100114 that emptied both columns at once.
#: ``&`` is in two of V19's seven labels — ``[Rights & Admin]`` and
#: ``[Benefit & Incentive]`` — and leaving it out of the character class cost
#: 100016 all seven of its codes. Restricted to ASCII inside the brackets, so
#: it cannot reach a Thai name: none of the 666 register categories and none of
#: the 467 agencies uses a square bracket at all.
_ANY_TAG = re.compile(r"\s*\[[A-Za-z][A-Za-z &/]*\]")
_KEEP_TAG = "[Exempted]"


def from_pairs(entries: list[str]) -> list[str]:
    """Codes taken from ``code = name`` entries, the name deciding.

    The register is asked for by name so that reading it can be checked. A
    model that never opened it writes a name of its own devising — measured
    over twenty-two documents, 87% of the names beside its codes were its own
    words, and only three of the wrong codes sat next to the right one, which
    is what "read it and slipped a row" would look like. The rest jumped
    families: ``สนามกีฬา`` tagged AM3 when it is AU6.

    So a pair whose name is not in the register is dropped rather than kept.
    Keeping it would carry forward a code with nothing behind it, and the
    column has no room to say "this one was guessed".
    """
    known = _by_name()
    out: list[str] = []
    for entry in entries:
        match = _PAIRED.match(entry or "")
        if not match:
            # No pair to check. An older answer file, or a model that ignored
            # the format — read the codes out of it as before.
            for code in codes_in(entry or ""):
                if code not in out:
                    out.append(code)
            continue
        # ``[CORE]`` / ``[SUPPORT]`` end every register line and a faithful
        # copy brings the tag along. It marks which column the row may be
        # answered in, and is not part of the name. A mixed-case tag is the
        # answer's own status and is kept.
        raw_name = match.group(3)
        tags = [t.strip() for t in ([match.group(2)] if match.group(2) else [])
                + _ANY_TAG.findall(raw_name)]
        status = _KEEP_TAG if any(t == _KEEP_TAG for t in tags) else ""
        raw_name = _ANY_TAG.sub("", raw_name)
        name = " ".join(_REGISTER_TAG.sub("", raw_name).split())
        # Matched without spaces too. The register writes ``การผลิต ผลิตภัณฑ์นม``
        # and a copy of it may come back closed up; the space is the register's
        # typography, not part of the name.
        real = known.get(name) or _by_name(bare=True).get(_bare_name(name))
        if real is None:
            continue
        tagged = f"{real}{status}"
        if tagged not in out:
            out.append(tagged)
    return out


#: ``AB2 = ผู้ค้าส่ง… [CORE]`` — which column the register lets a code be
#: answered in.
_TAGGED = re.compile(r"^\s*([A-Z]{1,2}\d+)\s*=.*\[([A-Z]+)\]")


@cache
def _tags() -> dict[str, str]:
    found: dict[str, str] = {}
    for line in _TAXONOMY.with_suffix(".txt").read_text(encoding="utf-8").splitlines():
        match = _TAGGED.match(line)
        if match:
            found.setdefault(match.group(1), match.group(2))
    return found


def support_only(codes: list[str]) -> list[str]:
    """``codes`` without the ones the register reserves for the core column.

    V19 rule 6 states the constraint outright — the support column takes
    "รหัสหมวดย่อย V8 (หมวด AY - CF)" — and that range turns out to be exactly
    the register's ``[SUPPORT]`` tag: all 583 codes agree, so the tag can
    stand in for the range.

    It binds one way only. Of the 278 codes in the operator's support column
    exactly one carries ``[CORE]``, while 195 of the 466 in their core column
    carry ``[SUPPORT]`` — which is rule 5's "อนุญาตให้ดึงรหัสจากทุกหมวด".

    Held back for a while because enforcing it scored −3.0 against the newer
    22-row answers, which break the rule on 9 of their 49 support codes. The
    master list settled it: ``Tier/Price`` labels A–AW as Core Biz and AY–CF
    as Support across all 582 rows, and the register we send agrees with that
    file on every one of them. The constraint is the operator's own, stated in
    their file and in every version of their prompt; their answers are where it
    is broken, and their notes on those answers record other mistakes of the
    same kind.
    """
    tags = _tags()
    return [code for code in codes if tags.get(code, "SUPPORT") != "CORE"]


#: ``สำนักงาน`` in front of an agency name is the office that administers the
#: institution; the register files the institution.
_THE_OFFICE_OF = re.compile(r"^สำนักงาน(?:คณะกรรมการ)?")


def of_institution(agencies: str) -> list[str]:
    """The register codes that name the bodies in ``agencies``, if any.

    A document is *about* something and it also *belongs to* somebody, and the
    two want different codes. Asked who is bound by an ombudsman's travel
    regulation, a model answers "staff" and reaches for the code for public
    servants in general; the sheet reaches for ``CC9 ผู้ตรวจการแผ่นดิน``, the
    code that names the institution itself. The model had the institution — it
    wrote it at the top of its own reasoning — and never turned it into a code.

    This does the turning, from the regulator column that a rule already fills,
    so the answer does not depend on the model noticing.
    """
    known = _by_name()
    out: list[str] = []
    for raw in (agencies or "").split(","):
        name = " ".join(re.sub(r"\s*\([^)]*\)", "", raw).split())
        if not name:
            continue
        for candidate in (name, _THE_OFFICE_OF.sub("", name).strip()):
            code = known.get(candidate)
            if code and code not in out:
                out.append(code)
                break
    return out


def realign(reasoning: str, codes: list[str]) -> list[str]:
    """Codes corrected against the category names written beside them.

    The register is 666 lines of ``code = name`` and the model reads it a row
    out: it picks the name it means and takes the code from the line above.
    Over twenty-two documents it wrote sixty codes whose name belongs to a
    different code, and the same shift repeats — ``AV1`` labelled with AV2's
    name, ``AB1`` with AB2's, ``AB2`` with AB3's.

    The name is the part the model chose deliberately, so the name wins. A
    swap is only made when the name it wrote *starts with a register name in
    full* — a prefix match on a few characters swapped codes that were right —
    and never when the corrected code is already in the list, because a
    document that ends up naming one category twice has lost a category.
    """
    if not reasoning:
        return codes
    known = _by_name()
    swap: dict[str, str] = {}
    for match in _LABELLED.finditer(reasoning):
        code, said = match.group(1), " ".join(match.group(2).split())
        for name, real in known.items():
            if said.startswith(name) and real != code:
                swap[code] = real
                break
    if not swap:
        return codes
    # Corrected in place, then deduplicated. A shift usually runs — ``AB1``
    # carrying AB2's name beside ``AB2`` carrying AB3's — so refusing a swap
    # whose target is already in the list would refuse exactly the case this
    # exists for. Where a run's last code was never labelled, the list comes
    # back one shorter, and that is right: a code whose name was never written
    # has nothing standing behind it.
    out: list[str] = []
    for code in codes:
        moved = swap.get(code, code)
        if moved not in out:
            out.append(moved)
    return out


#: The band the operator's own prompt describes as "รัฐคุมรัฐด้วยกันเอง" —
#: an instrument that puts a duty on officials and on nobody else.
_STATE_ON_STATE = "🔵 ฟ้า"


def institution_belongs_in_core(band: str) -> bool:
    """Whether the issuing body's own code goes to core rather than support.

    V19 rule 5.9 covers this case and covers it plainly: where the document is
    "ระเบียบการบริหารงานภายในของหน่วยงานรัฐหรือองค์กรอิสระ", tag the code of
    the body that owns the regulation into **Core Business**, and do not reach
    for a private business at all.

    The pipeline used to put that code in support unconditionally, chosen by
    watching where the operator's answers put it rather than by reading the
    rule. Their answers are split — on 100001 the office's code sits in
    support and the core column holds a procurement code whose register name
    ends in "เอกชนคู่ค้า", which is the private-sector reach rule 5.9 forbids
    outright, and rule 6.2.1 forbids a core code from repeating in support.

    The band is the signal because the operator defines it as one: 🔵 ฟ้า is
    their own name for an instrument the state aims at itself. A rule already
    fills that column before any question is asked, so this costs nothing.
    """
    return band.strip() == _STATE_ON_STATE


#: A summary line opens with its code. Three shapes reach here and the first
#: version of this pattern saw two of them: ``[K4] ชื่อ : ...`` and
#: ``K4 = ชื่อ : ...`` matched, while ``K4 ชื่อ : ...`` — the code, then the
#: name, then the colon — did not. That third shape is the one the support
#: answers mostly use, so 26 lines that were there read as missing and the
#: same measurement was reported wrong twice in a day. Anything that starts
#: with a code and a separator is a summary line.
_SUMMARY_LINE = re.compile(r"^\s*\[?([A-Z]{1,2}\d{1,2})\]?(?:\s|=|\]|:)")


#: The heading ``settled`` puts in front of the lines it set aside. V19's
#: prompt 3 names this step and gives it a shape — ``ปัดตก [รหัส] เนื่องจาก …``
#: under a ``STEP 3`` heading — and the model writes its own rejections that
#: way, so a rule that files its rejections differently reads as a second,
#: contradictory list. One heading, theirs.
CAST_OFF = "STEP 3: รายงานผลด่านคัดกรอง"


def _as_rejection(line: str, code: str) -> str:
    """``line`` in the shape V19 asks rejections to take."""
    if line.lstrip().startswith("ปัดตก"):
        return line
    rest = line.split(code, 1)[1].lstrip(" []=:").strip() if code in line else ""
    return f"ปัดตก [{code}] เนื่องจาก ไม่ผ่านกฎของทะเบียน — {rest}".rstrip(" —")


def _renumber(line: str, wrote: str, alive: set[str], known: dict[str, str]) -> str | None:
    """``line`` with its code corrected, when the name beside it names a kept code."""
    rest = line.split(wrote, 1)[1] if wrote in line else ""
    for name, code in known.items():
        if code in alive and name and name in rest:
            return line.replace(wrote, code, 1)
    return None


def settled(reasoning: str, kept: list[str]) -> tuple[str, list[str]]:
    """The summary with lines for codes that did not survive moved to the end.

    Every rule between the answer and the sheet can remove a code: the
    register's own ``[SUPPORT]`` tag, rule 6.2.1 against repeating a core code,
    the corrections read from the document. The line explaining that code stays
    behind, and a reader comparing the two columns finds reasoning for codes
    that are in neither — 14 of them over twenty-two documents, on top of the
    37 the model raised in its scratch work and never summarised.

    Moved rather than deleted, and labelled the way the operator's own
    self-correction gate labels them, because the fact that a code was found
    and then ruled out is worth more to the person reading than a silent gap.
    """
    if not reasoning.strip():
        return reasoning, []
    alive = {c for c in kept}
    known = _by_name()
    lines = reasoning.replace("<br>", "\n").split("\n")
    held, dropped, out = [], [], []
    for line in lines:
        m = _SUMMARY_LINE.match(line)
        if m and m.group(1) not in alive:
            # ``realign`` may have corrected the code in the column against the
            # name the model wrote beside it — ``CC11 = กฎหมายศุลกากร`` becomes
            # ``BW11`` because that is the code the register files that name
            # under. The line is right about everything except the number, so
            # the number is what gets fixed; moving the line away would throw
            # out a correct explanation over a digit.
            renamed = _renumber(line, m.group(1), alive, known)
            if renamed is not None:
                out.append(renamed)
                continue
            held.append(_as_rejection(line.strip(), m.group(1)))
            dropped.append(m.group(1))
            continue
        out.append(line)
    text = "<br>".join(x.strip() for x in out if x.strip())
    if held:
        text += f"<br>{CAST_OFF}<br>" + "<br>".join(held)
    return text, dropped


def explained(code: str, why: str) -> str:
    """One summary line for a code a rule put in the column, not the model.

    Two rules write codes the model never proposed: the institution's own code,
    read out of the regulator column, and the codes the document states about
    itself. They are right — that is why they are rules — but they arrive after
    the model has finished writing, so the column held codes with nothing
    behind them and a reader could not tell a rule's answer from a gap.
    """
    name = _by_code().get(code, "")
    return f"{code} {name} : {why}".replace("  ", " ").strip()


_BY_CODE: dict[str, str] | None = None


def _by_code() -> dict[str, str]:
    global _BY_CODE
    if _BY_CODE is None:
        _BY_CODE = {code: name for name, code in _by_name().items()}
    return _BY_CODE




#: A ``STEP 3`` line that reports nothing. The prompt asks for the heading and
#: the model writes one whether or not it threw anything out, so on 164 of 250
#: documents the cell ended ``STEP 3: รายงานผลด่านคัดกรอง<br>STEP 3: -`` — the
#: heading this file adds, and under it a heading that says nothing. Both are
#: dropped here, and where nothing is left the heading is not written at all.
_EMPTY_STEP_3 = re.compile(r"^\s*STEP\s*3\s*[:：]?\s*[-–—]?\s*$")


def _reported(text: str) -> str:
    """A cast-off block with its empty headings taken out."""
    lines = [line for line in text.replace("<br>", "\n").split("\n")
             if line.strip() and not _EMPTY_STEP_3.match(line)
             and line.strip() != CAST_OFF]
    return "<br>".join(lines)


def _split_tail(text: str) -> tuple[str, str]:
    """``text`` as (live part, cast-off part)."""
    at = text.find(CAST_OFF)
    if at < 0:
        # The model writes its own heading even when it rejected nothing, and
        # that line is not working — it is an empty report.
        return _reported(text).strip(), ""
    return text[:at].strip().rstrip("<br>"), _reported(text[at + len(CAST_OFF):]).strip()


def joined(existing: str, addition: str) -> str:
    """Two questions' working in one cell, with one cast-off block at the end.

    Each question settles its own lines, so appending the second question's
    text after the first left the first's cast-offs in the middle of the cell
    and the second's live summary lines underneath them. Anyone reading down
    the cell — or measuring it — takes everything below that label as
    discarded, which put six correct lines on the wrong side.
    """
    live_a, dead_a = _split_tail(existing or "")
    live_b, dead_b = _split_tail(addition or "")
    def tidy(*parts): return "<br>".join(
        y for x in parts for y in x.replace("<br>", "\n").split("\n") if y.strip())
    live = tidy(live_a, live_b)
    dead = tidy(dead_a, dead_b)
    return "<br>".join(x for x in (live, f"{CAST_OFF}<br>{dead}" if dead else "") if x)


#: The code a ``ปัดตก`` line rejects: the one in the first bracket after the
#: word, and no other. Other codes on the line are the reason it was rejected —
#: ``ปัดตก [K4] เนื่องจากโรงไฟฟ้านิวเคลียร์รวมอยู่ใน K1 แล้ว`` rejects K4 and
#: keeps K1 — so reading every code on the line counts five survivors as
#: casualties, which is what a first pass at this measurement did.
_REJECTED = re.compile(r"ปัดตก\s*\[?([A-Z]{1,2}\d{1,2})")


def rejected_in(reasoning: str) -> set[str]:
    """Codes the model itself wrote off, wherever on the cell it said so.

    The heading is not a reliable boundary: on 100006 the model wrote its
    ``ปัดตก [AB1]`` line above the STEP 3 heading and left AB1 in the column,
    and a check that read only below the heading reported the cell clean twice.
    """
    return {m.group(1) for m in _REJECTED.finditer(reasoning or "")}


def name_of(code: str) -> str:
    """The register's own name for ``code``, or "" when it files no such code."""
    return _by_code().get(code, "")
