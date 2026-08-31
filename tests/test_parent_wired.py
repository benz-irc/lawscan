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


class TestTheAddressIsWrittenWhole:
    """V16 says strip ``วรรค`` and the brackets. The operator's file keeps them.

    Measured against their own V16 run over 22 documents: stripping both scores
    63.6% on this column, keeping both 68.2%. Their sheet writes ``มาตรา 7
    วรรคสาม`` and ``ข้อ 4 (37)`` in the very column the instruction says to
    strip, so the address is written the way an address is written.
    """

    def test_a_sub_clause_is_kept(self):
        assert parent.DROP_BRACKETS is False
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 25 (5) แห่งพระราชบัญญัติทดสอบระบบ พ.ศ. 2542 ดังต่อไปนี้"
        )
        assert got == ["พระราชบัญญัติทดสอบระบบ พ.ศ. 2542 มาตรา 25 (5)"]

    def test_two_sub_clauses_of_one_section_stay_two_citations(self):
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 25 (5) และมาตรา 25 (7) "
            "แห่งพระราชบัญญัติทดสอบระบบ พ.ศ. 2542 ดังต่อไปนี้"
        )
        assert len(got) == 2

    def test_a_paragraph_is_kept_except_the_first(self):
        assert parent.KEEP_PARAGRAPH is True
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 7 วรรคสาม แห่งพระราชบัญญัติทดสอบระบบ พ.ศ. 2543 ดังต่อไปนี้"
        )
        assert got == ["พระราชบัญญัติทดสอบระบบ พ.ศ. 2543 มาตรา 7 วรรคสาม"]
        # ``วรรคหนึ่ง`` still goes: every section has a first paragraph, so
        # writing it points at nothing the bare number does not already.
        assert parent.read(
            "อาศัยอำนาจตามความในมาตรา 7 วรรคหนึ่ง แห่งพระราชบัญญัติทดสอบระบบ พ.ศ. 2543 ดังต่อไปนี้"
        ) == ["พระราชบัญญัติทดสอบระบบ พ.ศ. 2543 มาตรา 7"]


class TestNotPayingForIt:
    def test_the_question_is_dropped_once_the_rule_answers(self):
        # Both of the question's columns, not one: since V17 it also answers
        # ``กฎหมายที่อ้างถึง``, which no rule reads, so a filled parent column
        # on its own no longer means the question has nothing left to say.
        assert _answered_by_rules(PARENT, {
            "กฎหมายแม่": "พ.ร.บ. ก. พ.ศ. 2560 มาตรา 5",
            "กฎหมายที่อ้างถึง": "-",
        })
        assert not _answered_by_rules(
            PARENT, {"กฎหมายแม่": "พ.ร.บ. ก. พ.ศ. 2560 มาตรา 5"}
        )

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


class TestEveryFieldAQuestionAsksForReachesAColumn:
    """A field with no row in the map is answered, paid for, and thrown away.

    ``repealsWhole`` was in the schema and the model filled it correctly, and
    the column stayed empty on every document, because the map that turns
    fields into columns had no line for it. Nothing failed — the answer simply
    went nowhere, which reads exactly like a document that had nothing to say.
    """

    def test_no_question_asks_for_a_field_the_map_drops(self):
        from lawscan.llm.questions import ALL
        from lawscan.pipeline import _FIELDS as FIELDS

        # Three answers are composed by hand rather than copied cell for cell:
        # ``audience`` holds two readings of the same groups, ``parents`` is a
        # list of law-and-section pairs joined into one string, and
        # ``business`` asks for the scratch work and the per-code summary
        # separately so neither crowds the other out, then prints both in the
        # one column the sheet has for them.
        by_hand = {"audience": {"split", "roles"},
                   "parent": {"parents", "referenced"},
                   "business": {"analysis"},
                   # ``support`` shares the reasoning cell with ``business``
                   # and leaves the confidence cell to it, so that the two
                   # numbers do not overwrite each other in one column.
                   "support": {"analysis", "confidence"}}
        for question in ALL:
            fields = set(question.schema.get("properties", {}))
            mapped = set(FIELDS.get(question.name, {})) | by_hand.get(question.name, set())
            missing = fields - mapped
            assert not missing, (
                f"{question.name} ถามหา {sorted(missing)} แต่ไม่มีในตารางแปลงเป็นคอลัมน์ — "
                "จ่ายค่าคำตอบแล้วทิ้ง"
            )


