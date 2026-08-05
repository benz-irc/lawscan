"""The deterministic half, one rule at a time.

Every case here is a document that was read wrongly at some point, reduced to
the smallest text that reproduces it. Where a number appears in a comment it is
the measurement that decided the rule, so a later change that lowers it has
something to argue with.
"""

from datetime import date

from lawscan.rules import audience, categories, gazette, kind, places
from lawscan.rules.provinces import PROVINCES


class TestKind:
    """A Thai instrument names its own type in its first heading."""

    def test_reads_the_heading(self):
        assert kind.read("กฎกระทรวง\nการนำเข้า ส่งออก") == "กฎกระทรวง"

    def test_writes_a_judgment_out_in_full(self):
        assert kind.read("คำพิพากษา\nคดีหมายเลขดำที่ อม. 77/2561") == (
            "คำพิพากษาของศาลฎีกาแผนกคดีอาญา"
        )

    def test_longest_match_wins_over_its_own_prefix(self):
        text = "พระราชบัญญัติประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน"
        assert kind.read(text) == "พระราชบัญญัติประกอบรัฐธรรมนูญ"

    def test_earliest_word_wins(self):
        # The type is in the masthead; anything later is a citation.
        text = "ระเบียบผู้ตรวจการแผ่นดิน\nอาศัยอำนาจตามพระราชบัญญัติ"
        assert kind.read(text) == "ระเบียบ"

    def test_silent_when_the_document_says_nothing(self):
        assert kind.read("เอกสารแนบท้าย") == ""


class TestGazette:
    def test_reads_the_header(self):
        header = gazette.parse("หน้า ๘\nเล่ม ๑๓๗ ตอนที่ ๑๓ ก ราชกิจจานุเบกษา ๑๔ กุมภาพันธ์ ๒๕๖๓")
        assert header is not None
        assert header.volume == "137"
        assert header.publish_date == date(2020, 2, 14)
        assert header.page == "8"

    def test_a_stated_date_tied_to_commencement(self):
        text = "ทั้งนี้ ให้เปิดทำการสำนักงานประจำศาลแขวงเชียงดาวตั้งแต่วันที่ 1 เมษายน 2563"
        assert gazette.stated_effective_date(text) == date(2020, 4, 1)

    def test_onwards_after_the_date_is_enough(self):
        assert gazette.stated_effective_date(
            "ตั้งแต่วันที่ 21 กุมภาพันธ์ 2563 เป็นต้นไป"
        ) == date(2020, 2, 21)

    def test_a_date_merely_cited_is_not_a_commencement(self):
        # Document 100034 states 28 ตุลาคม 2554 in a recital about an older
        # instrument. Taking the first date found made that its commencement.
        text = "แก้ไขเพิ่มเติมประกาศฉบับลงวันที่ 28 ตุลาคม 2554 ซึ่งใช้อยู่เดิม"
        assert gazette.stated_effective_date(text) is None

    def test_an_impossible_date_is_not_repaired(self):
        assert gazette.stated_effective_date("ใช้บังคับตั้งแต่วันที่ 31 กันยายน 2563") is None


