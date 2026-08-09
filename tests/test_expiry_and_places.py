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
    """A regulation that waives a fee imposes nothing to be punished for."""

    def test_an_exemption_does_not_defer_to_its_parent(self):
        assert not penalties.links_to_parent(
            band="GREEN",
            parent="พระราชบัญญัติศุลกากร พ.ศ. 2560 มาตรา 5",
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
