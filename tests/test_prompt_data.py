"""Lists a prompt needs live in data/, not pasted into the prompt.

The business question already carries several hundred taxonomy codes this way.
The agency question needs the same thing for a different list, and one hard
coded placeholder was the reason it could not have it — so the substitution is
now a table, and adding a list is adding a row to it.
"""

import pytest

from lawscan.llm.question import Question

SCHEMA = {"type": "object"}


@pytest.fixture
def prompt_file(tmp_path, monkeypatch):
    def write(text: str) -> Question:
        monkeypatch.setattr("lawscan.llm.question.PROMPTS", tmp_path)
        (tmp_path / "sample.md").write_text(text, encoding="utf-8")
        return Question(name="sample", fills=(), schema=SCHEMA)
    return write


class TestFilling:
    def test_a_placeholder_is_replaced(self, prompt_file):
        question = prompt_file("เลือกจากรายการนี้\n{{agencies}}\n")
        assert "กรม ก." in question.prompt({"agencies": "กรม ก.\nกรม ข."})

    def test_two_placeholders_are_both_replaced(self, prompt_file):
        question = prompt_file("{{taxonomy}} และ {{agencies}}")
        text = question.prompt({"taxonomy": "รหัส", "agencies": "หน่วยงาน"})
        assert "รหัส" in text and "หน่วยงาน" in text

    def test_a_prompt_with_no_placeholder_is_untouched(self, prompt_file):
        question = prompt_file("ไม่มีอะไรต้องเติม")
        assert question.prompt({"taxonomy": "รหัส"}) == "ไม่มีอะไรต้องเติม"

    def test_a_placeholder_with_no_data_becomes_empty(self, prompt_file):
        """A missing data file must not leave the braces in the instruction."""
        question = prompt_file("รายการ: {{agencies}} จบ")
        assert "{{" not in question.prompt({})


class TestClientSuppliesTheFiles:
    def test_the_client_reads_each_list_from_data(self, tmp_path, monkeypatch):
        from lawscan.llm import client as client_module

        monkeypatch.setattr(client_module, "DATA", tmp_path)
        (tmp_path / "agencies.txt").write_text("กรมทดสอบ\n", encoding="utf-8")
        assert client_module.Client().lists()["agencies"] == "กรมทดสอบ\n"

    def test_a_list_this_install_does_not_have_leaves_no_braces(
        self, tmp_path, monkeypatch
    ):
        """An install without the operator's lists still sends a clean prompt."""
        from lawscan.llm import client as client_module
        from lawscan.llm import question as question_module

        monkeypatch.setattr(client_module, "DATA", tmp_path / "data")
        monkeypatch.setattr(question_module, "PROMPTS", tmp_path)
        (tmp_path / "sample.md").write_text("รายการ: {{agencies}} จบ", encoding="utf-8")
        question = Question(name="sample", fills=(), schema=SCHEMA)
        assert client_module.Client().prompt_for(question) == "รายการ:  จบ"


def test_the_business_prompt_still_carries_the_master_list():
    """Asking for codes from a list the model never receives.

    ``business.md`` was rewritten to V16 and the ``{{taxonomy}}`` placeholder
    did not survive the rewrite. Nothing failed: the prompt was valid, the
    call succeeded, and the model answered with two empty lists and a
    confidence of 32 — which is the correct answer to "pick a sub-category
    code" when no sub-category codes were supplied. Both columns came back
    "-" on every document.
    """
    from lawscan.llm.client import Client
    from lawscan.llm.questions import BUSINESS

    sent = Client().prompt_for(BUSINESS)
    assert "{{taxonomy}}" not in sent, "ตัวแทนที่ยังไม่ถูกแทนค่า — ไฟล์ข้อมูลหาย"
    assert len(sent) > 20_000, (
        f"คำสั่ง business ยาวเพียง {len(sent):,} ตัวอักษร — สั้นเกินกว่าจะมีทะเบียนหมวดธุรกิจอยู่"
    )


class TestACodeIsCorrectedByTheNameBesideIt:
    """The register is 666 lines of ``code = name`` and the model reads it a
    row out — sixty codes over twenty-two documents carried a name belonging
    to a different code, and the shift repeats: ``AV1`` with AV2's name,
    ``AB1`` with AB2's, ``AB2`` with AB3's.

    The name is the half chosen deliberately, so the name decides.
    """

    def test_a_shifted_code_is_moved_to_the_name_it_wrote(self):
        from lawscan.rules.categories import realign

        assert realign("พบ [AV1] ร้านคาราโอเกะ ในเอกสาร", ["AV1"]) == ["AV2"]

    def test_a_whole_shifted_run_is_walked_back(self):
        from lawscan.rules.categories import realign

        said = ("[AB1] ผู้ค้าส่งและตัวแทนจำหน่าย · "
                "[AB2] ห้างสรรพสินค้าและโมเดิร์นเทรด")
        assert realign(said, ["AB1", "AB2", "AB3"]) == ["AB2", "AB3"]

    def test_a_code_with_no_name_beside_it_is_left_alone(self):
        from lawscan.rules.categories import realign

        assert realign("ไม่มีชื่อหมวดเลย", ["AB1", "AB2"]) == ["AB1", "AB2"]
        assert realign("", ["AB1"]) == ["AB1"]

    def test_one_category_is_never_named_twice(self):
        """Corrected in place then deduplicated. Where a code's name was never
        written, and its correction lands on a code already there, the list
        comes back shorter — which is right, because that code had nothing
        standing behind it."""
        from lawscan.rules.categories import realign

        said = "[AB2] ห้างสรรพสินค้าและโมเดิร์นเทรด"
        assert realign(said, ["AB2", "AB3"]) == ["AB3"]


class TestTheRegisterLineIsTheAnswer:
    """The codes come back as ``code = name`` so that reading the register can
    be checked at all.

    Measured over twenty-two documents, 87% of the names the model wrote
    beside its codes were its own words rather than the register's, and only
    three of the wrong codes sat beside the right one — which is what reading
    it and slipping a row would look like. The rest jumped families entirely.
    It was not misreading the register; it was not opening it.
    """

    def test_the_name_decides_the_code(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB1 = ผู้ค้าส่งและตัวแทนจำหน่าย"]) == ["AB2"]

    def test_a_line_copied_whole_passes_through(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB2 = ผู้ค้าส่งและตัวแทนจำหน่าย",
                           "AC1 = การก่อสร้างอาคาร"]) == ["AB2", "AC1"]

    def test_the_register_s_own_spacing_is_not_part_of_the_name(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["D2 = การผลิตผลิตภัณฑ์เสริมอาหารและโภชนาการ"]) == ["D2"]

    def test_a_name_the_register_does_not_have_is_dropped(self):
        """A code with nothing behind it is worse than no code: the column has
        no room to say it was guessed."""
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AA1 = ธุรกิจซื้อมาขาย"]) == []
        assert from_pairs(["D2 = การผลิต ผลิตภัณฑ์เสริมอาหาร"]) == []

    def test_an_answer_with_no_pairs_still_reads(self):
        """Answer files recorded before the format changed still rebuild."""
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB2", "AC1"]) == ["AB2", "AC1"]

    def test_the_line_s_own_tag_is_not_part_of_the_name(self):
        """The register ends every line ``[CORE]`` or ``[SUPPORT]``; a faithful
        copy brings it along, and it says which column the row may be answered
        in, not what the category is called."""
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB2 = ผู้ค้าส่งและตัวแทนจำหน่าย [CORE]"]) == ["AB2"]
        assert from_pairs(["  A5 = ยางพารา [CORE]"]) == ["A5"]