class TestTheGapTheGazettePrints:
    """``พระราชบัญญัติ โรคระบาดสัตว์`` on the page, closed up everywhere else.

    The typesetting opens a space between the word an instrument calls itself
    and its name. The operator's sheet writes it closed, so the space made two
    otherwise identical strings compare as different.
    """

    def test_the_gap_after_the_instrument_word_closes(self):
        got = parent.read(
            "อาศัยอำนาจตามความในมาตรา 5 แห่งพระราชบัญญัติ ทดสอบระบบ พ.ศ. 2558 "
            "รัฐมนตรีออกกฎกระทรวงไว้ ดังต่อไปนี้"
        )
        assert got == ["พระราชบัญญัติทดสอบระบบ พ.ศ. 2558 มาตรา 5"]

    def test_the_space_before_wa_duai_is_left_alone(self):
        from lawscan.rules.parent import close_gap

        assert close_gap("ระเบียบ ว่าด้วยการทดสอบ") == "ระเบียบ ว่าด้วยการทดสอบ"
        assert close_gap("ประกาศ เรื่อง ทดสอบระบบ") == "ประกาศ เรื่อง ทดสอบระบบ"

    def test_a_name_already_closed_is_unchanged(self):
        from lawscan.rules.parent import close_gap

        assert close_gap("พระราชบัญญัติทดสอบระบบ พ.ศ. 2558") == "พระราชบัญญัติทดสอบระบบ พ.ศ. 2558"


class TestTheTwoWaysAnInstrumentHasAParentWithoutClaimingOne:
    """The operator's decision tree has three checks and the rule only had the
    first. Check 2: an amending act names the act it changes in its own title.
    Check 3: a circular or a ruling names the act it explains. Only what is
    neither leaves the column blank."""

    def test_an_amending_act_names_its_parent_in_its_title(self):
        from lawscan.rules.parent import read

        assert read('มาตรา ๑ พระราชบัญญัตินี้เรียกว่า "พระราชบัญญัติแก้ไขเพิ่มเติม'
                    'พระราชกำหนดการประมง พ.ศ. ๒๕๕๘ พ.ศ. ๒๕๖๑"') == [
            "พระราชกำหนดการประมง พ.ศ. 2558"]

    def test_the_amendment_number_and_its_own_year_come_off(self):
        """``(ฉบับที่ ๘) พ.ศ. ๒๕๕๗`` belongs to the amendment; the act it
        amends closed at its own year."""
        from lawscan.rules.parent import read

        assert read("พระราชบัญญัติ แก้ไขเพิ่มเติมพระราชกำหนดพิกัดอัตราศุลกากร "
                    "พ.ศ. ๒๕๓๐ (ฉบับที่ ๘) พ.ศ. ๒๕๕๗") == [
            "พระราชกำหนดพิกัดอัตราศุลกากร พ.ศ. 2530"]

    def test_a_circular_names_the_act_it_explains(self):
        from lawscan.rules.parent import read

        assert read("ตามที่ได้มีพระราชบัญญัติภาษีที่ดินและสิ่งปลูกสร้าง พ.ศ. ๒๕๖๒ "
                    "ใช้บังคับ เพื่อให้การปฏิบัติตามเป็นไปในแนวทางเดียวกัน") == [
            "พระราชบัญญัติภาษีที่ดินและสิ่งปลูกสร้าง พ.ศ. 2562"]

    def test_the_authority_clause_still_wins_when_there_is_one(self):
        """Check 1 runs first: an instrument that cites authority is read from
        the citation, sections and all, not from anything later."""
        from lawscan.rules.parent import read

        assert read("อาศัยอำนาจตามความในมาตรา ๑๗ วรรคหนึ่ง แห่งพระราชบัญญัติ"
                    "มาตรฐานผลิตภัณฑ์อุตสาหกรรม พ.ศ. ๒๕๑๑ ซึ่งแก้ไขเพิ่มเติมโดย"
                    "พระราชบัญญัติมาตรฐานผลิตภัณฑ์อุตสาหกรรม (ฉบับที่ ๘) พ.ศ. ๒๕๖๒") == [
            "พระราชบัญญัติมาตรฐานผลิตภัณฑ์อุตสาหกรรม พ.ศ. 2511 มาตรา 17"]


class TestARulingHasNoParent:
    """A judgment applies law rather than being made under one. Both answer
    files agree without exception — 18 rulings in the 240 and 1 in the 22, and
    a dash on every one — so the model's answer does not get to stand."""

    def test_the_kind_alone_settles_it(self):
        from lawscan.rules import kind

        assert "คำวินิจฉัยศาลรัฐธรรมนูญ" in kind.NARRATIVE
        assert "คำพิพากษาของศาลฎีกาแผนกคดีอาญา" in kind.NARRATIVE
        assert "กฎกระทรวง" not in kind.NARRATIVE

    def test_the_rule_reads_a_ruling_as_parentless(self):
        from lawscan.rules.parent import has_no_parent, read

        text = ("คำวินิจฉัยศาลรัฐธรรมนูญที่ ๑/๒๕๖๓ … ตามพระราชบัญญัติประกอบ"
                "รัฐธรรมนูญว่าด้วยพรรคการเมือง พ.ศ. ๒๕๖๐ มาตรา ๙๒ วรรคสอง")
        assert has_no_parent(text)
        assert read(text) == []


