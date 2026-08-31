"""When the penalty is not in this document, it is in the one above it.

The operator's risk scale has a band the rules did not know about, and it is
not a shade of severity — it is a statement about *where* the penalty is
written: ``โทษเชื่อมโยงจากกฎหมายแม่``. Every document in it carries
``รอเชื่อมโยง: <parent act> มาตรา …`` in the penalty column, and no document
outside it does. Two columns, one decision.
"""

from lawscan.rules.penalties import LINKED_BAND, link_text, links_to_parent


class TestWhenItApplies:
    def test_a_regulation_over_business_with_a_parent_and_no_penalty_of_its_own(self):
        assert links_to_parent(
            band="GREEN",
            parent="พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5",
            core="AB2, AB3",
        )

    def test_an_internal_regulation_does_not(self):
        """No business codes means the document binds the office, not the public."""
        assert not links_to_parent(band="GREEN", parent="พระราชบัญญัติ ก. มาตรา 5", core="")

    def test_a_document_with_no_parent_does_not(self):
        assert not links_to_parent(band="GREEN", parent="", core="AB2")

    def test_a_document_that_states_its_own_penalty_does_not(self):
        """A red band read จำคุก in this very document. It does not defer."""
        assert not links_to_parent(band="RED", parent="พระราชบัญญัติ ก. มาตรา 5", core="AB2")


class TestTheSentence:
    def test_one_act_with_two_sections_joins_them(self):
        parent = ("พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5, "
                  "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 8")
        assert link_text(parent) == (
            "รอเชื่อมโยง: พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5 และมาตรา 8"
        )

    def test_one_act_with_one_section(self):
        assert link_text("พระราชบัญญัติสถานบริการ พ.ศ. 2509 มาตรา 5") == (
            "รอเชื่อมโยง: พระราชบัญญัติสถานบริการ พ.ศ. 2509 มาตรา 5"
        )

    def test_only_the_first_act_is_named(self):
        """Where two acts are cited the operator names the one that governs."""
        parent = "พระราชบัญญัติอาหาร พ.ศ. 2522 มาตรา 4, พระราชบัญญัติระเบียบบริหาร พ.ศ. 2534 มาตรา 3"
        assert link_text(parent).startswith("รอเชื่อมโยง: พระราชบัญญัติอาหาร พ.ศ. 2522 มาตรา 4")
        assert "ระเบียบบริหาร" not in link_text(parent)

    def test_nothing_to_link_to_is_nothing(self):
        assert link_text("") == ""
        assert link_text("-") == ""

    def test_the_band_is_the_operators_own_words(self):
        assert LINKED_BAND == "โทษเชื่อมโยงจากกฎหมายแม่"


class TestQualifiersAreDropped:
    """The parent column says which paragraph; this column says which section.

    ``มาตรา 5 วรรคหนึ่ง (3)`` tells a reader where inside section 5 the power
    sits. The penalty column names the section to go and read, and a section is
    read whole — the operator writes ``มาตรา 5``.
    """

    def test_a_paragraph_is_dropped(self):
        assert link_text("พระราชบัญญัติแร่ พ.ศ. 2560 มาตรา 5 วรรคสี่") == (
            "รอเชื่อมโยง: พระราชบัญญัติแร่ พ.ศ. 2560 มาตรา 5"
        )

    def test_a_sub_clause_is_dropped(self):
        assert link_text("พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5 (3)") == (
            "รอเชื่อมโยง: พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5"
        )

    def test_both_at_once(self):
        assert link_text("พระราชบัญญัติ ก. พ.ศ. 2500 มาตรา 5 วรรคหนึ่ง (3)") == (
            "รอเชื่อมโยง: พระราชบัญญัติ ก. พ.ศ. 2500 มาตรา 5"
        )

    def test_two_sections_of_one_act_after_stripping(self):
        parent = ("พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5 (3), "
                  "พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 8 (10)")
        assert link_text(parent) == (
            "รอเชื่อมโยง: พระราชบัญญัติควบคุมอาคาร พ.ศ. 2522 มาตรา 5 และมาตรา 8"
        )


