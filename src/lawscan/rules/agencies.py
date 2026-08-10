"""The register of regulators, read from one file by everything that needs it.

``data/agencies.json`` is the operator's own register: 467 agencies, their
official spelling, the ministry each sits under, and the initialism a document
is likely to print instead. Two very different consumers read it, and they used
to read two different copies:

* the ``identity`` prompt, which ships the list to the model so it writes
  ``สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์ (ก.ล.ต.)`` rather than
  ``ก.ล.ต.``;
* this module, which repairs the answer afterwards.

``name`` is kept exactly as the register spells it, brackets and all, because
that string *is* the value the sheet expects — the operator's own row for the
data-protection office reads ``สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล
(PDPC / สคส.), กระทรวงดิจิทัลเพื่อเศรษฐกิจและสังคม``, agency first and the
ministry after a comma.

An initialism that points at two agencies is dropped rather than guessed:
``สช.`` is both สำนักงานคณะกรรมการสุขภาพแห่งชาติ and
สำนักงานคณะกรรมการส่งเสริมการศึกษาเอกชน, and a register that answers
ambiguously is worse than one that declines.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

REGISTER = Path(__file__).resolve().parents[3] / "data" / "agencies.json"

#: How the register is handed to a prompt: one agency per line, tab, ministry.
#: The prompt says so in words, and the format is here so the two cannot drift.
_LINE = "{name}\t{ministry}"

#: Some exports write ``ดํารง`` — nikhahit plus sara aa — where the register
#: means ``ดำรง``. The two look identical and compare unequal.
_DAMAGE = ("ํา", "ำ")

_TRAILING_BRACKET = re.compile(r"\s*\([^)]*\)\s*$")


def _tidy(text: str) -> str:
    return " ".join((text or "").replace(*_DAMAGE).split())


@cache
def _load(path: Path) -> tuple[dict, ...]:
    if not path.exists():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8")).get("agencies", []))


def _register() -> tuple[dict, ...]:
    return _load(REGISTER)


@cache
def _index() -> dict[str, dict]:
    """Every spelling that identifies one agency, pointing at its entry.

    Three spellings reach a cell: the register's own, the same name without the
    bracketed initialism (which is how most documents print it), and the
    initialism alone.
    """
    found: dict[str, dict] = {}
    for entry in _register():
        for key in (entry["name"], entry.get("plain"), *entry.get("short", ())):
            if key:
                found.setdefault(_tidy(key), entry)
    return found


def official(name: str) -> str:
    """The register's spelling of ``name``, or "" when it holds no such agency.

    Empty is a real answer: courts, ad-hoc committees and anything founded
    since the register was written are not in it, and their names are right as
    the document prints them. Bending those toward a near neighbour would put a
    different organisation in the cell.
    """
    entry = _index().get(_tidy(name))
    return entry["name"] if entry else ""


def ministry(name: str) -> str:
    """Which ministry ``name`` answers to, or "" if none or unknown."""
    entry = _index().get(_tidy(name))
    return entry.get("ministry", "") if entry else ""


def known(name: str) -> bool:
    """Whether the register holds this agency under any of its spellings."""
    return _tidy(name) in _index()


def with_ministry(names: list[str]) -> list[str]:
    """``names`` in register spelling, each followed by the ministry above it.

    The sheet wants the chain, not the leaf: the office that issued the
    instrument and then the ministry it belongs to. A ministry already named in
    the answer is not repeated, and one that is the answer keeps its place.
    """
    out: list[str] = []
    for raw in names:
        name = official(raw) or _tidy(raw)
        if name and name not in out:
            out.append(name)
        above = ministry(raw)
        if above and above not in out:
            out.append(above)
    return out


def catalogue(path: Path | None = None) -> str:
    """The register as the prompt receives it: name, tab, ministry, one a line.

    ``path`` exists so an install pointed at a different data directory — a
    test, or a machine without the operator's register — renders that one and
    gets "" when it is absent, rather than silently shipping the register that
    happens to sit beside the code.
    """
    return "\n".join(
        _LINE.format(name=e["name"], ministry=e.get("ministry", "")).rstrip("\t")
        for e in _load(path or REGISTER)
    )
