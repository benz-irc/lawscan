"""The shape of the file the operator opens, and how it is scored.

Two things are checked here that nothing else can catch. A column name that
drifts stops lining up in a comparison and reports every column after it as
wrong; and a comparison that is stricter than reality reports work that does
not exist.
"""

import csv

from lawscan.diff import compare_cell, norm
from lawscan.export.columns import COLUMNS, NONE_IS_AN_ANSWER, write_csv
from lawscan.merge import Row


class TestColumns:
    def test_the_count_and_the_typos_are_deliberate(self):
        assert len(COLUMNS) == 33
        # Three headers in the operator's sheet end in a space. They look like
        # mistakes and they are not ours to fix.
        assert "ชื่อไฟล์ " in COLUMNS
        assert "คำแนะนำสิ่งที่ต้องทำ " in COLUMNS
        assert "ระดับวามเสี่ยง " in COLUMNS

    def test_the_expected_file_agrees_column_for_column(self, tmp_path):
        from pathlib import Path

        expected = Path("data/expected.csv")
        if not expected.exists():
            return
        with expected.open(newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle))
        assert header == list(COLUMNS)

    def test_every_none_column_is_a_real_column(self):
        assert NONE_IS_AN_ANSWER <= set(COLUMNS)


class TestWriting:
    def test_absence_is_written_only_where_it_is_an_answer(self, tmp_path):
        row = Row(document="100001")
        row.put("ชื่อไฟล์ ", "100001", "rule")
        out = tmp_path / "r.csv"
        write_csv([row], out)
        with out.open(newline="", encoding="utf-8-sig") as handle:
            written = next(csv.DictReader(handle))
        # A law with no expiry date has one — none.
        assert written["วันที่สิ้นผล"] == "-"
        # Nothing has been asked about the summary yet, and saying "-" would
        # claim the document has no summary.
        assert written["คำอธิบายและสรุปสาระสำคัญ"] == ""

    def test_excel_gets_a_byte_order_mark(self, tmp_path):
        out = tmp_path / "r.csv"
        write_csv([Row(document="1")], out)
        assert out.read_bytes().startswith(b"\xef\xbb\xbf")


class TestMerge:
    def test_a_model_answer_cannot_displace_a_rule(self):
        row = Row(document="100001")
        row.put("ประเภทกฎหมาย", "ระเบียบ", "rule")
        row.put("ประเภทกฎหมาย", "REGULATION", "llm:identity")
        assert row.value("ประเภทกฎหมาย") == "ระเบียบ"
        assert row.sources()["ประเภทกฎหมาย"] == "rule"

    def test_a_rule_fills_what_no_rule_answered(self):
        row = Row(document="100001")
        row.put("ชื่อกฎหมาย", "ระเบียบผู้ตรวจการแผ่นดิน", "llm:identity")
        assert row.value("ชื่อกฎหมาย") == "ระเบียบผู้ตรวจการแผ่นดิน"


class TestScoring:
    def test_thai_and_arabic_digits_are_the_same_number(self):
        # The operator's own file writes both, row by row. Comparing the script
        # rather than the value scores agreement as disagreement.
        assert norm("เล่ม ๑๓๗") == norm("เล่ม 137")

    def test_the_gazettes_abbreviation_is_the_gazette(self):
        assert norm("ราชกิจจาฯ เล่ม 137") == norm("ราชกิจจานุเบกษา เล่ม 137")

    def test_a_dash_and_an_empty_cell_agree(self):
        assert compare_cell("อำเภอ", "-", "") == "blank"

    def test_one_side_empty_is_a_miss_in_both_directions(self):
        assert compare_cell("จังหวัด", "ชุมพร", "") == "wrong"
        assert compare_cell("จังหวัด", "", "ชุมพร") == "wrong"

    def test_overlapping_lists_are_partly_right(self):
        assert compare_cell("Activity_Tag", "ก, ข, ค", "ข, ง") == "partial"
        assert compare_cell("Activity_Tag", "ก, ข", "ค, ง") == "wrong"

    def test_a_document_number_from_numbers_is_still_a_number(self):
        assert norm("100001.0") == norm("100001")