def test_a_fee_schedule_that_also_waives_fees_still_links_to_its_parent():
    """The title guard read ``ยกเว้น`` as "no duty here" and it is not.

    ``กฎกระทรวงกำหนดค่าธรรมเนียมและยกเว้นค่าธรรมเนียม…`` sets what a business
    pays and waives some of it. The first half is a duty; the guard saw only
    the second and filed the document as carrying no penalty at all.
    """
    from lawscan.rules.penalties import links_to_parent

    assert links_to_parent(
        band="UNKNOWN",
        parent="พระราชบัญญัติทดสอบระบบ พ.ศ. 2559 มาตรา 5",
        core="K4",
        title="กฎกระทรวง กำหนดค่าธรรมเนียมและยกเว้นค่าธรรมเนียมใบอนุญาตทดสอบ พ.ศ. 2564",
    )


def test_an_amendment_still_carries_no_penalty_of_its_own():
    from lawscan.rules.penalties import links_to_parent

    assert not links_to_parent(
        band="GREY",
        parent="พระราชบัญญัติทดสอบระบบ พ.ศ. 2559 มาตรา 5",
        core="K4",
        title="ระเบียบทดสอบระบบ (ฉบับที่ 2) พ.ศ. 2564",
        amending=True,
    )


class TestTheBandFollowsThePenalty:
    """Two columns, one answer — the operator's rule says the words replace
    the colour, so a cell that says ``รอเชื่อมโยง`` cannot sit beside a colour
    that says the document has no penalty. It did: the band is decided by a
    rule reading the page and the penalty can be decided by the model reading
    the preamble, and the two disagreed on document after document.
    """

    def test_a_linked_penalty_from_the_model_sets_the_band(self):
        from lawscan.merge import Row
        from lawscan.rules import penalties

        row = Row(document="100015")
        row.put("ระดับวามเสี่ยง ", "⚪️ เทา", "rule")
        row.put("บทลงโทษ", "รอเชื่อมโยง: พระราชบัญญัติ ก. พ.ศ. 2522 มาตรา 4", "llm:summary")
        if row.value("บทลงโทษ").startswith(penalties.LINKED_PREFIX):
            row.cells.pop("ระดับวามเสี่ยง ", None)
            row.put("ระดับวามเสี่ยง ", penalties.LINKED_BAND, "rule:linked")
        assert row.value("ระดับวามเสี่ยง ") == penalties.LINKED_BAND

    def test_a_page_that_states_its_own_penalty_keeps_its_colour(self):
        from lawscan.merge import Row
        from lawscan.rules import penalties

        row = Row(document="100013")
        row.put("ระดับวามเสี่ยง ", "🔴 แดง", "rule")
        row.put("บทลงโทษ", "โทษทางอาญา", "rule")
        assert not row.value("บทลงโทษ").startswith(penalties.LINKED_PREFIX)


class TestTheStateIsNotABusiness:
    """``core`` carries the issuing body's own code now, on documents that bind
    nobody else — V19 rule 5.9. Reading the column as "not empty" then files a
    staff-travel regulation as waiting on a penalty in its parent act, which
    flips the risk band too.
    """

    def test_a_state_authority_code_alone_does_not_link(self):
        assert not links_to_parent(
            band="GREY", parent="พระราชบัญญัติ ก. พ.ศ. 2560 มาตรา 5", core="CC9")

    def test_a_business_code_still_links(self):
        assert links_to_parent(
            band="GREY", parent="พระราชบัญญัติ ก. พ.ศ. 2560 มาตรา 5", core="AB2")

    def test_a_business_code_beside_a_state_one_links(self):
        assert links_to_parent(
            band="GREY", parent="พระราชบัญญัติ ก. พ.ศ. 2560 มาตรา 5", core="CC9, AB2")
