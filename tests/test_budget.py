"""Cutting a document to a budget without losing what answers the question.

Splitting on structure was tried first and got it wrong twice — a citation of
another instrument's schedule emptied a whole act's body, and "ให้ไว้ ณ วันที่"
turned out to sit at the top of an act and the bottom of a notification. The
tests below are for the replacement, which cuts by position and therefore
cannot empty anything.
"""

from lawscan.ocr.budget import GAP, fit, reason

REASON_TEXT = (
    "หมายเหตุ :- เหตุผลในการประกาศใช้กฎกระทรวงฉบับนี้ คือ "
    "โดยที่มาตรา 32 (2) แห่งพระราชบัญญัติโรคระบาดสัตว์ พ.ศ. 2558 กำหนดให้ "
    "ผู้รับใบอนุญาตนำเข้าตามหลักเกณฑ์ที่กำหนดในกฎกระทรวง จึงจำเป็นต้องออกกฎกระทรวงนี้"
)


class TestReason:
    def test_finds_the_drafters_own_statement(self):
        assert reason(f"เนื้อหา\n{REASON_TEXT}").startswith("หมายเหตุ")

    def test_stops_at_the_next_running_header(self):
        found = reason(f"{REASON_TEXT}\nหน้า 7\nเล่ม 137 ตอนที่ 13 ก")
        assert "หน้า 7" not in found
        assert "เล่ม 137" not in found

    def test_absent_is_empty_not_a_guess(self):
        assert reason("กฎกระทรวงฉบับนี้กำหนดหลักเกณฑ์การนำเข้า") == ""


class TestFit:
    def test_a_short_document_is_untouched(self):
        text = "ก" * 500
        assert fit(text, head=8_000, tail=1_500) == text

    def test_no_budget_means_no_cut(self):
        text = "ก" * 100_000
        assert fit(text, head=None) == text

    def test_a_long_document_keeps_both_ends(self):
        text = "เริ่ม" + "ก" * 50_000 + "จบ"
        out = fit(text, head=1_000, tail=500)
        assert out.startswith("เริ่ม")
        assert out.endswith("จบ")
        assert len(out) < len(text)

    def test_the_cut_is_marked_not_hidden(self):
        """A model told nothing was cut would answer as if it had it all."""
        assert GAP in fit("ก" * 50_000, head=1_000, tail=500)

    def test_the_reason_survives_a_cut_that_would_lose_it(self):
        # Buried in the middle, where neither the head nor the tail reaches.
        text = "ก" * 5_000 + REASON_TEXT + "ข" * 5_000
        out = fit(text, head=1_000, tail=500)
        assert "จึงจำเป็นต้องออกกฎกระทรวงนี้" in out

    def test_the_reason_is_not_repeated_when_it_is_already_there(self):
        text = "ก" * 2_000 + REASON_TEXT
        out = fit(text, head=1_000, tail=1_500)
        assert out.count("จึงจำเป็นต้องออกกฎกระทรวงนี้") == 1

    def test_head_only_when_no_tail_is_asked_for(self):
        out = fit("ก" * 50_000, head=1_000)
        assert GAP not in out
        assert len(out) == 1_000

    def test_nothing_is_rewritten(self):
        """Every character kept is a character from the original."""
        text = "เริ่มต้น " + "ก" * 50_000 + " สิ้นสุด"
        out = fit(text, head=200, tail=100)
        assert out[:200] == text[:200]
        assert out.endswith(text[-100:])
