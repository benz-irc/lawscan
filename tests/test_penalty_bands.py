"""Two bands the phrase lists could not tell apart, and what settles them.

Both rules here read the business codes, which is a model answer — so both run
after the questions rather than in the first rules pass. That is not a design
preference; it is the only place the signal exists.

The numbers in the docstrings are from the operator's 240 answered documents.
Together these two moved ``ระดับวามเสี่ยง`` from 61.5% to 69.2% and ``บทลงโทษ``
from 29.3% to 36.0%.
"""

from lawscan.rules import penalties


class TestHousekeeping:
    """🔵 ฟ้า is about who the instrument binds, not about which words it uses."""

    def test_guidance_that_binds_no_business_is_government_housekeeping(self):
        assert penalties.is_housekeeping("GREEN", "")
        assert penalties.is_housekeeping("GREEN", "-")

    def test_guidance_that_binds_a_business_is_not(self):
        # The business codes are the whole distinction. A guidance document a
        # company has to follow is not internal housekeeping however politely
        # it is worded.
        assert not penalties.is_housekeeping("GREEN", "AA4, D7")

    def test_a_band_that_states_a_consequence_is_left_alone(self):
        # Only GREEN is reclassified. A document that jails people is not
        # housekeeping because nobody filled in a business code for it.
        for band in ("RED", "ORANGE", "YELLOW", "BLUE", "GREY", "UNKNOWN"):
            assert not penalties.is_housekeeping(band, "")


class TestAmendments:
    """An instrument whose whole job is editing an earlier one carries nothing."""

    def test_an_amending_instrument_is_recognised(self):
        assert penalties.amends(
            "ให้ยกเลิกความในมาตรา ๗ แห่งพระราชบัญญัติ… และให้ใช้ความต่อไปนี้แทน"
        )

    def test_an_ordinary_instrument_is_not(self):
        assert not penalties.amends(
            "อาศัยอำนาจตามความในมาตรา ๕ แห่งพระราชบัญญัติควบคุมอาคาร พ.ศ. ๒๕๒๒ "
            "รัฐมนตรีออกกฎกระทรวงไว้ดังต่อไปนี้"
        )

    def test_an_amendment_does_not_wait_on_its_parents_penalty(self):
        # It passed every other test — silent band, named parent, business
        # codes present — and was being filed as waiting for a penalty it will
        # never carry. Twelve of the fourteen that reached here are marked
        # "Amendment / No Impact" in the operator's file.
        common = {"band": "GREY", "parent": "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5",
                  "core": "AA4"}
        assert penalties.links_to_parent(**common, amending=False)
        assert not penalties.links_to_parent(**common, amending=True)

    def test_the_original_three_tests_still_hold(self):
        # Nothing above replaces them: a document with no parent, or one that
        # binds no business, or one that states its own penalty, still does not
        # link — and the relief carve-out is unchanged.
        assert not penalties.links_to_parent(band="GREY", parent="", core="AA4")
        assert not penalties.links_to_parent(
            band="GREY", parent="พระราชบัญญัติแร่ พ.ศ. 2560", core="")
        assert not penalties.links_to_parent(
            band="RED", parent="พระราชบัญญัติแร่ พ.ศ. 2560", core="AA4")
        assert not penalties.links_to_parent(
            band="GREY", parent="พระราชบัญญัติแร่ พ.ศ. 2560", core="AA4",
            title="กฎกระทรวงยกเว้นค่าธรรมเนียม")