class TestAnEditionNamesWhatItChangesByNamingItself:
    """An instrument titled ``(ฉบับที่ ๒)`` exists to change the one before it
    and carries none of the keywords the amends rule looks for — 100019 has no
    ``ให้ยกเลิกความใน``, no ``ให้ใช้ความต่อไปนี้แทน``, no ``ให้เพิ่มความ``. What
    it has is its own title at an earlier year, printed again further down."""

    def test_it_reads_the_earlier_year_and_the_first_real_section(self):
        from lawscan.rules.parent import amended_edition

        text = ("พระราชกฤษฎีกา กำหนดเขตพื้นที่ ในท้องที่จังหวัด ก. (ฉบับที่ ๒) พ.ศ. ๒๕๖๓ "
                "โดยที่เป็นการสมควรแก้ไขเพิ่มเติมการกำหนดเขตพื้นที่ "
                "อาศัยอำนาจตามความในมาตรา ๑๗๕ ของรัฐธรรมนูญ และมาตรา ๕ แห่งพระราชบัญญัติ ข. "
                "มาตรา ๑ พระราชกฤษฎีกานี้เรียกว่า… "
                "มาตรา ๒ ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ "
                "มาตรา ๓ ในท้องที่จังหวัด ก. ให้เฉพาะเขต… "
                "แผนที่ท้ายพระราชกฤษฎีกากำหนดเขตพื้นที่ในท้องที่จังหวัด ก. (ฉบับที่ ๒) พ.ศ. ๒๕๒๓")
        assert amended_edition(text) == (
            "พระราชกฤษฎีกา กำหนดเขตพื้นที่ ในท้องที่จังหวัด ก. พ.ศ. 2523 (มาตรา 3)")

    def test_the_preambles_own_citation_is_not_the_section(self):
        """Scanning from the top picked ``มาตรา 5`` out of the authority
        clause — the instrument's sections start at ``มาตรา ๑``."""
        from lawscan.rules.parent import amended_edition

        assert "มาตรา 3" in amended_edition(
            "พระราชกฤษฎีกา กำหนดเขตพื้นที่เพื่อการอนุญาต (ฉบับที่ ๒) พ.ศ. ๒๕๖๓ "
            "โดยที่เป็นการสมควรแก้ไขเพิ่มเติมการกำหนดเขตพื้นที่ "
            "อาศัยอำนาจตามความในมาตรา ๕ แห่งพระราชบัญญัติ ข. "
            "มาตรา ๑ เรียกว่า… มาตรา ๒ ให้ใช้บังคับ… มาตรา ๓ เนื้อหา… "
            "พระราชกฤษฎีกากำหนดเขตพื้นที่เพื่อการอนุญาต (ฉบับที่ ๒) พ.ศ. ๒๕๒๓")

    def test_a_title_too_short_to_identify_anything_is_left_alone(self):
        """OCR gives back a stub of a title often enough that a short one is
        not evidence — matching on it would name the wrong act."""
        from lawscan.rules.parent import amended_edition

        assert amended_edition("กฎ ก. (ฉบับที่ ๒) พ.ศ. ๒๕๖๓ โดยที่เป็นการสมควรแก้ไขเพิ่มเติม "
                               "… กฎ ก. พ.ศ. ๒๕๒๓") == ""

    def test_an_edition_that_does_not_say_it_amends_is_left_alone(self):
        """A royal decree issued under the Revenue Code is numbered by edition
        and still stands on its own — 100017 is ``(ฉบับที่ N)`` and the sheet
        leaves its amends column empty. The sentence of intent separates them."""
        from lawscan.rules.parent import amended_edition

        assert amended_edition(
            "พระราชกฤษฎีกา ออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร "
            "(ฉบับที่ ๗๗๐) พ.ศ. ๒๕๖๓ โดยที่เป็นการสมควรยกเว้นภาษีเงินได้ให้แก่บริษัท "
            "… พระราชกฤษฎีกา ออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร พ.ศ. ๒๕๖๐") == ""

    def test_an_instrument_with_no_edition_in_its_title_is_left_alone(self):
        from lawscan.rules.parent import amended_edition

        assert amended_edition("กฎกระทรวง กำหนดบริเวณห้ามก่อสร้าง พ.ศ. ๒๕๖๓ …") == ""
