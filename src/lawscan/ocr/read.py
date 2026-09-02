"""PDF in, Thai text out.

Two routes, chosen per page rather than per document. Real Gazette PDFs are
mixed: the first pages carry a text layer and a scanned annexe does not, and
picking one route for the whole file either loses the annexe or re-recognises
pages that were already perfect.

Everything here is deterministic. No model is called, and the same PDF produces
the same text every time — which is what makes the rules downstream testable.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from lawscan import progress
from lawscan.ocr.thai_text import (
    normalize_text, normalize_unicode, repair_clipped_years,
    repair_numeral_lookalikes, repair_swapped_sara_aa, restore_pua_marks,
    restore_sara_am, thai_char_ratio, thai_to_arabic_digits,
)

log = logging.getLogger(__name__)

#: Below this many characters a page is treated as having no usable text layer,
#: whatever the PDF claims. A scanned page often carries a handful of stray
#: characters from a watermark or a stamp.
_TEXT_LAYER_MIN = 40

#: The running header the Gazette prints on every page. Kept on the first page
#: — it is where the volume, issue and publication date are read from — and
#: dropped from the rest, where it interrupts a sentence mid-clause.
#: Tone marks are optional and the words may sit on separate lines, because
#: the Gazette's own font drops them: the header prints as ``เลม ๑๓๗`` and
#: ``หนา ๘``, not ``เล่ม`` and ``หน้า``, and ``ราชกิจจานุเบกษา`` lands on the
#: next line rather than the same one.
#:
#: The strict pattern this replaces matched **none** of the 91 documents with a
#: PDF here — the header was never once kept, on any document, ever. Which is
#: why ``prompts/*.md`` can say "read the top right corner of the page" and the
#: model never had a top right corner to read: only ``gazette.py``, reading the
#: layer by itself, ever saw one.
_RUNNING_HEADER = re.compile(
    r"^[ \t]*(?:หน้?า\s*[\d๐-๙]+[^\n]*\n)?"
    r"[ \t]*เล่?ม\s*\S+\s*ตอน\S*\s*[^\n]*\n"
    r"[ \t]*ราชกิจจานุเบกษา[^\n]*\n"
    r"(?:[ \t]*[\d๐-๙]+\s+\S+\s+[\d๐-๙]{4}[^\n]*\n)?",
    re.MULTILINE,
)


#: A picture below this is a crest, a logo or a signature — decoration that
#: carries no fact. Above it, on a page with almost no text, the picture *is*
#: the page: a map annexe, a government form, a diagram with its dimensions
#: written inside it.
_MEANINGFUL_IMAGE = 40_000

#: The two ways to read a document.
#:
#: ``text`` recognises only pages that have no text layer at all. It is the
#: cheap one and it is right for the ordinary Gazette PDF, where every page is
#: real text and recognising it again would be slower and worse.
#:
#: ``image`` also reads the pictures. A map annexe, a government form, a
#: diagram with its dimensions written inside it — these are pages whose
#: content is drawn rather than typed, and the text route returns nothing for
#: them however carefully it looks. Measured over 91 documents: 53 carry
#: pictures and 18 pages are content that ``text`` cannot see at all.
#:
#: The recognised text is *appended* rather than substituted, because those
#: pages usually do have a heading in real text above the picture, and
#: replacing it would trade one loss for another.
MODES = ("text", "image")

#: Sheets attached to an instrument to illustrate it: a map of the area, a
#: schedule of rates. They name places and quantities that belong to the
#: picture rather than to the law, and they say so on their first line.
#: Sheets attached to an instrument to illustrate it, matched through the
#: damage OCR does to their heading. The three spellings below are all the
#: same two words off one corpus page each — ``แผนทีฑาย``, ``แผนทีท้าย``,
#: ``แผนททาย`` — so the pattern asks for ``แผนท`` … ``าย`` and lets the middle
#: be whatever the scanner saw.
_ANNEX = re.compile(r"แผนท.{0,3}(?:าย|หมายเลข)|บัญช.{0,3}าย|มาตราสวน1")

#: Tone marks are the first thing OCR loses, and ``ำ`` the first it confuses.
_TONES = re.compile(r"[่-๋์]")

#: Latin junk the scanner invents around a map caption — ``= ay a แผนที…`` —
#: which would otherwise push the heading out of reach of the window below.
_NOT_THAI = re.compile(r"[^ก-๙0-9]")

#: How far into a page a marker may sit and still be its heading, counted in
#: Thai characters. A map scale is quoted inside ordinary text 79 times
#: against 9 as a caption; 100749 page 7 opens with an operative list of
#: localities and mentions a scale further down, and dropping it costs a
#: district the law really does cover.
_HEADING = 40

#: How little text makes a page "a picture with a caption" rather than "a page".
#: Set from what the corpus actually contains: the uniform-regulation pages
#: carry 120–160 characters of heading above a full-page illustration, and a
#: threshold of 40 — which is where the OCR route starts — called every one of
#: them a normal page.
_CAPTION_ONLY = 200


@dataclass(slots=True)
class Page:
    number: int
    text: str
    source: str  # "text-layer" or "ocr"
    #: Whether this page carries a picture large enough to be its content.
    #: Recorded even when nothing is done about it, because the failure this
    #: guards against is silent: a document can lose half its pages to images
    #: and reach the CSV looking complete.
    has_image: bool = False
    #: What the text layer said, kept only when OCR replaced it.
    #:
    #: The two damages are complementary and neither source is better at both
    #: jobs. A broken font destroys the Thai and leaves the numerals alone —
    #: they are Latin digits and the substitution never reaches them. OCR
    #: recovers the Thai and misreads the numerals: across the corpus it read
    #: the Gazette year ``๒๕๖๖`` as ``๒๕๒๐`` every time it got it wrong, which
    #: dated three documents to 1977.
    #:
    #: So both are kept. The body is read from whichever page won, and the
    #: running header — volume, issue, page, publication date, five columns
    #: that currently score 236-240 out of 240 — is read from the layer.
    layer: str = ""

    @property
    def unread(self) -> bool:
        """A page whose content is in a picture nobody has read."""
        return self.has_image and len(self.text.strip()) < _CAPTION_ONLY

    @property
    def is_annex(self) -> bool:
        """A map or schedule attached to the instrument rather than part of it."""
        head = _NOT_THAI.sub("", _TONES.sub("", self.text[:400]).replace("ำ", "า"))
        return bool(_ANNEX.search(head[:_HEADING]))


#: The operator numbers annexes with a suffix — ``100012.1`` is a sheet
#: belonging to ``100012`` — and one file in the corpus is numbered
#: ``1000012.1``, seven digits before the dot. ``\d{5,6}`` read the first six
#: of those as ``100001`` and wrote the annexe's text over that document's,
#: silently, because a stem that merely *contains* five digits was enough.
#:
#: Anchored at the start and allowed to run to seven digits with an optional
#: suffix, so a name is taken whole or not at all.
_DOCUMENT_NUMBER = re.compile(r"^(\d{5,7}(?:\.\d+)?)")


@dataclass(slots=True)
class Document:
    path: Path
    pages: list[Page]

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def number(self) -> str:
        """The operator's document number, from the file name."""
        match = _DOCUMENT_NUMBER.match(self.path.stem)
        return match.group(1) if match else self.path.stem

    def text(self, limit: int | None = None) -> str:
        joined = "\n\n".join(page.text for page in self.pages)
        return joined[:limit] if limit else joined

    @property
    def body_text(self) -> str:
        """The document without the sheets that only illustrate it.

        A map annex prints the districts *around* the area a law covers, and
        the place rule reads every name it finds. While those sheets were
        pictures nobody had read the two never met; reading them turned
        ``วัดโบสถ์, เมืองพิษณุโลก`` into ``พิชัย`` — a district of the next
        province, named on the map only because it borders the one the law is
        about.

        The sheets say what they are on their first line: ``แผนที่ท้าย…``,
        ``มาตราส่วน 1:50000``. 285 pages of the corpus open that way.
        """
        return "\n\n".join(p.text for p in self.pages if not p.is_annex)

    @property
    def header_text(self) -> str:
        """The document as the Gazette header should be read from it.

        Identical to :meth:`text` except on pages OCR replaced, where the text
        layer is used instead. Those pages have unreadable Thai and readable
        numerals, and the header is numerals.
        """
        return "\n\n".join(page.layer or page.text for page in self.pages)

    @property
    def scanned_pages(self) -> int:
        return sum(1 for page in self.pages if page.source == "ocr")

    @property
    def blind_pages(self) -> int:
        """Pages recognised with nothing else to fall back on.

        Not the same as :attr:`scanned_pages`, and the difference decides how
        much to trust the reading. A page with no text layer at all was
        recognised because there was no choice, and whatever recognition got
        wrong is simply wrong. A page that *had* a layer was recognised because
        the layer lied — ``looks_garbled`` or ``looks_collapsed`` caught it —
        and the layer is still here, holding the numerals the rules read. That
        page is better off than it was, not worse.
        """
        return sum(1 for page in self.pages if page.source == "ocr" and not page.layer)

    @property
    def unread_pages(self) -> tuple[int, ...]:
        """Pages whose content is a picture nothing has read."""
        return tuple(p.number for p in self.pages if p.unread)

    def save(self, into: Path) -> Path:
        """Keep the extracted text so nothing has to extract it again.

        Two files. The JSON is what the machine reads back — pages kept apart,
        because a rule that counts sections needs to know where one page ends.
        The ``.txt`` is what a person reads, and is the first thing to open
        when a cell looks wrong.
        """
        into.mkdir(parents=True, exist_ok=True)
        (into / f"{self.number}.txt").write_text(self.text(), encoding="utf-8")
        record = into / f"{self.number}.json"
        record.write_text(
            json.dumps(
                {
                    "number": self.number,
                    "source_pdf": str(self.path),
                    "unread_pages": list(self.unread_pages),
                    "pages": [
                        {
                            "number": p.number,
                            "source": p.source,
                            "has_image": p.has_image,
                            "text": p.text,
                            "layer": p.layer,
                        }
                        for p in self.pages
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return record


def load(record: Path) -> Document:
    """A document read back from saved text, with no PDF involved."""
    stored = json.loads(record.read_text(encoding="utf-8"))
    return Document(
        path=Path(stored["source_pdf"]),
        pages=[
            Page(p["number"], p["text"], p["source"],
                 has_image=p.get("has_image", False), layer=p.get("layer", ""))
            for p in stored["pages"]
        ],
    )


def extract(paths: list[Path], into: Path, *, ocr: bool = True, mode: str = "text") -> int:
    """Every PDF to saved text. The one expensive step, done once.

    Rendering a page at 300 dpi and recognising it takes seconds; reading the
    result back takes none. Separating them is what makes it reasonable to
    re-run the rules twenty times in an afternoon.
    """
    written = 0
    for position, path in enumerate(paths, start=1):
        progress.document(position, len(paths), path.name)
        try:
            document = read(path, ocr=ocr, mode=mode)
        except Exception as exc:  # noqa: BLE001 — one bad file is not a bad run
            log.error("%s ล้ม: %s: %s", path.name, type(exc).__name__, exc)
            continue
        record = document.save(into)
        written += 1
        lost = document.unread_pages
        layer = sum(1 for p in document.pages if p.source.startswith("text-layer"))
        added = sum(1 for p in document.pages if p.source == "text-layer+ocr")
        progress.step(
            "อ่าน", "pymupdf",
            f"{len(document.pages)} หน้า · text-layer {layer} · ocr {document.scanned_pages}"
            + (f" · อ่านภาพเพิ่ม {added}" if added else "")
            + f" · {len(document.text()):,} ตัวอักษร"
            + (f" · ⚠ {len(lost)} หน้าเป็นภาพ (หน้า {', '.join(map(str, lost))})" if lost else ""),
        )
        progress.step("เก็บ", "แฟ้มข้อความ", f"{record.parent}/{record.stem}.txt + .json")
    return written


def read(path: Path, *, ocr: bool = True, mode: str = "text") -> Document:
    """Every page of a PDF as repaired Thai text.

    ``mode`` is ``text`` or ``image``; see ``MODES``.
    """
    import fitz  # imported here so `lawscan --help` works without PyMuPDF

    pages: list[Page] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            raw = page.get_text() or ""
            source = "text-layer"
            pictured = _has_picture(page)

            layer = ""
            if ocr and (len(raw.strip()) < _TEXT_LAYER_MIN
                        or looks_garbled(raw) or looks_collapsed(raw)):
                # Kept only when there was something to keep: a page whose
                # layer was empty has no numerals to preserve.
                layer = raw if raw.strip() else ""
                raw = _recognise(page)
                source = "ocr"
            elif ocr and mode == "image" and pictured:
                # Only the pictures, and only what is inside them.
                drawn = _recognise_pictures(page).strip()
                if drawn:
                    raw = f"{raw}\n{drawn}"
                    source = "text-layer+ocr"

            pages.append(Page(index, raw, source, has_image=pictured, layer=layer))

    # The header is stripped after every page is read, not during, because
    # "keep the first one" means the first one in the document — and the first
    # page of a Gazette PDF is often a title page carrying no header at all.
    # Stripping per page against index == 1 threw the only copy away.
    _strip_headers(pages)

    document = Document(path, pages)

    # Said out loud, every time. A document that lost half its pages to
    # pictures used to reach the CSV looking exactly like one that lost none.
    lost = document.unread_pages
    if lost:
        log.warning(
            "%s: %d/%d หน้าเป็นภาพที่ยังอ่านไม่ได้ (หน้า %s) — ผลลัพธ์อาจไม่ครบ",
            path.name, len(lost), len(pages), ", ".join(str(n) for n in lost),
        )
    return document


#: Below this share of Thai letters, a page's text layer is not Thai text.
#: Chosen from the corpus rather than guessed: of 3,424 documents, 846 sit at
#: 0.2 or below and 2,415 at 0.6 or above, with almost nothing between. Any
#: value in that gap separates them; the middle is the one that stays right if
#: a future document lands nearer an edge.
_THAI_FLOOR = 0.4

#: Below this many letters the ratio is noise — a page holding "หน้า 3" is one
#: character away from either verdict. Such a page is already going to OCR for
#: being short, and this must not be what decides it.
_ENOUGH_LETTERS = 20


#: Letters that are neither Thai nor ASCII. A Gazette page prints English —
#: ``(account administrator)``, ``ISO``, a botanical name — so Latin letters
#: are not evidence of anything. Latin-1 letters are: ``Ö`` ``Ü`` ``Þ`` ``Ý``
#: belong to no language this corpus is written in, and they appear only where
#: a subset font's glyph table has slipped and the layer is returning the wrong
#: characters for the right shapes.
#:
#: This is the half of the lying-layer problem the Thai-share test cannot see.
#: That test asks how much of the page is Thai, and a layer that turned half
#: its letters into symbols still reads as 0.42 Thai — over the floor, so the
#: page was kept. Measured over the corpus the two are cleanly apart: the pages
#: that need recognising carry 13% to 29% of these, and pages that are merely
#: bilingual carry none at all.
_FOREIGN_CEILING = 0.05


def _foreign_share(letters: list[str]) -> float:
    """How much of this page is written in an alphabet nothing here uses."""
    if not letters:
        return 0.0
    odd = sum(1 for ch in letters if ord(ch) > 127 and not ("\u0e00" <= ch <= "\u0e7f"))
    return odd / len(letters)


def looks_garbled(text: str) -> bool:
    """Whether a page's text layer decoded to something that is not Thai.

    The failure this exists for is not a missing text layer but a *lying* one:
    a subset font whose glyph table does not line up with Unicode returns a
    full page of Latin noise, and every check that asks "is there text?"
    answers yes. ``ในพระปรมาภิไธย`` arrives as ``Ĕîóøąðøöćõĉĕí÷`` — same
    length, same shape on the page, nothing to notice downstream except five
    date columns that come out empty.

    Says true only when it can prove the damage. Rendering and recognising a
    page takes three seconds and can only make a correct page worse, so a page
    this cannot judge keeps the text it has: a schedule of rates carries no
    letters to measure, and a page with a line of them is one character away
    from either verdict. Both are already covered by the length rule.

    Judged on the share of *letters* that are Thai rather than of all
    characters, so the digits and commas of that schedule do not count against
    the Thai around them.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < _ENOUGH_LETTERS:
        return False
    if thai_char_ratio("".join(letters)) < _THAI_FLOOR:
        return True
    return _foreign_share(letters) > _FOREIGN_CEILING


#: Spellings that exist only on a page this fault has been over. Each is a
#: real word with ``า`` collapsed into ``ำ``, and none of them is a word in its
#: own right — there is no ``กำร``, no ``ควำม``, no ``งำน``. Counted over the
#: corpus, every one of them turns up twenty to forty times less often than the
#: word it is a ruin of, which is what a fault confined to a few pages looks
#: like. ``ทำง`` was a candidate and is not here: it sits inside ``ทำงาน``,
#: which is spelled exactly that way and is correct.
_COLLAPSED = re.compile(
    "กำร|ควำม|ตำม|นำย|หมำย|งำน|รำย|ประกำศ|กล่ำว|ผ่ำน|"
    "ต่ำง|อย่ำง|สำมำรถ|หน้ำ|อำนำจ|สถำน"
)

#: One impossible word is enough when the page's vowels are also wrong. A clean
#: Thai page spends about an eighth of its ``า``/``ำ`` budget on ``ำ``; a third
#: is already far outside that, and a collapsed page runs past nine tenths.
_AM_SHARE = 0.30


def looks_collapsed(text: str) -> bool:
    """Whether this text layer wrote every ``า`` as ``ำ``.

    A second way for a text layer to lie, and the one :func:`looks_garbled`
    cannot see: every character it returns is a valid Thai letter, so the
    Thai-share test passes and the page sails through holding ``กำรนำส่ง`` where
    it should hold ``การนำส่ง``.

    It cannot be undone by rule. :func:`repair_swapped_sara_aa` assumes the
    font *exchanged* the two vowels, and exchanging them back is exact. This
    fault is not an exchange but a collapse — ``า`` becomes ``ำ`` and ``ำ``
    stays ``ำ`` — so the two are no longer distinguishable and swapping back
    turns ``สำนักงำน`` into ``สานักงาน``, trading one error for two. What the
    page said survives only in its picture, so a page this returns true for is
    recognised instead, and its layer is kept for the numerals.

    Normalises before looking, because the gate this feeds runs before the
    normalising does: the raw layer writes ``อ ำนำจ`` with the sara-am adrift,
    and none of the spellings below would match it.
    """
    text = restore_sara_am(normalize_unicode(restore_pua_marks(text)))
    hits = len(_COLLAPSED.findall(text))
    if hits >= 2:
        return True
    if not hits:
        return False
    am, aa = text.count("ำ"), text.count("า")
    return am + aa >= _ENOUGH_LETTERS and am / (am + aa) > _AM_SHARE


def _has_picture(page: object) -> bool:
    """Whether this page carries a picture big enough to be its content."""
    try:
        images = page.get_images(full=True)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — a page that cannot be asked has none
        return False
    # PyMuPDF gives (xref, smask, width, height, ...) per image.
    return any(image[2] * image[3] >= _MEANINGFUL_IMAGE for image in images)


def _recognise_pictures(page: object) -> str:
    """Read what is drawn inside the pictures, and nothing else.

    Clipped to each picture's own rectangle rather than run over the page.
    Recognising the whole page re-read the text that was already there and
    returned it worse: on one document it added a second Gazette header saying
    "เล่ม oma ตอนที 12 ก … 25203" beside the real "เล่ม ๑๓๗ … ๒๕๖๓", which the
    header rule would have been entitled to believe. A repair that invents a
    publication date is worse than the gap it fills.
    """
    found: list[str] = []
    try:
        images = page.get_images(full=True)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return ""

    for image in images:
        if image[2] * image[3] < _MEANINGFUL_IMAGE:
            continue
        try:
            for rect in page.get_image_rects(image[0]):  # type: ignore[attr-defined]
                text = _recognise(page, clip=rect).strip()
                if text:
                    found.append(text)
        except Exception as exc:  # noqa: BLE001 — one bad picture is not a bad page
            log.debug("อ่านภาพไม่สำเร็จ: %s", type(exc).__name__)
    return "\n".join(found)


#: 400 dpi. Thai tone marks sit above the line and are the first thing lost at
#: a lower resolution; 600 was measured against 400 on three documents and
#: recovered nothing more for five times the time.
DPI = 400


def _by_vision(image: object) -> str | None:
    """macOS's own recogniser, or None where it is not available.

    Tesseract cannot read Thai numerals in this corpus. Measured against the
    operator's register over 206 documents it returned ๔ as ๕ two hundred and
    seven times, ๘ as ๕, ๗ as ๓ — and the wrong digits are well-formed, so
    ``พ.ศ. ๒๕๔๒`` arrives as ``พ.ศ. 2552`` and nothing downstream can tell.
    Every page it read had its volume and issue wrong: 153 of 153. Every page
    taken from the text layer instead had them right: 31 of 31.

    The recogniser built into macOS reads the same pages correctly. On the
    three documents measured against the digits held in the PDF's own text
    layer it recovered every year, where Tesseract recovered none.
    """
    try:
        from ocrmac import ocrmac
    except ImportError:
        return None
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        image.save(handle.name)  # type: ignore[attr-defined]
        found = ocrmac.OCR(handle.name, language_preference=["th-TH"],
                           recognition_level="accurate").recognize()

    lines: list[str] = []
    for text, _, box in found:
        gap = (_LOST_NUMERATOR.search(text) or _LOST_POINT.search(text)
               or _LIST_LOOKALIKE.search(text))
        if gap:
            again = _reread(image, box)
            # Only where reading it again actually closed the gap. A second
            # look that returns the same fault, or wanders off into the line
            # beside it, is not an improvement — and the length guard keeps a
            # crop that drifted onto a neighbour from replacing the line.
            better = (again and not _LOST_NUMERATOR.search(again)
                      and not _LOST_POINT.search(again)
                      and not _LIST_LOOKALIKE.search(again)
                      and 0.6 <= len(again) / max(1, len(text)) <= 1.6)
            if better:
                text = again
        lines.append(text)
    return "\n".join(lines)


#: A slash with no digit in front of it. ``เรื่องพิจารณาที่ ๘/๒๕๖๘`` comes
#: back ``เรื่องพิจารณาที่ /๒๕๖๘`` — the recogniser reads the whole line at
#: once and loses the numerator against the separator. 18 of the 62 numbers
#: missed over 128 pages of known text are this, and the number lost is a case
#: or meeting number, so unlike the year behind the slash there is nothing to
#: infer it from. Reading that fragment again on its own recovers it.
_LOST_NUMERATOR = re.compile(r"(?<![๐-๙\d])/[๐-๙\d]")

#: A comma-grouped number with more than three digits behind the comma. Thai
#: writes ``๑๐,๐๘๘.๘๑`` and the recogniser returns ``๑๐,๐๘๘๘๑`` — the decimal
#: point goes and the digits close up, so a sum of ten thousand baht reads as
#: a million. Sometimes a digit goes with it: ``๒,๒๑๕.๖๔๔`` came back
#: ``๒,๒๕๖๔๔``. Neither can be repaired by rule — putting the point back three
#: digits along would turn the second one into ๒,๒๕๖.๔๔, a number that was
#: never printed. Reading the fragment again recovers both.
_LOST_POINT = re.compile(r"[๐-๙\d],[๐-๙\d]{4,}")

#: A list marker read as the letter it looks like. ``๑.`` opening a line comes
#: back ``ด.``; the numeral repair leaves it alone, and correctly so — there is
#: no numeral beside it to make the case, and ``ด`` is a common letter.
_LIST_LOOKALIKE = re.compile(r"(?:^|\n)\s*[ดo]\s*\.\s")


def _reread(image: object, box: list[float]) -> str:
    """One fragment of a page, cropped out and read again at twice the size."""
    from PIL import Image

    from ocrmac import ocrmac

    width, height = image.size  # type: ignore[attr-defined]
    x, y, w, h = box
    left, right = int(x * width) - 20, int((x + w) * width) + 20
    top, bottom = int((1 - y - h) * height) - 10, int((1 - y) * height) + 10
    crop = image.crop((max(0, left), max(0, top),  # type: ignore[attr-defined]
                       min(width, right), min(height, bottom)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        crop.save(handle.name)
        found = ocrmac.OCR(handle.name, language_preference=["th-TH"],
                           recognition_level="accurate").recognize()
    return " ".join(text for text, _, _ in found)


#: A page carrying a number written as a fraction — a case number, a letter
#: number, a meeting number. These are where the recogniser loses digits: 25 of
#: the 54 numbers still missed over 128 pages of known text sit on pages like
#: this, and 13% of the corpus's pages carry one.
_FRACTION = re.compile(r"[๐-๙\d]{1,4}\s*/\s*[๐-๙\d]{1,4}")

#: Read again at this, when the first pass says the page is one of the hard
#: ones. Measured over eight pages known to lose digits: 400 dpi finds 88.5% of
#: the numbers printed, 600 finds 91.0%, and the two together find 92.9%.
#: 900 was measured beside them and added nothing. Combining is safe in a way
#: a repair rule is not — both readings are things the recogniser saw, so the
#: union can gain a number but cannot invent one.
_SECOND_DPI = 600


def _numbers(text: str) -> set[str]:
    """Every number in ``text``, spacing inside one number closed up."""
    return set(re.findall(r"\d+", re.sub(r"(?<=\d)\s+(?=\d)", "", thai_to_arabic_digits(text))))


def _combined(first: str, second: str) -> str:
    """The fuller of two readings, plus the lines the other one alone has.

    Whichever read found more numbers is the page; lines from the other that
    carry a number missing from it are added underneath. Appending rather than
    weaving them in: the two readings order the page differently, and a line
    dropped into the wrong place reads as part of a sentence it does not belong
    to. At the foot it is plainly a second reading.
    """
    base, other = ((second, first) if len(_numbers(second)) > len(_numbers(first))
                   else (first, second))
    held = _numbers(base)
    extra = [line for line in other.splitlines()
             if line.strip() and _numbers(line) - held]
    return base if not extra else base + "\n" + "\n".join(extra)


def _recognise(page: object, *, clip: object = None) -> str:
    """Recognise one page, or return nothing if the tools are not installed.

    A missing recogniser is a fact about the machine, not an error in the
    document — the page comes back empty, the rules find nothing on it, and
    that is visible rather than fatal.
    """
    try:
        import io

        from PIL import Image
    except ImportError:
        _engine_missing("Pillow ยังไม่ได้ติดตั้ง")
        return ""

    try:
        pixmap = page.get_pixmap(dpi=DPI, clip=clip)  # type: ignore[attr-defined]
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    except Exception as exc:  # noqa: BLE001 — one bad page is not a bad document
        log.warning("เรนเดอร์หน้านี้ไม่สำเร็จ: %s", type(exc).__name__)
        return ""

    seen = _by_vision(image)
    if seen is not None:
        seen = repair_clipped_years(repair_numeral_lookalikes(seen))
        if clip is None and _FRACTION.search(seen):
            try:
                bigger = page.get_pixmap(dpi=_SECOND_DPI)  # type: ignore[attr-defined]
                again = _by_vision(Image.open(io.BytesIO(bigger.tobytes("png"))))
            except Exception as exc:  # noqa: BLE001
                log.warning("อ่านซ้ำหน้านี้ไม่สำเร็จ: %s", type(exc).__name__)
                again = None
            if again:
                seen = _combined(seen, repair_clipped_years(
                    repair_numeral_lookalikes(again)))
        return seen

    try:
        import pytesseract
    except ImportError:
        _engine_missing("ไม่มีทั้ง ocrmac และ pytesseract")
        return ""
    try:
        return pytesseract.image_to_string(image, lang="tha+eng")
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "TesseractNotFoundError":
            _engine_missing("ไม่พบโปรแกรม tesseract")
            return ""
        log.warning("อ่านหน้านี้ไม่สำเร็จ: %s", type(exc).__name__)
        return ""


#: Said once per run, not once per page. Ninety-one documents produced the same
#: line hundreds of times and it read as noise rather than as the one thing
#: standing between the corpus and eighteen unread pages.
_ENGINE_WARNED = False


def _engine_missing(why: str) -> None:
    global _ENGINE_WARNED
    if _ENGINE_WARNED:
        return
    _ENGINE_WARNED = True
    log.warning(
        "%s — หน้าที่เป็นภาพจะว่างเปล่า\n"
        "  ติดตั้งด้วย:  brew install tesseract tesseract-lang\n"
        "  (ต้องมี tesseract-lang ด้วย ตัวหลักไม่มีภาษาไทย)",
        why,
    )


def _header_from_layer(text: str, layer: str) -> str:
    """The recognised page's header, replaced by the one the layer printed.

    A page is recognised because its layer lied about the Thai, and the lie is
    confined to the letters: the volume, issue and date are Thai numerals, and
    a font that collapses ``า`` into ``ำ`` leaves ``๒๕๖๓`` alone. Recognition
    is the other way round — it reads the body well and the header badly,
    because the header is one small line above a rule and it comes back as
    ``15 กุมภาพันธี์ 25203`` where the layer says ``๑๔ กุมภาพันธ์ ๒๕๖๓``.

    The rules never saw this: they read numerals from ``page.layer`` and got
    the right date all along. The model reads ``page.text`` and got 100006
    wrong by a day and forty years. So each side keeps what it is good at —
    the layer's header, the recognised body.

    Both are searched with digits normalised, because the pattern counts digits
    and the layer writes them in Thai; the replacement is the layer's own text.
    """
    here = _RUNNING_HEADER.search(thai_to_arabic_digits(text))
    there = _RUNNING_HEADER.search(thai_to_arabic_digits(layer))
    if here is None or there is None:
        return text
    return text[:here.start()] + layer[there.start():there.end()] + text[here.end():]


#: The two numbers a Gazette title is built from. Both are small print, and
#: both are printed in Thai numerals that recognition mangles.
#:
#: The year pattern takes four digits or more so a mangled ``25205`` still
#: matches its slot. The issue pattern reads whatever sits between
#: ``ฉบับที่`` and its closing bracket, digits or not, because recognition
#: returned ``(ฉบับที on)`` for ``(ฉบับที่ ๓)`` — a slot with no digit left in
#: it at all, which a digit pattern would skip and leave misaligned.
#: Slots whose value the layer holds and recognition mangles, each aligned on
#: its own. ``พ.ศ.`` and ``ฉบับที่`` may be replaced first-alone when the two
#: sides cannot be matched up — a year is set in the largest type on the page
#: and there is one of it. The Gazette's furniture may not: ``ข้อ`` appears a
#: dozen times and the first is no more anchored than the rest.
#:
#: ``[าำ]`` inside the keywords, not only the values. The layer that needs
#: repairing is the collapsed one, so it prints ``หน้ำ`` and ``มำตรำ``, and a
#: keyword spelled the right way matches the recognised side only — which left
#: the two sides holding different counts and the repair declining.
#:
#: Split one keyword per pattern rather than joined by alternation, because
#: recognition drops a slot here and there: page one of 100021 shows nine in
#: the layer and eight in the reading, and one joined pattern refuses the whole
#: page over it while ``เล่ม`` and ``หน้า`` line up perfectly on their own.
#: A grouped thousand is one slot, not two. 100121 page eight charges a fee
#: "สำหรับแต่ละ ๓,๓๐๐ กิโลวัตต์", and a value that stops at the comma counted
#: ``3`` and ``300`` as separate slots on the layer's side against the single
#: ``coo`` recognition returned — three slots against five, and the page was
#: refused. The grouped form comes first so it is preferred where both fit.
_VALUE = (
    r"([\d๐-๙]{1,3}(?:,[\d๐-๙]{3})+|[\d๐-๙A-Za-z]{1,4})(?![\d๐-๙A-Za-z])"
)
_FROM_LAYER: tuple[tuple[re.Pattern[str], bool], ...] = (
    # Two digits, not four. A year is always four on the layer's side, but the
    # recognised side is where the fault is: 100117 page four came back
    # ``พ.ศ. 250`` for ``พ.ศ. ๒๕๐๗``, a digit short. Demanding four made the
    # broken slot the one the repair could not see, which is backwards.
    (re.compile(r"(พ\.ศ\.\s*)([\d๐-๙]{2,6})"), True),
    (re.compile(r"(ฉบับที่?\s*)([^)\s]{1,8})(?=\))"), True),
    *((re.compile(rf"({word}\s+)" + _VALUE), False) for word in (
        r"เล่ม", r"ตอนที่?", r"หน้[าำ]", r"ข้อ", r"ม[าำ]ตร[าำ]", r"วันที่?",
    )),
    # A quantity has no keyword in front of it, only a unit behind: "อาคารที่มี
    # ความสูงเกิน oo เมตร", "แต่ละ coo กิโลวัตต์". 117 documents of the corpus
    # carry one. Anchored on the unit instead, with an empty first group so the
    # replacement machinery above needs no special case.
    (re.compile(
        r"()(?<=[\s(])([\d๐-๙]{1,3}(?:,[\d๐-๙]{3})+|[\d๐-๙A-Za-z]{1,4})"
        r"(?=\s*(?:เมตร|ตัน|กิโลวัตต์|ต[าำ]ร[าำงง]*เมตร"
        r"|บ[าำ]ท|วัน|ปี|คน|ฉบับ|ลิตร|กิโลกรัม))"
    ), False),
)


#: How alike two slots have to read before one is taken to stand for the
#: other. The eleven true pairs on 100015's page score 0.91 and above; the two
#: quantities on 100121's page seven that genuinely cannot be told apart —
#: recognition offering ``500`` where the layer prints ``๑๐๐`` — score 0.50 and
#: 0.65, and are left alone.
_SAME_SLOT = 0.75

_ONLY_LETTERS = re.compile(r"[^ก-ฮ]")


def _surroundings(text: str, start: int, end: int) -> str:
    """The Thai letters either side of a slot, digits and marks dropped.

    Both sides, because the first slot on a page has nothing in front of it —
    the volume in the masthead, the year in a title — and a key that is empty
    on the left matches every other empty key perfectly.

    Letters only, because the two sides disagree about everything else: one
    prints ``ำ`` where the other prints ``า``, one keeps the tone mark the
    other dropped, and the digits are the very thing being decided.
    """
    before = _ONLY_LETTERS.sub("", text[max(0, start - 30) : start])[-18:]
    return before + "|" + _ONLY_LETTERS.sub("", text[end : end + 30])[:18]


def _same_slot(
    pattern: re.Pattern[str], layer: str, text: str
) -> list[tuple[re.Match[str], re.Match[str]]]:
    """Recognised slots paired with the layer slots standing in the same place.

    Counting was the old rule: replace every slot when both sides hold the same
    number of them, and refuse the page otherwise. It refused often. 100015's
    page prints eleven years and recognition returned eight, so ten years kept
    the digits recognition guessed — ``๒๕๓๔`` came back ``2535``, ``๒๕๔๕`` came
    back ``2555``, ``๒๕๖๓`` came back ``2523``. Every one is a well-formed year
    in the right range, so nothing downstream can tell it is the wrong one.

    Reading what surrounds a slot settles it without counting. A year in a Thai
    instrument sits inside a phrase that names it — ``ตำมระเบียบบริหำรรำชกำร
    แผ่นดิน พ.ศ. ๒๕๓๔`` — and that phrase survives recognition well enough to
    recognise, even where the digits did not. Pairs are taken in order and each
    layer slot is spent once, so a match cannot reach back past one already
    used, and a slot with no convincing partner keeps what recognition read.
    """
    theirs = list(pattern.finditer(layer))
    ours = list(pattern.finditer(text))
    if not theirs or not ours:
        return []
    if len(theirs) == len(ours):
        return list(zip(ours, theirs))
    keys = [_surroundings(layer, m.start(), m.end()) for m in theirs]
    pairs: list[tuple[re.Match[str], re.Match[str]]] = []
    at = 0
    for mine in ours:
        key = _surroundings(text, mine.start(), mine.end())
        best, alike = None, 0.0
        for j in range(at, len(theirs)):
            ratio = SequenceMatcher(None, key, keys[j]).ratio()
            if ratio > alike:
                best, alike = j, ratio
        if best is None or alike < _SAME_SLOT:
            continue
        pairs.append((mine, theirs[best]))
        at = best + 1
    return pairs


def _numerals_from_layer(text: str, layer: str) -> str:
    """The recognised page's numbers, replaced by the ones its layer printed.

    The fault that sends a page to recognition is a fault in its *letters* —
    a font that collapsed ``า`` into ``ำ``, or a glyph table that slipped into
    Latin-1. Neither touches the digits, so a collapsed layer still holds
    ``พ.ศ. ๒๕๖๔`` exactly as the paper prints it. Recognition is the other way
    round: it reads the body well and small print badly, and a Thai numeral is
    the smallest print on the page.

    Three documents showed the three ways it goes wrong. 100121 came back
    ``พ.ศ. 25205`` for ``๒๕๖๔`` — malformed, and catchable by shape. 100021
    came back ``พ.ศ. 2523`` for ``๒๕๖๓`` — a perfectly well-formed year that is
    simply the wrong one, which no shape test can catch. 100015 came back
    ``(ฉบับที on)`` for ``(ฉบับที่ ๓)`` — the digit gone entirely. 578
    documents of the corpus carry at least one.

    Only when the layer is collapsed rather than garbled: a glyph table that
    slipped returns nonsense for digits too, and its numbers are worth no more
    than the recognised ones. Each pattern is paired on its own by
    ``_same_slot``, so a replacement cannot land on the wrong slot.
    """
    if not layer or looks_garbled(layer) or not looks_collapsed(layer):
        return text
    # The layer is still raw here — the repair runs before the normalising
    # does, by design, so the recognised text can be corrected before anything
    # else reads it. Raw means the Gazette's broken font writes its masthead in
    # private-use codepoints, ``เล\uf70aม ๑๓๗``, and a pattern looking for
    # ``เล่ม`` walks straight past the one slot on the page it was written for.
    layer = normalize_text(repair_swapped_sara_aa(layer))
    for pattern, title_slot in _FROM_LAYER:
        pairs = _same_slot(pattern, layer, text)
        if not pairs and title_slot:
            # Nothing on the page read alike enough to pair, and this is a
            # pattern whose first slot is the instrument's own — the year in
            # the title, the amendment number beside it. That one is safe where
            # the rest is not: it is set in the largest type on the sheet, it
            # comes first on both sides, and every date column is built from
            # it. Take it on position alone rather than leave the title unread.
            theirs = next(pattern.finditer(layer), None)
            mine = next(pattern.finditer(text), None)
            if theirs and mine:
                pairs = [(mine, theirs)]
        taken = {mine.start(): theirs.group(2) for mine, theirs in pairs}
        if taken:
            text = pattern.sub(
                lambda m: m.group(1) + taken.get(m.start(), m.group(2)), text
            )
    return text


def _strip_headers(pages: list[Page]) -> None:
    """Repair the Thai, and keep exactly one copy of the running header.

    The header is where the volume, issue and publication date are read from,
    so one copy has to survive. Every later copy interrupts a sentence mid
    clause and has to go.

    ``repair_swapped_sara_aa`` runs per page rather than over the whole
    document because the fault it fixes belongs to a font, and a document can
    change font between its body and an appendix.
    """
    seen = False
    for page in pages:
        # Normalised before the numbers are read, not after. Recognition writes
        # ``พ .ศ. ๒๕๓๔`` and ``พ.ศ.๒๕๓๔`` as readily as the spaced form, and
        # normalising is what settles them into one shape. Doing it afterwards
        # left three of 100015's eleven years invisible to the repair at the
        # moment it ran and printed in the file a moment later, still holding
        # the digits recognition guessed.
        text = normalize_text(repair_swapped_sara_aa(page.text))
        if page.layer:
            text = _header_from_layer(text, page.layer)
            text = _numerals_from_layer(text, page.layer)
        if seen:
            text = _RUNNING_HEADER.sub("", text)
        elif _RUNNING_HEADER.search(text):
            seen = True
        page.text = text
        # The layer gets the same treatment or it cannot be read either. A
        # broken Gazette font writes its header in private-use codepoints —
        # ``เล\uf70aม ๑๔๐`` — and ``normalize_text`` is what turns those into
        # Thai. Skipping it left the layer holding a header no rule could see,
        # which is the whole reason the layer is kept.
        if page.layer:
            page.layer = normalize_text(repair_swapped_sara_aa(page.layer))