class TestTheSupportColumnKeepsTheRegisterSTag:
    """The register's ``[CORE]`` / ``[SUPPORT]`` tag binds the support column
    and not the core one.

    The operator's own answers are what say so: of the 278 codes in their
    support column exactly one carries ``[CORE]``, while 195 of the 466 in
    their core column carry ``[SUPPORT]``. So the constraint runs one way.
    """

    def test_a_core_code_is_dropped_from_the_support_column(self):
        from lawscan.rules.categories import support_only

        assert support_only(["CC9", "AC1", "CE1"]) == ["CC9", "CE1"]

    def test_a_code_the_register_does_not_know_is_kept(self):
        """Dropping it would be a guess about a code we cannot look up."""
        from lawscan.rules.categories import support_only

        assert support_only(["ZZ99"]) == ["ZZ99"]


class TestTheDocumentBelongsToSomebody:
    """A document is *about* something and it also *belongs to* somebody, and
    the register has codes for both. Asked who is bound by an ombudsman's
    travel regulation a model answers "staff" and reaches for the code for
    public servants; the sheet reaches for ``CC9 ผู้ตรวจการแผ่นดิน``."""

    def test_the_office_prefix_is_not_part_of_the_institution(self):
        from lawscan.rules.categories import of_institution

        assert of_institution("สำนักงานผู้ตรวจการแผ่นดิน, องค์กรอิสระ") == ["CC9"]
        assert of_institution("สำนักงานศาลยุติธรรม, ประธานศาลฎีกา") == ["CC4"]

    def test_a_bracketed_initialism_does_not_block_the_lookup(self):
        from lawscan.rules.categories import of_institution

        assert of_institution(
            "สำนักงานคณะกรรมการกำกับกิจการพลังงาน (กกพ.), กระทรวงพลังงาน") == ["CC32"]

    def test_a_body_the_register_has_no_code_for_adds_nothing(self):
        """Most departments are not categories in their own right."""
        from lawscan.rules.categories import of_institution

        assert of_institution("กรมสรรพากร, กระทรวงการคลัง") == []


