"""One row against the reference row, which is how a prompt gets fixed.

Working on a prompt means looking at one document, changing one sentence, and
asking whether that document got better — and the forty-document table cannot
answer that. It averages the answer away: a change that fixes the document in
front of you and breaks two others reads as "no change".

So this compares a single row and says which cells moved.
"""

import csv

import pytest

from lawscan.rowcheck import compare_row, report_rows

HEADER = "ชื่อไฟล์ ,ชื่อกฎหมาย,จังหวัด,Activity_Tag\n"


def _files(tmp_path, theirs, ours):
    expected = tmp_path / "expected.csv"
    result = tmp_path / "ours.csv"
    expected.write_text(HEADER + theirs, encoding="utf-8")
    result.write_text(HEADER + ours, encoding="utf-8")
    return expected, result


class TestCompareRow:
    def test_every_column_comes_back_with_a_verdict(self, tmp_path):
        expected, ours = _files(
            tmp_path,
            "100001,ระเบียบ ก.,ชุมพร,แจ้ง\n",
            "100001,ระเบียบ ก.,ชุมพร,แจ้ง\n",
        )
        cells = compare_row(expected, ours, "100001")
        assert {c.column for c in cells} == {"ชื่อไฟล์ ", "ชื่อกฎหมาย", "จังหวัด", "Activity_Tag"}
        assert all(c.verdict == "exact" for c in cells)

    def test_worst_first(self, tmp_path):
        # ชื่อกฎหมาย overlaps as a prefix → partial · Activity_Tag shares no
        # item → wrong · จังหวัด and ชื่อไฟล์ match → exact.
        expected, ours = _files(
            tmp_path,
            "100001,ระเบียบ ก. ว่าด้วยของ,ชุมพร,แจ้ง\n",
            "100001,ระเบียบ ก. ว่าด้วยของ ข้อ ๓,ชุมพร,ยื่น\n",
        )
        verdicts = [c.verdict for c in compare_row(expected, ours, "100001")]
        assert verdicts[0] == "wrong", "ช่องที่ผิดต้องมาก่อน"
        assert verdicts.index("partial") < verdicts.index("exact")

    def test_a_document_the_reference_does_not_have(self, tmp_path):
        expected, ours = _files(tmp_path, "100001,ก,ก,ก\n", "100002,ก,ก,ก\n")
        with pytest.raises(KeyError):
            compare_row(expected, ours, "100002")


class TestReport:
    def test_it_names_the_document_and_scores_it(self, tmp_path):
        expected, ours = _files(
            tmp_path,
            "100001,ระเบียบ ก.,ชุมพร,แจ้ง\n",
            "100001,ระเบียบ ข.,ชุมพร,แจ้ง\n",
        )
        text = report_rows(expected, ours, ["100001"])
        assert "100001" in text
        assert "ชื่อกฎหมาย" in text
        assert "%" in text

    def test_a_perfect_row_says_so_rather_than_listing_nothing(self, tmp_path):
        expected, ours = _files(tmp_path, "100001,ก,ข,ค\n", "100001,ก,ข,ค\n")
        assert "ตรงทุกช่อง" in report_rows(expected, ours, ["100001"])

    def test_unscored_columns_are_shown_but_not_counted(self, tmp_path):
        """A prose column disagreeing must not drag the row's number down."""
        header = "ชื่อไฟล์ ,จังหวัด,AI ให้เหตุผล\n"
        expected = tmp_path / "e.csv"
        ours = tmp_path / "o.csv"
        expected.write_text(header + "100001,ชุมพร,เหตุผลของเขา\n", encoding="utf-8")
        ours.write_text(header + "100001,ชุมพร,เหตุผลของเรา\n", encoding="utf-8")
        text = report_rows(expected, ours, ["100001"])
        assert "100%" in text
        assert "AI ให้เหตุผล" in text
