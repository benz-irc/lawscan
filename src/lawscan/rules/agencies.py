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

#: The bracket a name ends with, whatever it holds. The register decides what
#: belongs in one: measured over the operator's 240 rows, all 96 brackets hold
#: an initialism and not one holds a ministry. So a bracket that arrives with
#: the answer is dropped before the lookup and the register writes its own
#: back — which repairs both ways the model gets it wrong at once, the
#: invented initialism (``สำนักงาน กกพ.`` for ``กกพ.``) and the parent
#: ministry put where the initialism goes (``กรมปศุสัตว์ (กระทรวงเกษตรและสหกรณ์)``).
_TRAILING_BRACKET = re.compile(r"\s*\([^)]*\)\s*$")

#: A person's title that names no organisation inside it. Unlike the titles in
#: ``_HELD_BY`` there is nothing here to convert — ``ประธานศาลฎีกา`` does not
#: contain ``สำนักงานศาลยุติธรรม`` — so these are dropped rather than rewritten,
#: and only ever when an organisation is left standing. The column asks which
#: body regulates; naming the person at its head answers a different question,
#: and the operator's sheet writes a title in 4 of 239 filled cells.
_A_TITLE = re.compile(
    r"^(?:ประธาน|อธิบดี|ผู้ว่าราชการ|ผู้บัญชาการ|ผู้ตรวจการแผ่นดิน"
    r"|รัฐมนตรีว่าการ|รัฐมนตรีช่วยว่าการ|ปลัด|เลขาธิการ)"
)

#: A person's title standing in for the body they head. The sheet files the
#: body: 100233 answered รัฐมนตรีว่าการกระทรวงการคลัง *and* กระทรวงการคลัง,
#: which is the same organisation written twice. Only titles whose body is
#: named inside them are here — ``อธิบดี`` and ``ประธานกรรมการ`` name no body,
#: and guessing one would put an organisation in the cell that the document
#: never mentioned.
_HELD_BY = re.compile(r"^(?:รัฐมนตรีว่าการ|รัฐมนตรีช่วยว่าการ|ปลัด|เลขาธิการ)\s*(?=กระทรวง|สำนัก|ทบวง)")

#: The one title that names no body but has exactly one answer.
_SEATS: dict[str, str] = {"นายกรัฐมนตรี": "สำนักนายกรัฐมนตรี"}


def _tidy(text: str) -> str:
    return " ".join((text or "").replace(*_DAMAGE).split())


def body_of(name: str) -> str:
    """The organisation ``name`` stands for, when ``name`` is a person's title."""
    tidied = _tidy(name)
    if tidied in _SEATS:
        return _SEATS[tidied]
    stripped = _HELD_BY.sub("", tidied)
    return stripped if stripped != tidied else tidied


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


def _bare(name: str) -> str:
    """``name`` without the bracket it ends with."""
    return _TRAILING_BRACKET.sub("", _tidy(name)).strip()


def _entry(name: str) -> dict | None:
    """The register's row for ``name``, under any spelling it may arrive in."""
    index = _index()
    return (index.get(_tidy(name))
            or index.get(_bare(name))
            or index.get(body_of(name))
            or index.get(_bare(body_of(name))))


def official(name: str) -> str:
    """The register's spelling of ``name``, or "" when it holds no such agency.

    Empty is a real answer: courts, ad-hoc committees and anything founded
    since the register was written are not in it, and their names are right as
    the document prints them. Bending those toward a near neighbour would put a
    different organisation in the cell.
    """
    entry = _entry(name)
    return entry["name"] if entry else ""


def ministry(name: str) -> str:
    """Which ministry ``name`` answers to, or "" if none or unknown."""
    entry = _entry(name)
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
    #: A body with no ministry above it. The register records what sits above
    #: each agency, and for these it records independence rather than a
    #: ministry — which is exactly when the operator's sheet keeps the title of
    #: the person who heads it as a further item.
    def _independent(name: str) -> bool:
        above = ministry(name)
        return above in {"องค์กรอิสระ", "หน่วยงานอิสระของรัฐ"} or above.startswith(
            ("ประธาน", "นายกรัฐมนตรี"))

    out: list[str] = []
    titles: list[str] = []
    for raw in _apart(names):
        if _tidy(raw) in out:
            # Already written, by the register, in the register's own words.
            # ``นายกรัฐมนตรี`` is what it files ปปง. under, so converting the
            # model's copy of it to ``สำนักนายกรัฐมนตรี`` would name the same
            # seat twice under two spellings.
            continue
        name = official(raw) or body_of(raw)
        if name and _A_TITLE.match(name) and not known(name):
            # Held back rather than written: it belongs in the cell only if
            # nothing better turns up in the rest of the answer.
            titles.append(name)
            continue
        if name and name not in out:
            out.append(name)
        above = ministry(raw)
        if above and above not in out:
            out.append(above)
    if not out:
        # Every name was a title. The document does say who regulates it, and
        # a title is a truer answer here than an empty cell.
        return _once(titles)
    # A title held back earlier is written after all when the body it heads has
    # no ministry above it: ``สำนักงานศาลยุติธรรม, ประธานศาลฎีกา``. Inside a
    # ministry chain the title is the ministry written twice, and stays out.
    if any(_independent(name) for name in out):
        for title in titles:
            if title not in out:
                out.append(title)
    return out


def _apart(names: list[str]) -> list[str]:
    """One name per item, however the answer arrived.

    Two agencies can come back as a single string with a comma between them.
    Left whole, the pair matches no register row at all, so it keeps whatever
    spelling the model gave it and neither name gets its ministry — which is
    how ``กรมปศุสัตว์ (กระทรวงเกษตรและสหกรณ์), รัฐมนตรีว่าการกระทรวงเกษตรและสหกรณ์``
    reached the sheet untouched. A comma inside a name would be split wrongly,
    and the register holds none: its 467 rows use spaces and brackets.
    """
    out: list[str] = []
    for raw in names:
        out.extend(part.strip() for part in str(raw).split(",") if part.strip())
    return out


def _once(names: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for name in names:
        seen.setdefault(name, None)
    return list(seen)


#: ``สำนักงานศาลรัฐธรรมนูญ`` → ``ศาลรัฐธรรมนูญ``. The office administers the
#: court; the court is what gave the ruling.
_THE_OFFICE_OF = re.compile(r"^สำนักงาน(?=ศาล)")


def court_only(names: list[str]) -> list[str]:
    """The court itself, for a document that is a judgment or a ruling.

    V19 rule 14.3 asks for the court and nothing else on these, and the sheet
    writes it that way: ``ศาลรัฐธรรมนูญ`` for a Constitutional Court ruling,
    not the office that runs it and not the presiding judge. Everywhere else
    the office *is* the regulator, so this is scoped to the two document kinds
    that recount rather than command.
    """
    out: list[str] = []
    for raw in _apart(names):
        name = _THE_OFFICE_OF.sub("", _tidy(raw))
        if name.startswith("ศาล") and name not in out:
            out.append(name)
    return out or [n for n in _apart(names) if n]


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
