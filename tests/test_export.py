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

    def test_the_two_ways_of_writing_sara_am_are_one_word(self):
        """``นํา`` and ``นำ`` read identically and Unicode disagrees.

        The operator's spreadsheet spells it นิคหิต + สระอา; the text extracted
        from the PDF uses SARA AM, which has no canonical decomposition — so
        NFC leaves them apart and a cell that looks right on both screens was
        scored as a miss.
        """
        assert norm("กฎกระทรวงการนําเข้า") == norm("กฎกระทรวงการนำเข้า")

    def test_a_real_difference_still_differs(self):
        assert norm("การนำเข้า") != norm("การส่งออก")


class TestColumnsOutsideTheDocument:
    """A column the page cannot answer is not a column we failed.

    The Gazette's own URL carries the site's document id, and that id is in
    neither the text nor the PDF metadata. Scoring it measures whether someone
    handed us a lookup table. It stays in the export and stays visible in the
    table; it just stops being counted.
    """

    def test_the_pdf_link_is_not_counted(self, tmp_path):
        from lawscan.diff import compare

        expected = tmp_path / "expected.csv"
        ours = tmp_path / "ours.csv"
        header = "ชื่อไฟล์ ,ลิงค์PDF,จังหวัด\n"
        expected.write_text(header + "100001,https://example.invalid/9.pdf,ชุมพร\n",
                            encoding="utf-8")
        ours.write_text(header + "100001,,ชุมพร\n", encoding="utf-8")

        result = compare(expected, ours)
        # ชื่อไฟล์ and จังหวัด are counted; the link is the one left out.
        assert result.scored == 2
        assert result.exact == 2
        assert result.columns["ลิงค์PDF"].wrong == 1, "ยังต้องรายงานว่าไม่ตรง"

    def test_it_is_still_shown_in_the_table(self, tmp_path):
        from lawscan.diff import compare, report

        expected = tmp_path / "expected.csv"
        ours = tmp_path / "ours.csv"
        header = "ชื่อไฟล์ ,ลิงค์PDF\n"
        expected.write_text(header + "100001,https://example.invalid/9.pdf\n", encoding="utf-8")
        ours.write_text(header + "100001,\n", encoding="utf-8")
        text = report(compare(expected, ours))
        assert "ลิงค์PDF" in text
        assert "นอกเอกสาร" in text


class TestNothingFoundIsNotAnAnswer:
    """A rule that found nothing must not outrank a model that found something.

    ``rules`` writes ``"-"`` into a column it could not read, and ``Row.put``
    counted that as an answer — so the model's answer to the same column was
    refused. On document 100008 the model had จังหวัด and อำเภอ exactly right
    and both were thrown away for a dash.
    """

    def test_a_dash_from_a_rule_does_not_block_the_model(self):
        row = Row(document="100001")
        row.put("บทลงโทษ", "-", "rule")
        row.put("บทลงโทษ", "โทษทางอาญา", "llm:summary")
        assert row.value("บทลงโทษ") == "โทษทางอาญา"

    def test_but_it_does_where_absence_is_the_answer(self):
        """A national law has no province, and the place rule said so."""
        row = Row(document="100001")
        row.put("จังหวัด", "-", "rule")
        row.put("จังหวัด", "เชียงใหม่", "llm:identity")
        assert row.value("จังหวัด") == "-"

    def test_a_real_rule_answer_still_wins(self):
        row = Row(document="100001")
        row.put("จังหวัด", "ชุมพร", "rule")
        row.put("จังหวัด", "ระนอง", "llm:identity")
        assert row.value("จังหวัด") == "ชุมพร"

    def test_the_dash_survives_when_nothing_else_answers(self):
        """The export still needs the cell to read as empty, not vanish."""
        row = Row(document="100001")
        row.put("จังหวัด", "-", "rule")
        assert row.value("จังหวัด") == "-"

    def test_the_second_rules_pass_does_not_clobber_a_model_answer(self, tmp_path):
        """Rules run twice: once before the model, once after the law type is
        known. The second pass corrects rule answers — it must not replace a
        model answer with "nothing found".
        """
        row = Row(document="100001")
        row.put("บทลงโทษ", "-", "rule")
        row.put("บทลงโทษ", "โทษทางอาญา", "llm:summary")

        from lawscan.pipeline import apply_rules

        apply_rules(row, {"บทลงโทษ": "-", "ประเภทกฎหมาย": "ประกาศ"})
        assert row.value("บทลงโทษ") == "โทษทางอาญา"
        assert row.value("ประเภทกฎหมาย") == "ประกาศ"
