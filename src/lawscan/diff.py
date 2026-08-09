"""Our CSV against theirs, column by column.

The point of this file is that it is boring and it never flatters us. A cell
counts as right when it matches after normalisation, half-right when the two
sides overlap but disagree on the edges, and wrong otherwise. Nothing here
rounds in our favour, because a score that moves when the code has not is worse
than no score at all.

The per-column table is the part that pays. A single number says "69.8%" and
tells you nothing to do next; the table says the codes column is losing forty
cells and the province column is losing two, which is where the next hour goes.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from lawscan import sheet

csv.field_size_limit(10**8)

#: Values both files use to mean "nothing here". Compared as equals, so a dash
#: against an empty cell is agreement, not a miss.
BLANK = {"", "-", "–", "—", "N/A", "n/a", "ไม่มี", "None", "nan"}

#: Long free text — a summary, a recommendation, the model's reasoning. Two
#: correct answers here are almost never the same string, so scoring them as
#: exact matches would drag the number down for no fault. Reported separately.
PROSE = {
    "คำอธิบายและสรุปสาระสำคัญ",
    "คำแนะนำสิ่งที่ต้องทำ ",
    "AI ให้เหตุผล",
    "หมายเหตุ",
}

#: Columns nothing in the document can answer. The Gazette's own URL carries
#: the site's document id, and that id appears in neither the extracted text
#: nor the PDF metadata — it is provenance the operator holds from downloading
#: the file. Scoring it would measure whether someone handed us a lookup table,
#: which is why it is reported like any other column and counted like none.
EXTERNAL = {"ลิงค์PDF"}

#: Everything left out of the score, for whichever reason.
UNSCORED = PROSE | EXTERNAL

#: Columns written as a set of items rather than a sentence. Order carries no
#: meaning in them, so they are compared as sets and can be partially right.
LISTS = {
    "หน่วยงานกำกับ",
    "อำเภอ",
    "กลุ่มเป้าหมาย",
    "Activity_Tag",
    "Product_Group_Tag",
    "Legal_Keyword_Tag",
    "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
    "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
    "ใบอนุญาต",
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
}

_SPLIT = re.compile(r"[,،;·|\n]+")
_PUNCT = re.compile(r"[\s​\"'()\[\]．.।]+")

#: ๑๓๗ and 137 are one number written two ways, and the operator's own file
#: writes it both ways — of the forty rows, some source cells use Thai digits
#: and some use Arabic. Comparing the script instead of the value would score
#: those as disagreements when nothing disagrees.
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

#: The Gazette's name and the operator's abbreviation of it.
_SAME_WORD = {"ราชกิจจาฯ": "ราชกิจจานุเบกษา"}

#: ``ำ`` typed as นิคหิต + สระอา. The two spell the same vowel and render the
#: same, and Unicode keeps them apart: SARA AM has no canonical decomposition,
#: so NFC leaves ``การนําเข้า`` and ``การนำเข้า`` as different strings. The
#: operator's spreadsheet uses the first, the text extracted from the PDF uses
#: the second, and the cell was scored as a miss over a keystroke.
_SARA_AM = ("ํา", "ำ")


def _plain(value: str) -> str:
    """Trimmed, blanks unified, numbers written one way, case folded."""
    text = unicodedata.normalize("NFC", value or "").strip()
    if text in BLANK:
        return ""
    # A number is a number however it is written: a document number arrives
    # from Numbers as 100001.0, and a confidence of 1 as "1.0" from one side
    # and "1.00" from the other.
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        number = float(text)
        text = f"{number:g}"
    return " ".join(text.split()).casefold()


def _digits(text: str) -> str:
    return text.translate(_THAI_DIGITS)


def _vowel(text: str) -> str:
    return text.replace(*_SARA_AM)


def _known_words(text: str) -> str:
    for short, full in _SAME_WORD.items():
        text = text.replace(short, full)
    return text


def _marks(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", text).split())


def norm(value: str) -> str:
    """One spelling of a value, so two spellings of the same answer agree.

    Assembled from the steps above rather than written out, because
    :func:`match_reason` walks the same steps one at a time to say which of
    them a given pair of cells needed. Two lists of folds would drift apart,
    and the one that drifted would be the one making the claim.
    """
    return _marks(_known_words(_vowel(_digits(_plain(value)))))


def items(value: str) -> set[str]:
    return {part for part in (norm(p) for p in _SPLIT.split(value or "")) if part}


#: Thai does not put spaces between words. Where a space falls in a Thai
#: sentence is a typesetting decision, and the two files make it differently on
#: purpose: ``export.columns._spaced`` opens a space before ``ว่าด้วย`` because
#: the Gazette prints one, and the reference spreadsheet closes it up. Of the
#: 5,301 scored cells in the 240-document run, 177 disagreed about nothing else.
#:
#: This is why the comparison key is built rather than the normal form reused:
#: ``norm`` still has to produce something a person can read back, and a value
#: with every space taken out is not that.
_SPACES_OUT = re.compile(r"\s+")

#: Thai tone marks, and ``ำ`` where ``า`` belongs. The text layer of a scanned
#: Gazette page returns ``ก่อสรำง`` for ``ก่อสร้าง`` — the vowel and the tone
#: mark are lost together — so both have to go for the two spellings to meet.
#: The fold is looser than Thai really is: it also makes ``นำ`` and ``นา`` one
#: word. That is the price of forgiving damage that cannot be repaired, and it
#: is paid where the alternative is reporting an extraction fault as a wrong
#: answer.
_OCR_DAMAGE = re.compile(r"[่-๋]")

#: The word in front of a place name. The reference file writes ``จังหวัด
#: บุรีรัมย์`` in some rows and ``บุรีรัมย์`` in others; the export always
#: writes it bare. Only offered in the columns that hold a place, because a law
#: whose *title* begins with ``จังหวัด`` is a different law from one that does
#: not.
_PLACE_WORD = re.compile(r"^(?:จังหวัด|อำเภอ|กิ่งอำเภอ)")

PLACE_COLUMNS = frozenset({"จังหวัด", "อำเภอ"})


def _bare_places(text: str) -> str:
    """Each place in a list with its word taken off, item by item.

    Done per item rather than with one pass over the whole string: a pattern
    that has to find the start of the second name has to match the separator
    too, and matching the separator means consuming the space after it on one
    side and not the other — which turns a place difference into a spacing
    difference and misreports why the two cells agreed.
    """
    return ",".join(_PLACE_WORD.sub("", part.strip()) for part in text.split(","))


def key(value: str, column: str = "") -> str:
    """The form two cells are compared in.

    Everything ``norm`` folds, plus the three differences that carry no meaning
    in Thai: where the spaces fall, which vowel the extraction managed to keep,
    and whether a place name was written with its word in front.

    Each fold is narrow and each one is reported by :func:`match_reason`, so a
    cell that only matched because of one can be found and argued with.
    """
    text = norm(value)
    if column.strip() in PLACE_COLUMNS:
        text = _bare_places(text)
    text = _OCR_DAMAGE.sub("", text).replace("ำ", "า")
    return _SPACES_OUT.sub("", text)


def parts(value: str, column: str = "") -> set[str]:
    """A list cell as the set of things it names."""
    return {p for p in (key(x, column) for x in _SPLIT.split(value or "")) if p}


#: A section, clause or bracketed sub-section. Stripping these leaves the law
#: being cited, so two citations of one law can be compared on the address
#: alone.
_CITATION = re.compile(r"\s*(?:มาตรา|ข้อ|วรรค[฀-๿]*|\([\d๐-๙/]+\))\s*[\d๐-๙/]*")

#: Columns whose whole point is to name a place inside a law. Two cells here
#: that name the same Act and differ only on where in it are not two answers
#: about which law applies — they are one answer with a finer address on one
#: side. Fifty-nine cells of the 240-document run are that and nothing else,
#: most of them a ``(๑)`` the penalty column drops and the reference keeps.
CITED_COLUMNS = frozenset({"กฎหมายแม่", "บทลงโทษ"})


def address(value: str) -> str:
    """A citation with its section numbers removed — the law it points at.

    Works on the raw string rather than on :func:`norm`, because normalising
    turns ``(3)`` into a bare ``3`` that no longer reads as a sub-section.
    """
    folded = (value or "").translate(_THAI_DIGITS)
    return " ".join(_CITATION.sub(" ", folded).split()).replace(".", "").lower()


def addresses(value: str) -> set[str]:
    """The section and clause references a citation carries."""
    folded = (value or "").translate(_THAI_DIGITS)
    return {found.strip() for found in _CITATION.findall(folded) if found.strip()}


def _place_step(text: str, column: str) -> str:
    return _bare_places(text) if column.strip() in PLACE_COLUMNS else text


#: Columns whose value is one of a fixed set of bands, written three ways in
#: the operator's own file:
#:
#:     ⚪️ เทา                            87 rows
#:     ⚪️ เทา (Amendment / No Impact)     24 rows — the band with its gloss
#:     เทา                                 1 row  — the band without its emoji
#:
#: All three name the same band. The parenthetical is a translation of the
#: colour, not a fact about the law, and the emoji is decoration their sheet
#: sometimes drops. Counting these as disagreements said the band was wrong on
#: 45 documents where it was right.
BAND_COLUMNS = frozenset({"ระดับวามเสี่ยง ", "ระดับวามเสี่ยง", "ระดับความเสี่ยง"})

_GLOSS = re.compile(r"\s*\([^)]*\)")
_NOT_THAI = re.compile(r"[^฀-๿ ]")


def band_of(value: str) -> str:
    """The colour a band cell names, with the gloss and the emoji taken off."""
    return " ".join(_NOT_THAI.sub("", _GLOSS.sub("", value or "")).split())


def _band_step(value: str, column: str) -> str:
    """The ladder's band fold — applied to the raw string, before ``key``."""
    if column not in BAND_COLUMNS:
        return key(value, column)
    return key(band_of(value), column)


