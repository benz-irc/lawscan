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

from dataclasses import dataclass, field
from typing import Any


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
        """
        existing = self.cells.get(column)
        if existing and existing.source == "rule" and existing.value:
            return
        text = _text(value)
        if not text and existing and existing.value:
            return
        self.cells[column] = Cell(text, source)

    def value(self, column: str) -> str:
        cell = self.cells.get(column)
        return cell.value if cell else ""

    def sources(self) -> dict[str, str]:
        return {c: cell.source for c, cell in self.cells.items() if cell.value}


def _text(value: Any) -> str:
    """A model answer as a cell.

    Lists become comma-joined because that is how the expected export writes a
    multi-valued cell, and because a JSON array in a spreadsheet is unreadable.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "ใช่" if value else ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(v) for v in value if _text(v))
    return str(value).strip()