class TestAnExemptedGroupKeepsItsTag:
    """V19 rule 5.4(3) asks for ``[Exempted]`` on a group the law excuses, and
    the operator's newer answers carry it three times. A reader who is in scope
    but excused needs to know that; it is not the same as not being mentioned.

    The tag is mixed case and the register's own tags are not, which is what
    tells a status apart from ``[CORE]``.
    """

    def test_a_tag_on_the_code_survives_the_lookup(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB2[Exempted] = ผู้ค้าส่งและตัวแทนจำหน่าย"]) == ["AB2[Exempted]"]

    def test_a_tag_written_after_the_name_moves_onto_the_code(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB2 = ผู้ค้าส่งและตัวแทนจำหน่าย [Exempted]"]) == ["AB2[Exempted]"]

    def test_the_registers_own_tag_still_comes_off(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB2 = ผู้ค้าส่งและตัวแทนจำหน่าย [CORE]"]) == ["AB2"]

    def test_the_name_still_decides_the_code_through_a_tag(self):
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["AB1[Exempted] = ผู้ค้าส่งและตัวแทนจำหน่าย"]) == ["AB2[Exempted]"]

    def test_an_impact_label_is_read_off_and_not_kept(self):
        """V19's STEP 2 asks for ``[Direct Duty]`` and the like in the
        reasoning column. When they arrive on a code instead, matching only
        ``[Exempted]`` left the label inside the name, matched no register row,
        and dropped the code — which emptied both columns on 100114."""
        from lawscan.rules.categories import from_pairs

        assert from_pairs(
            ["D4 = การผลิตเนื้อสัตว์แปรรูปและอาหารทะเล [Direct Duty]"]) == ["D4"]
        assert from_pairs(
            ["BL3 = ห้องปฏิบัติการทดสอบและสอบเทียบ [Service Opportunity]"]) == ["BL3"]

    def test_the_two_labels_with_an_ampersand_are_read_off_too(self):
        """``&`` is in two of V19's seven labels. Leaving it out of the
        character class cost 100016 all seven of its codes at once."""
        from lawscan.rules.categories import from_pairs

        assert from_pairs(["BW2 = ภาษีเงินได้นิติบุคคล[Benefit & Incentive]"]) == ["BW2"]
        assert from_pairs(["AM6 = มหาวิทยาลัย [Rights & Admin]"]) == ["AM6"]


class TestTheScratchWorkIsWrittenFirst:
    """Key order in the schema is the order the model thinks in.

    A strict ``response_format`` is generated key by key, so whichever key
    comes first is settled before the rest exists. ``business`` had ``core``
    and ``support`` ahead of ``reasoning``, which meant the codes were chosen
    before a word of analysis had been written and the analysis was a write-up
    of an answer already given. It showed: over twenty-two documents 96 of the
    167 codes in the two columns had no line explaining them, and four
    documents filled the columns while explaining nothing at all.
    """

    def test_the_thinking_comes_before_the_columns_it_justifies(self):
        from lawscan.llm.questions import BUSINESS

        from lawscan.llm.questions import SUPPORT

        for question, answer in ((BUSINESS, "core"), (SUPPORT, "support")):
            keys = list(question.schema["properties"])
            for thinking in ("analysis", "reasoning"):
                assert keys.index(thinking) < keys.index(answer), (
                    f"{question.name}: ลำดับคีย์คือลำดับความคิด — พบ {keys}"
                )

    def test_the_scratch_work_comes_before_the_summary_of_it(self):
        from lawscan.llm.questions import BUSINESS

        keys = list(BUSINESS.schema["properties"])
        assert keys.index("analysis") < keys.index("reasoning")

    def test_the_required_list_leads_with_the_thinking_too(self):
        from lawscan.llm.questions import BUSINESS

        assert BUSINESS.schema["required"][:2] == ["analysis", "reasoning"]

    def test_the_prompt_says_the_order_in_words_as_well(self):
        from pathlib import Path

        said = Path("prompts/business.md").read_text(encoding="utf-8")
        assert "มาก่อน `core` เสมอ" in said

    def test_every_code_in_a_column_owes_a_line_of_reasoning(self):
        from pathlib import Path

        said = Path("prompts/business.md").read_text(encoding="utf-8")
        assert "ต้องมีบรรทัดสรุปของตัวเองในช่องนี้เสมอ" in said

    def test_the_support_step_teaches_a_search_and_names_no_category(self):
        """Step 6.2 has to say how to look, because it may not say what to find.

        Its first wording listed four state-side category names as examples
        and the model picked one off the list instead of reading the register,
        which is how an ombudsman's office came back as ``องค์การมหาชน``.
        Deleting the list left a question so open that support fell again —
        25 codes against the key's 49. What replaces it is a lookup: three
        search terms drawn from the document's own words, written out before
        the codes, so the register is opened rather than recalled.
        """
        from pathlib import Path

        said = Path("prompts/support.md").read_text(encoding="utf-8")
        assert "คำค้นที่ 1" in said and "คำค้นที่ 2" in said and "คำค้นที่ 3" in said
        assert "ชื่อหน่วยงานผู้ออกกฎ" in said
        assert "ชื่อแผนกไม่ใช่คำค้น" in said

    def test_the_support_codes_are_found_during_the_thinking(self):
        """Support codes need a step of their own or the consistency rule eats them.

        The six scratch-work steps all ask who the law binds — the target, the
        ecosystem, the exempted. None of them asks which back-office or state
        process the document touches, so support codes were only ever invented
        at the moment the column was filled. Once every code in a column had to
        own a line of reasoning, codes with no step to come from simply stopped
        appearing: support fell from 69 to 23 over twenty-two documents against
        a key that holds 49, and twelve documents came back with none at all.
        """
        from pathlib import Path

        said = Path("prompts/support.md").read_text(encoding="utf-8")
        assert "ฝั่งที่ 1 — งานส่วนกลางของเอกชน" in said
        assert "ฝั่งที่ 2 — งานฝั่งรัฐ" in said

    def test_the_remedy_is_to_write_the_line_not_to_drop_the_code(self):
        """The first wording of this rule cost a quarter of the codes.

        Telling the model to cut any code it could not justify is an
        instruction to shorten the answer, and it followed it: 175 codes over
        twenty-two documents became 127, and the support column — where the
        codes are generic by design and a specific sentence is hardest to
        write — fell from 69 to 28 against a key that holds 49.
        """
        from pathlib import Path

        for name in ("business.md", "support.md"):
            said = Path("prompts", name).read_text(encoding="utf-8")
            assert "ไม่ใช่ตัดรหัสนั้นทิ้ง" in said, name
            assert "ห้ามลดจำนวนรหัสลงเพื่อให้เขียนน้อยลง" in said, name

    def test_both_halves_have_a_heading_of_their_own(self):
        from pathlib import Path

        said = Path("prompts/business.md").read_text(encoding="utf-8")
        assert "## analysis — สมุดทด" in said
        assert "## reasoning — สรุปรหัสและประเภทผลกระทบ" in said


class TestTheColumnStillShowsBothHalves:
    """Splitting the field must not lose half of what the operator reads.

    The sheet has one column for this and their own answers print the scratch
    work above the per-code summary, so the two fields are joined on the way
    into the cell rather than one of them being dropped.
    """

    def _row(self, value):
        from lawscan.merge import Row
        from lawscan.pipeline import _apply

        row = Row(document="ทดสอบ")
        _apply(row, "business", value, None)
        return row

    def test_the_two_fields_arrive_in_one_cell_in_order(self):
        row = self._row({"analysis": "0) เขตอำนาจ", "reasoning": "[A1] ชื่อ", "core": ["A1"], "support": []})
        assert row.value("AI ให้เหตุผล") == "0) เขตอำนาจ<br>[A1] ชื่อ"

    def test_a_summary_with_no_scratch_work_still_reaches_the_cell(self):
        row = self._row({"reasoning": "[A1] ชื่อ", "core": ["A1"], "support": []})
        assert row.value("AI ให้เหตุผล") == "[A1] ชื่อ"

    def test_scratch_work_with_no_summary_still_reaches_the_cell(self):
        row = self._row({"analysis": "0) เขตอำนาจ", "reasoning": "", "core": [], "support": []})
        assert row.value("AI ให้เหตุผล") == "0) เขตอำนาจ"


class TestTheIssuingBodySCodeFollowsRuleFiveNine:
    """V19 rule 5.9 decides which half the institution's own code lands in.

    The rule is plain: where the document is an internal regulation of a state
    body or an independent agency, tag the code of the body that owns it into
    Core Business, and do not reach for a private business at all. The
    pipeline used to put that code in support every time, a placement chosen
    by watching the operator's answers rather than by reading their rule —
    and on 100001 their answer puts the ombudsman's code in support while core
    holds a procurement code whose register name ends in "เอกชนคู่ค้า", the
    private-sector reach 5.9 forbids.

    Only two of the twenty-two documents carry the band, so the change is
    worth almost nothing against this sample; the corpus of 240 holds 39.
    """

    def test_the_state_on_state_band_sends_it_to_core(self):
        from lawscan.rules import categories

        assert categories.institution_belongs_in_core("🔵 ฟ้า")

    def test_every_other_band_leaves_it_in_support(self):
        from lawscan.rules import categories
        from lawscan.rules import BANDS

        for name, band in BANDS.items():
            if name != "BLUE":
                assert not categories.institution_belongs_in_core(band), name

    def test_an_unfilled_band_leaves_it_in_support(self):
        from lawscan.rules import categories

        assert not categories.institution_belongs_in_core("")
        assert not categories.institution_belongs_in_core("   ")


class TestTheRegisterSOwnTagDecidesTheColumn:
    """The master list labels every code, and the label is the constraint.

    ``Tier/Price`` in the operator's own V8 file reads "Core Biz" over A–AW
    and "Support" over AY–CF, across all 582 rows, and the register this
    project sends agrees with that file on every one of them. Rule 6 of their
    prompt says the same in words, in every version of it.

    Enforcing it was held back because it scored −3.0 against their newer
    answers, which break the rule on 9 of 49 support codes. Their own notes on
    those answers record mistakes of the same kind — "อ่านหมวด ผิด ผลลัพท์
    [BY6] ... ที่ถูก คือ CC9" — so the answers are where the rule is broken,
    not where it is defined.
    """

    def test_a_core_tagged_code_cannot_stand_in_the_support_column(self):
        from lawscan.rules import categories

        kept = categories.support_only(["A1", "BW1", "AA17", "CC17"])
        assert "A1" not in kept and "AA17" not in kept
        assert kept == ["BW1", "CC17"]

    def test_the_register_and_the_operators_file_label_the_same_codes(self):
        import csv
        import re
        from pathlib import Path

        theirs = Path.home() / "Downloads" / (
            "(ร่าง) รายชื่อหมวดหลัก หมวดย่อย V8 29.03.2026 .xlsx - หมวด (1).csv"
        )
        if not theirs.exists():
            return  # their file is not part of the repo; the check runs where it is
        tier = None
        expected = {}
        with theirs.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                tier = (row.get("Tier/Price") or "").strip() or tier
                code = (row.get("หมวดย่อย") or "").strip()
                if code:
                    expected[code] = "CORE" if tier == "Core Biz" else "SUPPORT"
        ours = {}
        for line in Path("data/taxonomy.txt").read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Z]{1,2}\d{1,2})\s*=\s*(.+?)\s*(?:\[([A-Z]+)\])?\s*$", line)
            if m:
                ours[m.group(1)] = m.group(3)
        wrong = {c: (ours.get(c), t) for c, t in expected.items() if ours.get(c) != t}
        assert not wrong, f"ป้าย CORE/SUPPORT ไม่ตรงกับไฟล์ผู้ดูแล: {list(wrong)[:8]}"


