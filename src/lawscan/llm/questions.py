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
    fills=("หน่วยงานกำกับ", "องค์กรปกครองส่วนท้องถิ่น"),
    chars=6_000,
    schema=_obj(
        {
            "agencies": _STRINGS,
            "localGovernment": _STRING,
        },
        ["agencies"],
    ),
)
# Four fields used to be asked here and are not any more, because the rules
# answer them and ``Row.put`` discarded every model answer for them anyway —
# the corpus was paying for four cells per document that nothing read.
#
#   title      rules/title.py  94.2% against the model's 90.0%
#   lawType    rules/kind.py   97%, and beat the model on 299 of 300
#   province   rules/places.py won 240/240
#   districts  rules/places.py won 240/240
#
# Only ``title`` cost anything to remove: the rule stays silent on 6 of the
# 240 and the model was right about 2 of those, so the column goes from 95.0%
# to 94.2%. The other three were free.

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
    # One field, because one of them reaches the CSV.
    #
    # A ``merged`` field sat beside this one, joining closely-related groups
    # with "และ" the way the reference file writes 14 of its 40. It was asked
    # for so the two could be scored against each other rather than argued
    # about; the argument is over. "และ" reads as a single group meeting both
    # conditions when it is two groups meeting one each, and a person opening
    # the file cannot tell which one is theirs — so ``split`` is the answer,
    # and ``merged`` was 4.0% of the run's output tokens, produced on every
    # document and discarded on every document.
    #
    # There is deliberately no third field. A ``roles`` field once sat here,
    # described as supporting detail and filling no column, and it was where a
    # correctly identified group went to be dropped — document 100014 bound
    # three, the model found three, two reached the CSV.
    schema=_obj({"split": _STRINGS}, ["split"]),
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
