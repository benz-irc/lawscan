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


class TestSaraAmWithTheMarkAfterTheSpace:
    """The same fault, with the tone mark on the other side of the gap.

    ``น้ำ`` is a consonant, a tone mark and a sara am. When the font drops the
    nikhahit the three can arrive either way round — ``น้ า`` or ``น ้า`` — and
    only the first was handled. The second is what the 2565 กฎกระทรวง on
    irrigation waterways is full of: ``ทางน ้าชลประทาน`` in every heading.
    """

    def test_the_mark_after_the_space_is_repaired(self):
        from lawscan.ocr.thai_text import restore_sara_am

        assert restore_sara_am("ทางน ้าชลประทาน") == "ทางน้ำชลประทาน"

    def test_the_mark_before_the_space_still_is(self):
        from lawscan.ocr.thai_text import restore_sara_am

        assert restore_sara_am("น้ า") == "น้ำ"

    def test_a_space_between_two_words_is_left_alone(self):
        from lawscan.ocr.thai_text import restore_sara_am

        assert restore_sara_am("กรม ก. และกรม ข.") == "กรม ก. และกรม ข."

    def test_a_real_sentence_keeps_its_spaces(self):
        from lawscan.ocr.thai_text import restore_sara_am

        assert restore_sara_am("ให้ใช้บังคับ ตั้งแต่วันถัดไป") == "ให้ใช้บังคับ ตั้งแต่วันถัดไป"


class TestUnmappedMarksAreReportedNotFatal:
    """A character we have no mapping for is news, not a reason to stop.

    The warning was written in structured-logging style — ``log.warning(msg,
    codepoints=[...])`` — which the standard library rejects with a TypeError.
    Every document containing an unmapped private-use mark therefore failed
    entirely, in the extractor and again in the pipeline: one 462-page
    instrument never produced a single row, and the log line that was supposed
    to explain it was the thing that raised.
    """

    def test_an_unmapped_mark_does_not_raise(self):
        from lawscan.ocr.thai_text import restore_pua_marks

        assert restore_pua_marks("กข") is not None

    def test_it_says_which_codepoint(self, caplog):
        import logging

        from lawscan.ocr.thai_text import _PUA_SEEN, restore_pua_marks

        _PUA_SEEN.discard("\uf71f")
        with caplog.at_level(logging.WARNING):
            restore_pua_marks("ก\uf71fข")
        assert "U+F71F" in caplog.text

    def test_ordinary_text_is_untouched(self):
        from lawscan.ocr.thai_text import restore_pua_marks

        assert restore_pua_marks("ประกาศกระทรวง") == "ประกาศกระทรวง"


def test_words_the_page_wide_swap_cannot_reach_are_repaired_by_name():
    """``สำนักงำน`` needs its first vowel kept and its second repaired.

    The page-wide swap turns every ``ำ`` into ``า``, which is right for a page
    the font damaged entirely and wrong for one damaged in part. Twelve
    documents of the corpus were left holding these after that pass ran.
    """
    from lawscan.ocr.thai_text import repair_known_words

    assert repair_known_words("สำนักงำน") == "สำนักงาน"
    assert repair_known_words("ราคาสินค้ำและบริการ") == "ราคาสินค้าและบริการ"
    assert repair_known_words("ค้ำปลีกค้ำส่ง") == "ค้าปลีกค้าส่ง"


def test_it_leaves_words_that_are_spelled_right():
    """``น้ำ`` is right 12,870 times and ``ค้ำประกัน`` is a real word."""
    from lawscan.ocr.thai_text import repair_known_words

    for right in ("น้ำมันเชื้อเพลิง", "หนังสือค้ำประกัน", "จำนวนสมาชิก", "สำนักงานคณะกรรมการ"):
        assert repair_known_words(right) == right


