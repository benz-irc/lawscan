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


def test_the_guard_can_actually_see_a_leak():
    """A test that cannot fail is not a test."""
    known = answers()
    assert known, "ไม่มีไฟล์อ้างอิงให้ตรวจ"
    sample = next(iter(known))
    assert sample in f"ตัวอย่างเช่น {sample} ซึ่งเป็นคำตอบที่ถูก"
