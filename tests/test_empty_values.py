"""Every way of writing "nothing", written one way.

Three states reach a cell and only two of them look alike:

    a value            → the value
    nobody answered    → ``""``   the export leaves it blank
    answered "nothing" → ``-``    the same mark a rule leaves

A model that writes ``ไม่มี`` or ``null`` has answered — it said the law has
none of this. Putting that in the column as the word ``null`` reads as a
program that broke, and as a blank it reads as a question nobody reached.

``null`` arrived with strict schemas: strict mode requires every property in
``required``, so an optional field is declared nullable and the model answers
``null`` rather than omitting it. ``ไม่มี`` and ``None`` predate it — eleven
cells of the last 300-document run carry one of the three.
"""

from lawscan.merge import NOTHING, Row, _text


class TestTheThreeStates:
    def test_a_value_is_itself(self):
        assert _text("ใบอนุญาตประกอบกิจการ") == "ใบอนุญาตประกอบกิจการ"

    def test_nobody_answered_stays_blank(self):
        # ``None`` is a key the model left out. ``""`` is how a rule abstains —
        # ``title.read`` returns it for the documents it cannot name, and a
        # dash there would claim the document has no title.
        assert _text(None) == ""
        assert _text("") == ""

    def test_answering_nothing_is_a_dash(self):
        for said in ("ไม่มี", "null", "None", "N/A", "nan", "ไม่ระบุ", "undefined"):
            assert _text(said) == NOTHING, said

    def test_case_does_not_matter(self):
        assert _text("NULL") == NOTHING
        assert _text("  None  ") == NOTHING


class TestLists:
    def test_items_are_joined_the_way_the_export_writes_them(self):
        assert _text(["ก", "ข"]) == "ก, ข"

    def test_a_hole_in_a_list_is_dropped_not_joined(self):
        # ``["ใบอนุญาต ก", null]`` is one licence, not one licence and a hole.
        assert _text(["ใบอนุญาต ก", None]) == "ใบอนุญาต ก"
        assert _text(["ใบอนุญาต ก", "ไม่มี"]) == "ใบอนุญาต ก"

    def test_a_list_with_nothing_in_it_is_an_answer(self):
        # The model returned a list and put nothing in it. That is "none",
        # not "unreached".
        assert _text([]) == NOTHING
        assert _text([None, "null"]) == NOTHING


class TestThroughTheRow:
    def test_a_model_saying_nothing_does_not_displace_a_rule(self):
        row = Row(document="1")
        row.put("จังหวัด", "บุรีรัมย์", "rule")
        row.put("จังหวัด", "ไม่มี", "llm:identity")
        assert row.value("จังหวัด") == "บุรีรัมย์"

    def test_it_reaches_the_cell_as_a_dash(self):
        row = Row(document="1")
        row.put("ใบอนุญาต", "null", "llm:summary")
        assert row.value("ใบอนุญาต") == NOTHING

    def test_an_abstaining_rule_leaves_room_for_the_model(self):
        row = Row(document="1")
        row.put("ชื่อกฎหมาย", "", "rule")
        row.put("ชื่อกฎหมาย", "ระเบียบกรมเจ้าท่า ว่าด้วยเขตการเดินเรือ", "llm:identity")
        assert row.value("ชื่อกฎหมาย").startswith("ระเบียบกรมเจ้าท่า")


class TestTheExportedFile:
    def test_no_cell_of_a_real_run_carries_one_of_these_words(self):
        import csv
        from pathlib import Path

        result = Path("out/ab-dash/result.csv")
        if not result.exists():
            return  # runs are not kept in the repository
        csv.field_size_limit(10**8)
        banned = {"none", "null", "nan", "n/a", "undefined", "[]", "{}",
                  "ไม่มี", "ไม่ระบุ"}
        with result.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                for column, value in row.items():
                    assert (value or "").strip().casefold() not in banned, (column, value)


