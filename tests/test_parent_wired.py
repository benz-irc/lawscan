"""The parent act, read off the page instead of asked for.

Document 100001 is why this rule is wired in. The model was asked, and it
answered ``พระราชบัญญัติควบคุมรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. 2560`` —
a word (``ควบคุม``) that appears nowhere in the document — with ``section:
null``, while its own ``evidence`` field quoted the preamble correctly:

    อาศัยอำนาจตามความในมาตรา 24 (3) และมาตรา 42 (4) แห่งพระราชบัญญัติ
    ประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. 2560

It copied the sentence and then got it wrong. The sentence has a fixed shape,
so the rule reads it and the question is not put at all.
"""

from lawscan.merge import Row
from lawscan.pipeline import _apply, _answered_by_rules, _piece
from lawscan.rules import parent, run_all
from lawscan.llm.questions import PARENT

PREAMBLE = (
    "ระเบียบผู้ตรวจการแผ่นดิน ว่าด้วยค่าใช้จ่ายในการเดินทางไปปฏิบัติงาน พ.ศ. 2563\n"
    "โดยที่เป็นการสมควรให้มีระเบียบเกี่ยวกับค่าใช้จ่ายในการเดินทางไปปฏิบัติงาน "
    "อาศัยอำนาจตามความในมาตรา 24 (3) และมาตรา 42 (4) "
    "แห่งพระราชบัญญัติประกอบรัฐธรรมนูญว่าด้วยผู้ตรวจการแผ่นดิน พ.ศ. 2560 "
    "ประธานผู้ตรวจการแผ่นดินและผู้ตรวจการแผ่นดินปรึกษาหารือและเห็นชอบร่วมกัน "
    "จึงออกระเบียบไว้ ดังต่อไปนี้ ข้อ 1 ระเบียบนี้เรียกว่า"
)


class TestTheDocumentThatCausedThis:
    def test_the_act_is_the_one_on_the_page(self):
        got = parent.read(PREAMBLE)
        assert all("ประกอบรัฐธรรมนูญ" in line for line in got)
        assert not any("ควบคุม" in line for line in got)

    def test_both_sections_are_kept_not_one(self):
        got = parent.read(PREAMBLE)
        assert len(got) == 2
        assert got[0].endswith("มาตรา 24 (3)")
        assert got[1].endswith("มาตรา 42 (4)")

    def test_the_rule_fills_the_column(self):
        class Doc:
            number = "100001"
            pages = ()
            unread_pages = ()
            header_text = PREAMBLE
            body_text = PREAMBLE

            def text(self):
                return PREAMBLE

        assert "ประกอบรัฐธรรมนูญ" in run_all(Doc())["กฎหมายแม่"]


class TestBracketsAreKept:
    def test_a_sub_clause_survives(self):
        # 86 of the reference's citations carry one; dropping it loses all 86,
        # and keeping one the document never wrote costs nothing.
        assert parent.DROP_BRACKETS is False
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 25 (5) แห่งพระราชบัญญัติป้องกันและปราบปราม"
            "การฟอกเงิน พ.ศ. 2542 ดังต่อไปนี้"
        )
        assert got == ["พระราชบัญญัติป้องกันและปราบปรามการฟอกเงิน พ.ศ. 2542 มาตรา 25 (5)"]

    def test_two_sub_clauses_of_one_section_stay_two_citations(self):
        # Dropping the brackets collapses these into one line and loses a
        # citation, which is the mechanism behind the 86.
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 25 (5) และมาตรา 25 (7) "
            "แห่งพระราชบัญญัติป้องกันและปราบปรามการฟอกเงิน พ.ศ. 2542 ดังต่อไปนี้"
        )
        assert len(got) == 2


class TestNotPayingForIt:
    def test_the_question_is_dropped_once_the_rule_answers(self):
        assert _answered_by_rules(PARENT, {"กฎหมายแม่": "พ.ร.บ. ก. พ.ศ. 2560 มาตรา 5"})

    def test_it_is_still_asked_where_the_rule_is_silent(self):
        # 35 of the 240 carry no authority sentence to read.
        assert parent.read("ประกาศฉบับนี้ไม่มีวลีอ้างอำนาจใด ๆ ทั้งสิ้น") == []
        assert not _answered_by_rules(PARENT, {"ประเภทกฎหมาย": "ประกาศ"})


class TestNullNeverReachesTheCell:
    """A composed string is built before ``merge._text`` ever sees it."""

    def test_a_null_section_does_not_become_the_word_None(self):
        row = Row(document="100001")
        _apply(row, "parent", {"parents": [{"law": "พระราชบัญญัติ ก. พ.ศ. 2560",
                                            "section": None}]})
        assert row.value("กฎหมายแม่") == "พระราชบัญญัติ ก. พ.ศ. 2560"

    def test_the_string_null_is_treated_the_same(self):
        row = Row(document="x")
        _apply(row, "parent", {"parents": [{"law": "พ.ร.บ. ก.", "section": "null"}]})
        assert row.value("กฎหมายแม่") == "พ.ร.บ. ก."

    def test_a_law_that_is_null_drops_the_whole_entry(self):
        row = Row(document="x")
        _apply(row, "parent", {"parents": [{"law": None, "section": "มาตรา 5"},
                                           {"law": "พ.ร.บ. ข.", "section": "มาตรา 7"}]})
        assert row.value("กฎหมายแม่") == "พ.ร.บ. ข. มาตรา 7"

    def test_the_helper_agrees_with_the_central_format(self):
        assert _piece(None) == ""
        assert _piece("null") == ""
        assert _piece("ไม่มี") == ""
        assert _piece("มาตรา 5") == "มาตรา 5"
