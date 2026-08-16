"""หัวกระดาษราชกิจจาฯ ไม่ใช่ชื่อกฎหมาย

หน้าแรกของ PDF ที่สะอาดไม่มีหัวกระดาษ ตัวตัดหัวใน ``title.py`` จึงไม่เคยถูก
ใช้งานจริง — และเมื่อลองดูก็พบว่ามันไม่เคยทำงานเลยด้วยซ้ำ รูปแบบที่เขียนไว้
ไม่มีที่ว่างให้ตัวอักษรชั้น (``ตอนพิเศษ ๒๕๑ ง ราชกิจจานุเบกษา``)

พอ OCR อ่านหัวที่พิมพ์อยู่บนหน้าแรกออก เอกสาร 591 ฉบับก็ได้ชื่อกฎหมายที่
ขึ้นต้นด้วย ``หน้า ๑๕ เล่ม ๑๕๑ …``
"""

import pytest

from lawscan.rules import kind, title

#: สามหน้าจริงในคลัง สะกดหัวกระดาษคนละแบบ เพราะ OCR อ่านคนละอย่าง
SCANNED = [
    ("หน้า 15 เล่ม 151 ตอนที 31 ก ราชกิจจานุเบกษา 25 พฤษภาคม 2521 0 17 "
     "ประกาศสำนักงานศาลปกครอง เรื่อง หลักเกณฑ์และวิธีการ พ.ศ. 2564",
     "ประกาศสำนักงานศาลปกครอง"),
    ("เล่ม 150 หน้า 1 ตอนพิเศษ 251 ง ราชกิจจานุเบกษา 2 ตุลา "
     "ระเบียบองค์การบริหารส่วนตำบลบ้านยาง ว่าด้วยข้อมูลข่าวสาร พ.ศ. 2563",
     "ระเบียบองค์การบริหารส่วนตำบลบ้านยาง"),
    ("หน้า 11 เล่ม 151 Maun al ก ราชกิจจานุเบกษา 15 กุมภาพันธ์ 2520 "
     "ระเบียบคณะกรรมการการเลือกตั้ง ว่าด้วยการเลือกสมาชิกวุฒิสภา พ.ศ. 2567",
     "ระเบียบคณะกรรมการการเลือกตั้ง"),
]


class TestTheMastheadComesOff:
    @pytest.mark.parametrize("page,starts", SCANNED)
    def test_the_title_starts_where_the_instrument_names_itself(self, page, starts):
        got = title.read(page)
        assert got.startswith(starts), got
        assert "ราชกิจจานุเบกษา" not in got

    def test_a_clean_page_is_left_alone(self):
        page = ("ระเบียบผู้ตรวจการแผ่นดิน ว่าด้วยค่าใช้จ่ายในการเดินทาง พ.ศ. 2563 "
                "โดยที่เป็นการสมควร")
        assert title.read(page) == ("ระเบียบผู้ตรวจการแผ่นดิน "
                                    "ว่าด้วยค่าใช้จ่ายในการเดินทาง พ.ศ. 2563")

    def test_a_title_that_is_about_the_gazette_keeps_its_words(self):
        # ระเบียบสำนักนายกรัฐมนตรี ว่าด้วยการประกาศเรื่องในราชกิจจานุเบกษา
        # เอ่ยถึงราชกิจจาฯ ในชื่อของตัวเอง ไม่ใช่หัวกระดาษ
        page = ("ระเบียบสำนักนายกรัฐมนตรี ว่าด้วยการประกาศเรื่องในราชกิจจานุเบกษา "
                "พ.ศ. 2566 โดยที่เป็นการสมควร")
        assert title.read(page).startswith("ระเบียบสำนักนายกรัฐมนตรี ว่าด้วยการประกาศ")


class TestWhereTheInstrumentNamesItself:
    def test_the_offset_points_into_the_original_text(self):
        page = "หน้า 15 เล่ม 151 ก ราชกิจจานุเบกษา 2521 ประกาศคณะกรรมการ"
        assert page[kind.position(page):] == "ประกาศคณะกรรมการ"

    def test_it_survives_the_damage_a_broken_font_does(self):
        # ``คำพิพากษา`` สกัดออกมาเป็น ``คำพิพำกษำ`` — การพับตัวอักษรทำให้
        # ตำแหน่งเลื่อน ถ้าไม่เก็บทางกลับไว้ก็ชี้ผิดที่
        page = "ในพระปรมำภิไธย คำพิพำกษำศำลฎีกำ"
        assert page[kind.position(page):].startswith("คำพิพำกษำ")

    def test_nothing_found_is_minus_one(self):
        assert kind.position("เอกสารที่ไม่บอกว่าตัวเองเป็นอะไร") == -1


