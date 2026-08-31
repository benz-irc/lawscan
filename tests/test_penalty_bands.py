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
        # link. The relief carve-out that used to be the fourth is gone — a
        # waiver in a title no longer stops a document from deferring to its
        # parent act, because a schedule that waives some fees still sets the
        # rest.
        assert not penalties.links_to_parent(band="GREY", parent="", core="AA4")
        assert not penalties.links_to_parent(
            band="GREY", parent="พระราชบัญญัติทดสอบระบบ พ.ศ. 2560", core="")
        assert not penalties.links_to_parent(
            band="RED", parent="พระราชบัญญัติทดสอบระบบ พ.ศ. 2560", core="AA4")
        assert penalties.links_to_parent(
            band="GREY", parent="พระราชบัญญัติทดสอบระบบ พ.ศ. 2560", core="AA4",
            title="กฎกระทรวงยกเว้นค่าธรรมเนียม")


class TestACageIsNotADetention:
    """``กักขัง`` is both a criminal penalty and a place you keep an animal.

    118 pages of the corpus carry the bare word, and eleven documents carry it
    with no other criminal word anywhere in them: an animal container, a fish
    kept in captivity, a prison workshop named in a list of suppliers. Every
    one of those was read as a criminal penalty on the strength of the word
    alone.
    """

    def test_a_container_for_animals_is_not_a_criminal_penalty(self):
        caged = ("ให้ทำลายภาชนะสิ่งห่อหุ้มหรือกักขังสัตว์หรือซากสัตว์ "
                 "และให้ผู้รับใบอนุญาตเป็นผู้รับผิดชอบค่าใช้จ่าย")
        assert penalties.read(caged, None).band != "RED"

    def test_detention_named_as_a_penalty_still_reads_red(self):
        assert penalties.read(
            "ผู้ใดฝ่าฝืนต้องระวางโทษกักขังไม่เกินหนึ่งเดือน", None
        ).band == "RED"


class TestSayingThereIsNoPenalty:
    """``ไม่มีโทษ`` and ``-`` are the same answer. The sheet writes the dash —
    across the operator's 240 rows these words appear in the column zero times
    — so an answer phrased this way is right but scored as though it named a
    punishment."""

    def test_the_words_for_absence_become_a_dash(self):
        assert penalties.plain("ไม่มีโทษ") == "-"
        assert penalties.plain("ไม่มีบทลงโทษ") == "-"
        assert penalties.plain("ไม่ระบุโทษ") == "-"
        assert penalties.plain("ไม่มีบทลงโทษในกฎหมายฉบับนี้") == "-"

    def test_a_stated_punishment_is_left_alone(self):
        assert penalties.plain("ปรับไม่เกิน 500 บาท") == "ปรับไม่เกิน 500 บาท"
        assert penalties.plain("โทษทางปกครอง / โทษทางแพ่ง") == "โทษทางปกครอง / โทษทางแพ่ง"

    def test_a_penalty_waiting_on_its_parent_act_is_left_alone(self):
        linked = "รอเชื่อมโยง: พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5"
        assert penalties.plain(linked) == linked

    def test_the_word_ไม่_inside_a_punishment_does_not_trip_it(self):
        """``ปรับไม่เกิน`` opens with the same syllable and is a real penalty."""
        assert penalties.plain("ปรับไม่เกินหนึ่งหมื่นบาท") == "ปรับไม่เกินหนึ่งหมื่นบาท"

    def test_the_reason_behind_the_absence_does_not_make_it_a_punishment(self):
        """``ไม่มีโทษ (คำวินิจฉัยฉบับนี้ไม่ได้สั่งลงโทษผู้ใด)`` — the bracket
        explains the answer rather than adding to it."""
        assert penalties.plain("ไม่มีโทษ (คำวินิจฉัยฉบับนี้ไม่ได้สั่งลงโทษผู้ใด)") == "-"
        assert penalties.plain("ไม่มีบทลงโทษ - เอกสารนี้เป็นระเบียบภายใน") == "-"

    def test_a_punishment_keeps_its_bracket(self):
        assert penalties.plain("ปรับไม่เกิน 500 บาท (มาตรา 5)") == "ปรับไม่เกิน 500 บาท (มาตรา 5)"


class TestHousekeepingDoesNotOverruleAStatedLink:
    """An empty core column stopped being reliable on its own once V19 asked
    for the issuing body's code there: a model that finds nothing has either
    read a housekeeping instrument or missed the businesses. What it wrote in
    the penalty column settles which."""

    def test_a_stated_link_blocks_the_rule(self):
        assert not penalties.is_housekeeping(
            "GREEN", "", "รอเชื่อมโยง: พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5")

    def test_silence_still_reads_as_housekeeping(self):
        assert penalties.is_housekeeping("GREEN", "", "-")
        assert penalties.is_housekeeping("GREEN", "")

    def test_a_business_code_still_blocks_it(self):
        assert not penalties.is_housekeeping("GREEN", "AB2")


class TestAReasonJoinedByAConjunction:
    """``ไม่มีโทษ เนื่องจาก…`` arrives with neither a bracket nor a dash — the
    model simply keeps writing — and the sheet still wants a dash in the cell."""

    def test_the_conjunction_ends_the_answer(self):
        assert penalties.plain("ไม่มีโทษ เนื่องจากคำวินิจฉัยไม่ได้สั่งลงโทษผู้ใด") == "-"
        assert penalties.plain("ไม่มีบทลงโทษ เพราะเป็นระเบียบภายใน") == "-"

    def test_a_real_punishment_is_untouched(self):
        assert penalties.plain("ปรับไม่เกินหนึ่งหมื่นบาท") == "ปรับไม่เกินหนึ่งหมื่นบาท"


class TestDenyingAPenaltyInWhateverWords:
    """The list of ways to write "no punishment" grew with every run —
    ``ไม่มีโทษ``, then ``ไม่มีโทษ เนื่องจาก…``, then
    ``ไม่มีข้อกำหนดโทษสำหรับภาคธุรกิจ…``. Matching a shape rather than a phrase
    is what stops the next wording from landing a sentence in a cell the sheet
    writes as a dash."""

    def test_a_denial_in_new_words_still_becomes_a_dash(self):
        assert penalties.plain("ไม่มีข้อกำหนดโทษสำหรับภาคธุรกิจหรือประชาชนในคำวินิจฉัยนี้") == "-"
        assert penalties.plain("ไม่ปรากฏบทลงโทษในเอกสารฉบับนี้") == "-"
        assert penalties.plain("ไม่ได้กำหนดโทษไว้") == "-"

    def test_a_denial_that_names_a_punishment_survives(self):
        """``ไม่มีโทษจำคุก แต่มีโทษปรับ`` opens with a denial and is still
        describing a consequence."""
        kept = "ไม่มีโทษจำคุก แต่มีโทษปรับทางปกครอง"
        assert penalties.plain(kept) == kept

    def test_a_stated_punishment_is_untouched(self):
        assert penalties.plain("โทษทางปกครอง (เพิกถอนสิทธิ)") == "โทษทางปกครอง (เพิกถอนสิทธิ)"
