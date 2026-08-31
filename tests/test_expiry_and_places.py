"""Three faults the second corpus found, which the first one could not.

Documents 141-150 are a year later and a different mix, and they exposed what
forty documents of one month could not: a law that states its own end date, a
regulation that grants an exemption rather than a duty, and OCR noise reaching
the district column because the district rule trusted a blacklist instead of a
list of the districts that exist.
"""

from datetime import date

from lawscan.rules import gazette, penalties, places
from lawscan.rules.provinces import PROVINCES


class TestEndDate:
    """``ถึงวันที่ 31 มีนาคม พ.ศ. 2565`` is the law saying when it stops."""

    def test_a_stated_range_end_is_read(self):
        text = "ให้ใช้บังคับตั้งแต่วันที่ 1 มกราคม พ.ศ. 2565 ถึงวันที่ 31 มีนาคม พ.ศ. 2565"
        assert gazette.stated_end_date(text) == date(2022, 3, 31)

    def test_a_law_with_no_end_has_none(self):
        assert gazette.stated_end_date("ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ") is None

    def test_a_deadline_to_do_something_is_not_the_law_ending(self):
        """A duty owed by a date does not end the instrument that imposes it."""
        assert gazette.stated_end_date("ให้ยื่นรายงานภายในวันที่ 31 มีนาคม พ.ศ. 2565") is None


class TestStatus:
    def test_a_law_past_its_end_date_has_expired(self):
        assert gazette.status(date(2022, 3, 31), today=date(2026, 8, 6)) == "สิ้นผล"

    def test_a_law_still_within_its_range_is_in_force(self):
        assert gazette.status(date(2026, 12, 31), today=date(2026, 8, 6)) == "บังคับใช้"

    def test_a_law_with_no_end_date_is_in_force(self):
        assert gazette.status(None, today=date(2026, 8, 6)) == "บังคับใช้"


class TestExemptionIsNotAPenalty:
    """A regulation that waives a fee still tells a business what to pay.

    This used to assert the opposite, on a guard that read ``ยกเว้น`` in a
    title as "no duty here". Measured over the twenty-two documents the guard
    cost one and saved none: a schedule that sets fees and waives some of them
    reads as relief in its title and as an obligation in its body, and the
    title is the wrong half to judge on.
    """

    def test_a_waiver_still_defers_to_its_parent(self):
        assert penalties.links_to_parent(
            band="GREEN",
            parent="พระราชบัญญัติทดสอบระบบ พ.ศ. 2560 มาตรา 5",
            core="AB2",
            title="กฎกระทรวงยกเว้นค่าธรรมเนียมรายปีให้แก่ผู้ได้รับใบอนุญาต",
        )

    def test_an_ordinary_regulation_still_does(self):
        assert penalties.links_to_parent(
            band="GREEN",
            parent="พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5",
            core="AB2",
            title="กฎกระทรวงกำหนดบริเวณห้ามก่อสร้าง",
        )


class TestDistrictsMustExist:
    """A name is a district when the register of districts contains it."""

    def test_ocr_noise_is_not_a_district(self):
        text = "ประกาศกำหนดเขตในอำเภอลถานที่ราชการ จังหวัดนครศรีธรรมราช"
        assert "ลถานที่ราชการ" not in places.scope(text, PROVINCES).districts

    def test_a_real_district_survives(self):
        text = "กำหนดให้ทางน้ำในอำเภอหัวไทร จังหวัดนครศรีธรรมราช เป็นทางน้ำชลประทาน"
        assert places.scope(text, PROVINCES).districts == ("หัวไทร",)

    def test_a_district_of_another_province_is_kept(self):
        """An instrument can cover districts in two provinces at once."""
        text = ("กำหนดให้ทางน้ำในอำเภอปากท่อ จังหวัดราชบุรี และอำเภอหนองหญ้าปล้อง "
                "จังหวัดเพชรบุรี เป็นทางน้ำชลประทาน")
        found = places.scope(text, PROVINCES).districts
        assert "ปากท่อ" in found and "หนองหญ้าปล้อง" in found


class TestJudgmentsHaveNoEndDate:
    """A judgment recounts periods; none of them is the judgment expiring.

    Document 100034 recites "ตั้งแต่วันที่ … ถึงวันที่ …" as the span of the
    conduct it is about. Read as an end date it filed a judgment from 2013 as
    expired, which is not a thing a judgment does.
    """

    def test_a_narrative_document_states_no_end(self):
        from pathlib import Path

        from lawscan.ocr.read import Document, Page
        from lawscan.rules import run_all

        text = ("คำพิพากษา ผู้ถูกกล่าวหาครอบครองทรัพย์สินตั้งแต่วันที่ 1 มกราคม พ.ศ. 2555 "
                "ถึงวันที่ 28 มกราคม พ.ศ. 2556")
        document = Document(
            path=Path("100034.pdf"),
            pages=[Page(number=1, text=text, source="text-layer")],
        )
        found = run_all(document, law_type="คำพิพากษา")
        assert found["วันที่สิ้นผล"] == "-"
        assert found["สถานะกฎหมาย"] == "บังคับใช้"


