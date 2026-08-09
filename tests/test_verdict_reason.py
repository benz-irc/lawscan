"""The label says which side; this says what made us say it.

A label on its own is an assertion. The operator has to be able to disagree
with it without opening the PDF, and that means naming the thing in the two
cells that produced it — the item we added, the address they carry and we
dropped, the keystroke that made two spellings of one answer look like two
answers.
"""

from lawscan.verdict import why


class TestCitations:
    LAW = "พระราชบัญญัติโรคระบาดสัตว์ พ.ศ. 2558"

    def test_it_names_the_address_we_dropped(self):
        text = why("กฎหมายแม่", f"{self.LAW} มาตรา 32 (2)", f"{self.LAW} มาตรา 32")
        assert "(2)" in text
        assert "เฉลย" in text

    def test_it_names_a_วรรค_we_dropped(self):
        text = why("กฎหมายแม่", f"{self.LAW} มาตรา 5 วรรคสอง", f"{self.LAW} มาตรา 5")
        assert "วรรคสอง" in text


class TestLists:
    def test_it_names_what_we_added(self):
        text = why("Activity_Tag", "เบิกค่าใช้จ่าย",
                   "เบิกค่าใช้จ่าย, ขออนุมัติเดินทาง")
        assert "ขออนุมัติเดินทาง" in text

    def test_it_names_what_we_are_missing(self):
        text = why("Activity_Tag", "เบิกค่าใช้จ่าย, ขออนุมัติเดินทาง",
                   "เบิกค่าใช้จ่าย")
        assert "ขออนุมัติเดินทาง" in text

    def test_it_names_both_sides_of_a_partial_overlap(self):
        text = why("Activity_Tag", "ก, ข", "ข, ค")
        assert "ก" in text and "ค" in text


class TestEmptiness:
    def test_it_says_which_side_was_blank(self):
        assert "เฉลยเว้นว่าง" in why("ใบอนุญาต", "-", "ใบอนุญาตนำเข้า")
        assert "เราเว้นว่าง" in why("ใบอนุญาต", "ใบอนุญาตนำเข้า", "-")


class TestTypography:
    def test_it_names_the_vowel_as_the_cause(self):
        text = why("ชื่อกฎหมาย", "อ่างเก็บน้ำลำเชียงไกร", "อ่างเก็บน้ำล้ำเชียงไกร")
        assert "ำ" in text and "OCR" in text

    def test_spacing_alone_is_named_as_spacing(self):
        text = why("ชื่อกฎหมาย", "กฎกระทรวงหนึ่ง สองสาม", "กฎกระทรวงหนึ่งสองสาม")
        assert "เว้นวรรค" in text
        assert "OCR" not in text


class TestUndecided:
    def test_it_says_plainly_that_nothing_is_shared(self):
        text = why("Activity_Tag", "เดินทางไปปฏิบัติงาน", "ยื่นบัญชีทรัพย์สิน")
        assert "ไม่มี" in text or "ไม่ซ้อน" in text

    def test_an_exact_match_has_nothing_to_explain(self):
        assert why("Activity_Tag", "ก", "ก") == ""


class TestWhyWeLeftItBlank:
    """"We left it blank" is not a reason. Sometimes the model answered "none"
    and was following an instruction that says so; sometimes a rule looked and
    found nothing. Those are different problems with different fixes, and the
    column is useless if it cannot tell them apart."""

    def test_it_says_the_model_answered_none(self):
        text = why("ใบอนุญาต", "ใบอนุญาตนำเข้า", "-", origin="llm:summary")
        assert "โมเดลตอบว่าไม่มี" in text

    def test_it_says_a_rule_found_nothing(self):
        text = why("อำเภอ", "เมืองนครนายก", "-", origin="rule")
        assert "กฎ" in text and "ไม่พบ" in text

    def test_a_law_in_their_manual_cell_names_the_instruction(self):
        """Our prompt forbids listing laws here. When theirs lists one, the
        blank is the instruction working, not the model failing."""
        text = why("คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
                   "พ.ร.บ.ประกอบรัฐธรรมนูญว่าด้วยการป้องกันและปราบปรามการทุจริต พ.ศ. 2542",
                   "-", origin="llm:summary")
        assert "กฎหมายไม่ใช่คู่มือ" in text

    def test_a_real_form_in_their_cell_does_not_get_that_excuse(self):
        text = why("คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
                   "แบบรายงานการเดินทางเพื่อขอเบิกจ่าย", "-", origin="llm:summary")
        assert "กฎหมายไม่ใช่คู่มือ" not in text

    def test_an_empty_core_names_the_instruction(self):
        text = why("กฎหมายเฉพาะธุรกิจ (Core Business Laws)", "AB2, AB3", "-",
                   origin="llm:business")
        assert "core" in text.lower()

    def test_without_a_known_origin_it_does_not_invent_one(self):
        text = why("ใบอนุญาต", "ใบอนุญาตนำเข้า", "-")
        assert "โมเดล" not in text and "กฎ" not in text


class TestReadability:
    """A reason nobody can act on is the same as no reason."""

    def test_a_business_code_is_given_with_its_name(self):
        """``เรากรอก BC6`` tells a reviewer nothing they did not already see."""
        text = why("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
                   "-", "BC6")
        assert "โรงเรียนสอนขับรถเอกชน" in text

    def test_an_unknown_code_is_left_alone(self):
        text = why("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
                   "-", "ZZ99")
        assert "ZZ99" in text

    def test_a_truncated_quote_says_it_was_truncated(self):
        long = "ก" * 200
        text = why("ใบอนุญาต", long, "-")
        assert "…" in text
