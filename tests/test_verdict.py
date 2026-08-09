"""The label has to be trustworthy or nobody will look past it."""

from lawscan.verdict import (
    OURS_FULLER, OURS_ONLY, OVERLAP, THEIRS_CITATION, THEIRS_FULLER,
    THEIRS_ONLY, UNDECIDED, better,
)


class TestCitations:
    """The operator's stated exception: their file is the one to keep when the
    two cells name the same law and differ on where inside it."""

    LAW = "พระราชบัญญัติโรคระบาดสัตว์ พ.ศ. 2558"

    def test_a_missing_bracket_makes_theirs_better(self):
        assert better("กฎหมายแม่", f"{self.LAW} มาตรา 32 (2)", f"{self.LAW} มาตรา 32") == THEIRS_CITATION

    def test_a_missing_วรรค_makes_theirs_better(self):
        assert better("กฎหมายแม่", f"{self.LAW} มาตรา 5 วรรคสอง", f"{self.LAW} มาตรา 5") == THEIRS_CITATION

    def test_a_different_section_of_the_same_law_is_still_the_address(self):
        assert better("กฎหมายแม่", f"{self.LAW} มาตรา 9", f"{self.LAW} มาตรา 8") == THEIRS_CITATION

    def test_a_different_law_is_not_an_address_difference(self):
        other = "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5"
        assert better("กฎหมายแม่", f"{self.LAW} มาตรา 5", other) == UNDECIDED

    def test_the_rule_does_not_apply_outside_citation_columns(self):
        """A tag column that happens to mention a section is not an address."""
        assert better("Activity_Tag", "ยื่นตามมาตรา 13", "ยื่นตามมาตรา 16") != THEIRS_CITATION


class TestFullness:
    def test_extra_items_make_ours_fuller(self):
        assert better("Activity_Tag", "เบิกค่าใช้จ่าย",
                      "เบิกค่าใช้จ่าย, ขออนุมัติเดินทาง") == OURS_FULLER

    def test_missing_items_make_theirs_fuller(self):
        assert better("Activity_Tag", "เบิกค่าใช้จ่าย, ขออนุมัติเดินทาง",
                      "เบิกค่าใช้จ่าย") == THEIRS_FULLER

    def test_a_longer_phrase_containing_theirs_is_fuller(self):
        assert better("กลุ่มเป้าหมาย", "ผู้ใช้น้ำชลประทาน",
                      "ผู้ใช้น้ำชลประทาน ในท้องที่ตำบลท่าช้าง") == OURS_FULLER

    def test_a_shorter_phrase_inside_theirs_is_not_fuller(self):
        assert better("กลุ่มเป้าหมาย", "ผู้ใช้น้ำชลประทาน ในท้องที่ตำบลท่าช้าง",
                      "ผู้ใช้น้ำชลประทาน") == THEIRS_FULLER


class TestEmptiness:
    def test_only_we_answered(self):
        assert better("ใบอนุญาต", "-", "ใบอนุญาตนำเข้า") == OURS_ONLY

    def test_only_they_answered(self):
        assert better("ใบอนุญาต", "ใบอนุญาตนำเข้า", "-") == THEIRS_ONLY

    def test_neither_answered_gets_no_label(self):
        assert better("ใบอนุญาต", "-", "") == ""


class TestWhatItRefusesToSay:
    def test_partly_shared_lists_are_called_that_and_no_more(self):
        assert better("Activity_Tag", "ก, ข", "ข, ค") == OVERLAP

    def test_two_unrelated_answers_are_left_to_a_person(self):
        """A label is what stops someone looking. Guessing here would stop
        them looking at exactly the rows that need it."""
        assert better("Activity_Tag", "เดินทางไปปฏิบัติงาน", "ยื่นบัญชีทรัพย์สิน") == UNDECIDED


class TestTypography:
    """Forty-one of the title mismatches are the same title. The extraction
    turned ``า`` into ``ำ`` in some words, or the operator's file breaks a line
    where ours does not — and neither is a disagreement about the law."""

    def test_a_sara_am_corruption_is_named_as_one(self):
        from lawscan.verdict import SAME_TEXT, better

        assert better("ชื่อกฎหมาย",
                      "อ่างเก็บน้ำลำเชียงไกร",
                      "อ่างเก็บน้ำล้ำเชียงไกร") == SAME_TEXT

    def test_a_spacing_difference_is_named_as_one(self):
        from lawscan.verdict import SAME_TEXT, better

        assert better("ชื่อกฎหมาย",
                      "กฎกระทรวงกำหนดหินเป็นหินประดับ และดินหรือทราย",
                      "กฎกระทรวงกำหนดหินเป็นหินประดับและดินหรือทราย") == SAME_TEXT

    def test_a_real_difference_is_not_called_typography(self):
        from lawscan.verdict import SAME_TEXT, better

        assert better("ชื่อกฎหมาย", "กฎกระทรวงเรื่องหนึ่ง", "กฎกระทรวงเรื่องอื่น") != SAME_TEXT


class TestCitationsAcrossScripts:
    """The operator's file writes years and sections in Thai digits and ours
    in Arabic. Comparing the script instead of the number made two citations
    of one Act look like two different Acts, and the row fell through to a
    label that said neither side was grounded — of a cell that was ours plus
    a bracket."""

    THEIRS = ("พระราชบัญญัติประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. ๒๕๖๐ มาตรา ๒๔, "
              "พระราชบัญญัติประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. ๒๕๖๐ มาตรา ๔๒")
    OURS = ("พระราชบัญญัติประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. 2560 มาตรา 24 (3), "
            "พระราชบัญญัติประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. 2560 มาตรา 42 (4)")

    def test_thai_and_arabic_digits_are_one_law(self):
        from lawscan.verdict import OURS_CITATION, better

        assert better("กฎหมายแม่", self.THEIRS, self.OURS) == OURS_CITATION

    def test_the_direction_is_reported(self):
        """We carry the sub-section here; theirs does not. Calling that
        "เฉลยแม่นกว่า" would be backwards."""
        from lawscan.verdict import THEIRS_CITATION, better

        assert better("กฎหมายแม่", self.OURS, self.THEIRS) == THEIRS_CITATION

    def test_the_reason_names_the_brackets(self):
        from lawscan.verdict import why

        text = why("กฎหมายแม่", self.THEIRS, self.OURS)
        assert "(3)" in text and "(4)" in text
