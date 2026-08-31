"""ทะเบียนหน่วยงานกำกับ — ไฟล์เดียวที่ทั้ง prompt และกฎอ่าน

เดิมมีสองสำเนา: ``data/agencies.txt`` ที่เติมให้ prompt กับความรู้ที่กระจายอยู่
ในโค้ด สำเนาสองชุดคือสองชุดที่เพี้ยนออกจากกันได้ ตอนนี้เหลือ
``data/agencies.json`` ชุดเดียว

ค่าที่แผ่นงานคาดหวังคือชื่อทางการพร้อมวงเล็บชื่อย่อ ตามด้วยกระทรวง เช่น
``สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล (PDPC / สคส.),
กระทรวงดิจิทัลเพื่อเศรษฐกิจและสังคม`` — ทะเบียนจึงเก็บชื่อไว้อย่างที่แผ่นงานเขียน
"""

import json

import pytest

from lawscan.rules import agencies


class TestTheRegisterLoads:
    def test_it_holds_the_operators_register(self):
        assert len(agencies.catalogue().splitlines()) > 400

    def test_every_entry_has_a_name(self):
        data = json.loads(agencies.REGISTER.read_text(encoding="utf-8"))
        assert all(e.get("name", "").strip() for e in data["agencies"])

    def test_a_missing_register_is_empty_not_a_crash(self, tmp_path):
        assert agencies.catalogue(tmp_path / "nothing.json") == ""


class TestTheDocumentWritesItShort:
    """เอกสารพิมพ์ชื่อย่อ แผ่นงานต้องการชื่อเต็ม"""

    @pytest.mark.parametrize("written", [
        "ก.ล.ต.",
        "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์",
        "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์ (ก.ล.ต.)",
    ])
    def test_all_three_spellings_reach_the_same_name(self, written):
        assert agencies.official(written) == (
            "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์ (ก.ล.ต.)"
        )

    def test_a_latin_initialism_works_too(self):
        assert agencies.official("PDPC").startswith("สำนักงานคณะกรรมการคุ้มครองข้อมูล")


class TestWhatTheRegisterDeclines:
    def test_an_initialism_two_agencies_share_answers_nothing(self):
        # สช. คือทั้งสำนักงานคณะกรรมการสุขภาพแห่งชาติ และ
        # สำนักงานคณะกรรมการส่งเสริมการศึกษาเอกชน
        assert agencies.official("สช.") == ""

    def test_a_court_is_left_as_the_document_wrote_it(self):
        # ศาลไม่อยู่ในทะเบียน และไม่ควรถูกดัดให้ใกล้ชื่อที่อยู่
        assert agencies.official("ศาลปกครองสูงสุด") == ""
        assert agencies.with_ministry(["ศาลปกครองสูงสุด"]) == ["ศาลปกครองสูงสุด"]


class TestTheMinistryAboveIt:
    def test_the_chain_is_filled_in(self):
        assert agencies.with_ministry(["ก.ล.ต."]) == [
            "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์ (ก.ล.ต.)",
            "กระทรวงการคลัง",
        ]

    def test_a_ministry_already_named_is_not_repeated(self):
        got = agencies.with_ministry(["กรมสรรพากร", "กระทรวงการคลัง"])
        assert got.count("กระทรวงการคลัง") == 1

    def test_a_ministry_on_its_own_stays_put(self):
        assert agencies.with_ministry(["กระทรวงการคลัง"]) == ["กระทรวงการคลัง"]

    def test_the_same_agency_twice_is_written_once(self):
        assert agencies.with_ministry(["ก.ล.ต.", "ก.ล.ต."]).count(
            "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์ (ก.ล.ต.)"
        ) == 1


class TestTheExportDamage:
    def test_nikhahit_plus_sara_aa_matches_the_real_vowel(self):
        # ``ดํารง`` กับ ``ดำรง`` หน้าตาเหมือนกันแต่เทียบกันไม่ติด
        name = "ศาลฎีกาแผนกคดีอาญาของผู้ดํารงตําแหน่งทางการเมือง"
        assert agencies.official(name) == agencies.official(name.replace("ํา", "ำ"))


