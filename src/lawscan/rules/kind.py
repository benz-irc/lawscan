"""What kind of instrument this is, read from what it calls itself.

A Thai legal document announces its own type in its first heading, in a closed
vocabulary, before anything else on the page. There is nothing to infer and
therefore nothing for a model to be creative about: measured over the forty
documents, taking the earliest of these words gets the type right forty times
out of forty, and the model — asked the same question in English enum form —
got it right zero times, because it answered ``REGULATION`` where the sheet
says ``ระเบียบ``.

That gap is the whole argument for this file. The model was not wrong about the
document; it was wrong about the vocabulary, and a vocabulary is exactly the
kind of thing to write down rather than ask about.
"""

from __future__ import annotations

import re

#: In the order a document would use them, longest-first where one contains
#: another (``พระราชบัญญัติประกอบรัฐธรรมนูญ`` before ``พระราชบัญญัติ``), because
#: the earliest match in the text wins and a prefix would win wrongly.
KINDS: tuple[str, ...] = (
    "พระราชบัญญัติประกอบรัฐธรรมนูญ",
    "พระราชกำหนด",
    "พระราชกฤษฎีกา",
    "พระราชบัญญัติ",
    "กฎกระทรวง",
    # A commission's own rules — ``กฎ ก.พ.``, ``กฎ ก.ตร.``, ``กฎ ก.ก.`` — and
    # the Prime Minister's Office's. The sheet files all of them as ``กฎ``.
    # Without them the earliest kind word on the page was the
    # ``พระราชบัญญัติ`` of the authority clause, which named the act these
    # instruments are issued *under* rather than what they are: 43 documents
    # in the corpus, two of them in the operator's own 240.
    "กฎ ก.",
    "กฎสำนักนายกรัฐมนตรี",
    "ข้อบัญญัติ",
    "ข้อบังคับ",
    "ระเบียบ",
    "ประกาศ",
    "คำสั่ง",
    "คำพิพากษา",
    "คำวินิจฉัย",
)

#: Two of them are written out in full in the sheet. A judgment is always the
#: Supreme Court's political-office division in this corpus, and a ruling always
#: the Constitutional Court — stated here rather than buried in a condition, so
#: a corpus that widens shows up as a wrong cell instead of a silent guess.
_COURT: dict[str, str] = {
    "คำพิพากษา": "คำพิพากษาของศาลฎีกาแผนกคดีอาญา",
    "คำวินิจฉัย": "คำวินิจฉัยศาลรัฐธรรมนูญ",
}

#: These go the other way: the page writes the name out and the sheet keeps the
#: bare word.
_SHORT_FORM: dict[str, str] = {
    "กฎ ก.": "กฎ",
    "กฎสำนักนายกรัฐมนตรี": "กฎ",
}

#: What to file a document as, where that is not the word it uses.
LONG_FORM: dict[str, str] = {**_COURT, **_SHORT_FORM}

#: Types that recount what happened rather than lay down what must happen.
#: Both the bare word and the long form, because either can be the answer.
#:
#: Built from the court types alone, not from every rewriting: reading it off
#: ``LONG_FORM`` was fine while the only rewritings *were* the court ones, and
#: the moment ``กฎ`` was added the title rule started abstaining on it — a rule
#: that recites is a fact about judgments, not about being written differently.
NARRATIVE: frozenset[str] = frozenset({*_COURT, *_COURT.values()})

#: How far in to look. The type is in the masthead; a mention of some other
#: instrument in the body is a citation, not a self-description.
HEAD = 3_000


#: The damage a Gazette text layer does inside Thai: the tone mark goes and
#: ``า`` comes back as ``ำ``. ``คำพิพากษา`` extracts as ``คำพิพำกษำ``, which is
#: still entirely Thai — so :func:`ocr.read.looks_garbled` cannot see it, the
#: page is kept as a text layer, and this rule finds no kind it recognises.
#:
#: Document 100081 is what that costs. Its masthead reads ``คำพิพำกษำ``, so the
#: earliest kind matched was ``พระราชบัญญัติ`` from the subject line 1,782
#: characters later — the Act the defendant was charged under, not what the
#: document is. Everything keyed on the type then went with it: the title
#: composition, the dash in ``กฎหมายแม่`` that judgments get, the expiry rule
#: that must not read a judgment's recited dates. Re-running cannot fix it,
#: which is why the document sat at 33% across two full passes.
#:
#: Both sides are folded, because the vocabulary carries the same vowel:
#: folding only the text turns ``คำพิพากษา`` in this list into something the
#: folded page no longer contains.
_DAMAGE = re.compile(r"[่-๋]")


def _forgiving(text: str) -> str:
    return _DAMAGE.sub("", text or "").replace("ำ", "า")


def _fold(text: str) -> tuple[str, list[int]]:
    """The folded text, and where each of its characters came from.

    Folding drops characters, so an offset found in the folded text does not
    point at the same place in the original. Anything that needs to hand a
    position back to the caller — where the title starts, say — needs the trail
    back as well.
    """
    kept: list[str] = []
    where: list[int] = []
    for index, char in enumerate(text or ""):
        if _DAMAGE.match(char):
            continue
        kept.append("า" if char == "ำ" else char)
        where.append(index)
    return "".join(kept), where


def _earliest(head: str):
    """The kind word that starts first, longest at a tie, or ``None``.

    Earliest first, and at the same position the longest — otherwise
    พระราชบัญญัติ wins over พระราชบัญญัติประกอบรัฐธรรมนูญ, which begins at the
    same character and is a different instrument.
    """
    found = [(head.find(k), -len(kind), kind)
             for kind in KINDS if (k := _forgiving(kind)) in head]
    return min(found) if found else None


def read(text: str) -> str:
    """The document's own name for itself, or nothing if it does not give one."""
    earliest = _earliest(_forgiving(text[:HEAD]))
    return LONG_FORM.get(earliest[2], earliest[2]) if earliest else ""


def position(text: str) -> int:
    """Where the document names itself, as an offset into ``text``, or -1.

    The instrument's title starts at that word, which is what makes this worth
    reporting: anything printed in front of it — the Gazette masthead, the
    letters a scanner invents around a crest — belongs to the page rather than
    to the law.
    """
    head, where = _fold(text[:HEAD])
    earliest = _earliest(head)
    return where[earliest[0]] if earliest else -1
