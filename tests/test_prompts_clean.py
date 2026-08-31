"""No prompt may contain an answer from the reference file.

This test exists because the prompts did. Working on the audience column, the
way to make the low-similarity band disappear was to put the operator's own
answers into the instruction as examples — and it worked, and the number moved
from 17 documents in the bad band to 6, and none of that was a measurement.
Fourteen of the forty documents were being answered by copying.

A prompt may use the vocabulary of Thai law. ``พระราชกฤษฎีกา`` and
``กรุงเทพมหานคร`` appear in the reference file and in any honest instruction
about Thai legal documents, and treating those as leaks would forbid writing
the prompt at all. What it may not contain is a *composed answer*: a full cell
value long enough, or listed enough, that it cannot have arrived by coincidence.
"""

import csv
import re
from pathlib import Path

import pytest

from lawscan.export.columns import COLUMNS

csv.field_size_limit(10**8)

ROOT = Path(__file__).resolve().parent.parent
#: The reference lives outside data/ so no prompt can draw from it. This
#: test needs it, and pointing at the old place silently disarmed nine checks
#: the moment the file moved — a leak guard that skips is worse than none.
EXPECTED = ROOT / "reference" / "expected.csv"
PROMPTS = sorted((ROOT / "prompts").glob("*.md"))

#: A value this long, appearing word for word, is not shared vocabulary.
TOO_LONG = 25

#: And one item out of a list this long is not shared vocabulary either.
#: Lower than ``TOO_LONG`` because an item is one group, not a whole cell.
#:
#: Twenty rather than sixteen, and the four characters were paid for: at
#: sixteen the guard fires on ``ขอรับหนังสือรับรอง`` and ``พนักงานเจ้าหน้าที่``,
#: which are ordinary Thai that any prompt about permits has to be able to
#: say. At twenty it still catches a named trade or a named right, which is
#: what a leak looks like.
DISTINCTIVE = 20

#: Where an item on its own is checked. These three name a party or a right —
#: things the model can only get from the document or from being told, so one
#: of them sitting in a prompt is a worked answer.
#:
#: The tag and keyword columns are left out on purpose. They share their
#: vocabulary with the taxonomy and with the category table ``parent.md`` ships
#: as its own fallback answers, so item-level matching there fires on the
#: prompt doing its job — ``ระเบียบบริหารราชการแผ่นดิน`` is a category this
#: repository assigns, and also, unavoidably, the name of a real act.
#: Column headings, which every prompt names and no prompt may be faulted for.
HEADINGS = {c.strip() for c in COLUMNS}

ITEMWISE = {
    "กลุ่มเป้าหมาย",
    "ใบอนุญาต",
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
}

#: Columns whose values are prose the model has to compose. A leak here is a
#: worked answer; the same test on a column like ``ประเภทกฎหมาย``, whose whole
#: vocabulary is six words, would forbid naming the six words.
COMPOSED = {
    "กลุ่มเป้าหมาย",
    "ใบอนุญาต",
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
    "Activity_Tag",
    "Product_Group_Tag",
    "Legal_Keyword_Tag",
    "คำอธิบายและสรุปสาระสำคัญ",
    "คำแนะนำสิ่งที่ต้องทำ ",
    "AI ให้เหตุผล",
    "หน่วยงานกำกับ",
    "ชื่อกฎหมาย",
    "กฎหมายแม่",
}


