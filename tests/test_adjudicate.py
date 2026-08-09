"""Going back to the document has to beat guessing, or it is not worth doing."""

from lawscan.adjudicate import (
    EVEN, GROUNDED, NEITHER, OURS, THEIRS, THEIRS_GROUNDED, grounding, source_line,
)

PAGE = "หน้า 1 เล่ม 137 ตอนที่ 11 ก ราชกิจจานุเบกษา 5 กุมภาพันธ์ 2563"


class TestGazetteLine:
    """The volume and issue are printed on the page. Nobody has to weigh this."""

    def test_ours_matching_the_page_wins(self):
        side, said = source_line("ราชกิจจานุเบกษา เล่ม 137 ตอนที่ 9 ก",
                                 "ราชกิจจานุเบกษา เล่ม 137 ตอนที่ 11 ก หน้า 1", PAGE)
        assert side == OURS
        assert "เล่ม 137 ตอนที่ 11 ก" in said

    def test_theirs_matching_the_page_wins(self):
        side, _ = source_line("ราชกิจจานุเบกษา เล่ม 137 ตอนที่ 11 ก",
                              "ราชกิจจานุเบกษา เล่ม 137 ตอนที่ 4 ก", PAGE)
        assert side == THEIRS

    def test_agreeing_on_the_volume_leaves_no_winner(self):
        side, said = source_line("เล่ม 137 ตอนที่ 11 ก", "เล่ม 137 ตอนที่ 11 ก หน้า 1", PAGE)
        assert side == ""
        assert "ต่างที่ส่วนอื่น" in said

    def test_neither_matching_says_so(self):
        side, _ = source_line("เล่ม 137 ตอนที่ 2 ก", "เล่ม 137 ตอนที่ 5 ก", PAGE)
        assert side == NEITHER

    def test_a_document_with_no_gazette_line_gives_no_verdict(self):
        assert source_line("อะไรก็ตาม", "อะไรก็ตาม", "ข้อความที่ไม่มีเลขเล่ม") == ("", "")


class TestGrounding:
    TEXT = "ผู้รับใบอนุญาตต้องยื่นรายงานต่อพนักงานเจ้าหน้าที่ทุกสามปี"

    def test_the_side_using_the_documents_words_is_named(self):
        side, said = grounding("ขออนุญาตก่อสร้าง", "ยื่นรายงาน", self.TEXT)
        assert side == GROUNDED
        assert "1/1" in said

    def test_it_works_the_other_way(self):
        side, _ = grounding("ยื่นรายงาน", "ขออนุญาตก่อสร้าง", self.TEXT)
        assert side == THEIRS_GROUNDED

    def test_both_grounded_is_not_a_verdict(self):
        side, _ = grounding("ยื่นรายงาน", "พนักงานเจ้าหน้าที่", self.TEXT)
        assert side == EVEN

    def test_ocr_damage_does_not_hide_a_match(self):
        """The extraction wrote ``ก่อสรำง``; a search for the real spelling
        must still find it, or every damaged document reads as unsourced."""
        side, _ = grounding("อะไรอื่น", "ก่อสร้าง", "ห้ามก่อสรำง ดัดแปลง")
        assert side == GROUNDED

    def test_it_counts_rather_than_declaring_correctness(self):
        """A summary can be right in words the document never uses, so the
        sentence has to report a count and not a verdict on the reading."""
        _, said = grounding("ขออนุญาตก่อสร้าง", "ยื่นรายงาน", self.TEXT)
        assert "พบในเอกสาร" in said


class TestNeitherIsGrounded:
    """"Equally grounded" and "neither is grounded at all" are not the same
    sentence. The first says both cells are fine; the second says nobody can
    defend either from the document, and those rows are the ones a reviewer
    most needs to stop at."""

    TEXT = "ผู้รับใบอนุญาตต้องยื่นรายงานต่อพนักงานเจ้าหน้าที่ทุกสามปี"

    def test_both_absent_is_named_as_absent(self):
        from lawscan.adjudicate import UNGROUNDED, grounding

        side, said = grounding("ขออนุญาตก่อสร้าง, จดทะเบียนพาณิชย์",
                               "ชำระค่าธรรมเนียม, ต่ออายุใบขับขี่", self.TEXT)
        assert side == UNGROUNDED
        assert "0/2" in said
        assert "ไม่ได้ยกคำจากตัวบท" in said

    def test_both_present_is_still_called_even(self):
        from lawscan.adjudicate import EVEN, grounding

        side, _ = grounding("ยื่นรายงาน", "พนักงานเจ้าหน้าที่", self.TEXT)
        assert side == EVEN
