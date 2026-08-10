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
from pathlib import Path

from lawscan import progress
from lawscan.ocr.thai_text import (
    normalize_text, repair_swapped_sara_aa, thai_char_ratio,
)

log = logging.getLogger(__name__)

#: Below this many characters a page is treated as having no usable text layer,
#: whatever the PDF claims. A scanned page often carries a handful of stray
#: characters from a watermark or a stamp.
_TEXT_LAYER_MIN = 40

#: The running header the Gazette prints on every page. Kept on the first page
#: — it is where the volume, issue and publication date are read from — and
#: dropped from the rest, where it interrupts a sentence mid-clause.
_RUNNING_HEADER = re.compile(
    r"^\s*(?:หน้า\s*\d+\s*\n)?\s*เล่ม\s*\S+\s*ตอน\S*\s*\S+\s*ราชกิจจานุเบกษา[^\n]*\n",
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
        match = re.search(r"(\d{5,6})", self.path.stem)
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
            if ocr and (len(raw.strip()) < _TEXT_LAYER_MIN or looks_garbled(raw)):
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
    return thai_char_ratio("".join(letters)) < _THAI_FLOOR


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


def _recognise(page: object, *, clip: object = None) -> str:
    """Recognise one page, or return nothing if the tools are not installed.

    A missing Tesseract is a fact about the machine, not an error in the
    document — the page comes back empty, the rules find nothing on it, and
    that is visible rather than fatal.
    """
    try:
        import io

        import pytesseract
        from PIL import Image
    except ImportError:
        _engine_missing("pytesseract ยังไม่ได้ติดตั้ง")
        return ""

    try:
        # 300 dpi. Thai tone marks sit above the line and are the first thing
        # lost at a lower resolution.
        pixmap = page.get_pixmap(dpi=300, clip=clip)  # type: ignore[attr-defined]
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang="tha+eng")
    except Exception as exc:  # noqa: BLE001 — one bad page is not a bad document
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
        text = repair_swapped_sara_aa(page.text)
        if seen:
            text = _RUNNING_HEADER.sub("", text)
        elif _RUNNING_HEADER.search(text):
            seen = True
        page.text = normalize_text(text)
        # The layer gets the same treatment or it cannot be read either. A
        # broken Gazette font writes its header in private-use codepoints —
        # ``เล\uf70aม ๑๔๐`` — and ``normalize_text`` is what turns those into
        # Thai. Skipping it left the layer holding a header no rule could see,
        # which is the whole reason the layer is kept.
        if page.layer:
            page.layer = normalize_text(repair_swapped_sara_aa(page.layer))