def answers() -> dict[str, tuple[str, str]]:
    """Composed answers from the reference file, by value."""
    if not EXPECTED.exists():
        return {}
    found: dict[str, tuple[str, str]] = {}
    with EXPECTED.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            document = row.get("ชื่อไฟล์ ", "").strip().replace(".0", "")
            for column in COMPOSED:
                value = " ".join((row.get(column) or "").split()).strip()
                if value in ("", "-"):
                    continue
                if len(value) > TOO_LONG or "," in value:
                    found[value] = (document, column.strip())
                # And each item on its own. A cell listing several groups
                # leaks just as badly one group at a time, and the whole-cell
                # test could not see it: an example naming two of the groups a
                # document's row happens to hold sat in the audience prompt for
                # weeks, because the row wrote them with a space between and
                # the guard was looking for the pair.
                if column in ITEMWISE:
                    # Split on spaces as well as commas. The row this guard
                    # was written for writes its two groups with a space
                    # between them, so a comma-only split saw one item forty
                    # characters long and never looked inside it — while the
                    # prompt held one of the two, word for word.
                    for item in re.split(r"[,·\s]+", value):
                        item = item.strip()
                        # A column's own name is not a leak. One row answers
                        # ``องค์กรปกครองส่วนท้องถิ่น`` and that is also the
                        # heading of a column every prompt has to be able to
                        # name.
                        if len(item) >= DISTINCTIVE and item not in HEADINGS:
                            found.setdefault(item, (document, column.strip()))
    return found


#: The reference file is the operator's own work and is not in this repository.
#: Without it there is nothing to leak and nothing to check, and the honest
#: outcome is a skip that says so — not a pass, which would read as "the
#: prompts were checked and are clean".
needs_reference = pytest.mark.skipif(
    not EXPECTED.exists(),
    reason=f"ไม่มี {EXPECTED} — ตรวจเฉลยที่หลุดเข้าพรอมป์ไม่ได้",
)


@needs_reference
@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_no_reference_answer_appears(prompt):
    text = " ".join(prompt.read_text(encoding="utf-8").split())
    leaked = [
        f"{document} [{column}] {value}"
        for value, (document, column) in answers().items()
        if value in text
    ]
    assert not leaked, (
        f"{prompt.name} มีคำตอบจากไฟล์อ้างอิง {len(leaked)} ค่า — "
        "ตัวเลขที่วัดได้จะไม่ใช่การวัด:\n  " + "\n  ".join(leaked[:10])
    )


@needs_reference
def test_the_guard_can_actually_see_a_leak():
    """A test that cannot fail is not a test."""
    known = answers()
    assert known, f"{EXPECTED} มีอยู่แต่อ่านคำตอบออกมาไม่ได้"
    sample = next(iter(known))
    assert sample in f"ตัวอย่างเช่น {sample} ซึ่งเป็นคำตอบที่ถูก"


#: Counting the reference answers and writing the count into the instruction
#: leaks the same thing a pasted answer does, one step removed: it tells the
#: model how the scored set is distributed. "core is empty 29 of 40 times"
#: moves the number without improving the reading, and the number then stops
#: being a measurement of anything.
STATISTIC = re.compile(
    r"(ชุดอ้างอิง|ที่มีเฉลย|ไฟล์เฉลย)[^\n]{0,40}\d"
    r"|\d+\s*(จาก|ใน)\s*\d+\s*ฉบับ"
    r"|ว่าง\s*\d+\s*ฉบับ"
)


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_no_reference_statistic_appears(prompt):
    found = STATISTIC.findall(prompt.read_text(encoding="utf-8"))
    assert not found, (
        f"{prompt.name} อ้างสถิติที่นับจากไฟล์เฉลย — "
        "คะแนนที่ได้จะมาจากการรู้การกระจายตัว ไม่ใช่การอ่านเอกสาร"
    )


def test_the_statistic_guard_can_actually_see_one():
    """A test that cannot fail is not a test."""
    assert STATISTIC.search("ในชุดอ้างอิง 29 จาก 40 ฉบับมี core ว่าง")
    assert not STATISTIC.search("ตอบ 2 ถึง 3 รหัส ตามที่เอกสารเขียน")


#: An example a model can lift straight into a cell. What separates the ones
#: that were copied from the ones that were not is whether the example names
#: something real: ``ใบอนุญาตให้ประกอบกิจการ`` fits any document and 30 of 240
#: came back with it, while ``กรม ก.`` fits none and was never copied.
#:
#: So an example naming an instrument must name one that does not exist. All
#: four of these were checked against the whole 3,424-document corpus and
#: appear in none of it.
INVENTED = ("ทดสอบระบบ", "ทดสอบอาคาร", "ทดสอบแร่", "ทดสอบผลิตภัณฑ์")

