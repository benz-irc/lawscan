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

csv.field_size_limit(10**8)

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = ROOT / "data" / "expected.csv"
PROMPTS = sorted((ROOT / "prompts").glob("*.md"))

#: A value this long, appearing word for word, is not shared vocabulary.
TOO_LONG = 25

#: Columns whose values are prose the model has to compose. A leak here is a
#: worked answer; the same test on a column like ``ประเภทกฎหมาย``, whose whole
#: vocabulary is six words, would forbid naming the six words.
COMPOSED = {
    "กลุ่มเป้าหมาย",
    "ใบอนุญาต",
    "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
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
