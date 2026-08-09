"""Shapes the reference file asks for that the answers keep getting wrong.

Each of these was read off the comparison rather than guessed: the operator's
file and ours disagree the same way across dozens of rows, and the difference
is mechanical every time. Mechanical differences belong in code — a prompt
that has to be obeyed 240 times in a row will not be.
"""

from lawscan.answers import irrigation_users, once_each


class TestRepeatedTags:
    """The tag prompt asks for a broad name and a specific one. Read literally
    it produces the broad name once per specific one — `ทรัพย์สิน, เงินฝาก,
    ทรัพย์สิน, ที่ดิน` — which is one tag and three copies of another."""

    def test_a_repeat_is_dropped(self):
        assert once_each(["ทรัพย์สิน", "เงินฝาก", "ทรัพย์สิน", "ที่ดิน"]) == [
            "ทรัพย์สิน", "เงินฝาก", "ที่ดิน",
        ]

    def test_the_first_position_is_the_one_kept(self):
        assert once_each(["ข", "ก", "ข"]) == ["ข", "ก"]

    def test_spacing_does_not_hide_a_repeat(self):
        assert once_each(["เอกสาร", " เอกสาร "]) == ["เอกสาร"]

    def test_distinct_tags_are_untouched(self):
        tags = ["ที่ดิน", "บ้าน", "รถยนต์"]
        assert once_each(tags) == tags


class TestIrrigationUsers:
    """These regulations are one sentence with one blank in it, and the
    reference fills the blank the same way every time."""

    TITLE = ("กฎกระทรวงกำหนดให้ทางน้ำชลประทานอ่างเก็บน้ำห้วยยางพะไล "
             "เป็นทางน้ำชลประทานที่จะเรียกเก็บค่าชลประทาน พ.ศ. 2564")

    def test_the_waterway_becomes_the_audience(self):
        assert irrigation_users(self.TITLE) == [
            "ผู้ใช้น้ำจากทางน้ำชลประทานอ่างเก็บน้ำห้วยยางพะไล"
        ]

    def test_it_works_without_the_space_before_เป็น(self):
        title = ("กฎกระทรวงกำหนดให้ทางน้ำชลประทานคลองตรอน"
                 "เป็นทางน้ำชลประทานที่จะเรียกเก็บค่าชลประทาน พ.ศ. 2564")
        assert irrigation_users(title) == ["ผู้ใช้น้ำจากทางน้ำชลประทานคลองตรอน"]

    def test_another_kind_of_law_is_not_touched(self):
        assert irrigation_users("กฎกระทรวงการจัดให้มีเจ้าหน้าที่ความปลอดภัยทางรังสี พ.ศ. 2564") == []


class TestReachesTheColumns:
    """None of it counts until the cell in the CSV changes."""

    def test_tag_cells_lose_repeats(self):
        from lawscan.merge import Row
        from lawscan.pipeline import _apply

        row = Row(document="100002")
        _apply(row, "summary", {
            "productGroupTags": ["ทรัพย์สิน", "เงินฝาก", "ทรัพย์สิน", "ที่ดิน"],
            "activityTags": ["ยื่นบัญชี", "ยื่นบัญชี", "ตรวจสอบ"],
        })
        assert row.cells["Product_Group_Tag"].value == "ทรัพย์สิน, เงินฝาก, ที่ดิน"
        assert row.cells["Activity_Tag"].value == "ยื่นบัญชี, ตรวจสอบ"


class TestPenaltyWording:
    """The band labels are the operator's vocabulary, not ours.

    The column is compared as one string, so a band whose label reads the same
    but is not written the same scores zero. Two of the four were our own
    phrasing; these are the words their file uses.
    """

    def test_the_four_bands_use_the_reference_wording(self):
        from lawscan.rules import PENALTY_TEXT

        assert PENALTY_TEXT == {
            "RED": "โทษทางอาญา",
            "ORANGE": "โทษทางปกครอง / โทษทางแพ่ง",
            "YELLOW": "เสียสิทธิประโยชน์ / ผลทางนิติกรรม",
            "BLUE": "ระเบียบภาครัฐ",
        }


class TestLocalGovernment:
    """Two shapes, both read off every mismatching row in the column."""

    def test_the_type_is_separated_from_the_name(self):
        from lawscan.answers import spaced_local_body

        assert spaced_local_body("องค์การบริหารส่วนตำบลกฤษณา") == "องค์การบริหารส่วนตำบล กฤษณา"
        assert spaced_local_body("องค์การบริหารส่วนจังหวัดพัทลุง") == "องค์การบริหารส่วนจังหวัด พัทลุง"
        assert spaced_local_body("เทศบาลตำบลบัวสว่าง") == "เทศบาลตำบล บัวสว่าง"

    def test_a_bare_type_is_left_as_it_is(self):
        """Nothing to separate, and inventing a name would be worse."""
        from lawscan.answers import spaced_local_body

        assert spaced_local_body("องค์การบริหารส่วนตำบล") == "องค์การบริหารส่วนตำบล"

    def test_an_already_spaced_name_is_not_spaced_twice(self):
        from lawscan.answers import spaced_local_body

        assert spaced_local_body("องค์การบริหารส่วนตำบล บ้านยาง") == "องค์การบริหารส่วนตำบล บ้านยาง"

    def test_a_judgment_names_no_local_body(self):
        """A ruling about a local politician is not a local ordinance. The
        council appears in it as the defendant's employer, not as a body the
        document binds."""
        from lawscan.answers import local_body_of

        assert local_body_of("เทศบาลตำบลขุนทะเล", "คำพิพากษาของศาลฎีกาแผนกคดีอาญา") == ""
        assert local_body_of("เทศบาลตำบลขุนทะเล", "ระเบียบ") == "เทศบาลตำบล ขุนทะเล"