#: A named act inside a prompt, with the year that makes it an act rather than
#: a phrase.
_NAMED_ACT = re.compile(
    r"(?:พระราชบัญญัติ|พระราชกำหนด|พระราชกฤษฎีกา|กฎกระทรวง)\s?[ก-๙]{2,30}\s*"
    r"(?:พ\.ศ\.|พุทธศักราช)\s*[\d๐-๙]{4}"
)


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_no_example_names_a_real_instrument(prompt):
    """A worked example must not be usable as an answer.

    Four prompts taught by example and all four were obeyed too literally: the
    tag columns came back wearing the angle brackets the examples were drawn
    in, summaries cited sections because an example did, the reasoning column
    abbreviated ``มาตรา`` to ``ม.`` because an example did, and the licence
    column returned the five kinds the prompt lists, in that order, on 30
    documents. An example that names a real act invites the same.
    """
    named = _NAMED_ACT.findall(prompt.read_text(encoding="utf-8"))
    real = [n for n in named if not any(mark in n for mark in INVENTED)]
    assert not real, (
        f"{prompt.name} ยกชื่อกฎหมายจริงมาเป็นตัวอย่าง: {real} — "
        "ใช้ชื่อสมมติที่ไม่มีในคลัง เพื่อไม่ให้ลอกไปเป็นคำตอบได้"
    )


def test_no_tag_vocabulary_is_shipped_to_the_model():
    """A list of the database's own tag names was tried, and cost more than it paid.

    The idea was sound on paper: the operator reuses their own vocabulary, and
    a little over half the tags on any new document have been written before,
    so a register of the terms already in the database — built only from
    documents the score never looks at — should let the model land on the
    spelling that is already there instead of inventing a synonym.

    Measured on the 240, it moved ``Activity_Tag`` from 28.5% to 15.9% and
    ``Product_Group_Tag`` from 37.0% to 31.0%. The register stopped being a
    hint and became a menu: the share of answers lifted from it went from 30%
    to 79%, and what came back was the shortest entry that fit — ``ตรวจสอบ``
    and ``อายัด`` where the page says ``ตรวจสอบทรัพย์สิน`` and
    ``อายัดทรัพย์สิน``. A model given a list of acceptable answers stops
    reading the document and starts satisfying the list.

    So there is no ``data/tags.txt``, and this is the test that says why. The
    lists that remain — the taxonomy and the register of regulators — are
    different in kind: their entries are codes and official names that the
    answer must match exactly, not phrases the document is supposed to supply.
    """
    from pathlib import Path

    assert not Path("data/tags.txt").exists(), (
        "data/tags.txt กลับมาแล้ว — วัดครั้งก่อนมันทำให้ Activity_Tag ตกจาก 28.5% เหลือ 15.9% "
        "ถ้าจะลองใหม่ ให้วัดทั้ง 240 ฉบับก่อนเก็บไว้"
    )


class TestSuggestNewSurvivesTheCodeFilter:
    """The one answer V16 allows that is not a code.

    The filter keeps only codes the register defines, which is right for the
    prose the model sometimes writes into these columns and wrong for
    ``[SUGGEST_NEW]``. That is the answer to a real question — the business is
    there and the register has no name for it — and dropping it left the cell
    blank, which reads as "nothing found" rather than "nothing fits".
    """

    def test_it_is_kept(self):
        from lawscan.rules.categories import codes_in

        assert codes_in("[SUGGEST_NEW]") == ["[SUGGEST_NEW]"]
        assert codes_in("SUGGEST_NEW") == ["[SUGGEST_NEW]"]

    def test_a_real_code_is_still_kept(self):
        from lawscan.rules.categories import codes_in

        assert "CC24" in codes_in("CC24 วินัยการเงินการคลังภาครัฐ")

    def test_an_invented_code_is_still_dropped(self):
        from lawscan.rules.categories import codes_in

        assert codes_in("ZZ99") == []