class TestOperatorConventions:
    """Two of the four ways the second corpus differs are rules; two are not.

    ``100%`` and a page range appear on every row that can carry them. The
    bracketed note after a risk band and the space before ``ว่าด้วย`` appear on
    some rows and not others *within the same file*, so they are habits rather
    than conventions and nothing here tries to reproduce them.
    """

    def test_confidence_is_a_percentage(self):
        from lawscan.confidence import as_cell

        assert as_cell(1.0) == "100%"
        assert as_cell(0.9) == "90%"
        assert as_cell(0.85) == "85%"

    def test_a_document_spanning_pages_cites_the_range(self):
        assert gazette.page_span([13, 14]) == "13-14"

    def test_a_document_on_one_page_cites_the_page(self):
        assert gazette.page_span([19]) == "19"

    def test_repeated_footers_do_not_make_a_range(self):
        assert gazette.page_span([4, 4, 4]) == "4"


class TestTheRepealedByColumnIsNeverBlank:
    """V16 makes this a standing question, not an empty answer.

    A document rarely announces its own repeal — the fact arrives later, in
    the instrument that does the repealing — so the honest answer is that
    nobody has checked yet, and V16 gives the words for it.
    """

    def _row(self, text):
        from pathlib import Path

        from lawscan.ocr.read import Document, Page
        from lawscan.rules import run_all

        return run_all(Document(path=Path("ทดสอบ.pdf"),
                                pages=[Page(number=1, text=text, source="text-layer")]))

    def test_an_ordinary_document_says_it_is_waiting_on_the_database(self):
        got = self._row("กฎกระทรวงทดสอบระบบ พ.ศ. 2563\nข้อ 1 กฎกระทรวงนี้ให้ใช้บังคับ")
        assert got["ถูกยกเลิกโดยกฎหมายชื่อ"] == "-"

    def test_a_document_that_names_its_repealer_says_the_name(self):
        got = self._row("ประกาศทดสอบระบบ พ.ศ. 2560\nประกาศฉบับนี้ถูกยกเลิกโดยประกาศทดสอบระบบ พ.ศ. 2565\n")
        assert got["ถูกยกเลิกโดยกฎหมายชื่อ"] == "ประกาศทดสอบระบบ พ.ศ. 2565"


class TestAWindowWithoutTheWordsUsedForCommencement:
    """A relief decree writes its expiry as the period the relief covers.

    "สำหรับการบริจาคที่ได้กระทำตั้งแต่วันที่ ๑ มกราคม พ.ศ. ๒๕๖๒ ถึงวันที่
    ๓๑ ธันวาคม พ.ศ. ๒๕๖๒" states an end date without ever saying
    ``ใช้บังคับ``, and the range pattern required those words.
    """

    def _end(self, text):
        from lawscan.rules.gazette import stated_end_date

        return stated_end_date(text)

    def test_the_window_is_read_as_the_expiry(self):
        from datetime import date

        got = self._end(
            "มาตรา 6 ให้ยกเว้นภาษีสำหรับการบริจาคที่ได้กระทำตั้งแต่วันที่ 1 มกราคม พ.ศ. 2562 "
            "ถึงวันที่ 31 ธันวาคม พ.ศ. 2562 ทั้งนี้ ตามหลักเกณฑ์ที่อธิบดีกำหนด"
        )
        assert got == date(2019, 12, 31)

    def test_an_instrument_with_no_window_still_has_no_end(self):
        assert self._end("กฎกระทรวงนี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศเป็นต้นไป") is None


class TestTheEndDateBelongsToThisDocument:
    """V16: "ห้ามดึงวันที่สิ้นสุดของกฎหมายฉบับเก่าที่ถูกอ้างถึงมาตอบ"

    A relief decree opens by explaining the one it replaces, end date and all.
    Read as its own, a decree made in 2563 was filed as having lapsed in 2561 —
    two years before it was written.
    """

    def _end(self, text):
        from lawscan.rules.gazette import stated_end_date

        return stated_end_date(text)

    def test_a_recited_predecessors_expiry_is_not_taken(self):
        from datetime import date

        got = self._end(
            "โดยที่พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร "
            "(ฉบับที่ 631) พ.ศ. 2560 มีผลใช้บังคับถึงวันที่ 31 ธันวาคม พ.ศ. 2561 "
            "แต่โดยที่ยังมีความจำเป็น จึงสมควรกำหนดต่อไป ทั้งนี้ สำหรับรอบระยะเวลาบัญชี "
            "ที่เริ่มในหรือหลังวันที่ 1 มกราคม พ.ศ. 2562 แต่ไม่เกินวันที่ 31 ธันวาคม พ.ศ. 2563"
        )
        assert got == date(2020, 12, 31)

    def test_the_not_later_wording_is_read_on_its_own(self):
        from datetime import date

        assert self._end(
            "ให้ยกเว้นภาษีสำหรับรายจ่ายที่จ่ายไปแต่ไม่เกินวันที่ 31 ธันวาคม พ.ศ. 2563"
        ) == date(2020, 12, 31)

    def test_an_instrument_that_states_its_own_end_is_still_read(self):
        from datetime import date

        assert self._end(
            "ประกาศนี้ให้ใช้บังคับถึงวันที่ 30 กันยายน พ.ศ. 2565"
        ) == date(2022, 9, 30)
