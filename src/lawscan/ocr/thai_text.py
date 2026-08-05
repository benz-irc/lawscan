"""Thai text normalization primitives.

Rule that governs this whole module (brief §9): never remove source text that a
reviewer would need as legal evidence. Everything here is either a reversible
character-level mapping or removal of artifacts the OCR layer introduced —
never removal of substantive content.
"""

from __future__ import annotations

import re
import unicodedata

import logging

log = logging.getLogger(__name__)

#: Thai digits ๐-๙ -> ASCII 0-9.
THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙"
_THAI_DIGIT_MAP = {ord(t): str(i) for i, t in enumerate(THAI_DIGITS)}
_ARABIC_TO_THAI = {str(i): t for i, t in enumerate(THAI_DIGITS)}

#: Zero-width and directional marks that scanners and PDF producers inject.
_INVISIBLE = re.compile(r"[​‌‍‎‏﻿­]")

#: Thai block, including Thai digits and combining marks.
_THAI_CHAR = re.compile(r"[฀-๿]")

#: Combining vowels and tone marks — they carry no width and must never be used
#: as a word-splitting signal.
_THAI_COMBINING = re.compile(r"[ัิ-ฺ็-๎]")

#: Sara am, written out. Tesseract returns it as its two visual parts —
#: nikhahit U+0E4D then sara aa U+0E32 — rather than the single character
#: U+0E33 that a keyboard produces and a PDF text layer contains.
#:
#: Unicode will not put it back together. U+0E33's decomposition is tagged
#: <compat>, not canonical, so NFC and NFKC both leave the pair exactly as it
#: arrived. The text then looks right and behaves wrong: สำนัก typed by a
#: reader never matches สํานัก read from a scan, so search misses it, duplicate
#: detection misses it, and the same word sorts apart from itself depending on
#: whether it came from a text layer or a scan.
_SARA_AM_PARTS = re.compile("\u0e4d\u0e32")

_MULTI_SPACE = re.compile(r"[ \t  - ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?\)\]}])")


#: Thai fonts of the Angsana / Cordia / TH Sarabun family do not encode a
#: combining mark that has to be raised or shifted. They put the positional
#: variant in the Private Use Area instead, so ตำแหน่ง is written
#: ต ำ แ ห น U+F70A ง and กษัตริย์ ends U+F70E.
#:
#: Nothing downstream can read those. The text survives normalization intact,
#: reaches the model, and the model drops the character it cannot interpret —
#: which is how a law called "...ว่าด้วยการป้องกัน..." arrives in the corpus as
#: "...วาดวยการปองกัน..." and matches nothing. The marks are not lost by OCR;
#: they are lost by being unreadable, one step later, in silence.
#:
#: Every entry below was read off the documents rather than taken from a font
#: table, each from its surrounding word:
#:
#:   ปกป·ด → ปกปิด            หนึ่งป· → หนึ่งปี       เฟ··องวิวัฒน → เฟื่องวิวัฒน์
#:   บานโป·ง → บ้านโป่ง        การป·องกัน → ป้องกัน   ตําแหน·ง → ตำแหน่ง
#:   ผู·ดํารง → ผู้ดำรง        เฟซบุ·ก → เฟซบุ๊ก      กษัตริย· → กษัตริย์
#:   ป·ญหา → ปัญหา            ตกเป·น → ตกเป็น
#:
#: 12 of the 140 documents in the first test set use them, 4,970 times, and
#: these twelve codepoints account for every one of those occurrences.
_PUA_MARKS = {
    "\uf701": "\u0e34",  # ิ
    "\uf702": "\u0e35",  # ี
    "\uf704": "\u0e37",  # ื
    "\uf705": "\u0e48",  # ่
    "\uf706": "\u0e49",  # ้
    "\uf70a": "\u0e48",  # ่
    "\uf70b": "\u0e49",  # ้
    "\uf70c": "\u0e4a",  # ๊
    # The only tone mark left, in the only slot left: the other four of
    # F70A-F70E are confirmed above, so this one follows without guessing.
    "\uf70d": "\u0e4b",  # ๋
    "\uf70e": "\u0e4c",  # ์
    # Not a mark but a consonant: ญ drawn without its lower hook, which these
    # fonts substitute when a lower vowel sits under it. วิญ·ูชน → วิญญูชน.
    "\uf70f": "\u0e0d",  # ญ
    "\uf710": "\u0e31",  # ั
    "\uf712": "\u0e47",  # ็
    "\uf713": "\u0e48",  # ่
}
_PUA_TRANSLATION = {ord(k): v for k, v in _PUA_MARKS.items()}