class TestTheAnswerKeyCannotReachTheModel:
    """The reference file lives outside every folder a prompt can draw from.

    ``Client.lists`` fills a ``{{name}}`` placeholder from ``data/<name>.txt``,
    and the reference used to sit in that same folder. Nothing was leaking —
    the loader takes ``.txt`` and the file is ``.csv`` — but a rename or a new
    loader would have been enough, and the guard was a file extension. It now
    lives in ``reference/``, which nothing in the sending path reads.
    """

    def test_the_reference_is_not_in_the_prompt_data_folder(self):
        from pathlib import Path

        assert not Path("data/expected.csv").exists(), (
            "ไฟล์เฉลยกลับเข้าไปอยู่ใน data/ ซึ่งเป็นโฟลเดอร์ที่ prompt ดึงไปเติม"
        )
        assert Path("reference/expected.csv").exists()

    def test_nothing_a_prompt_can_load_holds_reference_answers(self):
        import csv
        from pathlib import Path

        reference = Path("reference/expected.csv")
        if not reference.exists():
            pytest.skip("ไม่มีไฟล์อ้างอิงบนเครื่องนี้")
        with reference.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        # Long free-text answers: distinctive enough that a match is a leak.
        answers = {
            (r.get("คำอธิบายและสรุปสาระสำคัญ") or "").strip()
            for r in rows
        } - {""}
        answers = {a for a in answers if len(a) > 80}
        loadable = "\n".join(
            p.read_text(encoding="utf-8") for p in Path("data").glob("*.txt")
        ) + "\n".join(p.read_text(encoding="utf-8") for p in Path("prompts").glob("*.md"))
        leaked = sorted(a for a in answers if a in loadable)
        assert not leaked, f"คำตอบจากไฟล์เฉลยโผล่ในสิ่งที่ส่งให้โมเดล: {leaked[:1]}"


#: What the operator's registers legitimately contain, counted against both
#: answer files. Ministry names, department names and business-category names
#: are in the sheet *and* in the registers the operator supplied, and always
#: were — so a match is not by itself a leak. The number is.
#:
#: Raised only when a register genuinely grows for a reason that has nothing to
#: do with the answers, and the commit that raises it has to say so.
CONTACT = 1217


def _payload() -> str:
    """Every character that reaches the model, prompts and registers alike.

    The old guard read ``data/*.txt`` and stopped there, which is how two
    initialisms copied out of the answer sheet reached ``data/agencies.json``
    and were sent with every request for a day without anything noticing. The
    file is JSON, so the glob never saw it.
    """
    files = [*sorted(Path("data").glob("*.txt")),
             *sorted(Path("data").glob("*.json")),
             *sorted(Path("prompts").rglob("*.md"))]
    return re.sub(r"\s+", "", "\n".join(
        p.read_text(encoding="utf-8") for p in files))


def test_no_new_answer_text_reaches_the_model():
    """The count of answer strings reachable in the payload may not grow.

    A rule learned by measuring against the answers is allowed — the operator
    asks for it. Copying a *value* out of them is not, and the two are easy to
    confuse when the thing measured happens to be a value. This counts instead
    of forbidding: everything already matched stays matched, and the moment a
    register gains a string the sheet contains, the number moves and the test
    says so.
    """
    payload = _payload()
    seen = 0
    for ref in (ROOT / "reference/expected.csv", ROOT / "reference/expected22.csv"):
        if not ref.exists():
            continue
        with ref.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                for cell in row.values():
                    for item in re.split(r"[,·;|\n]+", cell or ""):
                        item = item.strip()
                        if len(item) >= 12 and re.sub(r"\s+", "", item) in payload:
                            seen += 1
    assert seen <= CONTACT, (
        f"ข้อความจากไฟล์เฉลยโผล่ในสิ่งที่ส่งให้โมเดลเพิ่มขึ้น {seen - CONTACT} ชิ้น "
        f"(เดิม {CONTACT}) — มีค่าจากเฉลยถูกคัดเข้า data/ หรือ prompts/ หรือไม่")


