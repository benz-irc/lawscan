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

from dataclasses import replace

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
    fills=(
        "หน่วยงานกำกับ",
        "องค์กรปกครองส่วนท้องถิ่น",
        "ยกเลิกกฎหมายอื่นทั้งฉบับ",
        "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
    ),
    chars=6_000,
    schema=_obj(
        {
            "agencies": _STRINGS,
            "localGovernment": _STRING,
            "repealsWhole": _STRING,
            "amends": _STRING,
        },
        ["agencies"],
    ),
)
# The two repeal columns arrived here because nothing else filled them. They
# were only ever in ``ONE``, the single-prompt path that is not in ``ALL``, so
# the five-question run left them empty on every document — including the five
# in twenty-one that print "ให้ยกเลิก" followed by a whole act's name. An empty
# cell that no code is trying to fill looks exactly like an empty cell that is
# correct, which is how this survived a corpus.
#
# They live with ``identity`` because they are read from the same few hundred
# words: the operative clauses at the top, beside the authority sentence.
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
    fills=("กฎหมายแม่", "กฎหมายที่อ้างถึง"),
    # The whole document, not the preamble: V17 13 says to scan "ทั้งฉบับ",
    # and a law cited in passing sits wherever the clause that cites it sits.
    chars=10_000,
    tail_chars=2_000,
    schema=_obj(
        {
            "parents": {
                "type": "array",
                "items": _obj(
                    {"law": _STRING, "section": _STRING, "evidence": _STRING},
                    ["law"],
                ),
            },
            # Laws this one points at without being made under. A separate
            # field rather than a flag on ``parents``, because the two are
            # decided by different questions — one asks what power was used,
            # the other asks what else was read.
            "referenced": _STRINGS,
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
        "AI ให้เหตุผล",
    ),
    # ``reasoning`` is first because a strict schema is generated in key order,
    # and the key order is the thinking order. With the codes first the model
    # committed to them before writing a word of analysis, and the analysis it
    # then wrote was a summary of an answer it already had: across twenty-two
    # documents 96 of the 167 codes in the two columns had no line explaining
    # them, and four documents filled the columns while explaining nothing.
    # Put the scratch work first and the codes are a consequence of it.
    # The scratch work and the per-code summary were one string, and one string
    # gets one budget: ``reasoning`` came back between 811 and 2,282 characters
    # whether the document had one code or seventeen. The scratch work is
    # written first and is mandatory, so it took the budget and the summary got
    # what was left — the four documents that summarised nothing at all are the
    # four with the longest scratch work. Documents with eight codes or more
    # averaged 3.2 summary lines; documents with six or fewer averaged 3.2 as
    # well. The number of lines never depended on the number of codes because
    # the two halves were competing for the same room. Two fields, two budgets.
    schema=_obj(
        {
            "analysis": _STRING,
            "reasoning": _STRING,
            "core": _STRINGS,
            "confidence": {"type": "number"},
        },
        ["analysis", "reasoning", "core"],
    ),
)


