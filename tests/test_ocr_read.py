

def test_a_layer_that_collapsed_every_sara_aa_is_recognised_instead():
    """Every character is valid Thai, so the Thai-share test passes it."""
    from lawscan.ocr.read import looks_collapsed, looks_garbled

    broken = "อำนำจในกำรนำส่งข้อมูลอิเล็กทรอนิกส์ต่อสำนักงำน และให้รวมถึงบุคคลอื่น"
    assert not looks_garbled(broken)
    assert looks_collapsed(broken)


def test_it_reads_the_raw_layer_with_the_sara_am_still_adrift():
    """The gate runs before normalising, and the layer writes ``อ ำนำจ``."""
    from lawscan.ocr.read import looks_collapsed

    assert looks_collapsed("แต่ไม่รวมถึงอ ำนำจในกำรน ำส่งข้อมูลต่อส ำนักงำน")


def test_clean_thai_is_left_alone_however_many_sara_am_it_has():
    """A page of ``ห้องน้ำ`` spends most of its budget on ``ำ`` and is right."""
    from lawscan.ocr.read import looks_collapsed

    assert not looks_collapsed(
        "บัญชีอัตราเงินช่วยเหลือค่าที่พักอาศัย สำหรับพนักงานและลูกจ้างสำนักงาน"
    )
    assert not looks_collapsed("ห้องน้ำ ห้องน้ำ ห้องน้ำ น้ำมัน ค้ำประกัน ซ้ำซ้อน ทำงาน")


def test_one_ruin_alone_is_not_enough_unless_the_vowels_agree():
    """A single hit on an otherwise ordinary page does not pay for a render."""
    from lawscan.ocr.read import looks_collapsed

    ordinary = "กำร" + " ".join(["ประกาศกระทรวงว่าด้วยการอนุญาตให้ทำการค้าขาย"] * 4)
    assert not looks_collapsed(ordinary)


def test_a_recognised_page_keeps_the_header_its_layer_printed():
    """Recognition reads the body well and the small header line badly."""
    from lawscan.ocr.read import _header_from_layer

    ocred = (
        "หน้า 5\nเล่ม 133 ตอนที 13 ก\nราชกิจจานุเบกษา\n15 กุมภาพันธี์ 25203\n"
        "กฎกระทรวง กำหนดบริเวณห้ามก่อสร้าง"
    )
    layer = (
        "หน้า ๕\nเล่ม ๑๓๓ ตอนที่ ๑๓ ก\nราชกิจจานุเบกษา\n๑๔ กุมภาพันธ์ ๒๕๖๓\n"
        "กฎกระทรวง กำหนดบริเวณห้ำมก่อสรำง"
    )
    fixed = _header_from_layer(ocred, layer)
    assert "๑๔ กุมภาพันธ์ ๒๕๖๓" in fixed
    assert "25203" not in fixed
    # The body is the recognised one, damage and all left behind.
    assert "ห้ามก่อสร้าง" in fixed
    assert "ห้ำมก่อสรำง" not in fixed


def test_a_page_whose_layer_has_no_header_is_left_as_it_is():
    from lawscan.ocr.read import _header_from_layer

    ocred = "หน้า 5\nเล่ม 133 ตอนที 13 ก\nราชกิจจานุเบกษา\n15 กุมภาพันธี์ 25203\nเนื้อความ"
    assert _header_from_layer(ocred, "เนื้อความล้วน ไม่มีหัวกระดาษ") == ocred


def test_a_layer_half_written_in_latin1_is_recognised():
    """Thai share stays over the floor while the page is unreadable."""
    from lawscan.ocr.read import looks_garbled

    slipped = "'1>Ö@0สํ@%?ÖÜ@%0@ล1?ฐ$11/%Cญ N1ANอÜ ลOหNÜคํ@/>%>ÝÞ?0×อÜ0@ล1?ฐ$11/%Cญ"
    assert looks_garbled(slipped)


