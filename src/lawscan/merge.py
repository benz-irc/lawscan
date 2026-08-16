"""Where the rules and the model meet, and who wins.

This is the only file that knows both exist. ``rules`` never calls the model;
``llm`` never reads a PDF. Keeping the arbitration in one place is the point:
in the old system the decision was spread across the extraction, the approval
and the export, and "why is this cell wrong" meant reading three services.

The rule is simple and worth stating plainly:

    Where a rule produced an answer, the rule wins.

Not "the rule fills the blanks". A rule here only ever reads something the
document states in a fixed format — a Gazette header line, a province matched
against the seeded list, a section heading. When it produces an answer at all,
it read that format successfully, and the model's answer to the same question is
a paraphrase at best. The previous system had this backwards for the province
and lost two documents' worth of data to it: the model answered "จังหวัดชุมพร",
the table holds "ชุมพร", the equality check failed, and the rule's correct
"ชุมพร" was never consulted because the field was not empty.

Every cell records which side produced it, so a wrong column can be traced to
one prompt file or one rule function without guessing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from lawscan import citation
from lawscan.export.columns import NONE_IS_AN_ANSWER

#: What ``rules`` writes into a column it read and found nothing in.
NOTHING = "-"

@dataclass(slots=True)
class Cell:
    """One value and where it came from."""

    value: str
    #: "rule", "llm:<question>", or "" when nothing produced it.
    source: str = ""


@dataclass(slots=True)
class Row:
    """One document's answer to all 33 columns, with provenance."""

    document: str
    cells: dict[str, Cell] = field(default_factory=dict)

    def put(self, column: str, value: Any, source: str) -> None:
        """Record a value unless a rule already answered this column.

        Rules are written first by the pipeline, so this is where the
        precedence actually holds — a later llm answer cannot overwrite one.

        A rule that writes ``-`` means one of two things, and the column says
        which. Where absence is a fact about the law — no expiry date, no
        province because the law is national — the dash is an answer and keeps
        its precedence. Everywhere else it is a gap the rule could not fill,
        and standing in the model's way there only produces an empty cell with
        a correct answer sitting unused in the answer file beside it.
        """
        existing = self.cells.get(column)
        if existing and existing.source == "rule" and existing.value:
            if existing.value != NOTHING or column in NONE_IS_AN_ANSWER:
                return
        text = _text(value)
        # Every rule in ``citation`` is anchored to a section or paragraph
        # number, so running it over a sentence is safe: ``ค่าใช้จ่าย(อื่น)``
        # is the writer's punctuation and stays as written, while
        # ``มาตรา 3(1)`` is an address and gets the shape it has everywhere
        # else. Applied to every column for exactly that reason — a citation
        # should not read one way in the parent column and another way in the
        # summary beside it.
        text = citation.tidy(text)
        if not text and existing and existing.value:
            return
        self.cells[column] = Cell(text, source)

    def value(self, column: str) -> str:
        cell = self.cells.get(column)
        return cell.value if cell else ""

    def sources(self) -> dict[str, str]:
        return {c: cell.source for c, cell in self.cells.items() if cell.value}


#: Ways a model writes "nothing here" that must never reach a cell as text.
#:
#: A spreadsheet showing ``None`` or ``null`` reads as a program that broke,
#: and ``ไม่มี`` reads as a fact the document states — none of the three is
#: what the model meant. They mean the same as an empty answer, and the export
#: already knows how to write an empty answer: ``-`` where absence is a fact
#: about the law, blank where it is a gap in the record.
#:
#: ``null`` arrived with strict schemas. Strict mode requires every property in
#: ``required``, so an optional field is declared nullable and the model
#: answers ``null`` rather than leaving it out — correct JSON, wrong cell.
#: ``ไม่มี`` and ``None`` predate it and appear on eleven cells of the last
#: 300-document run.
_EMPTY_WORDS = frozenset({
    "none", "null", "nan", "n/a", "na", "undefined", "[]", "{}",
    "ไม่มี", "ไม่ระบุ", "ไม่ปรากฏ", "ไม่พบ",
})


