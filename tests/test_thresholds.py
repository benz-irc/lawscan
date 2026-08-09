"""The numbers that decide who a law applies to.

Document 100006 bans commercial buildings — but only those of 300 square metres
or more. Drop the 300 and the row still reads as a sentence about shops, still
scores as a near miss, and no longer tells a small shop it is exempt. The
column score cannot see that: one number weighs the same as one tag.
"""

from lawscan import thresholds
from lawscan.thainum import to_digits, value


class TestNumbersWrittenAsWords:
    """Legal Thai spells a threshold far more often than it digits one."""

    def test_the_ordinary_ones(self):
        for words, number in (("หนึ่ง", 1), ("สิบ", 10), ("สิบเอ็ด", 11),
                              ("ยี่สิบ", 20), ("ยี่สิบเอ็ด", 21), ("หกสิบ", 60),
                              ("ห้าสิบห้า", 55), ("สามร้อย", 300)):
            assert value(words) == number, words

    def test_a_bare_place_word_carries_an_implied_one(self):
        assert value("ร้อย") == 100
        assert value("พัน") == 1_000

    def test_a_million_scales_what_came_before_it(self):
        assert value("สองล้าน") == 2_000_000
        assert value("สองล้านห้าแสน") == 2_500_000

    def test_zero_is_a_number_and_nonsense_is_not(self):
        assert value("ศูนย์") == 0
        assert value("ไม่ใช่ตัวเลข") is None
        assert value("") is None

    def test_a_sentence_keeps_its_shape(self):
        assert to_digits("ภายในหกสิบวัน") == "ภายใน60วัน"
        assert to_digits("เป็นจำนวนสองเท่า") == "เป็นจำนวน2เท่า"


class TestWhatCountsAsACondition:
    def test_a_threshold_with_its_unit(self):
        found = thresholds.read("อาคารที่มีพื้นที่ใช้สอยตั้งแต่ 300 ตารางเมตรขึ้นไป")
        limits = [c for c in found if c.limit]
        assert str(limits[0]) == "ตั้งแต่ 300 ตารางเมตร"

    def test_the_unit_is_found_even_though_thai_does_not_space_it(self):
        # Requiring a boundary after the unit rejected the very phrase this
        # was written for: ``300 ตารางเมตรขึ้นไป``.
        assert any(c.word == "ตารางเมตร"
                   for c in thresholds.read("พื้นที่ 300 ตารางเมตรขึ้นไป"))

    def test_a_threshold_spelled_out_in_words(self):
        limits = [c for c in thresholds.read("ดำเนินการให้แล้วเสร็จภายในหกสิบวัน")
                  if not c.limit]
        assert str(limits[0]) == "60 วัน"

    def test_a_section_number_is_not_a_condition(self):
        assert not thresholds.read("อาศัยอำนาจตามความในมาตรา 300")

    def test_a_gazette_volume_is_not_a_condition(self):
        assert not thresholds.read("ราชกิจจานุเบกษา เล่ม 137 ตอนที่ 20 หน้า 5")

    def test_a_date_after_a_comparator_is_not_a_condition(self):
        assert not [c for c in thresholds.read("ใช้บังคับตั้งแต่ 1 มกราคม 2563")
                    if c.limit]


class TestWhetherItSurvived:
    LIMIT = thresholds.Condition("300", "ตั้งแต่", limit=True, unit="ตารางเมตร")

    def test_a_cell_that_states_it_counts(self):
        assert thresholds.mentioned(
            self.LIMIT, "ห้ามอาคารพาณิชยกรรมพื้นที่ตั้งแต่ 300 ตารางเมตรขึ้นไป")

    def test_a_cell_that_spells_it_in_words_counts_too(self):
        assert thresholds.mentioned(self.LIMIT, "พื้นที่สามร้อยตารางเมตรขึ้นไป")

    def test_the_number_alone_is_not_enough(self):
        # A summary holding a year and a section number contains almost any
        # small number by accident. ``เกิน 10`` was scoring as kept against a
        # ``10`` that belonged to something else.
        assert not thresholds.mentioned(self.LIMIT, "ออกเมื่อ พ.ศ. 2563 มาตรา 300")

    def test_an_empty_cell_never_counts(self):
        assert not thresholds.mentioned(self.LIMIT, "")


class TestTheSurvey:
    DOCS = [
        ("1", "พื้นที่ตั้งแต่ 300 ตารางเมตรขึ้นไป", {"สรุป": "ห้ามอาคาร 300 ตารางเมตรขึ้นไป"}),
        ("2", "ภายในไม่เกิน 60 วัน", {"สรุป": "ต้องดำเนินการโดยเร็ว"}),
    ]

    def test_it_counts_what_reached_the_row(self):
        found = thresholds.survey(self.DOCS, columns=("สรุป",))
        assert (found.stated, found.kept) == (2, 1)

    def test_it_names_the_document_that_kept_none(self):
        assert thresholds.survey(self.DOCS, columns=("สรุป",)).silent == ["2"]

    def test_it_lists_what_was_lost(self):
        lost = thresholds.survey(self.DOCS, columns=("สรุป",)).lost
        assert [(n, str(c)) for n, c in lost] == [("2", "ไม่เกิน 60 วัน")]

    def test_a_corpus_with_no_conditions_is_not_a_failure(self):
        found = thresholds.survey([("1", "ประกาศเรื่องย้ายที่ทำการ", {})], columns=("สรุป",))
        assert found.recall == 1.0
        assert "ไม่มีเอกสาร" in thresholds.report(found, columns=("สรุป",))
