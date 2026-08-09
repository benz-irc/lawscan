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
LONG_FORM: dict[str, str] = {
    "คำพิพากษา": "คำพิพากษาของศาลฎีกาแผนกคดีอาญา",
    "คำวินิจฉัย": "คำวินิจฉัยศาลรัฐธรรมนูญ",
}

#: Types that recount what happened rather than lay down what must happen.
#: Both the bare word and the long form, because either can be the answer.
NARRATIVE: frozenset[str] = frozenset(
    {"คำพิพากษา", "คำวินิจฉัย", *LONG_FORM.values()}
)

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


def read(text: str) -> str:
    """The document's own name for itself, or nothing if it does not give one."""
    head = _forgiving(text[:HEAD])
    found = [(head.find(k), -len(kind), kind)
             for kind in KINDS if (k := _forgiving(kind)) in head]
    if not found:
        return ""
    # Earliest first, and at the same position the longest — otherwise
    # พระราชบัญญัติ wins over พระราชบัญญัติประกอบรัฐธรรมนูญ, which begins at the
    # same character and is a different instrument.
    _, _, kind = min(found)
    return LONG_FORM.get(kind, kind)
