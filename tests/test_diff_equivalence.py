"""Two spellings of one answer must not be scored as two answers.

Every case here was taken from the 240-document comparison, where a cell that
any reader would call correct was counted wrong. The reference file and the
extracted text disagree about things Thai does not use to carry meaning —
where the spaces fall, which digits the year is written in, whether the OCR
kept ``า`` or turned it into ``ำ`` — and a score that reads those as errors
sends someone to fix a prompt that was already right.

The opposite mistake is worse, so the folds are narrow on purpose and each one
says which class of difference it forgives. ``match_reason`` is what keeps them
honest: every cell that had to be folded to match reports the fold that did it,
so the workbook can be audited rather than believed.
"""

from lawscan.diff import compare_cell, key, match_reason


class TestSpacing:
    """Thai writes no spaces between words, so a space is never the answer."""

    def test_a_title_broken_where_the_gazette_breaks_it_is_the_same_title(self):
        # The export inserts a space before ว่าด้วย; the reference file does
        # not. 177 cells of the 240-document run turned on exactly this.
        theirs = "ระเบียบผู้ตรวจการแผ่นดินว่าด้วยค่าใช้จ่ายในการเดินทางไปปฏิบัติงาน พ.ศ. 2563"
        ours = "ระเบียบผู้ตรวจการแผ่นดิน ว่าด้วยค่าใช้จ่ายในการเดินทางไปปฏิบัติงาน พ.ศ. 2563"
        assert compare_cell("ชื่อกฎหมาย", theirs, ours) == "exact"
        assert match_reason(theirs, ours) == "ต่างแค่เว้นวรรค"

    def test_a_space_before_เรื่อง_is_not_a_different_law(self):
        assert compare_cell(
            "ชื่อกฎหมาย",
            "ประกาศคณะกรรมการบริหารศาลยุติธรรมเรื่อง เปลี่ยนแปลงสถานที่",
            "ประกาศคณะกรรมการบริหารศาลยุติธรรม เรื่อง เปลี่ยนแปลงสถานที่",
        ) == "exact"


class TestDigits:
    """๒๕๖๓ and 2563 are one year written two ways, and both files use both."""

    def test_thai_and_arabic_years_are_the_same_year(self):
        theirs = "พระราชบัญญัติควบคุมอาคาร พ.ศ. ๒๕๒๒ มาตรา ๕"
        ours = "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5"
        assert compare_cell("กฎหมายแม่", theirs, ours) == "exact"
        assert match_reason(theirs, ours) == "ต่างแค่เลขไทย/อารบิก"


class TestOcrDamage:
    """``ก่อสร้าง`` comes out of the text layer as ``ก่อสรำง`` often enough."""

    def test_a_vowel_the_extraction_broke_is_not_a_wrong_answer(self):
        theirs = "กฎกระทรวงกำหนดบริเวณห้ามก่อสร้าง ดัดแปลง"
        ours = "กฎกระทรวงกำหนดบริเวณห้ามก่อสรำง ดัดแปลง"
        assert compare_cell("ชื่อกฎหมาย", theirs, ours) == "exact"
        assert match_reason(theirs, ours) == "ต่างที่สระ ำ/า ซึ่ง OCR อ่านเพี้ยน"

    def test_two_genuinely_different_words_still_disagree(self):
        # The fold is loose enough to merge นำ with นา, which is the price of
        # forgiving the damage. It must not reach past a single vowel.
        assert compare_cell("ชื่อกฎหมาย", "กฎกระทรวงฉบับที่หนึ่ง",
                            "กฎกระทรวงฉบับที่สอง") == "wrong"


class TestListOrder:
    """A set of codes is a set. Writing it in another order says nothing."""

    def test_the_same_codes_in_another_order_are_the_same_answer(self):
        theirs, ours = "CC5, CB5", "CB5, CC5"
        column = "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)"
        assert compare_cell(column, theirs, ours) == "exact"
        assert match_reason(theirs, ours, column=column) == "ต่างแค่ลำดับรายการ"

    def test_a_missing_code_is_still_only_partly_right(self):
        column = "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
        assert compare_cell(column, "AA4, D7", "D7") == "partial"


class TestPlaceNames:
    """The reference writes the province with its word, and sometimes without."""

    def test_the_word_จังหวัด_is_not_part_of_the_name(self):
        theirs, ours = "จังหวัดบุรีรัมย์, จังหวัดนครราชสีมา", "บุรีรัมย์, นครราชสีมา"
        assert compare_cell("จังหวัด", theirs, ours) == "exact"
        assert match_reason(theirs, ours, column="จังหวัด") == "ต่างแค่คำนำหน้าชื่อสถานที่"

    def test_the_fold_is_only_offered_where_a_place_belongs(self):
        # A law whose title starts with จังหวัด is not the same law as one
        # without it, so the prefix stays outside the place columns.
        assert compare_cell("ชื่อกฎหมาย", "จังหวัดบุรีรัมย์", "บุรีรัมย์") == "partial"


