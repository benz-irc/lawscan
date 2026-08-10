"""A text layer that exists and is unreadable.

846 of the corpus's 3,424 documents carry a full text layer that decodes to
nothing — the PDF embeds a subset font whose glyph table does not line up with
Unicode, so every page comes back as Latin noise like ``Ĕîóøąðøöćõĉĕí÷``
where ``ในพระปรมาภิไธย`` was printed.

The probe that catches this already existed. ``thai_char_ratio`` even says in
its own docstring that it "drives the text-layer probe" — and nothing called
it. The reader asked whether a page *had* text, which these pages do, so the
OCR path was never reached and the damage reached the CSV as five empty date
columns with no warning attached.

Measured on the corpus: the ratio separates the two populations with nothing in
between — 846 documents at 0.2 or below, 2,415 at 0.6 or above.
"""

from lawscan.ocr.read import looks_garbled
from lawscan.ocr.thai_text import thai_char_ratio

#: One line of a real document (100719), as the broken font decodes it.
GARBLED = "Ĕîóøąðøöćõĉĕí÷óøąöĀćÖþĆêøĉ÷Ť ýćúøĆåíøøöîĎâ ÙĞćüĉîĉÝÞĆ÷ìĊę ħ/ģĦħĥ"

#: The same document's opening, read off the page image instead.
READABLE = "ในพระปรมาภิไธยพระมหากษัตริย์ ศาลรัฐธรรมนูญ คำวินิจฉัยที่ 2/2520"


class TestTheProbe:
    def test_the_two_populations_are_far_apart(self):
        assert thai_char_ratio(GARBLED) < 0.1
        assert thai_char_ratio(READABLE) > 0.8


class TestLooksGarbled:
    def test_a_broken_font_is_caught(self):
        assert looks_garbled(GARBLED)

    def test_real_thai_is_left_alone(self):
        assert not looks_garbled(READABLE)

    def test_a_page_too_short_to_judge_is_left_to_the_length_rule(self):
        # Below the letter floor the ratio is noise — one stray character
        # decides it. Such a page is already going to OCR for being short, and
        # this must not be the thing that says so.
        assert not looks_garbled("หน้า 3")
        assert not looks_garbled("")

    def test_a_page_of_figures_keeps_the_text_it_has(self):
        # A schedule of rates carries no letters to measure. Recognising it
        # again costs three seconds and can only turn exact digits into
        # guessed ones, so an unjudgeable page is never sent to OCR by this.
        figures = "1,250.00  2,500.00  3,750.00  4,000.00  5,125.50  6,000.00 " * 3
        assert not looks_garbled(figures)

    def test_a_page_of_english_is_not_thai_and_says_so(self):
        english = "This Act may be cited as the Emergency Decree on Public Administration " * 2
        assert looks_garbled(english)


class TestTheHeaderComesFromTheLayer:
    """The two damages are complementary, so both sources are kept.

    A broken font destroys the Thai and leaves the numerals — they are Latin
    digits and the substitution never reaches them. OCR recovers the Thai and
    misreads the numerals: re-extracting the corpus dated three documents to
    1977, because it read the Gazette year ``๒๕๖๖`` as ``๒๕๒๐`` every time it
    got it wrong. The header is numerals, so it is read from the layer.
    """

    def _document(self):
        import pathlib

        from lawscan.ocr.read import Document, Page

        return Document(pathlib.Path("x/100087.pdf"), [
            Page(1, "เล่ม 150 ตอนพิเศษ 251 ง ราชกิจจานุเบกษา 2 ตุลาคม 2520", "ocr",
                 layer="เล่ม 140 ตอนพิเศษ 251 ง ราชกิจจานุเบกษา 6 ตุลาคม 2566"),
            Page(2, "เนื้อความที่ OCR อ่านได้ดีกว่าชั้นข้อความ", "ocr"),
        ])

    def test_the_body_still_comes_from_the_page_that_won(self):
        assert "เนื้อความที่ OCR อ่านได้" in self._document().text()

    def test_the_header_comes_from_the_layer(self):
        from lawscan.rules import gazette

        header = gazette.parse(self._document().header_text)
        assert header and header.publish_date.year == 2023

    def test_a_page_with_no_layer_falls_back_to_its_own_text(self):
        import pathlib

        from lawscan.ocr.read import Document, Page

        d = Document(pathlib.Path("x/1.pdf"), [Page(1, "ข้อความเดียว", "text-layer")])
        assert d.header_text == d.text()

    def test_an_empty_layer_is_not_kept(self):
        # A page whose layer was blank has no numerals to preserve, so OCR's
        # reading is the only one there is.
        import pathlib

        from lawscan.ocr.read import Document, Page

        d = Document(pathlib.Path("x/1.pdf"), [Page(1, "OCR อ่านมา", "ocr", layer="")])
        assert d.header_text == "OCR อ่านมา"
