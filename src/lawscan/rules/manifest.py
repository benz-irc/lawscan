"""The catalogue's own name for a document, keyed by its gazette number.

The instrument prints its name on its first page, and ``title.read`` copies it
from there — which works until the scan does not. On the 2569 corpus it did
not: 107 of 250 names came back with tone marks dropped by OCR (``เลือกตัง``
for ``เลือกตั้ง``), and 67 were the wrong name altogether, because the line the
rule found was the parent act cited in the preamble, a running header, or a
sentence. Nineteen bore no resemblance to the document at all.

So the name is read from the catalogue instead, the same way the volume, issue,
page and date already are. This file holds **identity only** — the number and
the name, the two things that say *which document this is*. Nothing that says
what the document means: no category, no risk band, no summary, no reasoning.
Those are the questions this program exists to answer, and a file that carried
them would be answering them in advance. ``tests`` asserts the shape.
"""

from __future__ import annotations

import csv
import unicodedata
from functools import cache
from pathlib import Path

#: Beside the other lists the rules read — agencies, districts, taxonomy.
PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "manifest.csv"

#: The two columns, in order. Named here so a file that grew a third column
#: fails a test rather than quietly widening what the rules are told.
COLUMNS = ("เลขเอกสาร", "ชื่อกฎหมาย")


@cache
def _by_number() -> dict[str, str]:
    if not PATH.exists():
        return {}
    with PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            (row[COLUMNS[0]] or "").strip(): _tidy(row[COLUMNS[1]])
            for row in rows
            if (row.get(COLUMNS[0]) or "").strip()
        }


def _tidy(name: str | None) -> str:
    """One spelling of a name: composed, no non-breaking space, no edges."""
    if not name:
        return ""
    return unicodedata.normalize("NFC", name).replace("\xa0", " ").strip()


def name_of(number: str) -> str:
    """The catalogue's name for this document, or "" if it lists no such one."""
    return _by_number().get((number or "").strip(), "")


def names() -> list[str]:
    """Every name the catalogue lists, for looking one up by its text."""
    return list(_by_number().values())
