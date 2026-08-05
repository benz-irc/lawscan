"""The two font faults that made every Gazette header unreadable.

Both were found by measuring, not by reading code, and both were invisible:
the text looked like Thai, parsed as Thai, and simply did not contain the words
it appeared to contain. These tests exist so that stops being possible.
"""

from lawscan.ocr.thai_text import (
    normalize_text,
    reattach_stranded_marks,
    restore_sara_am,
)


class TestStrandedMarks:
    """A tone mark the PDF drew at the end of the line before its word."""

    def test_leading_vowel_word(self):
        # เล่ม extracts as "่" then "เลม": the mark belongs after the ล, which
        # is the second character because เ is written before its consonant.
        assert reattach_stranded_marks("หนา ๘่\nเลม ๑๓๗") == "หนา ๘\nเล่ม ๑๓๗"

    def test_leading_ho_nam(self):
        # หน้า: ห leads น, and the mark belongs to the consonant it leads.
        assert reattach_stranded_marks("ในข้อ ๕ ้\nหนา ๘") == "ในข้อ ๕ \nหน้า ๘"

    def test_leaves_ordinary_text_alone(self):
        text = "มาตรา ๕ วรรคหนึ่ง\nและมาตรา ๓๒"
        assert reattach_stranded_marks(text) == text

    def test_does_not_reach_across_a_long_word(self):
        # Bounded to four letters: an unbounded match would put the mark into
        # whatever word happened to start the next line.
        text = "จบประโยค่\nพระราชบัญญัติประกอบรัฐธรรมนูญ"
        assert reattach_stranded_marks(text) == text


class TestSaraAm:
    """ำ is a nikhahit over a sara aa, and the font drops the nikhahit."""

    def test_plain_consonant(self):
        assert restore_sara_am("อาศัยอ านาจตามความใน") == "อาศัยอำนาจตามความใน"

    def test_through_a_tone_mark(self):
        # น้ำ is น + ้ + ำ. The mark sits between the consonant and the space,
        # so a pattern anchored on the consonant alone cannot see it — which is
        # how อำเภอน้ำยืน stayed unreadable.
        assert restore_sara_am("อำเภอน้ ายืน") == "อำเภอน้ำยืน"

    def test_when_the_font_also_swaps_the_vowels(self):
        # There what follows the space is already a ำ; the space alone is the
        # fault.
        assert restore_sara_am("อ ำเภอกบินทร์บุรี") == "อำเภอกบินทร์บุรี"

    def test_a_real_space_before_a_consonant_survives(self):
        # No Thai word begins with a sara aa, which is what makes this safe.
        assert restore_sara_am("มาตรา ๕ และ อาหาร") == "มาตรา ๕ และ อาหาร"


def test_normalize_recovers_a_gazette_header():
    """End to end, on the shape the PDFs actually produce."""
    raw = "ในข้อ ๔ และข้อ ๕ ้\nหนา ๘่\nเลม ๑๓๗ ตอนที่ ๑๓ ก\nราชกิจจานุเบกษา"
    out = normalize_text(raw)
    assert "เล่ม 137" in out
    assert "หน้า 8" in out
