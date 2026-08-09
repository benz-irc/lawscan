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