def test_an_ordinary_bilingual_page_is_left_alone():
    """Gazette pages print English, and English is not evidence of damage."""
    from lawscan.ocr.read import looks_garbled

    bilingual = (
        "“ผู้บริหารบัญชีผู้ใช้งาน” (account administrator) หมายความว่า กรรมการ "
        "หุ้นส่วน หรือพนักงาน ตามมาตรฐาน ISO/IEC 27001 และ Certification Practice Statement"
    )
    assert not looks_garbled(bilingual)


def test_a_recognised_page_takes_its_numbers_from_the_layer():
    """The layer's digits survive the fault that sent the page to recognition.

    The values come back normalised — Thai numerals become Arabic on the way,
    because the layer is put through the same normalising the rest of the text
    gets before it is read. The value is the layer's; only the script changes.
    """
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "กฎกระทรวงทดสอบระบบ พ.ศ. 2523 อาศัยอำนาจตามพระราชบัญญัติทดสอบ พ.ศ. 2553"
    layer = ("กฎกระทรวงทดสอบระบบ พ.ศ. ๒๕๖๓ อำศัยอำนำจตำมควำมในพระรำชบัญญัติทดสอบ "
             "พ.ศ. ๒๕๔๓ ตำมรำยกำรที่ประกำศ")
    fixed = _numerals_from_layer(ocred, layer)
    assert "พ.ศ. 2563" in fixed and "พ.ศ. 2543" in fixed
    assert "2523" not in fixed and "2553" not in fixed
    # The body stays the recognised one, damage and all left behind.
    assert "อาศัยอำนาจ" in fixed


def test_a_garbled_layer_is_not_trusted_for_years():
    """A slipped glyph table returns nonsense for digits too."""
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "ประกาศทดสอบระบบ พ.ศ. 2565"
    garbled = "'1>Ö@0สํ@%?ÖÜ@%0@ล1?ฐ$11/%Cญ พ.ศ. 2501 N1ANอÜ ลOหNÜคํ@/>%>ÝÞ?0×อÜ"
    assert _numerals_from_layer(ocred, garbled) == ocred


def test_an_amendment_number_with_no_digit_left_is_restored():
    """``(ฉบับที on)`` for ``(ฉบับที่ ๓)`` — a slot recognition emptied."""
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "ระเบียบทดสอบระบบ (ฉบับที on) พ.ศ. 25203"
    layer = ("ระเบียบทดสอบระบบว่ำด้วยกำรดำเนินกำรตำมรำยกำรที่ประกำศ "
             "(ฉบับที่ ๓) พ.ศ. ๒๕๖๓")
    fixed = _numerals_from_layer(ocred, layer)
    assert "(ฉบับที 3)" in fixed or "(ฉบับที่ 3)" in fixed
    assert "on" not in fixed
    assert "2563" in fixed


def test_the_title_year_is_restored_even_when_the_rest_cannot_be_aligned():
    """100015: eleven years on the page, eight came back, three lost outright.

    Replacing all of them would land the wrong year in the wrong place. The
    first one is safe regardless: it is the instrument's own year, set in the
    title in the largest type on the sheet.
    """
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "ระเบียบทดสอบระบบ พ.ศ. 25203 อาศัยอำนาจตาม พ.ศ. 2535"
    layer = ("ระเบียบทดสอบระบบว่ำด้วยกำรดำเนินกำรตำมรำยกำร พ.ศ. ๒๕๖๓ "
             "อำศัยอำนำจตำม พ.ศ. ๒๕๓๔ ประกอบ พ.ศ. ๒๕๔๕")
    fixed = _numerals_from_layer(ocred, layer)
    assert "พ.ศ. 2563" in fixed
    assert "25203" not in fixed
    # The ones that could not be aligned are left exactly as recognition read
    # them, rather than replaced with a year from somewhere else on the page.
    assert "พ.ศ. 2535" in fixed