class TestASeparatorTheSchemaDidNotOffer:
    """A tab inside one list entry is two entries, not one long name.

    ``agencies`` came back as ``["สำนักงาน ก.\tกระทรวง ข."]`` on 77 entries of a
    240-document run — one array slot holding two bodies, joined by a character
    that is invisible in a spreadsheet. The cell then read as though one office
    had a very long name.
    """

    def test_a_tab_splits_into_two_entries(self):
        assert _text(["สำนักงาน ก.\tกระทรวง ข."]) == "สำนักงาน ก., กระทรวง ข."

    def test_a_newline_does_the_same(self):
        assert _text(["สำนักงาน ก.\nกระทรวง ข."]) == "สำนักงาน ก., กระทรวง ข."

    def test_a_trailing_tab_adds_nothing(self):
        assert _text(["คณะกรรมการข้อมูลข่าวสาร\t"]) == "คณะกรรมการข้อมูลข่าวสาร"

    def test_the_ministry_named_by_three_offices_appears_once(self):
        # Splitting is what creates the repeat, so the two belong together.
        assert _text([
            "กองกฎหมาย\tกระทรวงพาณิชย์",
            "กองราคา\tกระทรวงพาณิชย์",
        ]) == "กองกฎหมาย, กระทรวงพาณิชย์, กองราคา"

    def test_an_ordinary_space_is_left_alone(self):
        # Only tabs and line breaks are separators. A space is part of a name.
        assert _text(["สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล (PDPC / สคส.)"]) == (
            "สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล (PDPC / สคส.)"
        )

    def test_prose_is_not_a_list_and_keeps_its_shape(self):
        # A scalar is never split — ``คำอธิบายและสรุปสาระสำคัญ`` is one answer
        # even when the model wrapped it across lines.
        assert _text("บรรทัดหนึ่ง\nบรรทัดสอง") == "บรรทัดหนึ่ง\nบรรทัดสอง"

    def test_once_each_agrees_with_the_central_format(self):
        from lawscan.answers import once_each

        assert once_each(["ก\tข", "ข"]) == ["ก", "ข"]


class TestFormattingTheModelBorrowedFromThePrompt:
    """Answers that came back still wearing the shape of the instruction."""

    def test_angle_brackets_round_an_example_are_not_part_of_the_answer(self):
        # ``prompts/summary.md`` drew its tag examples as ``<หลักสูตร>`` and the
        # model copied the brackets onto real answers — 67 cells of a
        # 240-document run.
        assert _text(["<ทรัพย์สิน>, <เงิน>, <ที่ดิน>"]) == "ทรัพย์สิน, เงิน, ที่ดิน"

    def test_a_bracket_closed_but_never_opened_goes_too(self):
        assert _text(["<หิน>, หินประดับ, ทรายอุตสาหกรรม>"]) == "หิน, หินประดับ, ทรายอุตสาหกรรม"

    def test_a_bracketed_nothing_is_still_nothing(self):
        assert _text(["<ไม่ระบุ>"]) == NOTHING

    def test_a_generation_that_kept_talking_is_cut_at_the_fence(self):
        # Document 100052: valid JSON, then a code fence, then the model's own
        # second thoughts in English. ``ok`` was true and nothing downstream
        # had reason to doubt it.
        assert _text('เอกสาร ก.```Yes but there is a formatting error') == "เอกสาร ก."

    def test_an_answer_with_no_fence_is_untouched(self):
        assert _text("ระเบียบกรมเจ้าท่า ว่าด้วยเขตการเดินเรือ") == (
            "ระเบียบกรมเจ้าท่า ว่าด้วยเขตการเดินเรือ"
        )


class TestAnswersCopiedFromThePrompt:
    """The fourth time in one corpus that an example became the answer."""

    def test_a_licence_the_document_never_names_is_dropped(self):
        from lawscan.answers import named_in

        # `prompts/summary.md` listed five kinds of licence as examples, and
        # 30 documents of 240 came back with that list, in that order.
        assert named_in("ระเบียบว่าด้วยการสรรหากรรมการ", [
            "ใบอนุญาตให้ประกอบกิจการ", "ใบรับแจ้ง", "หนังสือแสดงความจำนง",
        ]) == []

    def test_one_the_document_does_name_survives(self):
        from lawscan.answers import named_in

        assert named_in("ผู้ใดประสงค์จะประกอบกิจการต้องมีใบอนุญาตให้ประกอบกิจการ",
                        ["ใบอนุญาตให้ประกอบกิจการ", "ใบรับแจ้ง"]) == [
            "ใบอนุญาตให้ประกอบกิจการ"]

    def test_a_form_code_in_brackets_matches_on_its_name(self):
        from lawscan.answers import named_in

        assert named_in("ให้ยื่นแบบแจ้งตามที่ระเบียบกำหนด",
                        ["แบบแจ้งตามที่ระเบียบกำหนด (แบบ ก.๑)"])

    def test_a_bare_family_code_is_not_an_answer(self):
        from lawscan.rules.categories import correct

        # "หมวดย่อยเสมอ" is in the prompt and nothing enforced it: ten reached
        # the sheet and the reference file contains none.
        core, support = correct("ประกาศเรื่องหนึ่ง", ["AM", "AM19"], ["CC", "CC17"])
        assert "AM" not in core and "CC" not in support
        assert "AM19" in core and "CC17" in support

    def test_the_constitution_is_never_a_parent(self):
        from lawscan.merge import Row
        from lawscan.pipeline import _apply

        row = Row(document="100059")
        _apply(row, "parent", {"parents": [
            {"law": "รัฐธรรมนูญแห่งราชอาณาจักรไทย", "section": "มาตรา 122"},
            {"law": "พระราชบัญญัติ ก. พ.ศ. 2560", "section": "มาตรา 5"},
        ]})
        assert row.value("กฎหมายแม่") == "พระราชบัญญัติ ก. พ.ศ. 2560 มาตรา 5"