#: The folds in the order they are applied, each with the difference it is the
#: first to forgive. ``match_reason`` walks this list and stops at the step
#: that makes two cells meet, so the reason names what actually mattered rather
#: than the last thing that was tried.
#:
#: Every entry rebuilds the value from the raw string, so the list reads as
#: "everything up to and including this step" and no entry depends on being
#: called after another.
LITERAL = "ตรงทุกตัวอักษร"

_LADDER: tuple[tuple[str, object], ...] = (
    (LITERAL, lambda s, c: (s or "").strip()),
    ("ต่างแค่ตัวพิมพ์หรือช่องว่างหัวท้าย", lambda s, c: _plain(s)),
    ("ต่างแค่เลขไทย/อารบิก", lambda s, c: _digits(_plain(s))),
    ("ต่างที่การพิมพ์สระ อำ", lambda s, c: _vowel(_digits(_plain(s)))),
    ("ต่างแค่เครื่องหมายวรรคตอน", lambda s, c: norm(s)),
    ("ต่างแค่คำนำหน้าชื่อสถานที่", lambda s, c: _place_step(norm(s), c)),
    ("ต่างแค่เว้นวรรค", lambda s, c: _SPACES_OUT.sub("", _place_step(norm(s), c))),
    ("ต่างที่สระ ำ/า ซึ่ง OCR อ่านเพี้ยน", lambda s, c: key(s, c)),
    ("ต่างแค่การเขียนชื่อแถบสี", _band_step),
)

