"""Reading the title off the page instead of paying to be told it.

Every case here is a real document from the corpus, and the two that look like
trivia are the two that cost the most to find: the ``ว่าด้วย`` substring, which
silently truncated 44% of the corpus, and the bracketed year, which renames the
instrument to one that does not exist.
"""

from lawscan.rules import title


class TestTheOrdinaryShape:
    def test_a_regulation_ends_at_its_year(self):
        assert title.read(
            "ระเบียบผู้ตรวจการแผ่นดิน\nว่าด้วยค่าใช้จ่ายในการเดินทางไปปฏิบัติงาน\nพ.ศ. 2563\n"
            "อาศัยอำนาจตามความในมาตรา 24 แห่งพระราชบัญญัติ..."
        ) == "ระเบียบผู้ตรวจการแผ่นดิน ว่าด้วยค่าใช้จ่ายในการเดินทางไปปฏิบัติงาน พ.ศ. 2563"

    def test_a_decree_ends_before_the_royal_opening(self):
        assert title.read(
            "พระราชกฤษฎีกา\nลดภาษีที่ดินและสิ่งปลูกสร้าง\nพ.ศ. 2563\n"
            "พระบาทสมเด็จพระปรเมนทรรามาธิบดีศรีสินทรมหาวชิราลงกรณ..."
        ) == "พระราชกฤษฎีกา ลดภาษีที่ดินและสิ่งปลูกสร้าง พ.ศ. 2563"

    def test_an_amendment_keeps_its_issue_number(self):
        assert title.read(
            "ระเบียบคณะกรรมการการเลือกตั้ง ว่าด้วยการเลือกตั้งสมาชิกสภาท้องถิ่น "
            "(ฉบับที่ 2) พ.ศ. 2563 โดยที่เป็นการสมควรแก้ไขเพิ่มเติม..."
        ).endswith("(ฉบับที่ 2) พ.ศ. 2563")


class TestTheTwoTraps:
    def test_ว่าด้วย_is_not_the_word_ด้วย(self):
        # ``ด้วย`` opens a body clause and also sits inside ``ว่าด้วย``, which
        # is in the middle of most titles. Matching it as a bare substring cut
        # 113 of 240 documents to their first three words.
        got = title.read(
            "ระเบียบกรมการขนส่งทางบก ว่าด้วยหลักเกณฑ์และวิธีการต่ออายุ พ.ศ. 2564 "
            "ตามที่ได้มีระเบียบ..."
        )
        assert got == "ระเบียบกรมการขนส่งทางบก ว่าด้วยหลักเกณฑ์และวิธีการต่ออายุ พ.ศ. 2564"

    def test_ด้วย_opening_a_clause_still_ends_the_title(self):
        assert title.read(
            "ประกาศคณะกรรมการบริหารศาลยุติธรรม เรื่อง เปลี่ยนแปลงสถานที่ตั้งของศาลแรงงานภาค 6 "
            "ด้วยศาลแรงงานภาค 6 ได้ย้ายที่ทำการ..."
        ) == "ประกาศคณะกรรมการบริหารศาลยุติธรรม เรื่อง เปลี่ยนแปลงสถานที่ตั้งของศาลแรงงานภาค 6"

    def test_a_bracketed_year_is_an_issue_number_not_an_ending(self):
        # Stopping at the first year names "กฎกระทรวง ฉบับที่ 4 (พ.ศ. 2563)",
        # an instrument that does not exist. The title runs to the year of the
        # Act it is made under.
        got = title.read(
            "กฎกระทรวง ฉบับที่ 4 (พ.ศ. 2563) ออกตามความในพระราชบัญญัติยศ "
            "และเครื่องแบบผู้บังคับบัญชา พ.ศ. 2497 อาศัยอำนาจตามความในมาตรา 12..."
        )
        assert got.endswith("พ.ศ. 2497")
        assert "(พ.ศ. 2563)" in got


class TestWhenItRefuses:
    def test_a_judgment_with_no_subject_line_is_left_to_the_model(self):
        # Composing a court title needs three pieces; this page carries two.
        # Silence hands the column back rather than naming it half-way.
        assert title.read(
            "(อม.30) คำพิพากษา คดีหมายเลขดำที่ อม. 77/2561 คดีหมายเลขแดงที่ อม. 238/2562 "
            "ในพระปรมาภิไธยพระมหากษัตริย์ ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง"
        ) == ""

    def test_a_ruling_with_no_subject_line_too(self):
        assert title.read(
            "ในพระปรมาภิไธยพระมหากษัตริย์ ศาลรัฐธรรมนูญ คำวินิจฉัยที่ 1/2563 "
            "เรื่องพิจารณาที่ 9/2562 วันที่ 5 เดือน กุมภาพันธ์ พุทธศักราช 2563"
        ) == ""

    def test_nothing_in_gives_nothing_out(self):
        assert title.read("") == ""

    def test_a_page_with_no_ending_is_not_a_title(self):
        # A body word or a year has to appear. Without either, what is left is
        # a paragraph, and returning it would put half a page in the column.
        assert title.read("ก" * 900) == ""

    def test_a_fragment_is_not_a_title(self):
        assert title.read("ประกาศ") == ""