class TestPlaces:
    def test_scope_ignores_a_cited_law_title(self):
        # "…อำเภอหลังสวน จังหวัดชุมพร พ.ศ. 2547" is the name of the instrument
        # being repealed, not this one's area. The document's own heading has
        # the same shape, so the two are told apart by where they sit — hence
        # the padding, which is the recitals a real instrument opens with.
        text = (
            "กฎกระทรวงกำหนดบริเวณห้ามก่อสร้างในท้องที่จังหวัดชุมพร พ.ศ. 2563\n"
            + "อาศัยอำนาจตามความในมาตรา 5 แห่งพระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 " * 6
            + "\nให้ยกเลิกกฎกระทรวงกำหนดบริเวณ อำเภอหลังสวน จังหวัดชุมพร พ.ศ. 2547"
        )
        assert len(text) > 400
        found = places.scope(text, PROVINCES)
        assert found.province == "ชุมพร"
        assert found.districts == ()

    def test_the_documents_own_heading_is_not_a_citation(self):
        # The guard that makes the test above possible: a heading in the first
        # four hundred characters is this law's own, and blanking it took the
        # province with it.
        text = "กฎกระทรวงกำหนดบริเวณห้ามก่อสร้างในท้องที่จังหวัดชุมพร พ.ศ. 2563"
        assert places.hide_citations(text) == text

    def test_one_address_is_the_place_the_instrument_is_about(self):
        text = (
            "ประกาศ เรื่อง เปลี่ยนแปลงสถานที่ตั้งของศาล ในจังหวัดอ่างทอง\n"
            "ไปยังอาคารเลขที่ 9 ตำบลศาลาแดง อำเภอเมืองอ่างทอง จังหวัดอ่างทอง"
        )
        assert places.scope(text, PROVINCES).districts == ("เมืองอ่างทอง",)

    def test_a_schedule_of_addresses_is_a_province_wide_plan(self):
        # Three or more tambon addresses: the operator records the province and
        # leaves the district cell empty. Measured, this is 39 districts right
        # against 37 for dropping them unconditionally.
        text = "ในท้องที่จังหวัดปราจีนบุรี\n" + "\n".join(
            f"({n}) ในท้องที่ตำบล{t} อำเภอ{d} จังหวัดปราจีนบุรี"
            for n, (t, d) in enumerate(
                [("เขาไม้แก้ว", "กบินทร์บุรี"), ("นาดี", "นาดี"), ("ดงบัง", "ประจันตคาม")], 1
            )
        )
        found = places.scope(text, PROVINCES)
        assert found.province == "ปราจีนบุรี"
        assert found.districts == ()

    def test_a_district_in_brackets_is_still_a_district(self):
        text = "พระราชกฤษฎีกา ในท้องที่จังหวัดอุบลราชธานี\nพื้นที่บริเวณที่ 1 (อำเภอโขงเจียม)"
        assert "โขงเจียม" in places.scope(text, PROVINCES).districts

    def test_bangkok_has_no_district_column(self):
        text = "ย้ายจากอาคารเดิม เขตจตุจักร กรุงเทพมหานคร ไปยังที่ทำการใหม่"
        found = places.scope(text, PROVINCES)
        assert found.province == "กรุงเทพมหานคร"
        assert found.districts == ()

    def test_a_judgment_has_no_territory(self):
        text = "คำพิพากษา ผู้ถูกกล่าวหาอยู่บ้านเลขที่ 1 อำเภอเมืองสุราษฎร์ธานี จังหวัดสุราษฎร์ธานี"
        assert places.scope(text, PROVINCES, narrative=True) == places.Place()


class TestCategories:
    JUDGMENT = "คำพิพากษา\nคดีหมายเลขดำที่ อม. 77/2561"

    def test_the_docket_identifies_the_category(self):
        assert "CC29" in categories.read(self.JUDGMENT)

    def test_correct_adds_what_the_document_states(self):
        core, support = categories.correct(self.JUDGMENT, [], ["CC1"])
        assert core == []
        assert set(support) == {"CC1", "CC29"}

    def test_correct_drops_administrative_codes_from_a_judgment(self):
        # A judgment of a court is not a law about courts.
        core, support = categories.correct(self.JUDGMENT, ["AK1"], ["CC17", "CC6", "CC1"])
        assert "CC17" not in support and "CC6" not in support
        assert "CC1" in support

    def test_an_ordinary_law_keeps_its_administrative_codes(self):
        core, support = categories.correct("ระเบียบสำนักนายกรัฐมนตรี", [], ["CC17"])
        assert support == ["CC17"]


class TestAudience:
    def test_a_judgment_binds_the_courts_jurisdiction(self):
        assert audience.read("คำพิพากษา\nคดีหมายเลขแดงที่ อม. 238/2562") == (
            "ผู้ดำรงตำแหน่งทางการเมือง"
        )

    def test_an_ordinary_law_is_left_to_the_model(self):
        assert audience.read("กฎกระทรวง การนำเข้าสัตว์") == ""