class TestAStateOnStateDocumentStopsAtItsOwner:
    """Rule 4.10 is a hard stop, not an addition.

    "Tag เฉพาะ รหัสหมวดย่อยของหน่วยงานราชการ/องค์กรอิสระที่เป็นเจ้าของระเบียบ
    นั้นๆ" and "บังคับให้ข้าม การประมวลผลหาห่วงโซ่คุณค่าและผู้ให้บริการทันที".
    The operator's own example of the error is this project's output word for
    word: a hotel code and a taxi code on an ombudsman's travel-expense
    regulation, tagged because the text mentions lodging and fares. Six codes
    became one, and the one is the code their notes call correct.
    """

    def _row(self, band, agencies, core):
        from lawscan.merge import Row
        from lawscan.rules import categories

        row = Row(document="ทดสอบ")
        row.put("ระดับวามเสี่ยง ", band, "rule")
        row.put("หน่วยงานกำกับ", agencies, "rule")
        if categories.institution_belongs_in_core(band):
            owner = categories.of_institution(agencies)
            return owner or core
        return core

    def test_the_owner_replaces_everything_the_chain_found(self):
        got = self._row("🔵 ฟ้า", "สำนักงานผู้ตรวจการแผ่นดิน",
                        ["CC17", "BU3", "AN1", "AE2", "BC5"])
        assert got == ["CC9"]

    def test_any_other_band_leaves_the_chain_alone(self):
        core = ["CC17", "AE2"]
        assert self._row("🔴 แดง", "สำนักงานผู้ตรวจการแผ่นดิน", core) == core

    def test_an_unknown_body_leaves_the_chain_rather_than_emptying_it(self):
        core = ["CC17", "AE2"]
        assert self._row("🔵 ฟ้า", "หน่วยงานที่ทะเบียนไม่รู้จัก", core) == core


class TestTheSevenRulesTakenFromTheOperatorsOwnNotes:
    """Rules their prompt states and this project did not carry.

    The operator's comparison sheet records their diagnosis beside each
    version: "The Good Enough Trap" — the model finds one code for an umbrella
    word and stops — and "Lost in the Middle" — a long prompt is read but not
    applied at the moment the answer is written. Both match what was measured
    here: they sweep a code family 71% of the time against this project's 51%.
    """

    def _said(self, name):
        from pathlib import Path

        return Path("prompts", name).read_text(encoding="utf-8")

    def test_a_code_family_is_swept_rather_than_sampled(self):
        said = self._said("business.md")
        assert "ขั้นที่ 4 กวาดพี่น้องให้ครบสาย" in said
        assert "หยุดตรงนี้คือทำงานครึ่งเดียว" in said
        assert "เก็บเฉพาะตัวที่ตัวบทเอ่ยถึงกิจกรรมของมันจริง" in said

    def test_an_end_user_that_is_a_company_is_not_a_consumer(self):
        said = self._said("business.md")
        assert "ผู้ใช้งานปลายทางไม่ได้แปลว่าประชาชนทั่วไป" in said

    def test_a_name_in_a_definition_is_not_a_target(self):
        said = self._said("business.md")
        assert "ในฐานะตัวอย่าง คำนิยาม หรือเงื่อนไข" in said

    def test_expropriation_stops_at_the_landholder(self):
        said = self._said("business.md")
        assert "ห้ามข้ามช็อตไป tag" in said and "เวนคืน" in said

    def test_a_political_case_takes_no_business_code(self):
        said = self._said("business.md")
        assert "ห้ามจับคู่\nกับรหัสธุรกิจใด ๆ" in said

    def test_the_practical_impact_exception_needs_evidence(self):
        said = self._said("support.md")
        for proof in ("ภาระงานเอกสาร", "การจัดอบรม", "การตั้งงบประมาณ"):
            assert proof in said, proof
        assert "ห้าม tag จากจินตนาการ" in said

    def test_a_dash_is_a_real_answer_in_the_support_column(self):
        """Their rule 3.3.2 mandates it; the prompt here used to say the opposite.

        "เกือบทุกฉบับมีอย่างน้อยหนึ่งรหัสที่นี่" was written into this project's
        support prompt and is not the operator's rule — theirs reads "หากไม่มี
        ข้อกำหนดควบคุมงานสนับสนุนโดยตรง ให้บังคับตอบ - ทันที".
        """
        said = self._said("support.md")
        assert "เป็นคำตอบที่ถูกต้อง ไม่ใช่การยอมแพ้" in said
        assert "เกือบทุกฉบับมีอย่างน้อยหนึ่งรหัส" not in said

    def test_the_support_column_has_a_gate_with_its_own_test(self):
        """Removed once, and removing the whole gate was the wrong cut.

        The gate this column first carried was the core column's: hold back any
        code that cannot cite a clause of the document. That is unanswerable
        here — a support code is a *different* act that already binds the
        reader — so it rejected almost everything and support fell from 33% to
        19%. The fix was to drop that one criterion, not the gate; with no gate
        at all an ombudsman's travel-expense rules came back tagged with
        corporate income tax, private accounting standards and labour law.
        """
        said = self._said("support.md")
        assert "## ด่านคัดกรอง" in said
        assert "การอ้างมาตราไม่ได้\nไม่ใช่เหตุให้ตัดรหัสทิ้ง" in said
        assert "ตอบไม่ได้แม้ข้อเดียว ให้ปัดตก" in said
        assert "ห้ามยกงานส่วนกลางของเอกชนขึ้นมา" in said


class TestTheReasoningHoldsNoCodeTheSheetDoesNot:
    """A line explaining a code that reached neither column misleads the reader.

    Between the model's answer and the sheet sit the register's own
    ``[SUPPORT]`` tag, rule 6.2.1 against repeating a core code, and the
    corrections read from the document. Each of them can remove a code, and
    the sentence explaining that code used to stay where it was.
    """

    def test_a_line_whose_code_was_cut_moves_to_the_end(self):
        from lawscan.rules.categories import settled

        text, dropped = settled(
            "[K4] นิวเคลียร์ : ทำ<br>G2 = หิน : ทำ<br>[BL3] แล็บ : ทำ", ["K4", "BL3"]
        )
        assert dropped == ["G2"]
        assert text.startswith("[K4] นิวเคลียร์ : ทำ<br>[BL3] แล็บ : ทำ")
        assert "ปัดตก [G2] เนื่องจาก" in text and "หิน" in text

    def test_prose_between_the_lines_is_left_alone(self):
        from lawscan.rules.categories import settled

        text, dropped = settled("0) เขตอำนาจ — กรมหนึ่ง<br>[K4] นิวเคลียร์ : ทำ", ["K4"])
        assert dropped == []
        assert text == "0) เขตอำนาจ — กรมหนึ่ง<br>[K4] นิวเคลียร์ : ทำ"

    def test_an_empty_answer_is_returned_unchanged(self):
        from lawscan.rules.categories import settled

        assert settled("", ["K4"]) == ("", [])

    def test_no_document_in_the_last_run_keeps_an_orphan_line(self):
        """The measure this exists for, taken from the run itself."""
        import csv
        import re
        from pathlib import Path

        from lawscan.rules.categories import CAST_OFF

        result = Path("out/v32/result.csv")
        if not result.exists():
            return
        code = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b")
        line = re.compile(r"^\s*\[?([A-Z]{1,2}\d{1,2})\]?\s*[=\]:]")
        core = "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
        support = ("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)")
        orphans = []
        with result.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                columns = set(code.findall(row.get(core) or ""))
                columns |= set(code.findall(row.get(support) or ""))
                why = (row.get("AI ให้เหตุผล") or "").replace("<br>", "\n")
                cut = why.find(CAST_OFF)
                live = why[:cut] if cut > 0 else why
                said = {line.match(x).group(1) for x in live.split("\n") if line.match(x)}
                orphans += [(row["ชื่อไฟล์ "].strip(), c) for c in said - columns]
        assert not orphans, f"บรรทัดสรุปที่รหัสไม่อยู่ในช่องไหนเลย: {orphans[:8]}"