def test_years_are_paired_by_what_surrounds_them_when_the_counts_differ():
    """100015 page one: eleven years printed, eight recognised, none malformed.

    ``๒๕๓๔`` came back ``2535`` and ``๒๕๔๕`` came back ``2555`` — well-formed
    years in the right range, so no shape test downstream can tell they are the
    wrong ones. Counting refuses the page; the phrase that names each year
    survives recognition and settles which is which.
    """
    from lawscan.ocr.read import _numerals_from_layer

    ocred = ("ระเบียบทดสอบระบบ พ.ศ. 2523 อาศัยอำนาจตามระเบียบบริหารราชการแผ่นดิน "
             "พ.ศ. 2535 ประกอบประกาศกระทรวงสาธารณสุข พ.ศ. 2553 จึงวางระเบียบไว้")
    layer = ("ระเบียบทดสอบระบบ พ.ศ. ๒๕๖๓ อำศัยอำนำจตำมระเบียบบริหำรรำชกำรแผ่นดิน "
             "พ.ศ. ๒๕๓๔ ประกอบประกำศกระทรวงสำธำรณสุข พ.ศ. ๒๕๕๗ จึงวำงระเบียบไว้ "
             "โดยให้ใช้บังคับตำมคำสั่งที่เกี่ยวข้อง พ.ศ. ๒๕๖๒ เป็นต้นไป")
    fixed = _numerals_from_layer(ocred, layer)
    assert "พ.ศ. 2563" in fixed
    assert "แผ่นดิน พ.ศ. 2534" in fixed
    assert "สาธารณสุข พ.ศ. 2557" in fixed
    # The layer's fourth year has no counterpart in the reading and is not
    # dragged in to stand beside a phrase it does not belong to.
    assert "2562" not in fixed


def test_a_grouped_thousand_counts_as_one_quantity():
    """100121 page eight: ``๓,๓๐๐ กิโลวัตต์`` came back ``coo กิโลวัตต์``.

    A value that stops at the comma reads the layer's one figure as two, so
    the page held three quantities against the reading's five and the repair
    declined. Grouped whole, the two sides agree and the figure is restored.
    """
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "ค่าธรรมเนียมเพิ่มเติม 5,000 บาท สำหรับแต่ละ coo กิโลวัตต์ ที่เพิ่มขึ้น"
    layer = ("ค่ำธรรมเนียมเพิ่มเติม ๕,๐๐๐ บำท สำหรับแต่ละ ๓,๓๐๐ กิโลวัตต์ "
             "ที่เพิ่มขึ้นตำมรำยกำรที่ประกำศ")
    fixed = _numerals_from_layer(ocred, layer)
    assert "3,300 กิโลวัตต์" in fixed
    assert "coo" not in fixed


def test_the_gazettes_own_numbers_come_from_the_layer():
    """``เล่ม oma`` for ``เล่ม ๑๓๗`` — a Thai numeral read as Latin."""
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "หน้า om เล่ม oma ตอนที 12 ก ราชกิจจานุเบกษา ข้อ ov อาคารที่ได้รับใบอนุญาต"
    layer = ("หน้ำ ๒๓ เล่ม ๑๓๗ ตอนที่ ๑๒ ก รำชกิจจำนุเบกษำ ข้อ ๙ "
             "อำคำรที่ได้รับใบอนุญำตตำมรำยกำรที่ประกำศ ต้องมีระยะห่ำงจำกแนวเขต")
    fixed = _numerals_from_layer(ocred, layer)
    assert "เล่ม 137" in fixed
    assert "ข้อ 9" in fixed
    assert "oma" not in fixed and " ov" not in fixed


def test_a_section_number_is_not_replaced_when_the_counts_disagree():
    """``ข้อ`` appears a dozen times; the first is no more anchored than the rest."""
    from lawscan.ocr.read import _numerals_from_layer

    ocred = "ข้อ oo ทดสอบ ข้อ om ทดสอบ ข้อ ow ทดสอบ"
    layer = "ข้อ ๑ ทดสอบระบบทำงำนตำมรำยกำรที่ประกำศ"
    assert _numerals_from_layer(ocred, layer) == ocred
