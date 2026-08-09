"""Where in a law something lives, written one way.

``วรรค`` and ``(๑)`` are different addresses. The operator's file uses both,
often in the same citation — ``มาตรา ๕๖ วรรคหนึ่ง (๑) (ซ)`` names a section, a
paragraph inside it, and two sub-clauses inside that. So this normalises how
the parts are written and never converts one part into another.
"""

from lawscan.citation import PARAGRAPHS, tidy
from lawscan.merge import Row


class TestTheFourWaysOfWritingOneAddress:
    CANONICAL = "มาตรา 5 วรรคหนึ่ง (3)"

    def test_a_paragraph_in_brackets_comes_out(self):
        # ``(วรรคหนึ่ง)`` reads as a sub-clause called "paragraph one".
        assert tidy("มาตรา 5(วรรคหนึ่ง)(3)") == self.CANONICAL

    def test_a_numbered_paragraph_becomes_the_word(self):
        # Their file writes ``วรรคหนึ่ง`` 132 times and ``วรรค 1`` never.
        assert tidy("มาตรา 5 วรรค 1 (3)") == self.CANONICAL

    def test_a_bracket_grown_against_the_word_is_spaced(self):
        assert tidy("มาตรา 5 วรรคหนึ่ง(3)") == self.CANONICAL

    def test_what_is_already_right_is_left_alone(self):
        assert tidy(self.CANONICAL) == self.CANONICAL


class TestWhatItRefusesToChange:
    def test_a_sub_clause_never_becomes_a_paragraph(self):
        # (5) is an อนุมาตรา. Rewriting it as วรรค 5 points somewhere else.
        assert tidy("พ.ร.บ. ก. พ.ศ. 2560 มาตรา 25 (5)") == (
            "พ.ร.บ. ก. พ.ศ. 2560 มาตรา 25 (5)"
        )

    def test_both_together_survive_intact(self):
        assert tidy("มาตรา 56 วรรคหนึ่ง (1) (ซ)") == "มาตรา 56 วรรคหนึ่ง (1) (ซ)"

    def test_thai_digits_are_not_converted(self):
        # Which numerals to print is the diff's business, not this file's.
        assert tidy("มาตรา ๕ วรรคหนึ่ง(๓)") == "มาตรา ๕ วรรคหนึ่ง (๓)"

    def test_a_paragraph_past_the_named_ones_is_left_as_written(self):
        assert "วรรค 47" in tidy("มาตรา 5 วรรค 47")

    def test_text_with_no_citation_is_untouched(self):
        assert tidy("กำหนดหลักเกณฑ์การเดินทางไปปฏิบัติงาน") == (
            "กำหนดหลักเกณฑ์การเดินทางไปปฏิบัติงาน"
        )

    def test_nothing_in_nothing_out(self):
        assert tidy("") == ""

    def test_every_named_paragraph_round_trips(self):
        for n, word in enumerate(PARAGRAPHS, start=1):
            assert tidy(f"มาตรา 1 วรรค {n}") == f"มาตรา 1 วรรค{word}"


class TestWhereItApplies:
    def test_the_parent_column_is_normalised(self):
        row = Row(document="1")
        row.put("กฎหมายแม่", "พ.ร.บ. ก. พ.ศ. 2560 มาตรา 5(วรรคหนึ่ง)(3)", "llm:parent")
        assert row.value("กฎหมายแม่") == "พ.ร.บ. ก. พ.ศ. 2560 มาตรา 5 วรรคหนึ่ง (3)"

    def test_a_citation_inside_a_sentence_gets_the_same_shape(self):
        # Applied to every column, because a citation should not read one way
        # in the parent column and another way in the summary beside it.
        row = Row(document="1")
        row.put("คำอธิบายและสรุปสาระสำคัญ",
                "ยกเลิกอัตราเดิมตามมาตรา 3(1)", "llm:summary")
        assert row.value("คำอธิบายและสรุปสาระสำคัญ").endswith("มาตรา 3 (1)")

    def test_ordinary_punctuation_in_a_sentence_is_left_alone(self):
        # Every rule anchors to a section or paragraph number, so a bracket
        # that is just the writer's punctuation is none of its business.
        row = Row(document="1")
        for sentence in ("กำหนดอัตรา (ตามบัญชีแนบท้าย) สำหรับผู้เดินทาง",
                         "ค่าใช้จ่าย(อื่น) ที่จำเป็น",
                         "ยกเลิกวรรคหนึ่งของข้อเดิม"):
            row.put("คำอธิบายและสรุปสาระสำคัญ", sentence, "llm:summary")
            assert row.value("คำอธิบายและสรุปสาระสำคัญ") == sentence


class TestTheShortForm:
    """``ม.24`` escaped every rule, because every rule anchored on ``มาตรา``.

    It reached the sheet as ``ม.24(3)`` after the bracket spacing was supposedly
    fixed — 147 citations of a 240-document run, and it was spotted by a person
    reading the file, not by the check that was supposed to catch it.
    """

    def test_the_abbreviation_becomes_the_word(self):
        assert tidy("ม.24(3) ม.42(4)") == "มาตรา 24 (3) มาตรา 42 (4)"

    def test_it_carries_a_paragraph_through(self):
        assert tidy("ม.4 วรรคสาม") == "มาตรา 4 วรรคสาม"

    def test_it_carries_a_slashed_section_number(self):
        assert tidy("ม.21/3, ม.25(5)") == "มาตรา 21/3, มาตรา 25 (5)"

    def test_the_word_grown_against_its_number_is_spaced(self):
        assert tidy("มาตรา7 วรรคสาม") == "มาตรา 7 วรรคสาม"
        assert tidy("ข้อ4(37)") == "ข้อ 4 (37)"

    def test_a_village_number_is_not_a_section(self):
        # A Thai address writes ``ม.6 ต.บางรัก``. หมู่ 6 is not a section.
        assert tidy("ม.6 ต.บางรัก อ.เมือง") == "ม.6 ต.บางรัก อ.เมือง"

    def test_a_university_is_not_a_section_either(self):
        assert tidy("สำนักงาน ม.เกษตรศาสตร์") == "สำนักงาน ม.เกษตรศาสตร์"