ORDER_ONLY = "ต่างแค่ลำดับรายการ"


def match_reason(theirs: str, ours: str, column: str = "") -> str:
    """Why two cells were counted as agreeing, or "" if they were not.

    A score that folds differences without saying which ones it folded is a
    score nobody can check. This is the column that makes the workbook
    auditable: every cell counted right names the difference it was forgiven,
    and ``ตรงทุกตัวอักษร`` is the answer for the ones that needed nothing.
    """
    for label, fold in _LADDER:
        if fold(theirs, column) == fold(ours, column):
            return label
    # Not a match on the whole string. It can still be one set of items in two
    # orders, which is the only remaining way to agree.
    here = parts(theirs, column)
    if here and here == parts(ours, column):
        return ORDER_ONLY
    return ""


@dataclass
class Column:
    name: str
    exact: int = 0
    partial: int = 0
    wrong: int = 0
    both_blank: int = 0
    #: (document, theirs, ours) for the first few misses, so the report can show
    #: what a failure actually looks like rather than only how many there were.
    examples: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def scored(self) -> int:
        return self.exact + self.partial + self.wrong

    @property
    def credit(self) -> float:
        return self.exact + 0.5 * self.partial


def compare_cell(column: str, theirs: str, ours: str) -> str:
    """One of: blank, exact, partial, wrong.

    Compared on :func:`key` rather than :func:`norm`, so a difference Thai does
    not use to carry meaning is not counted as a difference of answer. What
    each fold forgives is written beside it, and :func:`match_reason` reports
    which one a given cell needed.
    """
    a, b = key(theirs, column), key(ours, column)
    if not a and not b:
        return "blank"
    if a == b:
        return "exact"
    # The same band written with or without its gloss, with or without its
    # emoji. Their file does all three and means one thing by them.
    if column in BAND_COLUMNS and band_of(theirs) and band_of(theirs) == band_of(ours):
        return "exact"
    if not a or not b:
        # One side has an answer and the other does not. That is a real miss in
        # both directions: a cell we left empty, or one we invented.
        return "wrong"
    if column in LISTS:
        # A set written in another order is the same set. Scoring that as
        # "partial" charged half a cell for a comma, and the reference file
        # orders its codes by no rule at all.
        left, right = parts(theirs, column), parts(ours, column)
        if left == right:
            return "exact"
        return "partial" if left & right else "wrong"
    # A title that gained or lost a trailing clause is closer than a wrong one.
    if a in b or b in a:
        return "partial"
    # Same Act, different address inside it. Both cells agree about which law
    # a reader has to open, which is most of what these columns are for, so
    # this is a near miss and not a wrong answer.
    if column.strip() in CITED_COLUMNS and address(theirs) == address(ours):
        return "partial"
    return "wrong"


