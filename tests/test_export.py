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
        # 33 the operator numbers, plus ลำดับ, ชื่อไฟล์, ลิงค์PDF and
        # ลิงค์เอกสารที่แนะนำ which their sheet carries without numbering, plus
        # column 34 — the notification message, which is skipped unless asked
        # for by name.
        assert len(COLUMNS) == 38
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


class TestTheRowNumberBelongsToTheDocument:
    """``ลำดับ`` numbered by output position was wrong on every partial run.

    The operator numbers their corpus from 100001, unbroken to 103424, and
    their ``ลำดับ`` is that number minus 100000. Numbering by position in the
    file agrees on a full pass and disagrees on every subset: a twelve-document
    rescan produced 1–12 and lost one exact cell per document, which turned a
    +8 comparison into −4.
    """

    def test_it_comes_from_the_document_number(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("100001", 1) == "1"
        assert place_in_corpus("100240", 3) == "240"
        assert place_in_corpus("103424", 1) == "3424"

    def test_a_subset_keeps_the_corpus_numbering(self):
        from lawscan.export.columns import to_dict
        from lawscan.merge import Row

        # Second row of a two-document rescan, but document 135 of the corpus.
        assert to_dict(Row(document="100135"), 135)["ลำดับ"] == "135"

    def test_a_document_named_otherwise_falls_back_to_position(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("draft-a", 7) == "7"
        assert place_in_corpus("", 7) == "7"


def test_the_two_repeal_columns_write_a_dash_when_there_is_nothing():
    """V16 4.3 and 5.4: "หากไม่มี… ให้ใส่ -"

    The model answers null, which is what this system's schema offers it for
    "nothing found". The sheet wants the dash, so the dash is written here.
    """
    from lawscan.export.columns import to_dict
    from lawscan.merge import Row

    row = Row(document="100004")
    got = to_dict(row, 1)
    assert got["ยกเลิกกฎหมายอื่นทั้งฉบับ"] == "-"
    assert got["แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น"] == "-"


def test_a_real_answer_is_left_alone():
    from lawscan.export.columns import to_dict
    from lawscan.merge import Row

    row = Row(document="100094")
    row.put("ยกเลิกกฎหมายอื่นทั้งฉบับ", "ระเบียบทดสอบระบบ พ.ศ. 2563", "model")
    assert to_dict(row, 1)["ยกเลิกกฎหมายอื่นทั้งฉบับ"] == "ระเบียบทดสอบระบบ พ.ศ. 2563"


class TestAnAnnexeSitsBehindItsOwnDocument:
    """The operator files ``1000012.1`` between 100012 and 100013, numbered 12.1.

    Sorting on the file name as a string put it second in the sheet, directly
    after 100001, because that is where ``1000012.1`` falls alphabetically.
    """

    def test_it_is_numbered_off_the_sheet_it_belongs_to(self):
        """The suffix comes from the name; the number in front is the place.

        This used to read the number out of the file name too — which gives the
        right answer on a corpus named 100001 upwards and nonsense on one named
        with real Gazette numbers. ``write`` holds the counter still while an
        annexe is written, so the annexe still carries its document's number.
        """
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("1000012.1", 12) == "12.1"
        assert place_in_corpus("100012.1", 12) == "12.1"
        assert place_in_corpus("100012", 12) == "12"

    def test_it_sorts_between_its_document_and_the_next(self):
        from lawscan.export.columns import in_corpus_order

        names = ["100013", "100001", "1000012.1", "100012"]
        assert sorted(names, key=in_corpus_order) == [
            "100001", "100012", "1000012.1", "100013",
        ]

    def test_an_ordinary_document_is_untouched(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("100001", 1) == "1"
        assert place_in_corpus("103424", 99) == "3424"

    def test_a_name_that_is_not_a_number_falls_back_to_its_position(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("ทดสอบระบบ", 7) == "7"


class TestTheNotificationColumnIsOptIn:
    """Column 34 writes one message per V8 code. The operator's own note on it
    reads "รันเฉพาะตอนเทสแจ้งเตือน ไม่รันทั้งหมด", and the cost agrees: the
    corpus averages five codes a document, so running it by default would add
    five prose answers to every scan."""

    def test_the_column_exists(self):
        assert "ข้อความแจ้งเตือน (Smart Prompt)" in COLUMNS

    def test_it_is_not_asked_by_default(self):
        from lawscan.llm.questions import ALL, BY_NAME

        assert "notify" not in [q.name for q in ALL]
        assert "notify" in BY_NAME

    def test_it_is_not_scored(self):
        """Neither answer file has the column, so there is nothing to compare."""
        from lawscan.diff import UNSCORED

        assert "ข้อความแจ้งเตือน (Smart Prompt)" in UNSCORED


class TestWhichCorpusTheNamesBelongTo:
    """``number - 100000`` is the operator's numbering, not everyone's.

    Their corpus is named 100001 upwards and runs to 103424, so the name
    carries the place and a partial rescan has to keep it — numbering by
    position there lost one exact cell per document on a twelve-document run.
    The 2569 corpus is named with real Gazette numbers, and the same
    arithmetic wrote 830 for the first row, 22839 for another and a negative
    for the 9xxxx ones, where the operator's own sheet numbers the rows 1 to
    250. So the choice is made over the whole run: 100830 falls inside the
    band and still is not the 830th of anything.
    """

    def test_gazette_numbers_are_not_places(self):
        from lawscan.export.columns import numbered_by_name

        assert not numbered_by_name(["100830", "122839", "91099"])

    def test_the_operators_own_names_are_places(self):
        from lawscan.export.columns import numbered_by_name

        assert numbered_by_name(["100001", "100240", "103424"])

    def test_a_subset_of_their_corpus_keeps_their_numbers(self):
        from lawscan.export.columns import numbered_by_name, place_in_corpus

        names = ["100135", "100136"]
        by_name = numbered_by_name(names)
        assert place_in_corpus("100135", 1, by_name) == "135"

    def test_a_gazette_corpus_counts_from_one(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("100830", 1, False) == "1"
        assert place_in_corpus("122839", 2, False) == "2"

    def test_the_annexe_suffix_survives_either_way(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("1000012.1", 12, True) == "12.1"
        assert place_in_corpus("1000012.1", 12, False) == "12.1"

    def test_a_name_that_is_not_a_number_still_gets_its_place(self):
        from lawscan.export.columns import place_in_corpus

        assert place_in_corpus("ตัวอย่าง", 7) == "7"