class TestNoRegisterNameIsWrittenIntoAPrompt:
    """A category name in the instruction is a candidate answer in disguise.

    The register is already sent to the model as data; naming one of its
    categories in the instruction as well turns that name into a shortlist.
    It cost a real answer: a four-item list of state-side category names was
    added to ``business.md`` as an illustration, and on 100001 the model took
    the fourth item off the list — ``CC28 องค์การมหาชน`` — for an ombudsman's
    office that the agency register files under ``องค์กรอิสระ``. The run
    before, with no list to pick from, had read the document and answered
    ``BY1``.

    The names had also been chosen right after reading the operator's answers,
    which is the leak the rule against answers in the prompt exists to stop —
    a leak this file's other guard cannot see, because the strings are
    register text rather than answer text.
    """

    def test_no_prompt_the_flow_sends_names_a_category(self):
        import re
        from pathlib import Path

        names = {}
        for path in list(Path("data").glob("*.txt")) + list(Path("data").glob("*.json")):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"\b([A-Z]{1,2}\d{1,2})\s*(?:\[[A-Z]+\])?\s*=\s*([^\n\",\\]+)", text):
                name = re.sub(r"\s*\[[A-Z]+\]\s*$", "", m.group(2)).strip()
                # Twelve, the same length the answer-leak guard beside this one
                # uses, and for the same reason: shorter than that and a
                # category name is an ordinary Thai noun the instruction may
                # legitimately need — ``การส่งเสริม`` is both a register entry
                # and the plain word for promotion. Names of twelve characters
                # or more are specific enough that writing one is a choice.
                if len(name) >= 12:
                    names[name] = m.group(1)
        assert names, "อ่านทะเบียนไม่ได้ — เทสต์นี้จะผ่านโดยไม่ตรวจอะไรเลย"

        # The five the pipeline sends, plus the notification prompt. The
        # operator's own prompts kept under ``prompts/`` are theirs as written.
        sent = ("business.md", "identity.md", "parent.md", "audience.md",
                "summary.md", "notify.md")
        found = [
            f"{f} · {names[name]} = {name}"
            for f in sent
            for name in names
            if name in Path("prompts", f).read_text(encoding="utf-8")
        ]
        assert not found, (
            "ชื่อหมวดจากทะเบียนโผล่ในคำสั่ง — โมเดลจะหยิบจากรายการแทนที่จะเปิดอ่าน:\n  "
            + "\n  ".join(found)
        )


class TestEveryPromptIsReachable:
    """A prompt file nothing loads reads as a prompt in use.

    ``prompts/v16.md`` sat beside ``v15.md`` for weeks with no question behind
    it, so anyone reading the folder would have taken it for the live version.
    """

    def test_every_prompt_file_has_a_question(self):
        from pathlib import Path

        from lawscan.llm.questions import BY_NAME

        folder = Path(__file__).resolve().parent.parent / "prompts"
        loose = sorted(p.stem for p in folder.glob("*.md") if p.stem not in BY_NAME)
        assert loose == [], f"prompt ที่ไม่มีคำถามโหลด: {loose}"

    def test_every_question_has_a_prompt_file(self):
        from lawscan.llm.questions import BY_NAME

        missing = sorted(name for name, q in BY_NAME.items() if not q.path.exists())
        assert missing == [], f"คำถามที่ไม่มีไฟล์ prompt: {missing}"


class TestTheDocumentedDefaultIsTheRealOne:
    """Two files named a model the code does not use.

    ``.env.example`` and the README are the first things a person reads, and a
    wrong model name there sends the first run to the wrong provider — which
    fails as a quota error, not as a typo.
    """

    def test_the_env_example_names_the_model_the_client_falls_back_to(self):
        from pathlib import Path

        from lawscan.llm.client import FALLBACK_MODEL

        root = Path(__file__).resolve().parent.parent
        for name in (".env.example", "README.md"):
            said = (root / name).read_text(encoding="utf-8")
            assert FALLBACK_MODEL in said, f"{name} ไม่ได้พูดถึง {FALLBACK_MODEL}"