#: The support column, asked for on its own.
#:
#: It shared ``business`` for as long as the two columns existed, and shared
#: its budget with it: the codes for the businesses a law targets and the
#: codes for the back-office it touches were written in one pass, and the
#: second half was whatever room the first left. Every attempt to give the
#: support half more instruction inside that one prompt took the room from
#: somewhere else — a four-line list of examples cost the core column eight
#: points, and a three-term search procedure put the per-code summaries back
#: to fourteen percent unexplained after they had reached one.
#:
#: A sixth question costs about a baht per twenty-two documents. Two columns
#: that were competing for one answer's space now have one each.
SUPPORT = Question(
    name="support",
    chars=10_000,
    tail_chars=2_000,
    fills=(
        "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
    ),
    schema=_obj(
        {
            "analysis": _STRING,
            "reasoning": _STRING,
            "support": _STRINGS,
            "confidence": {"type": "number"},
        },
        ["analysis", "reasoning", "support"],
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
        "บทลงโทษ",
        "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
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
            # Asked of the model although a rule answers it, because the rule
            # can only read the words on the page and this column asks a
            # question the words do not always settle. ``Row.put`` keeps the
            # rule's answer wherever it has one, so this fills the cells the
            # rule left at a dash and nothing else.
            "penalty": _STRING,
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

#: Every column in one call, from the operator's own three prompts merged.
#:
#: The five questions above exist because each one needs a different reading of
#: the document and no more. This one exists because the operator asked for it
#: after being shown what it costs and what it risks, and because the cost
#: argument is real: 73% of the bill is output tokens, and five calls means the
#: model thinks about the same document five times.
#:
#: It asks for columns the rules already answer. That is deliberate and free:
#: ``Row.put`` refuses to let a model answer overwrite a rule answer, so the
#: model only reaches a cell the rules declined — the 130 documents whose title
#: no rule can read, and the three columns nothing fills yet.
#:
#: Not in ``ALL``. Reached with ``--only one``, so the five-question path stays
#: exactly as it is until there are numbers to compare.
ONE = Question(
    name="one",
    chars=10_000,
    tail_chars=2_500,
    fills=(
        "ชื่อกฎหมาย",
        "สถานะกฎหมาย",
        "ถูกยกเลิกโดยกฎหมายชื่อ",
        "ยกเลิกกฎหมายอื่นทั้งฉบับ",
        "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
        "วันที่ประกาศ",
        "เดือนที่ประกาศ",
        "ปีที่ประกาศ",
        "วันทีมีผลใช้บังคับ",
        "วันที่สิ้นผล",
        "ประเภทกฎหมาย",
        "กฎหมายแม่",
        "หน่วยงานกำกับ",
        "องค์กรปกครองส่วนท้องถิ่น",
        "อำเภอ",
        "จังหวัด",
        "ระดับวามเสี่ยง ",
        "บทลงโทษ",
        "ใบอนุญาต",
        "ข้อมูลแหล่งที่มา",
        "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
        "ลิงค์เอกสารที่แนะนำ",
        "กลุ่มเป้าหมาย",
        "Activity_Tag",
        "Product_Group_Tag",
        "Legal_Keyword_Tag",
        "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
        "AI ให้เหตุผล",
        "ระดับความมั่นใจ",
        "คำอธิบายและสรุปสาระสำคัญ",
        "คำแนะนำสิ่งที่ต้องทำ ",
        "หมายเหตุ",
    ),
    schema=_obj(
        {
            "title": _STRING,
            "status": _STRING,
            "repealedBy": _STRING,
            "repealsWhole": _STRING,
            "amends": _STRING,
            "publishDay": _STRING,
            "publishMonth": _STRING,
            "publishYear": _STRING,
            "effectiveDate": _STRING,
            "expiryDate": _STRING,
            "lawType": _STRING,
            "parents": {
                "type": "array",
                "items": _obj({"law": _STRING, "section": _STRING}, ["law"]),
            },
            "agencies": _STRINGS,
            "localGovernment": _STRING,
            "district": _STRING,
            "province": _STRING,
            "riskBand": _STRING,
            "penalty": _STRING,
            "licenses": _STRINGS,
            "source": _STRING,
            "documents": _STRINGS,
            "documentLinks": _STRINGS,
            "audience": _STRINGS,
            "activityTags": _STRINGS,
            "productGroupTags": _STRINGS,
            "legalKeywordTags": _STRINGS,
            "core": _STRINGS,
            "support": _STRINGS,
            "reasoning": _STRING,
            "confidence": {"type": "number"},
            "summary": _STRING,
            "actions": _STRING,
            "note": _STRING,
        },
        ["title", "lawType", "summary"],
    ),
)

#: The operator's V15 sheet — the same three prompts, revised, with the struck
#: paragraphs taken out — merged into one prompt the way ``ONE`` was.
#:
#: It carries ``ONE``'s schema and ``ONE``'s columns unchanged, on purpose: run
#: one against the other and the only thing that differs is the wording of the
#: instruction, so the difference in the score is the wording and nothing else.
#:
#: Not in ``ALL`` either. Reached with ``--only v15``.
V15 = replace(ONE, name="v15")

#: The same again, one revision on. Wired rather than left as a file in the
#: folder: ``prompts/v16.md`` was reachable by nothing, which reads as a prompt
#: in use until someone greps for it.
V16 = replace(ONE, name="v16")

#: Column 34 — one notification message per V8 code, for the alert screen
#: rather than for the sheet.
#:
#: Deliberately outside ``ALL``. The operator's own note on it reads
#: "รันเฉพาะตอนเทสแจ้งเตือน ไม่รันทั้งหมด", and the cost says the same: it writes
#: a message for every code a document carries, and the corpus averages five,
#: so a full run of it is five prose answers per document on top of everything
#: else. Reached with ``--only notify``.
NOTIFY = Question(
    name="notify",
    fills=("ข้อความแจ้งเตือน (Smart Prompt)",),
    schema=_obj({"alerts": _STRINGS}, ["alerts"]),
    # The message is written from the codes and the gist, not from the whole
    # instrument: what a reader needs is the condition and the first steps.
    chars=8_000,
    tail_chars=1_000,
    needs=("business", "support"),
)

def notify_for(codes: tuple[str, ...]) -> Question:
    """``NOTIFY`` with a schema that has one required field per code.

    Asking for a list and saying "ห้ามข้ามรหัสใด" does not work: on a document
    carrying sixteen codes the model wrote four and stopped. A required key per
    code makes the omission impossible to express — the answer either carries
    every code or fails validation and is asked again.
    """
    return replace(NOTIFY, schema=_obj({code: _STRING for code in codes}, list(codes)))


ALL: tuple[Question, ...] = (IDENTITY, PARENT, AUDIENCE, BUSINESS, SUPPORT, SUMMARY)
BY_NAME = {q.name: q for q in (*ALL, ONE, V15, V16, NOTIFY)}


def filled_by() -> dict[str, str]:
    """Column -> the question responsible for it."""
    return {column: q.name for q in ALL for column in q.fills}