def _rows(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    """(header, rows by document number) from a CSV or a spreadsheet.

    Keyed on the number rather than the filename cell: the reference writes
    ``100001.pdf`` and the export writes ``100001``, and keying on the cell
    matched nothing at all between the two files.
    """
    return sheet.by_document(path)


@dataclass
class Result:
    columns: dict[str, Column]
    per_document: dict[str, tuple[int, int]]  # document -> (credit*2, scored)
    documents: int
    missing: list[str]
    extra: list[str]

    @property
    def scored(self) -> int:
        return sum(c.scored for c in self.columns.values() if c.name not in UNSCORED)

    @property
    def credit(self) -> float:
        return sum(c.credit for c in self.columns.values() if c.name not in UNSCORED)

    @property
    def exact(self) -> int:
        return sum(c.exact for c in self.columns.values() if c.name not in UNSCORED)


def compare(expected: Path, ours: Path) -> Result:
    their_header, theirs = _rows(expected)
    our_header, mine = _rows(ours)

    shared = sorted(set(theirs) & set(mine))
    columns = {name: Column(name) for name in their_header if name in our_header}

    per_document: dict[str, tuple[int, int]] = {}
    for document in shared:
        credit = scored = 0
        for name, column in columns.items():
            left = theirs[document].get(name, "")
            right = mine[document].get(name, "")
            verdict = compare_cell(name, left, right)
            if verdict == "blank":
                column.both_blank += 1
                continue
            setattr(column, verdict, getattr(column, verdict) + 1)
            if verdict != "exact" and len(column.examples) < 3:
                column.examples.append((document, left.strip()[:60], right.strip()[:60]))
            if name in UNSCORED:
                continue
            scored += 1
            credit += 2 if verdict == "exact" else 1 if verdict == "partial" else 0
        per_document[document] = (credit, scored)

    return Result(
        columns=columns,
        per_document=per_document,
        documents=len(shared),
        missing=sorted(set(theirs) - set(mine)),
        extra=sorted(set(mine) - set(theirs)),
    )


def write_comparison(expected: Path, ours: Path, out: Path) -> int:
    """Every cell of both files side by side, one row per cell that differs.

    A per-column tally says where to look; this says what to look at. Rows are
    ordered worst-first within each document so the first screenful is the work
    to do, and both values are written in full — a comparison that truncates is
    a comparison you have to leave to check.
    """
    their_header, theirs = _rows(expected)
    our_header, mine = _rows(ours)
    shared = sorted(set(theirs) & set(mine))
    columns = [c for c in their_header if c in our_header]

    rank = {"wrong": 0, "partial": 1, "exact": 2, "blank": 3}
    written = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["เอกสาร", "คอลัมน์", "ผล", "ของผู้ดูแล", "ของระบบ", "ชนิด"])
        for document in shared:
            lines = []
            for name in columns:
                left = theirs[document].get(name, "")
                right = mine[document].get(name, "")
                verdict = compare_cell(name, left, right)
                if verdict in ("exact", "blank"):
                    continue
                lines.append((rank[verdict], name, verdict, left.strip(), right.strip()))
            for _, name, verdict, left, right in sorted(lines):
                kind = ("ข้อความยาว" if name in PROSE else "นอกเอกสาร" if name in EXTERNAL
                        else "รายการ" if name in LISTS else "ค่าเดียว")
                writer.writerow([
                    document, name.strip(),
                    {"wrong": "ไม่ตรง", "partial": "ตรงบางส่วน"}[verdict],
                    left, right, kind,
                ])
                written += 1
    return written


