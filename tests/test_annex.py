"""หน้าแผนที่ท้ายกฎหมาย ไม่ใช่ตัวกฎหมาย

แผนที่แนบท้ายพิมพ์ชื่ออำเภอ *รอบ* พื้นที่ที่กฎหมายกำหนด เพื่อให้อ่านแผนที่ออก
ตราบใดที่หน้าเหล่านั้นยังเป็นรูปที่ไม่มีใครอ่าน กฎอ่านสถานที่ก็ไม่เคยเจอมัน
พอ OCR อ่านออก ``100201`` ก็เปลี่ยนคำตอบจาก ``วัดโบสถ์, เมืองพิษณุโลก``
เป็น ``พิชัย`` — อำเภอของจังหวัดข้างเคียง ที่มีชื่ออยู่บนแผนที่เพราะมันติดกัน
เฉย ๆ

หน้าพวกนี้บอกตัวเองที่บรรทัดแรก แต่บอกผ่าน OCR ที่ทำหัวเรื่องพัง
"""

import pathlib

from lawscan.ocr.read import Document, Page


def page(text):
    return Page(number=1, text=text, source="ocr")


class TestThePageSaysWhatItIs:
    def test_a_clean_heading_is_an_annex(self):
        assert page("แผนที่ท้ายกฎกระทรวง กำหนดให้ทางน้ำชลประทาน").is_annex

    def test_an_ordinary_page_is_not(self):
        assert not page("กฎกระทรวง กำหนดให้ทางน้ำชลประทานในเขตโครงการ").is_annex


class TestReadThroughTheDamage:
    """สามหน้าจริงในคลัง สะกดคำเดียวกันสามแบบ"""

    def test_the_tone_mark_became_another_letter(self):
        # 100201 หน้า 2 — ``ท้าย`` ออกมาเป็น ``ฑาย``
        assert page(") แผนทีฑายกฎกระทรวง ฆ i ae vy กำหนดให้ทางน้้าชลประทาน").is_annex

    def test_latin_junk_in_front_does_not_hide_it(self):
        # 100073 หน้า 5 — สแกนเนอร์แต่งตัวอักษรละตินขึ้นมาก่อนหัวเรื่อง
        assert page('= ay a แผนทีท้ายพระราชกฤษฎีกา " Hak ad ม รกำหนด').is_annex

    def test_a_missing_vowel_does_not_hide_it_either(self):
        # 100073 หน้า 7
        assert page("aly a แผนททายพระราชกฤษฎกา ง a — 5ส").is_annex


class TestOnlyTheHeading:
    def test_a_scale_quoted_inside_the_text_is_not_an_annex(self):
        # 100749 หน้า 7 เป็นบัญชีท้องที่ที่กฎหมายครอบคลุมจริง และเอ่ยถึง
        # มาตราส่วนตอนท้ายย่อหน้า ตัดทิ้งแล้วเสียอำเภอที่กฎหมายพูดถึง
        assert not page(
            "(14) ในท้องที่ตำบลห้วยซ้อ ตำบลศรีดอนชัย ตำบลสถาน และตำบลเวียง "
            "อำเภอเชียงของ จังหวัดเชียงราย ตามแผนที่มาตราส่วน 1:50000"
        ).is_annex

    def test_a_scale_as_the_caption_is_one(self):
        assert page("มาตราส่วน 1:50000 แสดงแนวเขต").is_annex


class TestTheDocumentHandsOverTheBodyOnly:
    def test_the_annex_page_is_left_out(self):
        d = Document(pathlib.Path("100201.pdf"), [
            page("กฎกระทรวง กำหนดให้ทางน้ำชลประทานในท้องที่อำเภอวัดโบสถ์"),
            page("แผนที่ท้ายกฎกระทรวง อำเภอพิชัย อำเภอวังทอง"),
        ])
        assert "วัดโบสถ์" in d.body_text
        assert "พิชัย" not in d.body_text
        # ข้อความเต็มยังครบ — ตัดเฉพาะตอนอ่านสถานที่
        assert "พิชัย" in d.text()


class TestGazetteFurnitureIsReadFromTheTextLayer:
    """หัวกับท้ายกระดาษเป็นของราชกิจจาฯ ไม่ใช่ของกฎหมาย และเป็นเลขละติน

    ฟอนต์พังทำลายภาษาไทยแต่ปล่อยเลขไว้ ส่วน OCR ทำกลับกัน — 100087
    มีเลขหน้าท้ายกระดาษ 1..7 ในชั้นข้อความ แต่ OCR อ่านเป็น 1,2,3,5,5,2,3
    ทำให้กฎหมายเจ็ดหน้ากลายเป็นห้าหน้า
    """

    def test_the_footer_comes_from_the_layer_where_there_is_one(self):
        from lawscan.rules import gazette

        line = "หน้า {} เล่ม 140 ตอนพิเศษ 251 ง ราชกิจจานุเบกษา 6 ตุลาคม 2566"
        pages = [Page(number=i, text=line.format(bad), source="ocr",
                      layer=line.format(good))
                 for i, (good, bad) in enumerate([(1, 1), (2, 2), (3, 3),
                                                  (4, 5), (5, 5), (6, 2), (7, 3)])]
        assert gazette.page_span(gazette.pages_of([p.layer or p.text for p in pages])) == "1-7"
        assert gazette.page_span(gazette.pages_of([p.text for p in pages])) == "1-5"


class TestTheFooterIsNotEveryMentionOfAPage:
    """``หน้า ๒๐`` ในเนื้อความไม่ใช่เลขหน้า

    ราชกิจจาฯ พิมพ์เลขหน้าไว้บรรทัดเดียวกับเล่มและวันที่เสมอ สิ่งที่อยู่ข้าง ๆ
    จึงเป็นตัวแยกเลขหน้าจริงออกจากบัญชีค่าธรรมเนียมที่ลงท้ายว่า
    ``๕ บาท/หน้า ๗. ค่าพิมพ์`` — ทั้งคลังมี 24 ฉบับที่อ้างว่าตัวเองหนากว่า
    ที่เป็นจริง แก้แล้วเหลือศูนย์
    """

    def test_a_real_footer_is_read(self):
        from lawscan.rules import gazette

        assert gazette.pages_of([
            "…ภาพคน หน้า 14 เล่ม 139 ตอนพิเศษ 136 ง ราชกิจจานุเบกษา 15 มิถุนายน 2565"
        ]) == [14]

    def test_a_fee_per_page_is_not(self):
        from lawscan.rules import gazette

        assert gazette.pages_of([
            "ค่าถ่ายเอกสารโครงการวิจัยในคน 5 บาท/หน้า 7. ค่าพิมพ์ (Print) 15 บาท/หน้า"
        ]) == []

    def test_a_citation_in_the_middle_of_the_page_is_not(self):
        from lawscan.rules import gazette

        body = ("ตามที่ประกาศไว้ใน หน้า 40 ราชกิจจานุเบกษา แล้วนั้น " + "ก" * 400
                + " หน้า 22 เล่ม 140 ตอนพิเศษ 13 ง ราชกิจจานุเบกษา 19 มกราคม 2566")
        assert gazette.pages_of([body]) == [22]
