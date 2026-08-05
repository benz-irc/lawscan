"""The five questions, and nothing else.

Each one exists because a group of columns needs the same reading of the
document and no more. Splitting further would pay for the document twice to
learn one extra field; merging any two would put a wrong answer in a place
nobody would think to look for it.

``fills`` on each question is the map from model output to spreadsheet column.
It is declared here and used by the merge step, so "which question filled this
cell" is answerable without reading the pipeline.
"""

from __future__ import annotations

from lawscan.llm.question import Question

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": {"type": "string"}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
        "additionalProperties": False,
    }


#: What the document is. Read from the first page and the closing block, so it
#: does not need the middle of a ninety-page act.
IDENTITY = Question(
    name="identity",
    fills=("ชื่อกฎหมาย", "ประเภทกฎหมาย", "หน่วยงานกำกับ", "องค์กรปกครองส่วนท้องถิ่น"),
    chars=6_000,
    schema=_obj(
        {
            "title": _STRING,
            "lawType": _STRING,
            "agencies": _STRINGS,
            "localGovernment": _STRING,
            "province": _STRING,
            "districts": _STRINGS,
        },
        ["title", "lawType"],
    ),
)

#: Which law empowers this one. Lives in the preamble; the rest of the document
#: does not mention it again.
PARENT = Question(
    name="parent",
    fills=("กฎหมายแม่",),
    chars=4_000,
    schema=_obj(
        {
            "parents": {
                "type": "array",
                "items": _obj(
                    {"law": _STRING, "section": _STRING, "evidence": _STRING},
                    ["law"],
                ),
            }
        },
        ["parents"],
    ),
)

#: Who it binds. Needs the operative clauses, so it gets the whole text.
AUDIENCE = Question(
    name="audience",
    fills=("กลุ่มเป้าหมาย",),
    # Both ways of writing the same reading, in one answer.
    #
    # ``merged`` joins closely-related groups with "และ", which is how the
    # reference file writes 14 of its 40. ``split`` gives one group per item,
    # which is what the operator asked for: "และ" reads as a single group
    # meeting both conditions when it is two groups meeting one each, and a
    # person opening the file cannot tell which one is theirs.
    #
    # Asking for both costs a few dozen output tokens and settles the question
    # with a measurement instead of a preference. Which one reaches the CSV is
    # chosen at run time; the other stays in the answer file, so switching is
    # a rebuild from saved answers and not another hour of model calls.
    #
    # There is deliberately no third field. A ``roles`` field once sat here,
    # described as supporting detail and filling no column, and it was where a
    # correctly identified group went to be dropped — document 100014 bound
    # three, the model found three, two reached the CSV.
    schema=_obj({"merged": _STRING, "split": _STRINGS}, ["merged", "split"]),
    # Who is bound is stated in the opening and confirmed by the closing
    # provisions; the schedule of addresses in between says nothing about it.
    chars=8_000,
    tail_chars=1_500,
)

#: Which businesses must know it. The expensive one — it carries the taxonomy.
BUSINESS = Question(
    name="business",
    chars=10_000,
    tail_chars=2_000,
    fills=(
        "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
        "AI ให้เหตุผล",
    ),
    schema=_obj(
        {
            "core": _STRINGS,
            "support": _STRINGS,
            "reasoning": _STRING,
            "confidence": {"type": "number"},
        },
        ["core", "support", "reasoning"],
    ),
)

#: What it says and what to do about it. The most expensive question in the
#: set — 32% of the bill — because it fills nine columns and writes the two
#: longest ones.
SUMMARY = Question(
    name="summary",
    chars=10_000,
    tail_chars=2_500,
    fills=(
        "คำอธิบายและสรุปสาระสำคัญ",
        "คำแนะนำสิ่งที่ต้องทำ ",
        "ใบอนุญาต",
        "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
        "ลิงค์เอกสารที่แนะนำ",
        "Activity_Tag",
        "Product_Group_Tag",
        "Legal_Keyword_Tag",
        "หมายเหตุ",
    ),
    schema=_obj(
        {
            "summary": _STRING,
            "actions": _STRING,
            "licenses": _STRINGS,
            "documents": _STRINGS,
            "documentLinks": _STRINGS,
            "activityTags": _STRINGS,
            "productGroupTags": _STRINGS,
            "legalKeywordTags": _STRINGS,
            "note": _STRING,
        },
        ["summary"],
    ),
)

ALL: tuple[Question, ...] = (IDENTITY, PARENT, AUDIENCE, BUSINESS, SUMMARY)
BY_NAME = {q.name: q for q in ALL}


def filled_by() -> dict[str, str]:
    """Column -> the question responsible for it."""
    return {column: q.name for q in ALL for column in q.fills}