class TestTheSupportColumnSweepsTheParentLawSFamily:
    """Read out of their answers, not out of their rules.

    Of the 49 support codes in the reviewed answers, 13 repeat a core code
    outright, 5 share a family with one, and 5 are the same administrative
    code every time. Of the 26 that are genuinely new, the largest group is a
    family sweep off the parent act: a decree issued under the revenue code
    carries six codes from that one family, not the single one the decree is
    about.

    The rule this contradicts is their own 6.2.1, and enforcing that rule cost
    ten points on this column and eight of its thirteen correct codes.
    """

    def _said(self):
        from pathlib import Path

        return Path("prompts/support.md").read_text(encoding="utf-8")

    def test_the_parent_law_is_a_search_term_of_its_own(self):
        said = self._said()
        assert "คำค้นที่ 4  ชื่อกฎหมายแม่" in said
        assert "ไม่ใช่ชื่อเรื่องของเอกสารฉบับนี้" in said

    def test_finding_one_code_is_not_the_end_of_the_search(self):
        said = self._said()
        assert "ห้ามหยุดที่ตัวนั้น" in said
        assert "ห้ามกวาดข้ามเรื่อง" in said

    def test_a_code_already_in_core_may_still_belong_here(self):
        said = self._said()
        assert "อย่าตัดรหัสออกเพียงเพราะมันไปอยู่ช่องกิจการหลักแล้ว" in said

    def test_the_repeat_rule_is_enforced_again(self):
        """Turned off after reading their answers, back on at their request.

        Their sheet repeats a core code on 13 of its 49 support codes and the
        repetition reads as deliberate — a laboratory is both a business the
        law makes work for and a compliance area the reader's own operation
        touches. The rule is still theirs, and 6.2.1 says outright that a code
        chosen for core may not appear here. Keeping it costs this column
        about ten points; that cost is the operator's to accept.
        """
        from pathlib import Path

        code = Path("src/lawscan/pipeline.py").read_text(encoding="utf-8")
        assert 'value["support"] = [c for c in value["support"] if c not in core_now]' in code


class TestAnActivityIsTurnedIntoABusinessBeforeItIsLookedUp:
    """100017 is the case: a decree exempting spend on certain activities.

    Their answer carries the codes for the businesses that perform those
    activities; the sweep off the parent act reaches the tax family and stops.
    The register files businesses, not activities, so searching the activity
    name finds nothing and the model concludes there is nothing there. The
    core prompt has carried this conversion for a while; the support prompt
    did not.
    """

    def test_the_conversion_step_is_stated_and_is_mandatory(self):
        from pathlib import Path

        said = Path("prompts/support.md").read_text(encoding="utf-8")
        assert "คำค้นที่ 5  กิจกรรมที่ตัวบทผูกเงื่อนไขไว้" in said
        assert "ห้ามข้ามขั้นแปลง" in said
        assert "‹ธุรกิจหรืออาชีพที่รับทำกิจกรรมนั้น›" in said


class TestTheDocumentColumnIsAListNotANumberedList:
    """The sheet joins this column with commas, so the numbers are a second set.

    The model numbered fourteen of twenty-two documents and left the rest
    bare, which reads worse than either choice alone: ``1)`` looks like it
    means something when the entry beside it has no number at all.
    """

    def test_the_marker_comes_off_each_entry(self):
        from lawscan.answers import unnumbered

        assert unnumbered(["1) แบบรายงาน", "2. รายการ", "(3) อีกอัน", "4 - สุดท้าย"]) == [
            "แบบรายงาน", "รายการ", "อีกอัน", "สุดท้าย"
        ]

    def test_a_number_inside_a_document_name_survives(self):
        from lawscan.answers import unnumbered

        kept = unnumbered(["1) บัญชีหมายเลข 1 อัตราค่าเบี้ยเลี้ยง", "แบบ กปม./กตส. 2"])
        assert kept == ["บัญชีหมายเลข 1 อัตราค่าเบี้ยเลี้ยง", "แบบ กปม./กตส. 2"]

    def test_an_entry_that_was_only_a_marker_is_dropped(self):
        from lawscan.answers import unnumbered

        assert unnumbered(["1) ", "", None]) == []


class TestTheSummaryLineIsRecognisedInEveryShapeItArrives:
    """The pattern saw two of the three shapes, and the third is the common one.

    ``[K4] ชื่อ : ...`` and ``K4 = ชื่อ : ...`` matched; ``K4 ชื่อ : ...`` did
    not, and that is what the support answers mostly write. Twenty-six lines
    that were present read as missing, and the same wrong figure was reported
    twice in one day before anyone opened the file and looked.
    """

    def _codes(self, text):
        from lawscan.rules.categories import _SUMMARY_LINE

        return [m.group(1) for l in text.split("\n") if (m := _SUMMARY_LINE.match(l))]

    def test_all_three_shapes_are_read(self):
        assert self._codes(
            "[K4] นิวเคลียร์ : ทำ\nBW3 = ภาษีมูลค่าเพิ่ม : ทำ\nAA2 ตัวแทนออกของ : ทำ"
        ) == ["K4", "BW3", "AA2"]

    def test_a_line_that_merely_mentions_a_code_is_not_a_summary(self):
        assert self._codes("2.1 ผู้ตรวจสอบ — ห้องปฏิบัติการ [BL3]") == []
        assert self._codes("0) เขตอำนาจกฎหมาย — กรมหนึ่ง") == []


class TestALineIsRenumberedRatherThanDiscarded:
    """``realign`` fixes the code in the column; the line kept the old number.

    The model writes ``CC11 = กฎหมายศุลกากร`` — right name, wrong number — and
    the column ends up with ``BW11`` because that is what the register files
    that name under. Throwing the line away over the digit would lose a
    correct explanation, so the digit is corrected instead.
    """

    def test_a_wrong_number_beside_a_right_name_is_corrected(self):
        from lawscan.rules.categories import settled

        text, dropped = settled("CC11 = กฎหมายศุลกากร : ต้องผ่านพิธีการ", ["BW11"])
        assert dropped == []
        assert text.startswith("BW11 = กฎหมายศุลกากร")

    def test_a_name_that_names_nothing_kept_still_goes_to_the_end(self):
        from lawscan.rules.categories import CAST_OFF, settled

        text, dropped = settled("ZZ9 ชื่อที่ไม่มีในทะเบียน : ทำ", ["BW11"])
        assert dropped == ["ZZ9"]
        assert CAST_OFF in text