#: The whole block these fonts draw from. A codepoint in here that is not in
#: the table above is one this corpus has not shown yet — reported once, and
#: left in place, because guessing which mark it is would put a wrong tone on a
#: legal name and dropping it would repeat the failure this repair exists to fix.
_PUA_BLOCK = re.compile("[\uf700-\uf71f]")
_PUA_SEEN: set[str] = set()


def restore_pua_marks(text: str) -> str:
    """Turn a font's private-use combining marks back into Thai ones."""
    if not text:
        return text
    restored = text.translate(_PUA_TRANSLATION)

    unknown = {ch for ch in _PUA_BLOCK.findall(restored) if ch not in _PUA_SEEN}
    if unknown:
        _PUA_SEEN.update(unknown)
        log.warning(
            "unmapped_private_use_marks",
            codepoints=sorted(f"U+{ord(ch):04X}" for ch in unknown),
        )
    return restored


def thai_to_arabic_digits(text: str) -> str:
    """๑๒๓ -> 123. Applied before any numeric parsing."""
    return text.translate(_THAI_DIGIT_MAP)


def arabic_to_thai_digits(text: str) -> str:
    """123 -> ๑๒๓. Used when rendering Thai-facing output."""
    return "".join(_ARABIC_TO_THAI.get(ch, ch) for ch in text)


def compose_sara_am(text: str) -> str:
    """Join a split sara am back into one character.

    Only this pair. A nikhahit separated from its sara aa by a tone mark —
    น + ํ + ้ + า for น้ำ — is left alone deliberately: joining it means
    reordering marks, and guessing at mark order in statutory text is not
    something to do silently. It stays visible to the reviewer instead.
    """
    return _SARA_AM_PARTS.sub("\u0e33", text)


#: ``\u0e33`` is a nikhahit above a sara aa, and the Gazette's embedded fonts drop
#: the nikhahit and leave a space: ``\u0e2d\u0e33\u0e19\u0e32\u0e08`` extracts as ``\u0e2d`` + space + ``\u0e32``.
#: Recognising it is safe because no Thai word begins with a sara aa \u2014 a bare
#: ``\u0e32`` after a space has no other way to have got there.
#:
#: Two complications, both real in this corpus. A tone mark sits between the
#: consonant and the space, so ``\u0e19\u0e49\u0e33`` arrives as ``\u0e19`` ``\u0e49`` space ``\u0e32`` and a
#: pattern anchored straight on the consonant cannot see it \u2014 which is how
#: ``\u0e2d\u0e33\u0e40\u0e20\u0e2d\u0e19\u0e49\u0e33\u0e22\u0e37\u0e19`` stayed unreadable. And in the documents whose font also
#: swaps the two vowels, what follows the space is already a ``\u0e33``; there the
#: space alone is the fault. Both end in the same place, so both are written
#: the same way.
_SARA_AM_AS_SPACE = re.compile(r"([\u0e01-\u0e2e][\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]?) [\u0e32\u0e33]")


def restore_sara_am(text: str) -> str:
    """Put back the ``\u0e33`` the PDF fonts turned into a space.

    Measured over the forty documents: none of ``\u0e2d\u0e33\u0e19\u0e32\u0e08``, ``\u0e01\u0e33\u0e2b\u0e19\u0e14``,
    ``\u0e2a\u0e33\u0e19\u0e31\u0e01``, ``\u0e14\u0e33\u0e40\u0e19\u0e34\u0e19``, ``\u0e19\u0e33\u0e40\u0e02\u0e49\u0e32`` or ``\u0e2a\u0e33\u0e2b\u0e23\u0e31\u0e1a`` appeared even once before
    this ran, and 862 of them after. It is not a cosmetic repair \u2014 the phrase
    that identifies a subordinate instrument, ``\u0e2d\u0e32\u0e28\u0e31\u0e22\u0e2d\u0e33\u0e19\u0e32\u0e08\u0e15\u0e32\u0e21\u0e04\u0e27\u0e32\u0e21\u0e43\u0e19``, is
    unfindable without it, so the rules that depend on it could never fire.
    """
    return _SARA_AM_AS_SPACE.sub(lambda m: m.group(1) + "\u0e33", text)


