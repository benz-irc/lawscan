"""One document from PDF to a row, and every document to a CSV.

The order here is the whole design in eight lines: read, then rules, then the
model, then merge. Rules run first so that ``Row.put`` can refuse to let a
model answer overwrite one — precedence is a property of the sequence, not a
condition scattered through the code.

Each document leaves a folder behind under the work directory: the text that
was read, every raw answer, what the rules found, and where each cell came
from. That folder is the answer to "why is this cell wrong", and it costs
nothing to keep.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from lawscan.export.columns import COLUMNS, NONE_IS_AN_ANSWER, write_csv
from lawscan.llm.client import ENV_FILE, Client, key_is_available, key_names
from lawscan.llm.question import Question
from lawscan.llm.questions import ALL, BY_NAME
from lawscan import confidence, progress
from lawscan.answers import (
    irrigation_activities, irrigation_agencies, irrigation_users,
    local_body_of, named_in, once_each,
)
from lawscan.audience import tidy
from lawscan.merge import NOTHING, Row
from lawscan.ocr.read import Document, load, read
from lawscan.rules import BANDS, PENALTY_TEXT, categories, penalties, run_all
from lawscan.rules import agencies as agency_rule
from lawscan.rules import parent as parent_rule

log = logging.getLogger(__name__)


def _grouped_work(work, position: int, path: Path) -> Row | None:
    """One document's worth of log lines, printed as one block.

    Ten documents in flight would otherwise interleave their steps and the log
    would be a list of facts with nothing to attach them to.
    """
    with progress.grouped():
        return work(position, path)


def done_before(
    roots: list[Path], wanted: tuple[str, ...], *, exclude: Path | None = None
) -> dict[str, Path]:
    """Documents some earlier run already answered, newest run first.

    A run of 240 documents is long enough that it will be interrupted, and
    every interruption that throws away finished work costs real money to
    redo. This looks across the kept runs under ``tests/`` and reports which
    documents already have a complete set of answers and where they are.

    Completeness is per document and per question: a folder that has four of
    the five answers is not done, and re-asking one question is much cheaper
    than being wrong about what is on disk.

    ``exclude`` is this run's own folder, and leaving it out is not a detail.
    A second run started inside the same minute lands on the same stamp, finds
    the first run's answers under its own output path, and tries to copy every
    file onto itself — which raises, and a raise per document is a CSV with a
    header and no rows. That is exactly how it failed the first time.
    """
    index: dict[str, Path] = {}
    skip = exclude.resolve() if exclude else None
    for root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(root.glob("result40-*/documents/*"), reverse=True):
            number = folder.name
            if number in index or not folder.is_dir():
                continue
            if skip is not None and folder.resolve().parent == skip:
                continue
            if all(_saved(folder, question) is not None for question in wanted):
                index[number] = folder
    return index


def _saved(here: Path, question: str) -> dict | None:
    """An answer this document already has on disk, if it succeeded.

    Rules change far more often than prompts do, and re-asking the model to
    measure a change in a regular expression is both slow and a waste of the
    operator's money. Every answer is already written down; this reads it back
    so the deterministic half can be re-measured for nothing.
    """
    path = here / f"{question}.json"
    if not path.exists():
        return None
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return stored.get("value") if stored.get("ok") else None


def _answered_by_rules(question: Question, found: dict[str, str]) -> bool:
    """True when the rules already filled every column this question fills.

    The test is what the rules wrote, not whether the answer is any good — a
    rule only writes a column it read successfully, and where it did, the
    model's answer to the same question is discarded on arrival. Paying for a
    discarded answer is the whole of what this prevents.

    A dash counts. ``-`` from a rule is an answer — this document has none of
    this — and the columns where that is a fact about the law rather than a gap
    are exactly the columns the rules write a dash into.

    Questions that fill many columns are never skipped by this, which is the
    intended shape: ``summary`` fills nine and the rules reach one of them.
    """
    return bool(question.fills) and all(column in found for column in question.fills)


def one(path: Path, client: Client | None, workdir: Path, *, no_ocr: bool = False,
        only: tuple[str, ...] | None = None, reuse: bool = False,
        borrow: Path | None = None, text_from: Path | None = None) -> Row:
    """PDF in, one row out, with everything it took written down.

    ``text_from`` is a folder of text ``lawscan ocr`` already extracted. The
    result is identical — extraction is deterministic — and the difference is
    seconds per document against none, which is what makes it reasonable to
    re-run the rules over and over while working on them.
    """
    with progress.timed("อ่าน", "แฟ้มข้อความ" if text_from else "pymupdf") as said:
        document = _text_of(path, text_from) if text_from else read(path, ocr=not no_ocr)
        layer = sum(1 for p in document.pages if p.source == "text-layer")
        lost = document.unread_pages
        said.append(
            f"{len(document.pages)} หน้า · text-layer {layer} · ocr {document.scanned_pages}"
            f" · {len(document.text()):,} ตัวอักษร"
            + (f" · ⚠ {len(lost)} หน้าเป็นภาพ" if lost else "")
        )
    here = workdir / document.number
    here.mkdir(parents=True, exist_ok=True)
    (here / "text.txt").write_text(document.text(), encoding="utf-8")

    row = Row(document=document.number)

    # Rules first, so nothing the model says can displace them.
    with progress.timed("กฎ", "lawscan.rules") as said:
        found = run_all(document)
        filled = [k for k in found if not k.startswith("_")]
        said.append(
            f"{len(filled)} ช่อง · {found.get('ประเภทกฎหมาย', '—')}"
            f" · {found.get('ระดับวามเสี่ยง ', '—')}"
            f" · จ.{found.get('จังหวัด', '—')}"
        )
    (here / "rules.json").write_text(
        json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for column, value in found.items():
        if not column.startswith("_"):
            row.put(column, value, "rule")

    # No client means the deterministic half on its own — which is worth
    # measuring, because it is the half that costs nothing and the half whose
    # mistakes are fixable by reading code rather than by rewording a prompt.
    questions = [] if client is None else [BY_NAME[n] for n in only] if only else list(ALL)
    # A question whose every column the rules already filled has nothing left
    # to say: ``Row.put`` would discard its answer on arrival, so the call is
    # paid for, written to disk, and thrown away. Two fire on this corpus —
    # ``parent`` on the seventeen court documents, which are not made under an
    # act, and ``audience`` wherever the court's own jurisdiction is the answer.
    #
    # Asking anyway is the failure this replaces, and it is invisible: the CSV
    # is identical either way, so nothing but the bill shows it happened.
    skipped = [q for q in questions if _answered_by_rules(q, found)]
    questions = [q for q in questions if q not in skipped]
    for question in skipped:
        progress.step(question.name, "ข้าม", "กฎตอบครบทุกช่องแล้ว ไม่ต้องเรียกโมเดล")
    spend = 0.0
    for question in questions:
        saved = _saved(here, question.name) if reuse else None
        if saved is None and borrow is not None:
            # An answer this document already has from an earlier run. Copied
            # into this run's folder as it is used, so the folder stays a
            # complete record of the run rather than a partial one that only
            # makes sense next to its predecessor.
            saved = _saved(borrow, question.name)
            if saved is not None and borrow.resolve() != here.resolve():
                shutil.copy(borrow / f"{question.name}.json", here / f"{question.name}.json")
        if saved is not None:
            progress.step(question.name, "ของเดิม", "ใช้คำตอบที่บันทึกไว้ ไม่เรียกโมเดล")
            value = saved
        else:
            with progress.timed(question.name, client.model.split("-preview")[0]) as said:
                answer = client.ask(question, document)
                answer.write(here)
                spend += answer.billed_input + answer.output_tokens
                said.append(
                    f"เข้า {answer.input_tokens:,} (cache {answer.cached_tokens:,})"
                    f" · ออก {answer.output_tokens:,}"
                    if answer.ok else f"ล้ม: {answer.error}"
                )
            if not answer.ok:
                continue
            value = answer.value
        if question.name == "business":
            # The document's own statement about itself outranks the model's
            # reading of it, here as everywhere else.
            value = dict(value)
            value["core"], value["support"] = categories.correct(
                document.text(), value.get("core") or [], value.get("support") or []
            )
        _apply(row, question.name, value, document)

    # One rule reads a judgment differently from a law, so it wants the type.
    # It used to come from the model's first answer; the type is now a rule of
    # its own and beat the model on 299 of 300 documents, so the second pass
    # reads what the first pass already wrote.
    law_type = row.value("ประเภทกฎหมาย")
    if law_type:
        apply_rules(row, run_all(document, law_type=law_type))

    # Where the penalty lives can only be decided once the business codes are
    # in, because "binds a business" is what separates a document waiting on
    # its parent act from an internal one that simply has no penalty. The same
    # answer settles the other question the phrase lists cannot: an instrument
    # that reads as guidance and binds no business is government housekeeping,
    # whatever words it happens to use.
    band = found.get("_แถบสี", "").split(" · ")[0]
    core = row.value("กฎหมายเฉพาะธุรกิจ (Core Business Laws)")
    if penalties.is_housekeeping(band, core):
        for column, value in (
            ("ระดับวามเสี่ยง ", BANDS["BLUE"]),
            ("บทลงโทษ", PENALTY_TEXT["BLUE"]),
        ):
            row.cells.pop(column, None)
            row.put(column, value, "rule:housekeeping")
    if penalties.links_to_parent(
        band=band,
        parent=row.value("กฎหมายแม่"),
        core=core,
        title=row.value("ชื่อกฎหมาย"),
        amending=penalties.amends(document.text()),
    ):
        for column, value in (
            ("ระดับวามเสี่ยง ", penalties.LINKED_BAND),
            ("บทลงโทษ", penalties.link_text(row.value("กฎหมายแม่"))),
        ):
            if value:
                row.cells.pop(column, None)
                row.put(column, value, "rule:linked")

    # Confidence last, once every column has whatever it is going to have.
    # It is computed rather than asked for: the model returned 0.8 or higher
    # on all 91 documents, including one that had lost twelve pages.
    verdict = confidence.judge(document, row)
    row.cells.pop("ระดับความมั่นใจ", None)
    # Written the way the operator's file writes it, which is a percentage.
    # The number is the same either way and the string is not, and a column
    # that disagrees on formatting reads as forty wrong cells.
    row.put("ระดับความมั่นใจ", confidence.as_cell(verdict.score), "rule:confidence")
    if verdict.findings:
        existing = row.value("หมายเหตุ")
        row.cells.pop("หมายเหตุ", None)
        row.put("หมายเหตุ", " · ".join(x for x in (existing, verdict.note) if x),
                "rule:confidence")
        (here / "confidence.json").write_text(
            json.dumps(
                {
                    "score": verdict.score,
                    "needs_review": verdict.needs_review,
                    "findings": [
                        {"rule": f.rule, "penalty": f.penalty, "why": f.why,
                         "columns": list(f.columns)}
                        for f in verdict.findings
                    ],
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    sources = row.sources()
    progress.step(
        "รวม", "merge",
        f"{len(sources)}/{len(COLUMNS)} ช่อง"
        f" · กฎ {sum(1 for v in sources.values() if v == 'rule')}"
        f" · โมเดล {sum(1 for v in sources.values() if v.startswith('llm'))}"
        + (f" · {round(spend):,} token" if spend else ""),
    )

    (here / "row.json").write_text(
        json.dumps(
            {
                "cells": {c: row.value(c) for c in COLUMNS},
                "sources": sources,
                "tokens": round(spend),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return row


def apply_rules(row: Row, found: dict[str, str]) -> None:
    """The second rules pass, which corrects rather than overwrites.

    Rules run twice: once before the model, and once after the first answer
    reveals the law type, because one rule reads a judgment differently from a
    law. The second pass has to be able to replace what the first pass wrote —
    hence the ``pop`` — and that is exactly what made it dangerous: it also
    replaced answers the model had produced in between, including replacing a
    correct province with ``-``.

    So a rule that found nothing steps aside for whatever is already there.
    """
    for column, value in found.items():
        if column.startswith("_"):
            continue
        if (str(value).strip() == NOTHING and column not in NONE_IS_AN_ANSWER
                and row.value(column) not in ("", NOTHING)):
            continue
        row.cells.pop(column, None)
        row.put(column, value, "rule")


def _text_of(path: Path, saved: Path) -> Document:
    """Saved text for this PDF, or the PDF itself if none was kept."""
    number = re.search(r"(\d{5,6})", path.stem)
    record = saved / f"{number.group(1) if number else path.stem}.json"
    if record.exists():
        return load(record)
    log.info("%s ยังไม่มีข้อความที่บันทึกไว้ อ่านจาก PDF", path.name)
    return read(path)


#: Model field -> export column, per question. Declared beside the questions
#: rather than inferred, so a renamed field fails loudly instead of quietly
#: emptying a column.
_FIELDS: dict[str, dict[str, str]] = {
    "identity": {
        "agencies": "หน่วยงานกำกับ",
        "localGovernment": "องค์กรปกครองส่วนท้องถิ่น",
    },
    # audience is applied by hand below: the answer holds two ways of writing
    # the same reading and only one of them goes in the column.
    "business": {
        "core": "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "support": "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
        "reasoning": "AI ให้เหตุผล",
        "confidence": "ระดับความมั่นใจ",
    },
    "summary": {
        "summary": "คำอธิบายและสรุปสาระสำคัญ",
        "actions": "คำแนะนำสิ่งที่ต้องทำ ",
        "licenses": "ใบอนุญาต",
        "documents": "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ",
        "documentLinks": "ลิงค์เอกสารที่แนะนำ",
        "activityTags": "Activity_Tag",
        "productGroupTags": "Product_Group_Tag",
        "legalKeywordTags": "Legal_Keyword_Tag",
        "note": "หมายเหตุ",
    },
}


#: Columns the model writes as a list and repeats itself in. The tag prompt
#: asks for a broad name beside each specific one, which read literally gives
#: the broad name once per neighbour — three copies of ``ทรัพย์สิน`` next to
#: three kinds of property. A repeat is never information here.
_DEDUPED = frozenset({
    "activityTags", "productGroupTags", "legalKeywordTags",
    "agencies", "licenses", "documents",
})


def _piece(value: object) -> str:
    """One fragment of a composed cell, or "" for every way of writing nothing.

    ``merge._text`` guards whole values; this guards the parts before they are
    joined into one. Both are needed and neither replaces the other — a string
    built from ``None`` is a valid string by the time it reaches the cell.
    """
    from lawscan.merge import _item

    return _item(value)


def _apply(row: Row, question: str, value: dict, document=None) -> None:
    if question == "parent":
        # One line per section cited, which is how the expected file writes it:
        # "พ.ร.บ.ผู้ตรวจการแผ่นดิน พ.ศ. 2560 มาตรา 24, ... มาตรา 42".
        #
        # ``section`` is joined through ``_piece`` rather than interpolated.
        # Under a strict schema an optional field is declared nullable and the
        # model answers ``null``, and an f-string turns that into the word
        # ``None`` — which is how document 100001 reached the sheet reading
        # "…พ.ศ. 2560 None". The central empty-value format never saw it,
        # because by then it was part of a longer string.
        # The Constitution is never a parent. ``rules.parent`` knows this and
        # cuts the clause out of the preamble before reading it; the model was
        # never told, and answered ``รัฐธรรมนูญแห่งราชอาณาจักรไทย มาตรา 122``
        # for two documents whose reference row is a dash. The power to issue
        # an instrument at all is shared by every instrument of its kind and
        # says nothing about which act this one implements.
        parents = [
            " ".join(filter(None, (_piece(p.get("law")), _piece(p.get("section")))))
            for p in value.get("parents") or []
            if _piece(p.get("law")) and not parent_rule.is_constitution(p.get("law"))
        ]
        row.put("กฎหมายแม่", parents, f"llm:{question}")
        return
    if question == "audience":
        # These regulations are one sentence with a waterway in it, and the
        # title already holds the waterway. Reading it from there beats any
        # answer about it, and identity runs before audience so it is there.
        title = _cell(row, "ชื่อกฎหมาย")
        derived = irrigation_users(title)
        if derived:
            row.put("กลุ่มเป้าหมาย", derived, "rule:irrigation")
            return
        # ``merged`` is read for answer files recorded before it was dropped
        # from the schema, so an old run still rebuilds with --reuse. Nothing
        # asks for it any more.
        chosen = value.get("split") or value.get("merged")
        if isinstance(chosen, list):
            # Only a list can be tidied without guessing where one group ends
            # and the next begins.
            chosen = tidy(chosen)
        row.put("กลุ่มเป้าหมาย", chosen, "llm:audience")
        return
    for field, column in _FIELDS.get(question, {}).items():
        if field not in value:
            continue
        cell = value[field]
        if field in _DEDUPED and isinstance(cell, list):
            cell = once_each(cell)
        if field == "activityTags":
            cell = irrigation_activities(_cell(row, "ชื่อกฎหมาย")) or cell
        if field == "licenses" and isinstance(cell, list):
            # A licence the document never mentions sends the reader after a
            # form that does not exist.
            cell = named_in(document.text() if document else "", cell) if document else cell
        if field == "agencies":
            # The register has the last word on how a name is spelt. A document
            # writes ``ก.ล.ต.`` and the sheet wants the name it is filed under,
            # with the ministry above it — a lookup, not a judgement, so it
            # does not go to a model.
            if isinstance(cell, list):
                cell = agency_rule.with_ministry([str(x) for x in cell if x])
            # A rule still outranks it: the waterway regulations name the same
            # two bodies every time, in the operator's own punctuation, and the
            # title says which kind of document this is.
            cell = irrigation_agencies(_cell(row, "ชื่อกฎหมาย")) or cell
        if field == "localGovernment" and isinstance(cell, str):
            # A judgment against a local politician names their council. The
            # column is for a body the document binds, and this one binds a
            # person — so the name is context, not an answer.
            cell = local_body_of(cell, _cell(row, "ประเภทกฎหมาย"))
            if not cell:
                continue
        row.put(column, cell, f"llm:{question}")


def _cell(row: Row, column: str) -> str:
    """What the row already holds for a column, or "" if nothing does."""
    found = row.cells.get(column)
    return getattr(found, "value", "") or ""


def new_run(root: Path, stamp: str) -> tuple[Path, Path]:
    """Where a run writes: its CSV and its per-document folders.

    One timestamp, computed once. The obvious shell version of this —
    ``--out tests/result40-$(date ...)/result.csv --workdir tests/result40-$(date ...)/documents``
    calls ``date`` twice, and a run that starts as the minute turns over puts
    its CSV in one folder and its evidence in another.
    """
    here = root / f"result40-{stamp}"
    return here / "result.csv", here / "documents"


def scan(paths: list[Path], *, out: Path, workdir: Path, no_ocr: bool = False,
         only: str | None = None, no_llm: bool = False, reuse: bool = False,
         skip_done: list[Path] | None = None, text_from: Path | None = None,
         batch: int = 1) -> int:
    """Every document to one CSV."""
    if not no_llm and not key_is_available():
        # Named for the model that is actually about to run: a machine holding
        # a Gemini key and asked for GPT should be told which key is missing,
        # not which key the program was first written for.
        wanted = key_names()[0]
        log.error(
            "ไม่พบ %s — จะได้ไฟล์ที่มีแต่เลขเอกสาร ไม่มีชื่อกฎหมาย\n"
            "  ตั้งค่าอย่างใดอย่างหนึ่ง:\n"
            "    echo '%s=<คีย์ของคุณ>' >> %s\n"
            "    export %s=<คีย์ของคุณ>\n"
            "  หรือรัน --no-llm ถ้าตั้งใจจะเอาเฉพาะส่วนที่กฎอ่านได้",
            wanted, wanted, ENV_FILE, wanted,
        )
        return 2

    client = None if no_llm else Client()
    wanted = tuple(q.strip() for q in only.split(",")) if only else None
    if wanted:
        unknown = [q for q in wanted if q not in BY_NAME]
        if unknown:
            log.error("ไม่รู้จักคำถาม: %s", ", ".join(unknown))
            return 2

    asked = wanted or tuple(q.name for q in ALL)
    already = done_before(skip_done, asked, exclude=workdir) if skip_done else {}
    if already:
        log.info("มีคำตอบเดิมอยู่แล้ว %d ฉบับ จะไม่ถามโมเดลซ้ำ", len(already))

    def work(position: int, path: Path) -> Row | None:
        number = re.search(r"(\d{5,6})", path.stem)
        borrow = already.get(number.group(1) if number else path.stem)
        progress.document(position, len(paths), path.name,
                          f"ยืมคำตอบจาก {borrow.parts[-3]}" if borrow else "")
        try:
            return one(path, client, workdir, no_ocr=no_ocr, only=wanted,
                       reuse=reuse, borrow=borrow, text_from=text_from)
        except Exception as exc:  # noqa: BLE001 — one bad file is not a bad run
            log.error("%s ล้ม: %s: %s", path.name, type(exc).__name__, exc)
            return None

    rows: list[Row] = []
    if batch > 1:
        # The work is waiting on a network, not on this machine — five
        # questions per document, seconds each, all of it idle. Threads are the
        # right shape for that, and the rows are sorted by document number on
        # the way out, so finishing out of order changes nothing in the file.
        log.info("ทำพร้อมกันครั้งละ %d ฉบับ", batch)
        with ThreadPoolExecutor(max_workers=batch) as pool:
            futures = [
                pool.submit(_grouped_work, work, position, path)
                for position, path in enumerate(paths, start=1)
            ]
            for future in as_completed(futures):
                row = future.result()
                if row is not None:
                    rows.append(row)
    else:
        for position, path in enumerate(paths, start=1):
            row = work(position, path)
            if row is not None:
                rows.append(row)

    out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out)
    log.info("%d แถว → %s", len(rows), out)
    return 0
