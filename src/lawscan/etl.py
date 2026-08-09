"""The whole job, one command.

``etl`` is the only command a person needs on an ordinary day. Everything under
it is available separately — ``read``, ``rules``, ``ask``, ``scan``, ``diff``
— and that is the point: this is a sequence of steps that can each be run and
inspected on their own, not a black box that happens to have a name.

The steps, in order:

    extract    PDF to text, per page, text layer or OCR
    transform  rules first, then the model, then merge under rule precedence
    load       one CSV in the operator's own 33 columns
    check      against the reference file, if there is one

Only the fourth is optional, and it is skipped silently when no reference file
exists — a new corpus has nothing to be checked against and that is not an
error.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from lawscan import testrun
from lawscan.ocr.read import extract
from lawscan.pipeline import new_run, scan
from lawscan.where import report

log = logging.getLogger(__name__)


def _unread(files: list[Path], text: Path) -> list[Path]:
    """Documents whose saved text still has pages nobody could read."""
    needing = []
    for pdf in files:
        record = text / f"{_number(pdf)}.json"
        if not record.exists():
            continue
        try:
            stored = json.loads(record.read_text(encoding="utf-8"))
        except ValueError:
            continue
        # Already read the pictures on a previous pass; nothing more to try.
        if any(p.get("source") == "text-layer+ocr" for p in stored.get("pages", [])):
            continue
        if stored.get("unread_pages"):
            needing.append(pdf)
    return needing


def _number(path: Path) -> str:
    found = re.search(r"(\d{5,6})", path.stem)
    return found.group(1) if found else path.stem


def run(
    pdfs: Path,
    *,
    into: Path,
    expected: Path | None = None,
    no_ocr: bool = False,
    fresh: bool = False,
    text: Path | None = None,
    batch: int = 1,
    stamp: str | None = None,
) -> int:
    """Every PDF under ``pdfs`` to a kept run under ``into``.

    ``fresh`` asks every question again instead of reusing the answers earlier
    runs already paid for. It exists because a changed prompt has to be
    measured on answers it actually produced, and the default — reuse — would
    quietly compare the new prompt against the old one's output.
    """
    files = sorted(pdfs.glob("*.pdf")) if pdfs.is_dir() else [pdfs]
    if not files:
        log.error("ไม่พบไฟล์ PDF ใน %s", pdfs)
        return 2

    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M")
    out, workdir = new_run(into, stamp)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Extraction is deterministic, so it is done once and kept. Every later
    # run reads the text instead of the PDF: measured over 91 documents, 4.2
    # seconds against 0.26, and the CSV is identical byte for byte.
    if text is not None:
        missing = [f for f in files if not (text / f"{_number(f)}.json").exists()]
        if missing:
            log.info("── ขั้นที่ 1  แปลง PDF เป็นข้อความ ── %d ฉบับ", len(missing))
            extract(missing, text, ocr=not no_ocr)
        else:
            log.info("── ขั้นที่ 1  ข้อความครบแล้วใน %s ── ข้าม", text)

        # Go back to the PDF only for the documents that need it. Reading the
        # pictures on all 91 took seven minutes for 0.3% more text; reading
        # them on the six documents that lost pages to pictures takes seconds.
        #
        # The trigger is a fact about the file, not the model's opinion of its
        # own answer: `confidence` came back at or above 0.8 on every one of
        # the 91, which makes it useless for deciding anything.
        if not no_ocr:
            unread = _unread(files, text)
            if unread:
                log.info(
                    "── ขั้นที่ 1ข  %d ฉบับมีหน้าเป็นภาพ อ่านภาพเพิ่ม ──", len(unread)
                )
                extract(unread, text, mode="image")

    log.info("")
    log.info("── ขั้นที่ 2  อ่านกฎและถามโมเดล ── %d ฉบับ", len(files))
    code = scan(
        files,
        out=out,
        workdir=workdir,
        no_ocr=no_ocr,
        reuse=not fresh,
        skip_done=None if fresh else [into],
        text_from=text,
        batch=batch,
    )
    if code != 0:
        return code

    made = [out, out.parent / "documents"]
    if text is not None:
        made.append(text)

    if expected and expected.exists():
        log.info("")
        log.info("── ขั้นที่ 3  เทียบกับ %s ──", expected)
        compare_dir = into / f"compare40-{stamp}"
        print()
        print(testrun.write(out, expected, out.parent, compare_dir, workdir=workdir))
        made.append(compare_dir)
        steps = [("เปิดผลลัพธ์", f"open {out}"), ("ดูที่ไม่ตรง", f"open {compare_dir}/cells.csv")]
    else:
        log.info("ไม่มีไฟล์อ้างอิงให้เทียบ — ข้ามขั้นตอนตรวจ")
        steps = [("เปิดผลลัพธ์", f"open {out}")]

    print(report("รอบนี้เขียนอะไรไว้บ้าง", made, next_steps=steps))
    return 0
