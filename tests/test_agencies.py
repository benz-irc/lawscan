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
