"""A district can name its province without the province being written down.

Document 100008 is 812 characters, says ``สำนักงานประจำศาลแขวงเชียงดาว``, and
never writes เชียงใหม่ anywhere. The operator's row has both cells filled,
because a person knows which province เชียงดาว is in. That knowledge is a table
of 872 districts, and this is it being used.
"""

import pytest

from lawscan.rules import districts
from lawscan.rules.provinces import PROVINCES


class TestTable:
    def test_a_district_resolves_to_its_province(self):
        assert districts.province_of("เชียงดาว") == "เชียงใหม่"

    def test_an_unknown_name_resolves_to_nothing(self):
        assert districts.province_of("ไม่มีอำเภอนี้") is None

    def test_a_name_used_by_two_provinces_is_not_in_the_table(self):
        """เฉลิมพระเกียรติ exists in several provinces and names none of them."""
        assert districts.province_of("เฉลิมพระเกียรติ") is None

    def test_every_province_in_the_table_is_one_the_rules_know(self):
        unknown = {p for p in districts.TABLE.values() if p not in PROVINCES}
        assert not unknown


class TestReading:
    def test_it_finds_a_district_written_without_the_word_อำเภอ(self):
        text = "ให้มีสำนักงานประจำศาลแขวงเชียงดาว"
        assert districts.read(text) == ("เชียงดาว", "เชียงใหม่")

    def test_a_short_name_is_ignored(self):
        """"ปาย" is three characters and is a piece of ordinary words."""
        assert districts.read("ให้ปายังคงเดิม") is None

    def test_nothing_found_is_nothing(self):
        assert districts.read("ประกาศฉบับนี้ไม่ได้พูดถึงสถานที่ใด") is None

    @pytest.mark.parametrize("text", [
        "ศาลจังหวัดเชียงใหม่",          # the province is already written
        "",
    ])
    def test_it_does_not_invent(self, text):
        found = districts.read(text)
        assert found is None or found[1] in PROVINCES


class TestInThePlaceRule:
    """The fallback belongs behind the narrative guard, not in front of it.

    Judgments print the addresses of the people in them — อำเภอบ้านโป่ง,
    อำเภอควนกาหลง — and the operator's rows leave those cells empty. Reading
    them as scope put three documents in provinces they have nothing to do
    with, which is the same mistake the place rule was written to avoid.
    """

    def test_a_notice_naming_only_a_district_gets_its_province(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = "ประกาศ เรื่อง กำหนดให้มีสำนักงานประจำศาลแขวงเชียงดาว"
        found = scope(text, PROVINCES)
        assert found.province == "เชียงใหม่"
        assert found.districts == ("เชียงดาว",)

    def test_a_judgment_naming_a_district_gets_nothing(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = "ผู้ถูกกล่าวหามีภูมิลำเนาอยู่ที่อำเภอบ้านโป่ง"
        assert scope(text, PROVINCES, narrative=True).province is None

    def test_a_province_the_document_states_is_not_overridden(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = "ศาลเยาวชนและครอบครัวจังหวัดอ่างทอง ตั้งอยู่ที่อำเภอเมืองอ่างทอง"
        assert scope(text, PROVINCES).province == "อ่างทอง"


class TestFindingRatherThanFiltering:
    """The register should find districts, not only veto them.

    Filtering what the old regex produced traded one fault for another: the
    noise went, and so did ปากพนัง and เชียรใหญ่, which the regex had never
    picked up in the first place. Reading ``อำเภอ`` + a name the register knows
    finds them directly.
    """

    def test_districts_listed_in_a_row_are_all_found(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = ("กำหนดให้ทางน้ำในท้องที่อำเภอปากพนัง อำเภอเชียรใหญ่ และอำเภอหัวไทร "
                "จังหวัดนครศรีธรรมราช เป็นทางน้ำชลประทาน")
        found = scope(text, PROVINCES)
        assert found.province == "นครศรีธรรมราช"
        assert set(found.districts) == {"ปากพนัง", "เชียรใหญ่", "หัวไทร"}

    def test_ocr_noise_beside_a_real_name_is_dropped(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = "ท้องที่อำเภอปากพนัง อำเภอเขียรใหญ่ อำเภอลถานที่ราชการ จังหวัดนครศรีธรรมราช"
        assert scope(text, PROVINCES).districts == ("ปากพนัง",)


class TestTwoProvincesAtOnce:
    """An instrument can cover districts on both sides of a province line."""

    def test_both_provinces_are_named(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = ("กำหนดให้ทางน้ำในท้องที่อำเภอปากท่อ จังหวัดราชบุรี และอำเภอหนองหญ้าปล้อง "
                "จังหวัดเพชรบุรี เป็นทางน้ำชลประทาน")
        found = scope(text, PROVINCES)
        assert found.province == "ราชบุรี, เพชรบุรี"
        assert set(found.districts) == {"ปากท่อ", "หนองหญ้าปล้อง"}

    def test_one_province_is_still_written_alone(self):
        from lawscan.rules.places import scope
        from lawscan.rules.provinces import PROVINCES

        text = "ท้องที่อำเภอปากพนัง จังหวัดนครศรีธรรมราช"
        assert scope(text, PROVINCES).province == "นครศรีธรรมราช"


class TestNamesTheFontDamaged:
    """``หญ้า`` comes out of some PDFs as ``หญำ``, and only here can it be undone.

    The collapse of ``้า`` into ``ำ`` is ambiguous in running text — ``สำนัก``
    and ``กำหนด`` are spelt with a real ``ำ`` — so ``thai_text`` leaves it
    alone. Against a register of 872 names it stops being ambiguous: if the
    undamaged spelling is a district and the damaged one is not, there is only
    one thing it can be.
    """

    def test_a_damaged_name_resolves(self):
        assert districts.province_of("หนองหญำปล้อง") == "เพชรบุรี"

    def test_the_undamaged_name_still_resolves(self):
        assert districts.province_of("หนองหญ้าปล้อง") == "เพชรบุรี"

    def test_a_word_that_really_has_sara_am_is_not_rewritten(self):
        """``ลำปลายมาศ`` is spelt with ``ำ`` and means what it says."""
        assert districts.province_of("ลำปลายมาศ") == "บุรีรัมย์"

    def test_noise_still_resolves_to_nothing(self):
        assert districts.province_of("ลถานที่ราชการ") is None

    def test_the_file_gets_the_spelling_that_is_correct(self):
        from lawscan.rules.districts import read_all

        found = read_all("ในท้องที่ตำบลยางหัก อำเภอหนองหญำปล้อง จังหวัดเพชรบุรี")
        assert found == [("หนองหญ้าปล้อง", "เพชรบุรี")]
