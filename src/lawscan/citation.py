"""One way of writing where in a law something lives.

A Thai citation has up to four parts and they nest, outermost first:

    มาตรา ๕๖ วรรคหนึ่ง (๑) (ซ)
    └ section ┘ └paragraph┘ └ sub-clauses ┘

``วรรค`` and ``(๑)`` are different addresses, not two ways of writing one, and
the operator's file uses both together — 132 citations carry a ``วรรค`` and 114
carry a bracket. So neither is converted into the other. What is normalised is
how the parts are *written*, because the model wrote them four ways for the
same address:

    มาตรา 5(วรรคหนึ่ง)(3)      the paragraph in brackets, nothing spaced
    มาตรา 5 วรรค 1 (3)         the paragraph numbered with a digit
    มาตรา ๕ วรรคหนึ่ง(๓)       spaced on one side only
    มาตรา 5 วรรคหนึ่ง (3)      what their file writes, all 132 times

The last is the one this produces. Their file never once writes ``วรรค`` with a
digit, so a digit is converted to the word rather than the other way round.
"""

from __future__ import annotations

import re

#: ``วรรค`` counts in words, and only ever this far — a section with an
#: eleventh paragraph does not occur in the corpus, and inventing a spelling
#: for one would be a guess. A number past the list is left as it was written.
PARAGRAPHS: tuple[str, ...] = (
    "หนึ่ง", "สอง", "สาม", "สี่", "ห้า",
    "หก", "เจ็ด", "แปด", "เก้า", "สิบ",
)

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

#: ``(วรรคหนึ่ง)`` — a paragraph wearing the brackets that belong to a
#: sub-clause. Five cells of a 240-document run did this, and it reads as an
#: address one level deeper than the one meant.
_WRAPPED = re.compile(r"\(\s*(วรรค[^)]*?)\s*\)")

#: ``วรรค 2`` — the paragraph numbered rather than named.
_NUMBERED = re.compile(r"วรรค\s*([\d๐-๙]+)")

#: ``ม.24`` — the section word abbreviated. The reasoning column is written
#: terse and ``prompts/business.md`` shows ``ม.8`` in its own examples, so the
#: model writes it there and it spreads: 147 citations of a 240-document run.
#: Their file writes ``มาตรา`` 637 times against ``ม.`` twice, so the short
#: form is expanded rather than adopted.
#:
#: It also escaped every other rule here, because all of them anchor on the
#: word ``มาตรา`` — which is why ``ม.24(3)`` still reached the sheet with the
#: bracket run up against the number after the brackets were supposedly fixed.
#:
#: Not expanded where it is a village number: a Thai address writes
#: ``ม.6 ต.บางรัก``, and หมู่ 6 is not a section of anything.
_ABBREVIATED = re.compile(
    r"(?<![ก-๙])ม\.?\s*(?=[\d๐-๙])(?!.{0,10}?(?:ต\.|ตำบล|อ\.|อำเภอ|จ\.|จังหวัด)\s*[ก-๙])"
)

#: ``มาตรา7`` — the word grown against its own number.
_TIGHT_NUMBER = re.compile(r"(มาตรา|ข้อ)(?=[\d๐-๙])")

#: A sub-clause grown against the section number it belongs to —
#: ``มาตรา 3(1)``. Anchored to the number rather than to any bracket, so this
#: is safe to run over a sentence: ``ค่าใช้จ่าย(อื่น)`` in prose is the
#: writer's punctuation and none of this file's business.
_TIGHT_BRACKET = re.compile(r"((?:มาตรา|ข้อ)\s*[\d๐-๙]+(?:/[\d๐-๙]+)?)\s*\(")

#: A sub-clause grown against the paragraph it sits in — ``วรรคหนึ่ง(3)``.
_TIGHT_AFTER_PARAGRAPH = re.compile(r"(วรรค[ก-๙]+)\s*\(")

#: Two sub-clauses of one section, run together: ``(1)(ซ)``.
_TIGHT_PAIR = re.compile(r"\)\s*\(")

#: ``วรรค`` grown against the number before it — ``มาตรา 5วรรคหนึ่ง``. Also
#: anchored to a digit, so ``ยกเลิกวรรคหนึ่ง`` in a sentence stays as written.
_TIGHT_PARAGRAPH = re.compile(r"(?<=[\d๐-๙])(?=วรรค[ก-ฮ])")

_SPACES = re.compile(r"[ \t]{2,}")

#: Nothing to do unless the value holds one of the things this file knows
#: about. Checked before any substitution so ordinary prose costs one scan.
_WORTH_LOOKING = re.compile(r"วรรค|\(|มาตรา|ข้อ|(?<![ก-๙])ม\.?[\d๐-๙]")


def _word(match: re.Match[str]) -> str:
    number = int(match.group(1).translate(_THAI_DIGITS))
    if 1 <= number <= len(PARAGRAPHS):
        return f"วรรค{PARAGRAPHS[number - 1]}"
    return match.group(0)


def tidy(text: str) -> str:
    """A citation written the way the reference file writes one.

    Only the shape changes. A section number stays the number it was, a
    sub-clause stays a sub-clause, and a paragraph stays a paragraph — this
    moves no address, it only stops the same address being written four ways.
    """
    if not text or not _WORTH_LOOKING.search(text):
        return text
    # The short form first: every rule below anchors on the word ``มาตรา``,
    # so a citation still wearing ``ม.`` would slip past all of them.
    text = _ABBREVIATED.sub("มาตรา ", text)
    text = _TIGHT_NUMBER.sub(r"\1 ", text)
    text = _WRAPPED.sub(r" \1", text)
    text = _NUMBERED.sub(_word, text)
    text = _TIGHT_PARAGRAPH.sub(" ", text)
    text = _TIGHT_BRACKET.sub(r"\1 (", text)
    text = _TIGHT_AFTER_PARAGRAPH.sub(r"\1 (", text)
    text = _TIGHT_PAIR.sub(") (", text)
    return _SPACES.sub(" ", text).strip()