def _text(value: Any) -> str:
    """A model answer as a cell, with every spelling of "nothing" reduced to one.

    Three states, and the difference between the last two is the point:

    * a value            → the value
    * nobody answered    → ``""``, which the export leaves blank
    * answered "nothing" → ``-``, the same mark a rule leaves

    A model that writes ``ไม่มี`` or ``null`` has answered the question. It said
    the law has none of this, which is a fact about the law and belongs in the
    column as a dash — not as the word ``null``, which reads as a program that
    broke, and not as a blank, which reads as a question nobody reached.

    Lists become comma-joined because that is how the expected export writes a
    multi-valued cell. An item inside a list that means nothing is dropped
    rather than joined, so ``["ใบอนุญาต ก", null]`` is one licence and not one
    licence and a hole.
    """
    if value is None or value == "":
        # Absent rather than answered. ``None`` is a key the model left out;
        # ``""`` is how a rule abstains — ``title.read`` returns it for the six
        # documents it cannot name, and turning that into a dash would block
        # the model from answering instead of inviting it to.
        return ""
    if isinstance(value, bool):
        return "ใช่" if value else NOTHING
    if isinstance(value, (list, tuple)):
        kept = _once_each(part for v in value for part in entries(v))
        return ", ".join(kept) if kept else NOTHING
    return _item(value) or NOTHING


#: A tab or a line break inside one list entry. The model reaches for these
#: when it has two answers and one slot, and both are invisible in a CSV: the
#: cell reads ``สำนักงาน ก. กระทรวง ข.`` as though one office had a long name.
#:
#: 77 entries of a 240-document run did it, every one of them in ``agencies``,
#: and the shape is always the same — a real separator the schema did not
#: offer. Splitting is not a guess about what was meant; nothing in these
#: columns is ever written across two lines on purpose.
#: What separates two answers that arrived in one slot. Tabs and newlines are
#: how a model runs a list together; the arrows are how it copies a prompt.
#: 100239 answered ``กรมอุทยานแห่งชาติ … → กระทรวงทรัพยากรธรรมชาติ…`` for four
#: of its six agencies, imitating a table in the instruction that had nothing
#: to do with the shape of an answer.
_BREAKS = re.compile(r"[\t\r\n\v\f]+|\s*[→➜➔⟶]\s*")


def entries(value: Any) -> list[str]:
    """One list slot as the entries it actually holds, usually exactly one."""
    if value is None or isinstance(value, (list, tuple, dict)):
        return []
    return [text for text in (_item(part) for part in _BREAKS.split(str(value))) if text]


def _once_each(items: Iterable[str]) -> list[str]:
    """The same entries with repeats dropped, in the order they arrived.

    Splitting creates them: ``["กองกฎหมาย\\tกระทรวงพาณิชย์", "กองราคา\\tกระทรวง
    พาณิชย์"]`` is three offices, not four, and the ministry named twice in a
    cell reads as an error rather than as emphasis.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            kept.append(item)
    return kept


#: Where a generation stopped being an answer and started being its own
#: workings. Document 100052 came back with a whole second attempt attached:
#:
#:     …"note":null} }```Yes but there is a formatting error: extra characters
#:     and mis-quoted JSON. I need to correct. Let's construct properly…
#:
#: The JSON parsed, so ``ok`` was true and nothing downstream had reason to
#: doubt it. A fence is never part of an answer in these columns, and neither
#: is anything after one.
_FENCE = re.compile(r"```")

#: A value still wearing the brackets the prompt drew around its examples.
#:
#: ``prompts/summary.md`` illustrated the tag columns as ``<หลักสูตร>,
#: <แบบทดสอบ>`` — angle brackets meaning "a name goes here" — and the model
#: read them as part of the format and copied them onto real answers. 67 cells
#: of a 240-document run came back as ``<ทรัพย์สิน>, <เงิน>, <ที่ดิน>``.
#:
#: The examples no longer wear them, which fixes the next run. This fixes the
#: runs already on disk, and holds if a later prompt reintroduces the habit:
#: no answer in these columns is ever really called ``<something>``.
#:
#: Stripped everywhere in the value, not at its ends. One slot often holds
#: several — ``<ทรัพย์สิน>, <เงิน>, <ที่ดิน>`` is one string — and taking only
#: the outermost pair leaves ``ทรัพย์สิน>, <เงิน>, <ที่ดิน``, which is worse
#: than leaving it alone. The second pass takes the odd one left over when the
#: model closed a bracket it never opened.
_BRACKETED = re.compile(r"<([^<>]*)>")
_STRAY_BRACKET = re.compile(r"[<>]")


def _item(value: Any) -> str:
    """One scalar, or "" when it is a way of writing nothing."""
    if value is None or isinstance(value, (list, tuple, dict)):
        return ""
    text = str(value)
    fence = _FENCE.search(text)
    if fence:
        text = text[: fence.start()]
    text = _STRAY_BRACKET.sub("", _BRACKETED.sub(r"\1", text)).strip()
    return "" if text.casefold() in _EMPTY_WORDS else text
