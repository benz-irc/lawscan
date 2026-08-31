"""Two things found by pulling on the risk-band column.

The band was scoring 51% against a reference that writes the same band three
ways, and the penalty text beside it was naming a section of the Constitution
as though it belonged to the act underneath.
"""

from lawscan.diff import BAND_COLUMNS, band_of, compare_cell, match_reason
from lawscan.rules import parent

BAND = "ระดับวามเสี่ยง "


class TestOneBandWrittenThreeWays:
    """Their file writes ⚪️ เทา, ⚪️ เทา (Amendment / No Impact), and เทา."""

    def test_the_gloss_does_not_make_it_a_different_band(self):
        assert compare_cell(BAND, "⚪️ เทา (Amendment / No Impact)", "⚪️ เทา") == "exact"

    def test_neither_does_a_missing_emoji(self):
        assert compare_cell(BAND, "ฟ้า", "🔵 ฟ้า") == "exact"

    def test_nor_the_two_together(self):
        assert compare_cell(BAND, "🟡 เหลือง (เสียสิทธิ/นิติกรรม)", "🟡 เหลือง") == "exact"

    def test_a_different_colour_is_still_wrong(self):
        assert compare_cell(BAND, "⚪️ เทา", "🔵 ฟ้า") == "wrong"

    def test_the_linked_penalty_value_is_not_a_colour(self):
        # It sits in the same column and names no band, so it must not fold
        # into one.
        assert compare_cell(BAND, "โทษเชื่อมโยงจากกฎหมายแม่", "⚪️ เทา") == "wrong"

    def test_the_reason_says_which_step_forgave_it(self):
        assert match_reason("⚪️ เทา (Amendment / No Impact)", "⚪️ เทา", BAND) == (
            "ต่างแค่การเขียนชื่อแถบสี"
        )

    def test_only_band_columns_fold_this_way(self):
        # A title that gained a bracketed clause is a different title.
        assert "ชื่อกฎหมาย" not in BAND_COLUMNS
        assert compare_cell("ชื่อกฎหมาย", "ระเบียบ ก. (ฉบับที่ 2)", "ระเบียบ ก.") != "exact"

    def test_band_of_keeps_the_colour_and_drops_the_rest(self):
        assert band_of("⚪️ เทา (Amendment / No Impact)") == "เทา"
        assert band_of("") == ""


class TestTheConstitutionIsNotAParent:
    """``มาตรา ๑๗๕ ของรัฐธรรมนูญ`` is the power to issue a decree at all."""

    DECREE = (
        "พระราชกฤษฎีกากำหนดเขตพื้นที่ พ.ศ. 2560 "
        "อาศัยอำนาจตามความในมาตรา 175 ของรัฐธรรมนูญแห่งราชอาณาจักรไทย "
        "และมาตรา 5 แห่งพระราชบัญญัติสถานบริการ พ.ศ. 2509 "
        "จึงทรงพระกรุณาโปรดเกล้าฯ ให้ตราพระราชกฤษฎีกาขึ้นไว้ ดังต่อไปนี้"
    )

    def test_its_section_does_not_attach_to_the_act_below_it(self):
        # How this was noticed: ``มาตรา 175`` filed under two unrelated acts.
        assert parent.read(self.DECREE) == [
            "พระราชบัญญัติสถานบริการ พ.ศ. 2509 มาตรา 5"
        ]

    def test_the_act_keeps_every_section_that_is_its_own(self):
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 175 ของรัฐธรรมนูญแห่งราชอาณาจักรไทย "
            "กับมาตรา 56 และมาตรา 60 "
            "แห่งพระราชบัญญัติมหาวิทยาลัยราชภัฏ พ.ศ. 2547 ดังต่อไปนี้"
        )
        assert got == [
            "พระราชบัญญัติมหาวิทยาลัยราชภัฏ พ.ศ. 2547 มาตรา 56",
            "พระราชบัญญัติมหาวิทยาลัยราชภัฏ พ.ศ. 2547 มาตรา 60",
        ]

    def test_a_preamble_with_no_constitution_is_unchanged(self):
        # Written closed up because ``close_gap`` shuts the space the Gazette
        # prints between an instrument's word and its name. The ``ก.`` style
        # used elsewhere in these tests reads as that gap, so this one spells
        # an invented name out instead.
        assert parent.read(
            "อาศัยอำนาจตามความในมาตรา 24 แห่งพระราชบัญญัติทดสอบระบบ พ.ศ. 2560 ดังต่อไปนี้"
        ) == ["พระราชบัญญัติทดสอบระบบ พ.ศ. 2560 มาตรา 24"]

    def test_the_constitution_alone_leaves_nothing_behind(self):
        assert parent.read(
            "อาศัยอำนาจตามความในมาตรา 175 ของรัฐธรรมนูญแห่งราชอาณาจักรไทย ดังต่อไปนี้"
        ) == []