def report(result: Result, *, examples: bool = False) -> str:
    """The table, worst column first."""
    lines: list[str] = []
    scored, credit, exact = result.scored, result.credit, result.exact
    lines.append(f"เทียบ {result.documents} ฉบับ · ช่องที่นับ {scored:,}")
    if scored:
        lines.append(
            f"ตรงเป๊ะ {exact:,} ({exact / scored:.1%}) · "
            f"รวมตรงบางส่วน {credit / scored:.1%} · "
            f"ผิด {scored - exact - sum(c.partial for c in result.columns.values() if c.name not in UNSCORED):,}"
        )
    if result.missing:
        lines.append(f"เราไม่มี: {', '.join(result.missing)}")
    if result.extra:
        lines.append(f"เกินมา: {', '.join(result.extra)}")

    lines.append("")
    lines.append(f"{'คอลัมน์':<48}{'เป๊ะ':>6}{'บางส่วน':>9}{'ผิด':>6}{'ว่างทั้งคู่':>12}")
    lines.append("─" * 84)
    ranked = sorted(
        result.columns.values(),
        key=lambda c: (-(c.wrong + 0.5 * c.partial), c.name),
    )
    for column in ranked:
        if not column.scored and not column.both_blank:
            continue
        tag = (" (ข้อความยาว)" if column.name in PROSE
               else " (นอกเอกสาร ไม่นับ)" if column.name in EXTERNAL else "")
        name = (column.name.strip() + tag)[:47]
        lines.append(
            f"{name:<48}{column.exact:>6}{column.partial:>9}"
            f"{column.wrong:>6}{column.both_blank:>12}"
        )
        if examples and column.examples:
            for document, left, right in column.examples:
                lines.append(f"      {document}  เขา: {left or '—'}")
                lines.append(f"      {'':<6}  เรา: {right or '—'}")

    worst = sorted(
        ((d, c, s) for d, (c, s) in result.per_document.items() if s),
        key=lambda x: x[1] / (2 * x[2]),
    )[:8]
    if worst:
        lines.append("")
        lines.append("ฉบับที่ห่างที่สุด: " + ", ".join(
            f"{d} {c / (2 * s):.0%}" for d, c, s in worst
        ))
    return "\n".join(lines)