def normalize_unicode(text: str) -> str:
    """NFC-compose so Thai vowel/tone sequences compare equal.

    Thai text arrives from OCR engines with inconsistent combining-mark order;
    without composition, two visually identical strings can differ byte-wise and
    defeat duplicate matching. NFC alone is not enough for Thai — see
    ``compose_sara_am`` for the one sequence it will not fix.
    """
    return compose_sara_am(unicodedata.normalize("NFC", text))


def strip_invisible(text: str) -> str:
    return _INVISIBLE.sub("", text)


def collapse_whitespace(text: str, *, preserve_newlines: bool = True) -> str:
    """Collapse runs of spaces without destroying paragraph boundaries."""
    text = _MULTI_SPACE.sub(" ", text)
    if preserve_newlines:
        text = _MULTI_NEWLINE.sub("\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
    else:
        text = text.replace("\n", " ")
        text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


#: Words that begin a structural unit. A line break before one of these is a
#: real boundary in the document, never a broken word.
_STRUCTURAL_STARTS = (
    "มาตรา",
    "ข้อ",
    "หมวด",
    "ส่วน",
    "วรรค",
    "อนุมาตรา",
    "ภาค",
    "ลักษณะ",
    "บทเฉพาะกาล",
    "บทกำหนดโทษ",
    "บททั่วไป",
    "ผู้รับสนอง",
    "ประกาศ",
    "ให้ไว้",
    "ราชกิจจานุเบกษา",
    "เล่ม",
    "หมายเหตุ",
    "อาศัยอำนาจ",
)


#: Words that a line may begin with which are separated from what precedes
#: them by a space, not joined to it. A title carries its year on its own line
#: — "…ซึ่งสัตว์หรือซากสัตว์" then "พ.ศ. ๒๕๖๓" — and Thai writes a space before
#: the era, always. Joined with nothing, 48 of the 140 stored titles read
#: "ซากสัตว์พ.ศ. ๒๕๖๓", which is wrong everywhere the name is shown and in
#: every export of it.
_SPACED_STARTS = (r"พ\.ศ\.", r"\(ฉบับที่", r"ลงวันที่", r"ครั้งที่")

_JOIN_WITH_SPACE = re.compile(r"([฀-๿])\n(?!\n)[ \t]*(" + "|".join(_SPACED_STARTS) + r")")


#: Words that can only be the ``า``-for-``ำ`` fault, never correct Thai. One
#: document in the 140-document test set carries it: its font maps สระ อา onto
#: สระ อำ and สระ อำ onto ้ + สระ อำ, so "มาตรา" prints as "มำตรำ", "กำหนด" as
#: "ก้ำหนด", and "จังหวัดปทุมธานี" as "จังหวัดปทุมธำนี" — which is why that
#: law's province looked absent when it is on the page twice.
_SWAPPED_AA_MARKERS = ("มำตรำ", "พระรำชบัญญัติ", "ตำมควำม", "อ้ำเภอ", "รำชกำร")

#: ``C ้ ำ`` in a faulty document is ambiguous, and this is the one thing the
#: repair cannot settle by rule. It is either a genuine สระ อำ that the fault
#: gave a spurious tone mark — ก้ำหนด for กำหนด — or a genuine ``้ า`` whose
#: สระ อา the fault swapped — ท้ำย for ท้าย. Nothing in the output distinguishes
#: them; telling them apart needs a dictionary, and this file does not guess.
#:
#: So the three cases are listed instead, from what the words are:
#:
#: * already correct, tone mark and all — น้ำ is a word;
#: * a genuine ``้ า``, because the alternative is not a word in this position:
#:   ท้าย (แผนท้ายกฎกระทรวง), ห้าม, ข้าง — "ทำย", "หำ", "ขำ" are not;
#: * everything else: a spurious tone mark, which is what อ้ำเภอ, ต้ำบล and
#:   ก้ำหนด are, and what the one faulty document in the test set mostly holds.
_REAL_TONE_AM = frozenset({"น้ำ", "ซ้ำ", "ค้ำ", "ล้ำ", "ช้ำ", "ย้ำ", "จ้ำ"})
_TONE_PLUS_AA = frozenset({"ท้ำ", "ห้ำ", "ข้ำ", "ก่ำ", "บ้ำ", "ผ้ำ", "ฝ้ำ", "ส้ำ"})

#: Stands for a สระ อำ already known to be genuine, so the sweep that restores
#: สระ อา cannot take it back out again.
_TRUE_AM = "\uf8ff"


def has_swapped_sara_aa(text: str) -> bool:
    """Whether this text shows the swapped-vowel fault.

    Asked of a whole page rather than of each block. The signature is a handful
    of words, and a block containing none of them — a title line, say — would
    be left corrupt while the rest of the page was repaired, which then hides
    the fault from any later check.
    """
    return any(marker in text for marker in _SWAPPED_AA_MARKERS)


def repair_swapped_sara_aa(text: str, *, force: bool = False) -> str:
    """Undo a font that prints สระ อา as สระ อำ and สระ อำ as ้ + สระ อำ.

    Gated on words that cannot occur otherwise, so it cannot fire on a document
    whose vowels are all correct — which is 139 of the 140 in the test set.
    ``force`` applies it to a fragment of a page already known to carry the
    fault, where the fragment itself may show no signature.
    """
    if not force and not has_swapped_sara_aa(text):
        return text

    def restore_am(match: re.Match[str]) -> str:
        syllable = match.group(0)
        if syllable in _REAL_TONE_AM:
            return syllable[0] + syllable[1] + _TRUE_AM
        if syllable in _TONE_PLUS_AA:
            # The tone mark is real and the vowel is not: leave both, and let
            # the สระ อา sweep below turn the ำ back into า.
            return syllable
        return syllable[0] + _TRUE_AM

    text = re.sub(r"[ก-ฮ]้ำ", restore_am, text)
    text = text.replace("ำ", "า").replace(_TRUE_AM, "ำ")
    log.info("swapped_sara_aa_repaired")
    return text


def join_broken_thai_words(text: str) -> str:
    """Rejoin a Thai word split across a line break.

    Thai does not use spaces between words, so a break inside a word leaves two
    Thai fragments with no separator of their own. Three things are not simply
    concatenated, because doing so destroys the document's structure or its
    wording:

    * a blank line — always a paragraph boundary;
    * a line starting a structural unit (มาตรา, ข้อ, หมวด, …) — marker detection
      anchors on line starts, so merging one into the previous line makes the
      section invisible to the parser and loses it from the extracted structure;
    * a line starting with พ.ศ. or another element the document separates with
      a space — the break is the space, so it is joined as one.
    """
    text = _JOIN_WITH_SPACE.sub(r"\1 \2", text)
    alternatives = "|".join(re.escape(word) for word in _STRUCTURAL_STARTS)
    pattern = re.compile(r"([฀-๿])\n(?!\n)[ \t]*(?!(?:" + alternatives + r"))([฀-๿])")
    return pattern.sub(r"\1\2", text)


def fix_orphan_combining_marks(text: str) -> str:
    """Drop combining marks stranded at the start of a line.

    OCR line segmentation sometimes emits a tone mark alone at a line start,
    where it has no base character to attach to and renders as a dotted circle.
    """
    return re.sub(r"(?m)^" + _THAI_COMBINING.pattern + "+", "", text)


#: Tone and vowel marks that the Gazette's own font strands.
_TONE = "่้๊๋็์"
_LEAD_VOWEL = "เแโใไ"

#: A mark at the end of a line, and the short Thai word that starts the next.
#: The words this fault produces are ``เลม``, ``หนา``, ``ตอนท`` — never a whole
#: clause. Both halves of that bound are needed: at most four letters, and the
#: word must END there. Without the trailing check the pattern happily matched
#: the first four letters of ``พระราชบัญญัติประกอบรัฐธรรมนูญ`` and produced
#: ``พ่ระราชบัญญัติ…`` — a corruption in the middle of a statute's name.
_STRANDED_MARK = re.compile(
    r"([" + _TONE + r"])\n[ \t]*([ก-ฮ" + _LEAD_VOWEL + r"][ก-ฮะ-ู]{1,3})(?![ก-๙])"
)


def _reattach(word: str, mark: str) -> str:
    """Put a tone mark back where its syllable wants it.

    Thai writes the mark over the initial consonant, which is not the first
    character: a leading vowel is written before its consonant (เ-ล-่-ม), and
    ห or อ leading another consonant carries the mark on the one it leads
    (ห-น-้-า). Both cases are decided by position, not by a word list.
    """
    at = 1 if word[:1] in _LEAD_VOWEL else 0
    at += 1  # the initial consonant itself
    if word[at - 1] in "หอ" and at < len(word) and "ก" <= word[at] <= "ฮ":
        at += 1
    return word[:at] + mark + word[at:]


def reattach_stranded_marks(text: str) -> str:
    """Repair marks the PDF drew at the end of the wrong line.

    The Gazette's running header is typeset as a separate box, and its tone
    marks extract one line early: ``เล่ม`` arrives as ``่`` then ``เลม``. Every
    one of the forty documents measured had this, and not one header could be
    read before the repair — the publication date, volume and issue all come
    from that line, so it was five columns lost on every document.

    Deleting the mark, which is what a stranded mark at a *line start* deserves,
    would be wrong here: the mark is real, it is simply in the wrong place.
    """
    return _STRANDED_MARK.sub(lambda m: "\n" + _reattach(m.group(2), m.group(1)), text)


def thai_char_ratio(text: str) -> float:
    """Share of non-space characters that are Thai.

    Drives the text-layer probe: a PDF whose "text" is mostly Latin noise is a
    scan with a junk OCR layer, not a real text PDF.
    """
    meaningful = [ch for ch in text if not ch.isspace()]
    if not meaningful:
        return 0.0
    thai = sum(1 for ch in meaningful if _THAI_CHAR.match(ch))
    return thai / len(meaningful)


def normalize_text(text: str, *, join_words: bool = True, convert_digits: bool = True) -> str:
    """Full normalization pass for OCR and extracted text.

    Order matters: compose first so combining-mark repairs see stable sequences,
    convert digits before anything parses numbers, and join words before
    whitespace collapsing removes the line breaks that mark the joins.

    ``convert_digits`` is on for anything that will be parsed — a date or a
    section number has to be a number — and off where the text is the product
    rather than an input to one. The conversion only runs one way: ๑ becomes 1,
    but turning 1 back into ๑ would also rewrite the Arabic numerals a document
    genuinely printed. Whatever is meant to be kept has to be kept from the
    start.
    """
    text = restore_pua_marks(text)
    text = normalize_unicode(text)
    text = strip_invisible(text)
    # Before whitespace is touched: the evidence this reads is a single space,
    # and collapsing runs of spaces would erase the difference between the one
    # that used to be a ``ำ`` and the ones that separate words.
    text = restore_sara_am(text)
    # Reattach before dropping: a mark at the end of a line belongs to the next
    # word and is recoverable, and only what is left over is genuinely orphaned.
    text = reattach_stranded_marks(text)
    text = fix_orphan_combining_marks(text)
    if convert_digits:
        text = thai_to_arabic_digits(text)
    if join_words:
        text = join_broken_thai_words(text)
    text = collapse_whitespace(text)
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def normalize_for_matching(text: str) -> str:
    """Aggressive normalization used only as a duplicate-matching key.

    Never stored as display text and never shown to a reviewer: it discards
    punctuation and spacing that legal citations do care about.
    """
    text = normalize_text(text, join_words=False)
    text = text.lower()
    text = re.sub(r"[\s๏๚๛]+", "", text)
    text = re.sub(r"[^\w฀-๿]", "", text)
    return text