class TestTwoQuestionsShareTheCellWithOneTailBetweenThem:
    """Each question settles its own lines; the tails must not stack up inside.

    ``business`` writes the cell first and ``support`` appends to it, so the
    first question's cast-off block landed in the middle and the second
    question's live summary lines sat underneath it. Everything below that
    label reads as discarded, which is how six correct lines were counted as
    codes with no reasoning behind them.
    """

    def test_the_live_halves_join_and_the_tails_go_last(self):
        from lawscan.rules.categories import CAST_OFF, joined

        out = joined(
            f"A1 หนึ่ง : ทำ<br>{CAST_OFF}<br>Z9 เก้า : ทำ",
            f"B2 สอง : ทำ<br>{CAST_OFF}<br>Y8 แปด : ทำ",
        ).split("<br>")
        assert out == ["A1 หนึ่ง : ทำ", "B2 สอง : ทำ", CAST_OFF, "Z9 เก้า : ทำ", "Y8 แปด : ทำ"]

    def test_one_tail_only_however_many_halves_carry_one(self):
        from lawscan.rules.categories import CAST_OFF, joined

        assert joined(f"A1 : ทำ<br>{CAST_OFF}<br>Z9 : ทำ", "B2 : ทำ").count(CAST_OFF) == 1

    def test_halves_with_no_tail_are_simply_joined(self):
        from lawscan.rules.categories import CAST_OFF, joined

        out = joined("A1 : ทำ", "B2 : ทำ")
        assert out == "A1 : ทำ<br>B2 : ทำ" and CAST_OFF not in out

    def test_every_code_in_the_last_run_owns_a_line(self):
        import csv
        import re
        from pathlib import Path

        from lawscan.rules.categories import CAST_OFF, _SUMMARY_LINE

        result = Path("out/v36/result.csv")
        if not result.exists():
            return
        code = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b")
        core = "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
        support = ("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)")
        bare = []
        with result.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                columns = set(code.findall(row.get(core) or ""))
                columns |= set(code.findall(row.get(support) or ""))
                why = (row.get("AI ให้เหตุผล") or "").replace("<br>", "\n")
                cut = why.find(CAST_OFF)
                live = why[:cut] if cut > 0 else why
                said = {m.group(1) for l in live.split("\n")
                        if (m := _SUMMARY_LINE.match(l))}
                bare += [(row["ชื่อไฟล์ "].strip(), c) for c in columns - said]
        assert not bare, f"รหัสในช่องที่ไม่มีบรรทัดเหตุผล: {bare[:8]}"


class TestNothingIsBothAnAnswerAndCastOff:
    """A code listed as discarded must not also be sitting in a column.

    ``settled`` ran per question and saw only that question's codes, so the
    lines ``business`` wrote were settled against the support column and moved
    to the cast-off block while their codes stayed in core: on 100015 five
    food-production codes read as rejected and as answers at once, and 24 codes
    over 13 documents did the same.
    """

    def test_the_last_run_has_no_code_on_both_sides(self):
        import csv
        import re
        from pathlib import Path

        from lawscan.rules.categories import CAST_OFF

        result = Path("out/v37/result.csv")
        if not result.exists():
            return
        code = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b")
        core = "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
        support = ("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)")
        both = []
        with result.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                columns = set(code.findall(row.get(core) or ""))
                columns |= set(code.findall(row.get(support) or ""))
                why = (row.get("AI ให้เหตุผล") or "").replace("<br>", "\n")
                at = why.find(CAST_OFF)
                if at < 0:
                    continue
                cast = set(code.findall(why[at:]))
                both += [(row["ชื่อไฟล์ "].strip(), c) for c in cast & columns]
        assert not both, f"รหัสที่ถูกปัดตกแต่ยังอยู่ในช่อง: {both[:8]}"

    def test_no_code_repeats_across_the_two_columns(self):
        import csv
        import re
        from pathlib import Path

        result = Path("out/v37/result.csv")
        if not result.exists():
            return
        code = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b")
        core = "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
        support = ("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)")
        dup = []
        with result.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                shared = set(code.findall(row.get(core) or "")) & set(
                    code.findall(row.get(support) or ""))
                dup += [(row["ชื่อไฟล์ "].strip(), c) for c in shared]
        assert not dup, f"รหัสซ้ำสองช่อง ผิดกฎ 6.2.1: {dup[:8]}"


class TestTheReasoningCellFollowsTheOperatorsThreeSteps:
    """V19 prompt 3 names the shape of this column; ours had its own.

    Their column reads ``STEP 1: พื้นที่ทดเลขในใจ`` with six numbered items,
    then ``STEP 2: สรุปผลรหัสและ Impact Classification`` as one line per code,
    then ``STEP 3: รายงานผลด่านคัดกรอง`` listing what was rejected and why.
    Two questions write this cell here, so only the first prints the STEP 1 and
    STEP 2 headings and the rules put STEP 3 at the bottom once.
    """

    def _said(self, name):
        from pathlib import Path

        return Path("prompts", name).read_text(encoding="utf-8")

    def test_the_first_question_opens_each_step(self):
        said = self._said("business.md")
        assert "`STEP 1: พื้นที่ทดเลขในใจ`" in said
        assert "`STEP 2: สรุปผลรหัสและ Impact Classification`" in said
        assert "STEP 3: รายงานผลด่านคัดกรอง" in said

    def test_the_second_question_does_not_repeat_them(self):
        said = self._said("support.md")
        assert "ห้ามพิมพ์หัวข้อ\n`STEP 1` หรือ `STEP 2` ซ้ำ" in said

    def test_the_six_items_are_numbered_their_way(self):
        said = self._said("business.md")
        for item in ("    1) เขตอำนาจกฎหมาย", "    1.2) คำร่มที่พบ",
                     "    2) กลุ่มผู้ถูกบังคับใช้หลักทุกกลุ่ม",
                     "    3) ผู้ให้บริการใน ecosystem",
                     "    4) ผู้รับผลกระทบแฝงหรือสืบเนื่อง",
                     "    5) สินค้าหรือบริการที่ถูกควบคุม",
                     "    6) ข้อยกเว้นหรือการผ่อนผัน"):
            assert item in said, item

    def test_the_jurisdiction_lock_is_stated(self):
        said = self._said("business.md")
        assert "ล็อคเขตอำนาจทุกเส้นทาง" in said
        assert "ให้ปัดตกเข้า STEP 3 ทันที" in said

    def test_the_gate_runs_before_step_two_is_written(self):
        said = self._said("business.md")
        assert "ด่านคัดกรองก่อนพิมพ์" in said
        assert "ห้ามเขียนลง STEP 2 เด็ดขาด" in said

    def test_a_rejection_takes_their_wording(self):
        from lawscan.rules.categories import CAST_OFF, settled

        text, dropped = settled("G2 = เหมืองหิน : ทำ", ["K4"])
        assert dropped == ["G2"]
        assert CAST_OFF == "STEP 3: รายงานผลด่านคัดกรอง"
        assert "ปัดตก [G2] เนื่องจาก" in text

    def test_a_rejection_the_model_already_worded_is_left_alone(self):
        from lawscan.rules.categories import settled

        text, _ = settled("ปัดตก [G2] เนื่องจาก โยงข้ามเรื่องไปเอง", ["K4"])
        assert text.count("ปัดตก [G2]") == 1


