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


def test_a_court_subject_is_read_off_its_own_line():
    """The subject ends where its line ends, so the line breaks have to survive."""
    from lawscan.rules.title import read

    page = (
        "ในพระปรมาภิไธยพระมหากษัตริย์\n"
        "ศาลรัฐธรรมนูญ\n\n"
        "คำวินิจฉัยที่ 20/2564\n"
        "เรื่องพิจารณาที่ 30/2563\n\n"
        "วันที่ 17 เดือน พฤศจิกายน พุทธศักราช 2564\n"
        "ศาลเยาวชนและครอบครัวกลาง\nผู้ร้อง\n-\nผู้ถูกร้อง\n"
        "เรื่อง ‹หัวข้อคดีที่หน้ากระดาษพิมพ์ไว้เป็นบรรทัดของตัวเอง›\n"
        "ประเด็นที่ศาลรัฐธรรมนูญต้องพิจารณาวินิจฉัยมีว่า\n"
    )
    got = read(page)
    assert got.startswith("คำวินิจฉัยของศาลรัฐธรรมนูญ คำวินิจฉัยที่ 20/2564 เรื่อง ")
    # ``เรื่องพิจารณาที่`` is the internal file reference, not the subject.
    assert "พิจารณาที่" not in got


def test_a_recognised_court_name_is_written_the_way_it_is_spelled():
    """Recognition drops a vowel and adds a digit; the title must not."""
    from lawscan.rules.title import _court_name

    assert _court_name("ในพระปรมาภิไธย ศาลรฐธ5รรมนูญ คำวินิจฉัยที่ 2/2565") == "ศาลรัฐธรรมนูญ"
    assert _court_name("ศาลรัฐธรรมนูญ") == "ศาลรัฐธรรมนูญ"
    assert _court_name("ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง") == (
        "ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง"
    )
    assert _court_name("ระเบียบคณะกรรมการ ว่าด้วยหลักเกณฑ์") == ""


def test_the_subject_line_survives_a_dropped_tone_mark():
    """A recognised page writes ``เรือง`` where the paper writes ``เรื่อง``."""
    from lawscan.rules.title import _SUBJECT

    got = _SUBJECT.search("ผู้ถูกร้อง\nเรือง ‹หัวข้อคดีที่พิมพ์ไว้เป็นบรรทัดของตัวเอง›\nประเด็นที่ต้องวินิจฉัย\n")
    assert got and got.group(1).startswith("‹หัวข้อคดี")


def test_the_internal_file_reference_is_still_not_a_subject():
    from lawscan.rules.title import _SUBJECT

    assert not _SUBJECT.search("คำวินิจฉัยที่ 2/2567\nเรื่องพิจารณาที่ 23/2566\nวันที่ 25 มกราคม\n")


class TestTheCatalogueNamesTheDocument:
    """OCR reached the name through a broken font and got it wrong 67 times.

    ``title.read`` copies the name off the first page, which is where it is —
    until the scan drops tone marks (``เลือกตัง``) or the rule locks onto the
    parent act cited in the preamble instead. On the 2569 corpus 107 of 250
    names lost marks and 67 were a different law entirely.
    """

    def _found(self, stem, text="ประกาศ"):
        from pathlib import Path

        from lawscan.ocr.read import Document, Page
        from lawscan.rules import run_all

        return run_all(Document(path=Path(f"{stem}.pdf"),
                                pages=[Page(number=1, text=text, source="ocr")]))

    def test_the_catalogue_beats_a_page_the_scanner_mangled(self):
        from lawscan.rules import manifest

        listed = manifest.name_of("122839")
        assert listed, "ทะเบียนต้องรู้จักเอกสารฉบับนี้"
        assert self._found("122839", "ระเบยบ ก.ศป. เลือกตัง")["ชื่อกฎหมาย"] == listed

    def test_a_document_the_catalogue_does_not_list_still_reads_its_page(self):
        from lawscan.rules import manifest

        assert manifest.name_of("999999") == ""
        page = "ระเบียบคณะกรรมการสิทธิมนุษยชนแห่งชาติ\nว่าด้วยค่าใช้จ่าย\nพ.ศ. 2569"
        assert self._found("999999", page)["ชื่อกฎหมาย"]

    def test_the_catalogue_carries_identity_and_nothing_else(self):
        """A file that also held categories or a summary would be an answer key."""
        import csv

        from lawscan.rules.manifest import COLUMNS, PATH

        with PATH.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        assert tuple(header) == COLUMNS, f"ทะเบียนมีคอลัมน์เกิน: {header}"

    def test_the_name_is_normalised_the_same_way_every_time(self):
        from lawscan.rules.manifest import _tidy

        assert _tidy("  ระเบียบ\xa0ก.ศป. ") == "ระเบียบ ก.ศป."
        assert _tidy(None) == ""