def test_the_buddhist_era_abbreviation_is_restored_when_a_year_follows():
    """``พ.ศ.`` comes back from recognition as ``WA.`` — 670 documents carry it."""
    from lawscan.ocr.thai_text import repair_buddhist_era

    assert repair_buddhist_era("พระราชบัญญัติควบคุมอาคาร WA. 2522") == (
        "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522"
    )
    assert repair_buddhist_era("ระเบียบบริหารราชการแผ่นดิน We. 2535 ซึ่งแก้ไข") == (
        "ระเบียบบริหารราชการแผ่นดิน พ.ศ. 2535 ซึ่งแก้ไข"
    )


def test_it_is_left_alone_without_a_year_behind_it():
    """``WA.`` on its own could be anything, and 222 of them are."""
    from lawscan.ocr.thai_text import repair_buddhist_era

    assert repair_buddhist_era("มาตรฐาน WA. ตามที่กำหนด") == "มาตรฐาน WA. ตามที่กำหนด"


def test_a_dropped_tone_mark_is_put_back():
    """``ตอนที 13 ก`` — the masthead of every page recognition has been over."""
    from lawscan.ocr.thai_text import repair_dropped_marks

    assert repair_dropped_marks("เล่ม 137 ตอนที 13 ก") == "เล่ม 137 ตอนที่ 13 ก"
    assert repair_dropped_marks("ในท้องทีจังหวัด") == "ในท้องที่จังหวัด"
    assert repair_dropped_marks("ผู้ซึงทำงาน") == "ผู้ซึ่งทำงาน"


def test_a_spelling_that_is_already_right_is_left_alone():
    """The broken forms are prefixes of the correct ones; the guard is the mark."""
    from lawscan.ocr.thai_text import repair_dropped_marks

    for whole in ("เล่ม 137 ตอนที่ 13 ก", "ในท้องที่จังหวัด", "ผู้ซึ่งทำงาน",
                  "ชื่อกฎหมาย", "วันที่ 5 มกราคม"):
        assert repair_dropped_marks(whole) == whole


def test_the_city_keeps_its_name():
    """``เมือ`` is ``เมื่อ`` with a mark gone, and ``เมือง`` is a word.

    14,269 of them in the corpus against 607 of the broken ``เมือ``, so the
    guard here is the letter behind rather than the mark above.
    """
    from lawscan.ocr.thai_text import repair_dropped_marks

    assert repair_dropped_marks("ผังเมือง อำเภอเมืองขอนแก่น") == "ผังเมือง อำเภอเมืองขอนแก่น"
    assert repair_dropped_marks("เมือรถออก") == "เมื่อรถออก"


def test_a_word_broken_in_two_places_is_repaired_whole():
    """``พืนที`` lost a vowel and a tone mark; the longer entry wins."""
    from lawscan.ocr.thai_text import repair_dropped_marks

    assert repair_dropped_marks("พืนทีสกัด") == "พื้นที่สกัด"
    assert repair_dropped_marks("ในพินทีบางส่วน") == "ในพื้นที่บางส่วน"


def test_the_subject_word_read_as_a_latin_one_is_put_back():
    """``เรื่อง`` between an instrument's name and its subject came back ``Gas``."""
    from lawscan.ocr.thai_text import repair_misread_subject

    broken = "ประกาศกระทรวงสาธารณสุข (ฉบับที่ 367) พ.ศ. 2557 Gas การแสดงฉลากของอาหาร"
    assert repair_misread_subject(broken).endswith("เรื่อง การแสดงฉลากของอาหาร")


def test_the_english_word_gas_is_left_alone():
    """Thirteen of the corpus's twenty are the word, not the fault."""
    from lawscan.ocr.thai_text import repair_misread_subject

    for english in ("Exhaust Gas Cleaning System (EGCS)",
                    "แก๊สโครมาโทกราฟี (Gas Chromatography)",
                    "Liquefied Natural Gas (LNG)",
                    "Calibration Gas Cylinder I.D."):
        assert repair_misread_subject(english) == english