class TestNothingIsFlattered:
    """The folds forgive spelling. They must never forgive a wrong answer."""

    def test_a_different_section_is_near_and_never_right(self):
        # Same Act, different address inside it. Both cells send the reader to
        # the same law, so this is closer than naming another Act — and it is
        # not agreement, because the section is the part being cited.
        assert compare_cell(
            "กฎหมายแม่",
            "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 มาตรา 9",
            "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 มาตรา 8",
        ) == "partial"

    def test_a_dropped_sub_clause_is_near_and_never_right(self):
        # The penalty column strips ``(1)`` and the reference keeps it. Fifty-
        # nine cells of the 240-document run are exactly this.
        assert compare_cell(
            "บทลงโทษ",
            "รอเชื่อมโยง: พระราชบัญญัติการชลประทานหลวง พุทธศักราช 2485 มาตรา 8 (1) และมาตรา 42",
            "รอเชื่อมโยง: พระราชบัญญัติการชลประทานหลวง พุทธศักราช 2485 มาตรา 8 และมาตรา 42",
        ) == "partial"

    def test_a_different_act_is_wrong_however_the_sections_line_up(self):
        assert compare_cell(
            "กฎหมายแม่",
            "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5",
            "พระราชบัญญัติโรคระบาดสัตว์ พ.ศ. 2558 มาตรา 5",
        ) == "wrong"

    def test_the_citation_tier_is_only_offered_in_citation_columns(self):
        # A tag column full of section numbers is not a citation, and folding
        # them together there would call two different activities one answer.
        assert compare_cell("Activity_Tag", "ยื่นตามมาตรา 13", "ยื่นตามมาตรา 16") == "wrong"

    def test_a_cell_we_left_empty_is_still_a_miss(self):
        assert compare_cell("บทลงโทษ", "โทษทางอาญา", "") == "wrong"

    def test_an_answer_we_invented_is_still_a_miss(self):
        assert compare_cell("บทลงโทษ", "", "โทษทางอาญา") == "wrong"

    def test_a_dash_against_a_blank_is_agreement(self):
        assert compare_cell("จังหวัด", "-", "") == "blank"

    def test_an_exact_match_says_so_plainly(self):
        assert match_reason("โทษทางอาญา", "โทษทางอาญา") == "ตรงทุกตัวอักษร"

    def test_cells_that_do_not_match_have_no_reason_to_give(self):
        assert match_reason("โทษทางอาญา", "โทษทางแพ่ง") == ""


class TestKey:
    def test_the_comparison_key_survives_every_fold_at_once(self):
        # Thai digits, a stray space, and OCR damage in one cell.
        assert key("พ.ศ. ๒๕๖๓ ก่อสรำง") == key("พ.ศ.2563ก่อสร้าง")


def test_overlap_counts_how_much_matched_not_whether_any_did():
    """``credit`` ให้ครึ่งช่องกับการทับซ้อนใด ๆ — ตรง 1 ใน 5 เท่ากับตรง 4 ใน 5

    แปดคอลัมน์ที่คำตอบเป็นชุดรายการคือ 28% ของตาราง การวัดมันด้วยการโยนเหรียญ
    คือการไม่วัดมัน
    """
    from lawscan.diff import overlap

    col = "Activity_Tag"
    assert overlap(col, "ก, ข, ค", "ก, ข, ค") == 1.0
    assert overlap(col, "ก, ข, ค", "ง, จ, ฉ") == 0.0
    # ตรงสองจาก (3+3) รายการ → 2*2/6
    assert abs(overlap(col, "ก, ข, ค", "ก, ข, ง") - 2 / 3) < 1e-9
    # เติมรายการเกินมาแล้วคะแนนต้องตก ไม่ใช่เท่าเดิม
    assert overlap(col, "ก, ข", "ก, ข, ค, ง") < overlap(col, "ก, ข", "ก, ข")


def test_a_column_that_is_not_a_list_keeps_the_half_cell():
    from lawscan.diff import overlap

    assert overlap("ชื่อกฎหมาย", "ประกาศ เรื่อง ก", "ประกาศ เรื่อง ก") == 1.0
    assert overlap("ชื่อกฎหมาย", "ประกาศ เรื่อง ก", "ระเบียบ เรื่อง ข") == 0.0
