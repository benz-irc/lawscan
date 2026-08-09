"""The comparison workbook: the two sheets, and the arithmetic on them.

The point being checked is that the summary and the detail cannot disagree.
A reader who filters the detail sheet down to ``ไม่ตรง`` and counts the rows
has to get the number the summary printed, or one of the two is lying and
there is no way to tell which.
"""

import csv

import pytest

from lawscan.export.columns import COLUMNS
from lawscan.export import workbook

openpyxl = pytest.importorskip("openpyxl")


def _csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in COLUMNS})


@pytest.fixture
def pair(tmp_path):
    """One document, four cells: right, forgiven, near, and wrong."""
    theirs = {
        "ชื่อไฟล์ ": "100001.pdf",
        "ประเภทกฎหมาย": "ระเบียบ",
        "ชื่อกฎหมาย": "ระเบียบผู้ตรวจการแผ่นดินว่าด้วยค่าใช้จ่าย พ.ศ. ๒๕๖๓",
        "กฎหมายแม่": "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5 (3)",
        "สถานะกฎหมาย": "สิ้นผล",
    }
    ours = {
        "ชื่อไฟล์ ": "100001",
        "ประเภทกฎหมาย": "ระเบียบ",
        # Same title: a space the Gazette prints, and Arabic digits.
        "ชื่อกฎหมาย": "ระเบียบผู้ตรวจการแผ่นดิน ว่าด้วยค่าใช้จ่าย พ.ศ. 2563",
        # Same Act, the sub-clause dropped.
        "กฎหมายแม่": "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5",
        "สถานะกฎหมาย": "บังคับใช้",
    }
    expected, mine = tmp_path / "expected.csv", tmp_path / "ours.csv"
    _csv(expected, [theirs])
    _csv(mine, [ours])
    return expected, mine, tmp_path / "out.xlsx"


class TestCells:
    def test_each_kind_of_disagreement_lands_where_it_should(self, pair):
        expected, mine, _ = pair
        found = {c.column.strip(): c for c in workbook.cells(expected, mine)}
        assert found["ประเภทกฎหมาย"].verdict == "exact"
        assert found["ชื่อกฎหมาย"].verdict == "exact"
        assert found["กฎหมายแม่"].verdict == "partial"
        assert found["สถานะกฎหมาย"].verdict == "wrong"

    def test_a_forgiven_cell_says_what_it_was_forgiven(self, pair):
        expected, mine, _ = pair
        found = {c.column.strip(): c for c in workbook.cells(expected, mine)}
        assert found["ชื่อกฎหมาย"].reason == "ต่างแค่เว้นวรรค"
        assert found["ประเภทกฎหมาย"].reason == "ตรงทุกตัวอักษร"

    def test_the_filename_column_is_matched_on_the_number_alone(self, pair):
        # ``100001.pdf`` against ``100001``. Keyed on the cell instead, the two
        # files share no documents at all and the comparison reports nothing.
        expected, mine, _ = pair
        assert {c.document for c in workbook.cells(expected, mine)} == {"100001"}


class TestWorkbook:
    def test_both_sheets_are_written(self, pair):
        expected, mine, out = pair
        workbook.write(expected, mine, out)
        book = openpyxl.load_workbook(out)
        assert book.sheetnames == [workbook.SUMMARY, workbook.DETAIL]

    def test_the_summary_and_the_detail_count_the_same_cells(self, pair):
        expected, mine, out = pair
        tally = workbook.write(expected, mine, out)

        detail = openpyxl.load_workbook(out)[workbook.DETAIL]
        header = [cell.value for cell in detail[1]]
        verdicts = [row[header.index("ผล")] for row in detail.iter_rows(min_row=2, values_only=True)]
        columns = [row[header.index("คอลัมน์")] for row in detail.iter_rows(min_row=2, values_only=True)]

        unscored = {c.strip() for c in workbook.UNSCORED}
        counted = [v for v, c in zip(verdicts, columns) if c not in unscored]
        assert counted.count(workbook.VERDICTS["exact"]) == tally.exact
        assert counted.count(workbook.VERDICTS["partial"]) == tally.partial
        assert counted.count(workbook.VERDICTS["wrong"]) == tally.wrong

    def test_a_run_with_no_evidence_folder_still_writes(self, pair):
        # The workdir is where the "who filled this cell" column comes from.
        # A comparison of two files someone was sent is still worth having.
        expected, mine, out = pair
        workbook.write(expected, mine, out, workdir=None)
        assert out.exists()


class TestColour:
    """The colour has to agree with the verdict beside it, on every row.

    A sheet where the two drift apart is worse than one with no colour: the
    reader stops checking the word once they trust the fill.
    """

    def test_every_verdict_is_painted_its_own_colour(self, pair):
        expected, mine, out = pair
        workbook.write(expected, mine, out)
        detail = openpyxl.load_workbook(out)[workbook.DETAIL]
        header = [cell.value for cell in detail[1]]
        at = header.index("ผล")

        painted = {}
        for row in detail.iter_rows(min_row=2):
            painted.setdefault(row[at].value, set()).add(row[at].fill.fgColor.rgb[-6:])

        for name, word in workbook.VERDICTS.items():
            if word in painted:
                assert painted[word] == {workbook.BANDS[name][0]}, word

    def test_the_summary_headline_uses_the_same_three_colours(self, pair):
        expected, mine, out = pair
        workbook.write(expected, mine, out)
        page = openpyxl.load_workbook(out)[workbook.SUMMARY]
        found = {row[0].value: row[0].fill.fgColor.rgb[-6:] for row in page.iter_rows()
                 if row[0].value in workbook.VERDICTS.values()}
        assert found["ตรง"] == workbook.BANDS["exact"][0]
        assert found["ใกล้เคียง"] == workbook.BANDS["partial"][0]
        assert found["ไม่ตรง"] == workbook.BANDS["wrong"][0]

    def test_the_reader_can_filter_and_the_headings_stay_put(self, pair):
        expected, mine, out = pair
        workbook.write(expected, mine, out)
        detail = openpyxl.load_workbook(out)[workbook.DETAIL]
        assert detail.freeze_panes == "C2"
        assert detail.auto_filter.ref is not None