class TestTheMainTargetsItemCarriesCodesAndIsSweptFrom:
    """Item 2 of STEP 1 was prose, and the codes surfaced one item too late.

    Over twenty-two documents, 17 wrote the heading "กลุ่มผู้ถูกบังคับใช้หลัก"
    and then described the groups without tagging a single code; the codes
    appeared instead under item 3, the ecosystem slot meant for contractors.
    On 100121 that put hospitals — which own the x-ray machines the fee
    schedule licenses — among the service providers, and the family sweep,
    which reads from the main-target codes, had nothing to read. The key
    carries the whole medical and veterinary run there; this project had two
    of fourteen codes. The one document whose item 2 held codes, 100067 with
    fifteen, is also the one whose core column matched the key best.
    """

    def _said(self):
        from pathlib import Path

        return Path("prompts/business.md").read_text(encoding="utf-8")

    def test_item_two_must_end_in_codes(self):
        said = self._said()
        assert "ข้อนี้ต้องจบด้วยรายการรหัส ห้ามจบด้วยประโยคบรรยาย" in said
        assert "ถ้าข้อนี้ว่าง แปลว่ายังไม่ได้ทำงาน" in said

    def test_a_company_end_user_belongs_to_item_two(self):
        said = self._said()
        assert "ผู้ใช้งานปลายทางที่เป็นนิติบุคคล อยู่ในข้อนี้ ไม่ใช่ข้อ 3" in said
        assert "วางผิดช่อง แล้วจะไม่ถูกกวาดต่อ" in said

    def test_the_sweep_reads_from_item_two(self):
        said = self._said()
        assert "แล้วอ่านพี่น้องของทุกรหัสในข้อนี้ให้ครบสาย" in said

    def test_the_sweep_keeps_only_what_the_text_mentions(self):
        """Sweeping the whole run was too strong: core answered 134 codes
        against the key's 125 and precision fell from 58% to 46%. Reading the
        run is right; keeping all of it is not. A sibling is kept only where
        the text names what that category does.
        """
        said = self._said()
        assert "อ่านให้ครบ แต่เก็บเฉพาะตัวที่ผ่านด่าน" in said
        assert "การอยู่สายเดียวกันไม่ใช่เหตุผล" in said
        assert "ตอบไม่ได้ว่าตัวบทเอ่ยตรงไหน ให้ปัดตกเข้า STEP 3" in said


class TestACodeCannotBeBothAnAnswerAndARejection:
    """The model contradicts its own STEP 3, and the prompt now says so.

    Measured on the last two runs: flash-lite wrote three codes into STEP 3 and
    left two of them sitting in a column; pro wrote seven and left two. The
    rules clean it up afterwards, but a model that writes the answer first and
    settles second will keep producing the contradiction, so the instruction
    now tells it to settle first and write what survives.
    """

    def test_both_prompts_forbid_it_in_words(self):
        from pathlib import Path

        for name in ("business.md", "support.md"):
            said = Path("prompts", name).read_text(encoding="utf-8")
            assert "1) ปัดตกให้เสร็จก่อน  2) เหลืออะไรค่อยเขียนลงช่อง" in said, name
            assert "ให้ลบออกจากช่อง\nไม่ใช่ลบออกจาก STEP 3" in said, name

    def test_the_rule_does_not_read_as_reject_less(self):
        """First wording cut the wrong way: rejections fell from 3 to 1.

        "รหัสที่รายงานใน STEP 3 ห้ามปรากฏในช่องคำตอบ" was read as a reason to
        stop rejecting rather than a reason to clear the column, so the model
        kept the doubtful codes as answers instead — core answered 119 against
        111 and precision fell from 61% to 54%.
        """
        from pathlib import Path

        for name in ("business.md", "support.md"):
            said = Path("prompts", name).read_text(encoding="utf-8")
            assert "ปัดตกให้มากเท่าที่ควรปัด" in said, name
            assert "STEP 3 ที่ยาวคือการทำงานที่ดี" in said, name
            assert "การเลี่ยงไม่ปัดตกเพื่อให้ STEP 3 สั้น คือการทำผิดที่หนักกว่า" in said, name


class TestAModelSOwnRejectionIsHonoured:
    """It writes ``ปัดตก [X]`` and leaves X in the column; the rules take it out.

    Two things made this hard to see. The heading is not a boundary — on
    100006 the rejection line sat above ``STEP 3``, so a check that read below
    the heading called the cell clean, twice. And the line names more than one
    code: ``ปัดตก [K4] เนื่องจาก…รวมอยู่ใน K1 แล้ว`` rejects K4 and keeps K1,
    so reading every code on the line reported five survivors as casualties.
    """

    def test_only_the_bracketed_code_counts_as_rejected(self):
        from lawscan.rules.categories import rejected_in

        assert rejected_in(
            "ปัดตก [K4] เนื่องจากโรงไฟฟ้านิวเคลียร์รวมอยู่ใน K1 แล้ว"
        ) == {"K4"}

    def test_a_rejection_anywhere_in_the_cell_is_found(self):
        from lawscan.rules.categories import rejected_in

        assert rejected_in(
            "STEP 1: …<br>ปัดตก [AB1] เนื่องจากเป็นผลกระทบทางอ้อม<br>STEP 2: …"
        ) == {"AB1"}

    def test_nothing_is_rejected_when_nothing_says_so(self):
        from lawscan.rules.categories import rejected_in

        assert rejected_in("[K4] นิวเคลียร์ : ทำ") == set()
        assert rejected_in("") == set()

    def test_the_last_run_honours_every_rejection(self):
        import csv
        import re
        from pathlib import Path

        from lawscan.rules.categories import rejected_in

        result = Path("out/v43/result.csv")
        if not result.exists():
            return
        code = re.compile(r"\b([A-Z]{1,2}\d{1,2})\b")
        core = "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
        support = ("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)")
        both = []
        with result.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                columns = set(code.findall(row.get(core) or ""))
                columns |= set(code.findall(row.get(support) or ""))
                said_no = rejected_in((row.get("AI ให้เหตุผล") or "").replace("<br>", "\n"))
                both += [(row["ชื่อไฟล์ "].strip(), c) for c in said_no & columns]
        assert not both, f"รหัสที่โมเดลปัดตกเองแต่ยังอยู่ในช่อง: {both[:8]}"


class TestTheDefaultModelIsOneThatAnswers:
    """A plain ``lawscan scan`` used to fail on every document.

    The default was an OpenAI model on an account with no credits, so a run
    without ``LAWSCAN_MODEL`` set returned a 429 for each call — silently, in
    the sense that it cost nothing and produced nothing. Every run this year
    passed the variable anyway; the default now matches what is passed.
    """

    def test_the_default_is_the_model_the_operator_chose(self):
        import os

        from lawscan.llm import client

        if os.environ.get("LAWSCAN_MODEL"):
            return  # the variable wins, which is the point of it
        assert client.MODEL == "gemini-3.1-flash-lite"

    def test_the_default_has_a_price_on_record(self):
        from lawscan.llm import client
        from lawscan.usage import PRICES

        assert client.MODEL in PRICES


