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

import re
from dataclasses import dataclass

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

    kept_core = [c for c in core if c not in dead]
    kept_support = [c for c in support if c not in dead]
    for code in found:
        if code not in dead and code not in kept_core and code not in kept_support:
            kept_support.append(code)
    return kept_core, kept_support