class TestBothReachThePipeline:
    """Two of these lived in a one-off script for a while. A correction that
    only exists outside the pipeline is undone by the next run that pays for
    itself, which is the worst place for it to be."""

    def _row_with(self, **cells):
        from lawscan.merge import Row

        row = Row(document="100187")
        for column, value in cells.items():
            row.put(column, value, "rule")
        return row

    def test_a_waterway_title_sets_the_audience(self):
        from lawscan.pipeline import _apply

        row = self._row_with(**{
            "ชื่อกฎหมาย": "กฎกระทรวงกำหนดให้ทางน้ำชลประทานคลองส่งน้ำฝั่งขวา "
                          "เป็นทางน้ำชลประทานที่จะเรียกเก็บค่าชลประทาน พ.ศ. 2564",
        })
        _apply(row, "audience", {"split": ["ผู้ใช้น้ำชลประทานคลองส่งน้ำฝั่งขวา "
                                           "ในท้องที่ตำบลท่าช้าง อำเภอเมืองนครนายก"]})
        assert row.cells["กลุ่มเป้าหมาย"].value == "ผู้ใช้น้ำจากทางน้ำชลประทานคลองส่งน้ำฝั่งขวา"

    def test_an_ordinary_title_leaves_the_audience_alone(self):
        from lawscan.pipeline import _apply

        row = self._row_with(**{"ชื่อกฎหมาย": "กฎกระทรวงการจัดให้มีเจ้าหน้าที่ความปลอดภัยทางรังสี พ.ศ. 2564"})
        _apply(row, "audience", {"split": ["ผู้รับใบอนุญาต", "เจ้าหน้าที่ความปลอดภัยทางรังสี"]})
        assert row.cells["กลุ่มเป้าหมาย"].value == "ผู้รับใบอนุญาต, เจ้าหน้าที่ความปลอดภัยทางรังสี"

    def test_a_local_body_is_spaced(self):
        from lawscan.pipeline import _apply

        row = self._row_with(**{"ประเภทกฎหมาย": "ระเบียบ"})
        _apply(row, "identity", {"localGovernment": "องค์การบริหารส่วนตำบลกฤษณา"})
        assert row.cells["องค์กรปกครองส่วนท้องถิ่น"].value == "องค์การบริหารส่วนตำบล กฤษณา"

    def test_a_judgment_keeps_the_column_empty(self):
        from lawscan.pipeline import _apply

        row = self._row_with(**{"ประเภทกฎหมาย": "คำพิพากษาของศาลฎีกาแผนกคดีอาญา"})
        _apply(row, "identity", {"localGovernment": "เทศบาลตำบลขุนทะเล"})
        assert row.cells.get("องค์กรปกครองส่วนท้องถิ่น") is None


class TestIrrigationAgency:
    """The waterway regulations are all issued by the same two bodies, and the
    reference names them as one item with both abbreviations. Deriving it from
    the title is the third thing this run of documents gives away for free."""

    TITLE = ("กฎกระทรวงกำหนดให้ทางน้ำชลประทานคลองตรอน"
             "เป็นทางน้ำชลประทานที่จะเรียกเก็บค่าชลประทาน พ.ศ. 2564")

    def test_a_waterway_title_names_both_bodies(self):
        from lawscan.answers import irrigation_agencies

        assert irrigation_agencies(self.TITLE) == [
            "กรมชลประทาน (ชป.) /กระทรวงเกษตรและสหกรณ์ (กษ.)"
        ]

    def test_another_kind_of_law_is_not_touched(self):
        from lawscan.answers import irrigation_agencies

        assert irrigation_agencies("กฎกระทรวงการจัดให้มีเจ้าหน้าที่ความปลอดภัยทางรังสี พ.ศ. 2564") == []

    def test_it_reaches_the_column(self):
        from lawscan.merge import Row
        from lawscan.pipeline import _apply

        row = Row(document="100194")
        row.put("ชื่อกฎหมาย", self.TITLE, "rule")
        _apply(row, "identity", {"agencies": ["กระทรวงเกษตรและสหกรณ์", "กรมชลประทาน"]})
        assert row.cells["หน่วยงานกำกับ"].value == "กรมชลประทาน (ชป.) /กระทรวงเกษตรและสหกรณ์ (กษ.)"


class TestIrrigationActivity:
    """Four tags scored a fraction higher than two by collecting partial
    credit on every row. Two scored twelve cells exactly right against three.
    A cell that is exactly right is finished; one that overlaps still has to
    be read, so the two-tag form is the one worth having."""

    TITLE = ("กฎกระทรวงกำหนดให้ทางน้ำชลประทานคลองตรอน"
             "เป็นทางน้ำชลประทานที่จะเรียกเก็บค่าชลประทาน พ.ศ. 2564")

    def test_a_waterway_title_sets_both_tags(self):
        from lawscan.answers import irrigation_activities

        assert irrigation_activities(self.TITLE) == [
            "กำหนดทางน้ำชลประทาน", "เรียกเก็บค่าชลประทาน",
        ]

    def test_another_kind_of_law_is_not_touched(self):
        from lawscan.answers import irrigation_activities

        assert irrigation_activities("กฎกระทรวงสถานีบริการก๊าซธรรมชาติ พ.ศ. 2564") == []

    def test_it_reaches_the_column(self):
        from lawscan.merge import Row
        from lawscan.pipeline import _apply

        row = Row(document="100194")
        row.put("ชื่อกฎหมาย", self.TITLE, "rule")
        _apply(row, "summary", {"activityTags": ["ใช้น้ำชลประทาน"]})
        assert row.cells["Activity_Tag"].value == "กำหนดทางน้ำชลประทาน, เรียกเก็บค่าชลประทาน"