class TestTheCommissionRules:
    """``กฎ ก.พ.`` เป็นประเภทที่แผ่นงานใช้จริง — 2 ฉบับใน 240"""

    @pytest.mark.parametrize("page", [
        "กฎ ก.พ.ค. กรุงเทพมหานคร ว่าด้วยการร้องทุกข์ พ.ศ. 2564",
        "กฎ ก.ตร. ว่าด้วยการสืบสวนข้อเท็จจริง พ.ศ. 2564",
        "กฎสำนักนายกรัฐมนตรี ฉบับที่ 101 (พ.ศ. 2564) ออกตามความในพระราชบัญญัติ"
        "เครื่องแบบข้าราชการฝ่ายพลเรือน พุทธศักราช 2478",
    ])
    def test_the_sheet_files_them_as_kod(self, page):
        assert kind.read(page) == "กฎ"

    def test_the_authority_clause_no_longer_names_the_instrument(self):
        # ก่อนหน้านี้คำว่า พระราชบัญญัติ ในวรรคอ้างอำนาจชนะ เพราะไม่มีคำว่า
        # กฎ ก. ในคลังคำ — 43 ฉบับทั้งคลังถูกตอบผิดแบบมั่นใจ
        page = ("กฎ ก.พ. ว่าด้วยการย้ายข้าราชการ พ.ศ. 2564 อาศัยอำนาจตามความใน"
                "มาตรา 8 แห่งพระราชบัญญัติระเบียบข้าราชการพลเรือน พ.ศ. 2551")
        assert kind.read(page) == "กฎ"

    def test_a_rule_is_not_a_judgment(self):
        # ``NARRATIVE`` เคยสร้างจาก ``LONG_FORM.values()`` ทั้งก้อน พอเพิ่ม
        # ``กฎ`` เข้าไป กฎการอ่านชื่อก็เลิกอ่านให้ทันที
        assert "กฎ" not in kind.NARRATIVE
        assert title.read("กฎ ก.พ. ว่าด้วยการย้ายข้าราชการ พ.ศ. 2564 โดยที่เป็นการสมควร")

    def test_a_mention_further_down_does_not_win(self):
        page = "ระเบียบกรมการปกครอง ว่าด้วยการทำงาน พ.ศ. 2564 ตามกฎ ก.พ. ว่าด้วยการย้าย"
        assert kind.read(page) == "ระเบียบ"


class TestWhatTheScannerLeavesRoundACrest:
    """``a 17 6 aa al 17 a 0 1 al A vy 17 Ca vy`` คือตราครุฑที่ OCR อ่านเป็นตัวอักษร"""

    def test_a_run_of_marks_goes(self):
        got = title.read(
            "ประกาศสำนักงานศาลปกครอง a 17 6 aa al 17 a 0 1 al A vy 17 Ca vy "
            "เรื่อง หลักเกณฑ์การชำระราคา พ.ศ. 2564"
        )
        assert got == "ประกาศสำนักงานศาลปกครอง เรื่อง หลักเกณฑ์การชำระราคา พ.ศ. 2564"

    def test_an_amendment_number_stays(self):
        got = title.read("กฎกระทรวง แบ่งส่วนราชการ (ฉบับที่ 3) พ.ศ. 2564 อาศัยอำนาจ")
        assert got == "กฎกระทรวง แบ่งส่วนราชการ (ฉบับที่ 3) พ.ศ. 2564"

    def test_a_standard_named_in_latin_stays(self):
        got = title.read(
            "ระเบียบกรมปศุสัตว์ ว่าด้วยการออกใบรับรอง GHPs และระบบ HACCP พ.ศ. 2564"
        )
        assert "GHPs" in got and "HACCP" in got

    def test_two_short_numbers_are_not_noise(self):
        # ไม่มีตัวอักษรในชุด จึงไม่ใช่รอยสแกน
        got = title.read("ประกาศกระทรวง เรื่อง มาตรฐาน 3 5 พ.ศ. 2564 โดยที่เป็นการสมควร")
        assert "3 5" in got


class TestALongTitleThatEndedProperly:
    """เพดานความยาวมีไว้ตัดย่อหน้าที่หาจุดจบไม่เจอ ไม่ใช่ชื่อที่จบเรียบร้อย"""

    def test_a_title_closing_on_its_year_is_kept(self):
        # 100236 แจกแจงแปดอย่างที่ใบอนุญาตครอบคลุม ยาว 408 ตัวอักษร
        # และจบด้วย พ.ศ. 2564 ตามปกติ — ไม่มีกฎอื่นเติมช่องนี้ถ้ารูปนี้ปฏิเสธ
        long = ("ระเบียบกรมอุทยานแห่งชาติ สัตว์ป่า และพันธุ์พืช ว่าด้วย"
                + "การออกใบอนุญาตหรือใบรับรอง " * 14 + "พ.ศ. 2564 อาศัยอำนาจ")
        got = title.read(long)
        assert len(got) > title._TOO_LONG
        assert got.endswith("พ.ศ. 2564")

    def test_a_paragraph_that_never_ended_is_still_refused(self):
        runaway = "ประกาศกรมทดสอบ " + "เรื่องที่ยืดยาวไม่มีวันจบ " * 30
        assert title.read(runaway) == ""