class TestAgainstTheCorpus:
    """The number this rule exists for, checked rather than asserted."""

    def test_it_reads_most_of_the_operators_documents(self):
        import json
        from pathlib import Path

        from lawscan import sheet
        from lawscan.diff import compare_cell

        reference = Path.home() / "Downloads" / "expect-final - ชีต1.csv"
        if not reference.exists():
            return  # the operator's file is not in the repository

        answers = sheet.by_document(reference)[1]
        exact = scored = 0
        for number, row in answers.items():
            saved = Path("text") / f"{number}.json"
            if not saved.exists():
                continue
            text = "\n".join(
                page["text"]
                for page in json.loads(saved.read_text(encoding="utf-8"))["pages"]
            )
            got = title.read(text)
            if not got:
                continue  # abstained on purpose; the model answers these
            scored += 1
            exact += compare_cell("ชื่อกฎหมาย", row["ชื่อกฎหมาย"], got) == "exact"

        assert scored > 200, scored
        # 209/222 when this was written. The floor is set below that so a small
        # regression is visible without the test failing on a single document.
        assert exact / scored > 0.90, f"{exact}/{scored}"


class TestCourtDocuments:
    """A judgment prints a docket number; the reference writes a name.

    Every piece of that name is on the page — the kind and the court in the
    masthead, the docket beside them, the subject on the ``เรื่อง`` line that
    opens the recital. Composing it from those three moved the rule from 88.3%
    to 94.2% and past the model's 90.0%.
    """

    JUDGMENT = (
        "(อม.30) คำพิพากษา คดีหมายเลขดำที่ อม. 77/2561 คดีหมายเลขแดงที่ อม. 238/2562 "
        "ในพระปรมาภิไธยพระมหากษัตริย์ ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง "
        "วันที่ 16 เดือน กันยายน พุทธศักราช 2562 อัยการสูงสุด ผู้ร้อง "
        "เรื่อง ขอให้ทรัพย์สินตกเป็นของแผ่นดิน ผู้ร้องยื่นคำร้องว่า ผู้ถูกกล่าวหาได้รับ"
    )

    def test_a_judgment_is_named_from_its_three_pieces(self):
        got = title.read(self.JUDGMENT)
        assert got.startswith("คำพิพากษาของศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง")
        assert "เรื่อง ขอให้ทรัพย์สินตกเป็นของแผ่นดิน" in got
        assert "คดีหมายเลขดำที่ อม. 77/2561" in got

    def test_a_ruling_carries_its_own_number_instead_of_a_docket(self):
        got = title.read(
            "ในพระปรมาภิไธยพระมหากษัตริย์ ศาลรัฐธรรมนูญ คำวินิจฉัยที่ 1/2563 "
            "เรื่องพิจารณาที่ 9/2562 วันที่ 21 เดือน มกราคม พุทธศักราช 2563 "
            "เรื่อง คำร้องขอให้ศาลรัฐธรรมนูญวินิจฉัยตามรัฐธรรมนูญ มาตรา 49 นายณฐพร โตประยูร"
        )
        assert got.startswith("คำวินิจฉัยของศาลรัฐธรรมนูญ คำวินิจฉัยที่ 1/2563")
        assert "เรื่อง คำร้องขอให้ศาลรัฐธรรมนูญวินิจฉัยตามรัฐธรรมนูญ" in got

    def test_เรื่องพิจารณาที่_is_a_file_reference_not_a_subject(self):
        # It sits directly above the real subject line and would otherwise win
        # by being first.
        got = title.read(
            "ศาลรัฐธรรมนูญ คำวินิจฉัยที่ 1/2563 เรื่องพิจารณาที่ 9/2562 "
            "เรื่อง คำร้องขอให้ศาลรัฐธรรมนูญวินิจฉัย นายณฐพร โตประยูร"
        )
        assert "เรื่องพิจารณาที่" not in got

    def test_a_missing_piece_means_no_answer_rather_than_half_of_one(self):
        # A half-composed name still takes precedence over the model, which
        # reads all three pieces at once. Silence hands the column back.
        assert title.read("(อม.30) คำพิพากษา คดีหมายเลขดำที่ อม. 77/2561 ไม่มีชื่อศาล") == ""

    def test_the_composition_can_be_turned_off(self):
        title.COMPOSE_COURT_TITLES = False
        try:
            assert title.read(self.JUDGMENT) == ""
        finally:
            title.COMPOSE_COURT_TITLES = True
