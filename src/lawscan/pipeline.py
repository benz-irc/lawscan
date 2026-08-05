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

from lawscan.export.columns import COLUMNS, write_csv
from lawscan.llm.client import ENV_FILE, Client, key_is_available
from lawscan.llm.questions import ALL, BY_NAME
from lawscan import progress
from lawscan.merge import Row
from lawscan.ocr.read import Document, load, read
from lawscan.rules import categories, run_all

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
    law_type = ""
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
        if question.name == "identity":
            law_type = str(value.get("lawType") or "")
        if question.name == "business":
            # The document's own statement about itself outranks the model's
            # reading of it, here as everywhere else.
            value = dict(value)
            value["core"], value["support"] = categories.correct(
                document.text(), value.get("core") or [], value.get("support") or []
            )
        _apply(row, question.name, value)

    # The law type only arrives with the first answer, and one rule reads
    # differently once it knows a document is a judgment rather than a law.
    if law_type:
        for column, value in run_all(document, law_type=law_type).items():
            if not column.startswith("_"):
                row.cells.pop(column, None)
                row.put(column, value, "rule")

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
        "title": "ชื่อกฎหมาย",
        "lawType": "ประเภทกฎหมาย",
        "agencies": "หน่วยงานกำกับ",
        "localGovernment": "องค์กรปกครองส่วนท้องถิ่น",
        "province": "จังหวัด",
        "districts": "อำเภอ",
    },
    "audience": {"audience": "กลุ่มเป้าหมาย"},
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


def _apply(row: Row, question: str, value: dict) -> None:
    if question == "parent":
        # One line per section cited, which is how the expected file writes it:
        # "พ.ร.บ.ผู้ตรวจการแผ่นดิน พ.ศ. 2560 มาตรา 24, ... มาตรา 42".
        parents = [
            f"{p.get('law', '')} {p.get('section', '')}".strip()
            for p in value.get("parents") or []
            if p.get("law")
        ]
        row.put("กฎหมายแม่", parents, f"llm:{question}")
        return
    for field, column in _FIELDS.get(question, {}).items():
        if field in value:
            row.put(column, value[field], f"llm:{question}")


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
        log.error(
            "ไม่พบ GEMINI_API_KEY — จะได้ไฟล์ที่มีแต่เลขเอกสาร ไม่มีชื่อกฎหมาย\n"
            "  ตั้งค่าอย่างใดอย่างหนึ่ง:\n"
            "    echo 'GEMINI_API_KEY=<คีย์ของคุณ>' >> %s\n"
            "    export GEMINI_API_KEY=<คีย์ของคุณ>\n"
            "  หรือรัน --no-llm ถ้าตั้งใจจะเอาเฉพาะส่วนที่กฎอ่านได้",
            ENV_FILE,
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