class TestAnEmptyModelVariableFallsBackRatherThanBreaking:
    """``LAWSCAN_MODEL=`` is a shell saying "use the default", not a model name."""

    def test_an_empty_value_is_not_a_model(self, monkeypatch):
        import importlib

        from lawscan.llm import client

        monkeypatch.setenv("LAWSCAN_MODEL", "")
        assert importlib.reload(client).MODEL == "gemini-3.1-flash-lite"
        monkeypatch.delenv("LAWSCAN_MODEL")
        importlib.reload(client)

    def test_a_real_value_still_wins(self, monkeypatch):
        import importlib

        from lawscan.llm import client

        monkeypatch.setenv("LAWSCAN_MODEL", "gemini-2.5-pro")
        assert importlib.reload(client).MODEL == "gemini-2.5-pro"
        monkeypatch.delenv("LAWSCAN_MODEL")
        importlib.reload(client)


class TestTheNotifyQuestionIsGivenTheCodes:
    """Its prompt asks for codes it is forbidden to invent, and got none.

    ``notify.md`` reads "รหัสที่ต้องเขียนให้ คือรหัสในช่อง กฎหมายเฉพาะธุรกิจ และ
    กฎหมายสนับสนุน ที่ส่งมาให้พร้อมเอกสารนี้ ห้ามคิดรหัสขึ้นเอง" — and nothing
    in the pipeline sent them. The codes ride in the body rather than the
    instruction so the instruction stays identical across documents and stays
    cached.
    """

    def _row(self, core="", support=""):
        from lawscan.merge import Row

        row = Row(document="ทดสอบ")
        if core:
            row.put("กฎหมายเฉพาะธุรกิจ (Core Business Laws)", core, "llm")
        if support:
            row.put("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                    "(Support & General Compliance)", support, "llm")
        return row

    def test_both_columns_reach_the_question_with_their_names(self):
        from lawscan.pipeline import _preamble

        said = _preamble("notify", self._row("K4", "BW1"))
        assert "K4 = เทคโนโลยีนิวเคลียร์และรังสี" in said
        assert "BW1 = กฎหมายบัญชีและมาตรฐานการรายงานทางการเงิน" in said
        assert "ห้ามเพิ่ม ห้ามข้าม" in said

    def test_a_code_in_both_columns_is_listed_once(self):
        from lawscan.pipeline import _preamble

        assert _preamble("notify", self._row("CC4", "CC4")).count("CC4") == 1

    def test_a_document_with_no_codes_says_so(self):
        from lawscan.pipeline import _preamble

        assert _preamble("notify", self._row()) == "รหัสหมวดธุรกิจของเอกสารฉบับนี้: ไม่มี"

    def test_no_other_question_gets_a_preamble(self):
        from lawscan.pipeline import _preamble

        for q in ("business", "support", "summary", "identity", "parent", "audience"):
            assert _preamble(q, self._row("K4")) == "", q


class TestEveryCodeGetsAMessage:
    """Sixteen codes in, four messages out — until the schema required them.

    ``notify.md`` said "ห้ามข้ามรหัสใด" and the model skipped twelve of sixteen
    on 122839. Wording cannot fix a model that stops early; a required field
    per code can, because the omission no longer has a shape to be written in.
    """

    def test_the_schema_requires_one_field_per_code(self):
        from lawscan.llm.questions import notify_for

        q = notify_for(("CC18", "CC2", "CA3"))
        assert q.name == "notify"
        assert q.schema["required"] == ["CC18", "CC2", "CA3"]
        assert set(q.schema["properties"]) == {"CC18", "CC2", "CA3"}

    def test_the_answer_flattens_in_the_order_the_codes_came(self):
        from lawscan.pipeline import _alerts

        got = _alerts({"CC2": "[CC2]: สอง", "CC18": "[CC18]: หนึ่ง"}, ["CC18", "CC2"])
        assert got == {"alerts": ["[CC18]: หนึ่ง", "[CC2]: สอง"]}

    def test_an_answer_saved_before_the_schema_changed_still_rebuilds(self):
        from lawscan.pipeline import _alerts

        old = {"alerts": ["[CC2]: เดิม"]}
        assert _alerts(old, ["CC2"]) == old

    def test_an_empty_message_is_dropped_rather_than_written_blank(self):
        from lawscan.pipeline import _alerts

        assert _alerts({"CC2": "   ", "CC18": "[CC18]: มี"}, ["CC18", "CC2"]) == {
            "alerts": ["[CC18]: มี"]}

    def test_notify_declares_what_it_reads(self):
        from lawscan.llm.questions import NOTIFY

        assert NOTIFY.needs == ("business", "support")


class TestNoAlertOutlivesItsCode:
    """A message may not name a code the sheet does not carry.

    Two ways it happened on the 250-document run: the post-loop rejection sweep
    removes a code ``notify`` had already written about, and the model packs a
    second message into one code's field. Five of 790 messages, and each one
    would alert a follower about a law this document was found not to touch.
    """

    def _row(self, core, alerts):
        from lawscan.merge import Row

        row = Row(document="ทดสอบ")
        row.put("กฎหมายเฉพาะธุรกิจ (Core Business Laws)", core, "llm")
        row.put("ข้อความแจ้งเตือน (Smart Prompt)", alerts, "llm")
        return row

    def test_a_message_for_a_rejected_code_is_dropped(self):
        from lawscan.pipeline import _prune_alerts

        row = self._row("BT2", "[BT2]: อยู่, [CC17]: ถูกปัดตกไปแล้ว")
        _prune_alerts(row)
        assert row.value("ข้อความแจ้งเตือน (Smart Prompt)") == "[BT2]: อยู่"

    def test_a_second_message_packed_into_one_field_is_dropped(self):
        from lawscan.pipeline import _prune_alerts

        row = self._row("CC6", "[CC6]: หนึ่ง<br>[ ] ทำ, [CC17]: แถมมา")
        _prune_alerts(row)
        assert "CC17" not in row.value("ข้อความแจ้งเตือน (Smart Prompt)")
        assert "[ ] ทำ" in row.value("ข้อความแจ้งเตือน (Smart Prompt)")

    def test_an_exempted_tag_survives_the_prune(self):
        from lawscan.pipeline import _prune_alerts

        row = self._row("BT2", "[BT2[Exempted]]: ยกเว้น")
        _prune_alerts(row)
        assert row.value("ข้อความแจ้งเตือน (Smart Prompt)") == "[BT2[Exempted]]: ยกเว้น"

    def test_a_clean_column_is_left_exactly_as_written(self):
        from lawscan.pipeline import _prune_alerts

        said = "[BT2]: หนึ่ง, [CC6]: สอง"
        row = self._row("BT2, CC6", said)
        _prune_alerts(row)
        assert row.value("ข้อความแจ้งเตือน (Smart Prompt)") == said

    def test_a_document_whose_every_code_was_rejected_reads_empty(self):
        from lawscan.merge import Row
        from lawscan.pipeline import _prune_alerts

        row = Row(document="ทดสอบ")
        row.put("กฎหมายเฉพาะธุรกิจ (Core Business Laws)", "-", "rule:rejected")
        row.put("ข้อความแจ้งเตือน (Smart Prompt)", "[CC5]: ถูกปัดตกทั้งหมด", "llm")
        _prune_alerts(row)
        assert row.value("ข้อความแจ้งเตือน (Smart Prompt)") == ""