class TestOneSourceOnly:
    def test_the_prompt_and_the_rule_read_the_same_file(self):
        from lawscan.llm import client as client_module

        rendered = client_module.Client().lists()["agencies"]
        assert rendered == agencies.catalogue()

    def test_a_line_is_the_name_then_its_ministry(self):
        line = next(l for l in agencies.catalogue().splitlines() if "\t" in l)
        name, _, ministry = line.partition("\t")
        assert agencies.ministry(name) == ministry


class TestATitleStandsForABody:
    """แผ่นงานเก็บชื่อองค์กร ไม่ใช่ชื่อตำแหน่ง

    100233 ตอบทั้ง ``รัฐมนตรีว่าการกระทรวงการคลัง`` และ ``กระทรวงการคลัง``
    ซึ่งเป็นองค์กรเดียวกันเขียนสองครั้ง
    """

    def test_a_minister_is_their_ministry(self):
        assert agencies.body_of("รัฐมนตรีว่าการกระทรวงการคลัง") == "กระทรวงการคลัง"
        assert agencies.body_of("ปลัดกระทรวงมหาดไทย") == "กระทรวงมหาดไทย"

    def test_the_prime_minister_has_one_office(self):
        assert agencies.body_of("นายกรัฐมนตรี") == "สำนักนายกรัฐมนตรี"

    def test_a_title_that_names_no_body_is_left_alone(self):
        # ``อธิบดี`` ของกรมไหนก็ได้ เดาแล้วจะใส่องค์กรที่เอกสารไม่เคยเอ่ยถึง
        assert agencies.body_of("อธิบดี") == "อธิบดี"
        assert agencies.official("อธิบดี") == ""

    def test_the_same_body_twice_collapses(self):
        got = agencies.with_ministry([
            "รัฐมนตรีว่าการกระทรวงการคลัง", "กระทรวงการคลัง",
            "รัฐมนตรีว่าการกระทรวงมหาดไทย", "กระทรวงมหาดไทย",
        ])
        assert got == ["กระทรวงการคลัง", "กระทรวงมหาดไทย"]


class TestTwoAgenciesInOneSlot:
    """โมเดลลอกลูกศรจากตัวอย่างใน prompt มาต่อสองหน่วยงานเข้าด้วยกัน"""

    def test_an_arrow_separates_rather_than_joins(self):
        from lawscan.merge import Row

        row = Row(document="100239")
        row.put("หน่วยงานกำกับ",
                ["กรมอุทยานแห่งชาติ สัตว์ป่า และพันธุ์พืช → กระทรวงทรัพยากรธรรมชาติและสิ่งแวดล้อม"],
                "llm:identity")
        got = row.value("หน่วยงานกำกับ")
        assert " → " not in got
        assert got == ("กรมอุทยานแห่งชาติ สัตว์ป่า และพันธุ์พืช, "
                       "กระทรวงทรัพยากรธรรมชาติและสิ่งแวดล้อม")


class TestTheRegisterWritesTheBracket:
    """Whatever bracket arrives with a name is dropped before the lookup.

    Measured over the operator's 240 rows: 96 cells carry a bracket, every one
    of them holds an initialism, and not one holds a ministry. So the bracket
    is the register's to write, and a name that arrives wearing another one is
    still the same agency.
    """

    def test_an_invented_initialism_is_replaced_by_the_register_s(self):
        assert agencies.with_ministry(["สำนักงานคณะกรรมการกำกับกิจการพลังงาน (สำนักงาน กกพ.)"]) == [
            "สำนักงานคณะกรรมการกำกับกิจการพลังงาน (กกพ.)", "กระทรวงพลังงาน"]

    def test_a_ministry_in_the_bracket_becomes_its_own_item(self):
        """``กรมปศุสัตว์ (กระทรวงเกษตรและสหกรณ์)`` matches no register row at
        all while the bracket is on it, so neither name was reaching the
        sheet in the register's spelling."""
        assert agencies.with_ministry(["กรมปศุสัตว์ (กระทรวงเกษตรและสหกรณ์)"]) == [
            "กรมปศุสัตว์", "กระทรวงเกษตรและสหกรณ์"]


