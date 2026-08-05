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
    # A list, not a sentence, and no second field to put an answer in.
    #
    # Both halves of that were bugs. Asked for a string, the model wrote two
    # groups joined by "และ" — one cell that reads as a single group meeting
    # both conditions, when it is two groups meeting one each. And a ``roles``
    # field, described as supporting detail and filling no column at all, was
    # where a correctly identified third group went to be dropped: document
    # 100014's นิติบุคคลที่ประสงค์จะจัดการฝึกอบรม was found, listed under
    # roles, and never reached the CSV.
    #
    # One group per item, one place to put them.
    schema=_obj({"audience": _STRINGS}, ["audience"]),
)

#: Which businesses must know it. The expensive one — it carries the taxonomy.
BUSINESS = Question(
    name="business",
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

#: What it says and what to do about it.
SUMMARY = Question(
    name="summary",
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