class TestTwoNamesInOneItem:
    """A pair joined by a comma is two answers, not one name."""

    def test_the_pair_is_split_before_the_lookup(self):
        assert agencies.with_ministry(["กรมเจ้าท่า (กระทรวงคมนาคม), รัฐมนตรีว่าการกระทรวงคมนาคม"]) == [
            "กรมเจ้าท่า", "กระทรวงคมนาคม"]

    def test_no_register_name_holds_a_comma(self):
        """Which is what makes splitting on one safe."""
        import json
        rows = json.loads(agencies.REGISTER.read_text(encoding="utf-8"))["agencies"]
        assert not [r for r in rows if "," in r["name"]]


class TestATitleIsNotAnOrganisation:
    """The column asks which body regulates. Naming the person at its head
    answers a different question — the operator's sheet writes a title in 4 of
    239 filled cells, and in each of those the register already supplies it."""

    def test_a_title_is_dropped_inside_a_ministry_chain(self):
        """A department's own director is the department written twice."""
        assert agencies.with_ministry(["กรมปศุสัตว์", "อธิบดีกรมปศุสัตว์"]) == [
            "กรมปศุสัตว์", "กระทรวงเกษตรและสหกรณ์"]

    def test_a_title_survives_where_no_ministry_sits_above(self):
        """An independent body's head regulates a layer of its own, which is
        why the operator's sheet writes ``สำนักงานศาลยุติธรรม, ประธานศาลฎีกา``
        and ``สำนักงานผู้ตรวจการแผ่นดิน, องค์กรอิสระ, ประธานผู้ตรวจการแผ่นดิน``."""
        assert agencies.with_ministry(["สำนักงานผู้ตรวจการแผ่นดิน", "ผู้ตรวจการแผ่นดิน"]) == [
            "สำนักงานผู้ตรวจการแผ่นดิน", "องค์กรอิสระ", "ผู้ตรวจการแผ่นดิน"]

    def test_a_title_the_register_supplies_is_kept(self):
        """``ประธานศาลฎีกา`` is what the register files สำนักงานศาลยุติธรรม
        under. Dropping it would be overruling the register, not the model."""
        assert agencies.with_ministry(["สำนักงานศาลยุติธรรม"]) == [
            "สำนักงานศาลยุติธรรม", "ประธานศาลฎีกา"]

    def test_a_title_is_kept_when_it_is_the_only_answer(self):
        """An empty cell says the document names no regulator. It does."""
        assert agencies.with_ministry(["ประธานศาลฎีกา"]) == ["ประธานศาลฎีกา"]

    def test_a_seat_the_register_already_wrote_is_not_written_twice(self):
        """The register files ปปง. under ``นายกรัฐมนตรี``. Converting the
        model's own copy of that title to ``สำนักนายกรัฐมนตรี`` would put the
        same seat in the cell twice under two spellings."""
        assert agencies.with_ministry([
            "สำนักงานคณะกรรมการป้องกันและปราบปรามการฟอกเงิน (สำนักงาน ป.ป.ง.)",
            "นายกรัฐมนตรี",
        ]) == ["สำนักงานคณะกรรมการป้องกันและปราบปรามการฟอกเงิน (ปปง.)", "นายกรัฐมนตรี"]


class TestAJudgmentNamesItsCourt:
    """V19 rule 14.3 asks for the court alone on a judgment or a ruling, and
    the sheet writes ``ศาลรัฐธรรมนูญ`` — not the office that administers it,
    and not the presiding judge."""

    def test_the_office_prefix_comes_off(self):
        assert agencies.court_only(
            ["สำนักงานศาลรัฐธรรมนูญ", "ประธานศาลรัฐธรรมนูญ"]) == ["ศาลรัฐธรรมนูญ"]

    def test_a_court_already_named_is_left_alone(self):
        assert agencies.court_only(["ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง"]) == [
            "ศาลฎีกาแผนกคดีอาญาของผู้ดำรงตำแหน่งทางการเมือง"]

    def test_an_answer_with_no_court_in_it_survives(self):
        """The rule only fires on judgments; if one names no court at all,
        emptying the cell would be worse than leaving what was found."""
        assert agencies.court_only(["กรมสรรพากร"]) == ["กรมสรรพากร"]
