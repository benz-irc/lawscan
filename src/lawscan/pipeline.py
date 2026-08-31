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
from lawscan.llm.questions import ALL, BY_NAME, notify_for
from lawscan import confidence, progress
from lawscan.answers import (
    irrigation_activities, irrigation_agencies, irrigation_users,
    local_body_of, named_in, once_each, unnumbered,
)
from lawscan.audience import tidy
from lawscan.merge import NOTHING, Row
from lawscan.ocr.read import Document, load, read
from lawscan.rules import BANDS, kind, PENALTY_TEXT, categories, penalties, run_all
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
    # A question that reads another question's answer cannot be asked alone.
    # ``--only notify`` would otherwise send an empty code list to a prompt
    # whose whole job is to write one message per code, and the model would
    # obey: nine tokens back, an empty column, and a bill for it. What the
    # dependency needs is replayed from disk, never asked — spending money on
    # a question nobody named is worse than the empty column.
    replay = [BY_NAME[n] for q in questions for n in q.needs
              if n not in {x.name for x in questions}]
    questions = _deduplicated(replay) + questions
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
        replay_only = question in replay
        if question.name == "notify":
            # Nothing to announce on a document that carries no code, and the
            # schema below would have no fields to require.
            codes = _notify_codes(row)
            if not codes:
                progress.step(question.name, "ข้าม", "ไม่มีรหัสหมวดธุรกิจให้เขียนข้อความ")
                continue
            question = notify_for(tuple(codes))
        saved = _saved(here, question.name) if reuse or replay_only else None
        if saved is None and borrow is not None:
            # An answer this document already has from an earlier run. Copied
            # into this run's folder as it is used, so the folder stays a
            # complete record of the run rather than a partial one that only
            # makes sense next to its predecessor.
            saved = _saved(borrow, question.name)
            if saved is not None and borrow.resolve() != here.resolve():
                shutil.copy(borrow / f"{question.name}.json", here / f"{question.name}.json")
        if saved is None and replay_only:
            progress.step(question.name, "ข้าม",
                          f"ไม่มีคำตอบเดิมของ {question.name} ที่ {question.needs or 'คำถามอื่น'} ต้องใช้")
            continue
        if saved is not None:
            progress.step(question.name, "ของเดิม", "ใช้คำตอบที่บันทึกไว้ ไม่เรียกโมเดล")
            value = saved
        else:
            with progress.timed(question.name, client.model.split("-preview")[0]) as said:
                answer = client.ask(question, document, _preamble(question.name, row))
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
        if question.name == "notify":
            value = _alerts(value, codes)
        if question.name in ("business", "support"):
            # A code the model wrote off in its own working may not also be an
            # answer. It contradicts itself on about one code in twenty-two
            # documents, and the contradiction reaches the sheet as a code
            # sitting in a column with a line beside it explaining why it was
            # rejected.
            value = dict(value)
            # Both questions' rejections, not just this one's. ``business``
            # settles the cell first and ``support`` never sees what it threw
            # out, so a code the first question rejected came back as the
            # second question's answer — CC17 on 100021.
            written_off = categories.rejected_in(value.get("reasoning") or "")
            written_off |= categories.rejected_in(_cell(row, "AI ให้เหตุผล"))
            for field in ("core", "support"):
                if isinstance(value.get(field), list):
                    value[field] = [c for c in value[field]
                                    if not (written_off & set(categories.codes_in(str(c))))]
        if question.name == "support":
            # Asked on its own now, so the same treatment core gets, applied
            # to the one column this question fills.
            value = dict(value)
            reasoning = value.get("reasoning") or ""
            value["support"] = categories.from_pairs(value.get("support") or [])
            value["support"] = categories.realign(reasoning, value["support"])
            # V19 rule 6 and the master list agree: this column takes AY–CF.
            value["support"] = categories.support_only(value["support"])
            added: list[str] = []
            if categories.institution_belongs_in_core(_cell(row, "ระดับวามเสี่ยง ")):
                # Rule 4.10's stop applies to this column too. It says tag the
                # owning body "เฉพาะ" into core and "บังคับให้ข้าม การประมวลผล
                # หาห่วงโซ่คุณค่าและผู้ให้บริการทันที" — a state body's internal
                # regulation reaches no private back-office at all. Asked
                # separately, this question did not know the band and swept one
                # anyway: an ombudsman's travel-expense rules came back tagged
                # with corporate income tax, private accounting standards and
                # labour law, none of which a state agency is under.
                value["support"] = []
            else:
                for code in categories.of_institution(_cell(row, "หน่วยงานกำกับ")):
                    if code not in value["support"]:
                        value["support"].append(code)
                        added.append(categories.explained(code, "รหัสของหน่วยงานเจ้าของเอกสาร อ่านจากช่องหน่วยงานกำกับ"))
            core_now = categories.codes_in(_cell(row, "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"))
            before = set(value["support"])
            core_now, value["support"] = categories.correct(
                document.text(), list(core_now), value["support"]
            )
            added += [categories.explained(c, "รหัสที่เอกสารระบุถึงตัวเองโดยตรง")
                      for c in value["support"] if c not in before]
            if added:
                # ``joined`` and not a plain append: the model now closes its
                # working with a STEP 3 block, and a line tacked on after that
                # heading reads as a rejection. Five rule-written lines landed
                # there on the first run with the new structure.
                value["reasoning"] = categories.joined(
                    value.get("reasoning") or "", "<br>".join(added))
            # V19 rule 6.2.1: a code chosen for core may not repeat here.
            # Reinstated at the operator's request. Their own answers break it
            # on 13 of their 49 support codes, and reading those cases the
            # repetition looked deliberate — but the rule is theirs, and the
            # cost of keeping it is measured: support loses about ten points.
            value["support"] = [c for c in value["support"] if c not in core_now]
        if question.name in ("business", "one", "v15"):
            # The document's own statement about itself outranks the model's
            # reading of it, here as everywhere else.
            value = dict(value)
            # The code first, against the name the model wrote beside it. It
            # reads the 666-line register a row out often enough to matter,
            # and the name is the half it chose on purpose.
            reasoning = value.get("reasoning") or value.get("reason") or ""
            # The answer is asked for as ``code = name`` so that reading the
            # register can be checked. Where the pair is there, the name
            # decides and an invented name is dropped; where it is not, this
            # falls back to reading the codes out and correcting them against
            # the names in the reasoning.
            value["core"] = categories.from_pairs(value.get("core") or [])
            value["core"] = categories.realign(reasoning, value["core"])
            # The institution the document belongs to, taken from the column a
            # rule already filled. Which half it lands in is V19 rule 5.9's
            # call, not the sheet's: an instrument the state aims at itself
            # puts the issuing body's code in core, and the support question
            # picks it up in every other case.
            if categories.institution_belongs_in_core(_cell(row, "ระดับวามเสี่ยง ")):
                # Rule 4.10 is a hard stop, not an addition: "Tag เฉพาะ รหัส
                # หมวดย่อยของหน่วยงานราชการ/องค์กรอิสระที่เป็นเจ้าของระเบียบนั้น"
                # and "บังคับให้ข้าม การประมวลผลหาห่วงโซ่คุณค่าและผู้ให้บริการ
                # ทันที". Their own example of what this forbids is ours
                # exactly — a hotel code and a taxi code on an ombudsman's
                # travel-expense regulation, tagged because the text mentions
                # lodging and fares.
                owner = categories.of_institution(_cell(row, "หน่วยงานกำกับ"))
                if owner:
                    value["core"] = owner
                    value["reasoning"] = categories.joined(
                        value.get("reasoning") or "",
                        "<br>".join(categories.explained(
                            c, "รหัสของหน่วยงานเจ้าของเอกสาร อ่านจากช่องหน่วยงานกำกับ")
                            for c in owner))
            was = set(value["core"])
            value["core"], _ = categories.correct(
                document.text(), value["core"], value.get("support") or []
            )
            grown = [categories.explained(c, "รหัสที่เอกสารระบุถึงตัวเองโดยตรง")
                     for c in value["core"] if c not in was]
            if grown:
                value["reasoning"] = categories.joined(
                    value.get("reasoning") or "", "<br>".join(grown))
        _apply(row, question.name, value, document)

    # One rule reads a judgment differently from a law, so it wants the type.
    # It used to come from the model's first answer; the type is now a rule of
    # its own and beat the model on 299 of 300 documents, so the second pass
    # reads what the first pass already wrote.
    # One sweep after every question has spoken. ``business`` writes the core
    # column first and ``support`` runs afterwards, so a code the second
    # question rejects may already be sitting in the first question's column
    # with nobody left to take it out — five of 790 codes over 250 documents.
    _honour_rejections(row)
    # The alert column is written from the codes, so it has to be corrected
    # when they are. Two ways it drifts: a code rejected by the sweep above is
    # already announced by then, and the model sometimes packs a second
    # message into one code's field. Both leave a message for a code the sheet
    # does not carry — a follower matched on it would be alerted about a law
    # this document was found not to touch.
    _prune_alerts(row)

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
    # An instrument titled ``(ฉบับที่ N)`` names what it changes by naming
    # itself, and carries none of the keywords the model is told to look for —
    # 100019 answered nothing at all, so this cannot live inside the loop that
    # walks the model's fields. Only fires on that title.
    # Fills an empty cell, never replaces an answer. On 100114 the model read
    # the amended clauses out of the text correctly, down to ``ข้อ 3 (1)``, and
    # overwriting that with what the title implies made it worse.
    if not row.value("แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น").strip("- "):
        edition = parent_rule.amended_edition(document.text()) if document else ""
        if edition:
            row.cells.pop("แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น", None)
            row.put("แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น", edition, "rule:edition")

    if penalties.is_housekeeping(band, core, row.value("บทลงโทษ")):
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

    # The two columns are one answer written twice, and the operator's own
    # rule says so: "รอเทียบกฎหมายแม่ — ให้ตอบคำนี้ (แทนการใส่สี)". The band is
    # decided by a rule reading the page's words, and the penalty can be
    # decided by the model reading the preamble, so the two reached the sheet
    # disagreeing — a document waiting on its parent act for a penalty, filed
    # under a colour that says it has none.
    #
    # Whoever wrote the penalty, the band follows it. Nothing else about the
    # band changes: a page that states its own penalty keeps the colour its
    # words earned.
    if row.value("บทลงโทษ").startswith(penalties.LINKED_PREFIX):
        row.cells.pop("ระดับวามเสี่ยง ", None)
        row.put("ระดับวามเสี่ยง ", penalties.LINKED_BAND, "rule:linked")

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
    number = re.match(r"(\d{5,7}(?:\.\d+)?)", path.stem)
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
        "repealsWhole": "ยกเลิกกฎหมายอื่นทั้งฉบับ",
        "amends": "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
    },
    # audience is applied by hand below: the answer holds two ways of writing
    # the same reading and only one of them goes in the column.
    "business": {
        "core": "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "reasoning": "AI ให้เหตุผล",
        "confidence": "ระดับความมั่นใจ",
    },
    # Its ``reasoning`` lands in the same cell ``business`` writes, appended
    # rather than put: the sheet has one column for the working behind both
    # code columns, and losing half of it would make the other half read as
    # the whole answer.
    "support": {
        "support": "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
        "reasoning": "AI ให้เหตุผล",
    },
    # The operator's three prompts as one question. Shares field names with the
    # five wherever they overlap, so the same handling below applies to both.
    "one": {
        "title": "ชื่อกฎหมาย",
        "status": "สถานะกฎหมาย",
        "repealedBy": "ถูกยกเลิกโดยกฎหมายชื่อ",
        "repealsWhole": "ยกเลิกกฎหมายอื่นทั้งฉบับ",
        "amends": "แก้ไข/ยกเลิกบางส่วนของกฎหมายอื่น",
        "publishDay": "วันที่ประกาศ",
        "publishMonth": "เดือนที่ประกาศ",
        "publishYear": "ปีที่ประกาศ",
        "effectiveDate": "วันทีมีผลใช้บังคับ",
        "expiryDate": "วันที่สิ้นผล",
        "lawType": "ประเภทกฎหมาย",
        "agencies": "หน่วยงานกำกับ",
        "localGovernment": "องค์กรปกครองส่วนท้องถิ่น",
        "district": "อำเภอ",
        "province": "จังหวัด",
        "riskBand": "ระดับวามเสี่ยง ",
        "penalty": "บทลงโทษ",
        "licenses": "ใบอนุญาต",
        "source": "ข้อมูลแหล่งที่มา",
        "documents": "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
        "documentLinks": "ลิงค์เอกสารที่แนะนำ",
        "activityTags": "Activity_Tag",
        "productGroupTags": "Product_Group_Tag",
        "legalKeywordTags": "Legal_Keyword_Tag",
        "core": "กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
        "support": "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม (Support & General Compliance)",
        "reasoning": "AI ให้เหตุผล",
        "confidence": "ระดับความมั่นใจ",
        "summary": "คำอธิบายและสรุปสาระสำคัญ",
        "actions": "คำแนะนำสิ่งที่ต้องทำ ",
        "note": "หมายเหตุ",
    },
    "notify": {"alerts": "ข้อความแจ้งเตือน (Smart Prompt)"},
    "summary": {
        "summary": "คำอธิบายและสรุปสาระสำคัญ",
        "actions": "คำแนะนำสิ่งที่ต้องทำ ",
        "licenses": "ใบอนุญาต",
        "penalty": "บทลงโทษ",
        "documents": "คู่มือ แบบฟอร์ม เอกสารที่แนะนำ ",
        "documentLinks": "ลิงค์เอกสารที่แนะนำ",
        "activityTags": "Activity_Tag",
        "productGroupTags": "Product_Group_Tag",
        "legalKeywordTags": "Legal_Keyword_Tag",
        "note": "หมายเหตุ",
    },
}

# The operator's V15 sheet answers the same fields under the same names, so it
# lands in the same columns. Shared rather than copied: two dictionaries that
# have to stay identical are one dictionary that will not.
_FIELDS["v15"] = _FIELDS["one"]
_FIELDS["v16"] = _FIELDS["one"]


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
    if question in ("one", "v15"):
        # The one-question form carries the parent list and the audience list
        # in the same answer as everything else. Both need the handling the
        # separate questions get, so they are routed through it rather than
        # copied — one of them turns a null section into the word "None" if it
        # is not, and the other joins two groups into one cell.
        if "parents" in value:
            _apply(row, "parent", value, document)
        if "audience" in value:
            _apply(row, "audience", {"split": value.get("audience")}, document)
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
        # A judgment or a ruling has no parent at all: it applies law rather
        # than being made under one, and the sections it cites are grounds of
        # offence. Both answer files agree without a single exception — 19
        # rulings between them, 19 dashes — so the model's answer is not
        # allowed to stand here, only the rule's silence.
        if _cell(row, "ประเภทกฎหมาย") in kind.NARRATIVE:
            parents = []
        row.put("กฎหมายแม่", parents, f"llm:{question}")
        # The same cleansing the parent column gets, for the same reason: a
        # citation and its amendment history are one law, and the sheet writes
        # the law.
        row.put(
            "กฎหมายที่อ้างถึง",
            [c for c in (_piece(x) for x in value.get("referenced") or []) if c],
            f"llm:{question}",
        )
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
        if field == "penalty" and isinstance(cell, str):
            # "ไม่มีโทษ" and "-" are the same answer; the sheet writes the dash.
            cell = penalties.plain(cell)
        if field == "reasoning" and isinstance(cell, str) and question in ("business", "support"):
            # The rules have finished with the code lists by now, so this is
            # where the summary can be squared against what actually reached
            # the sheet.
            # Both columns, not just this question's. ``business`` writes the
            # cell first and ``support`` appends to it, so settling the second
            # half against support alone moved the first half's lines into the
            # cast-off block while their codes were still sitting in core — on
            # 100015 five food-production codes read as discarded and as
            # answers at the same time.
            other = ("กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                     "(Support & General Compliance)") if question == "business" else \
                    "กฎหมายเฉพาะธุรกิจ (Core Business Laws)"
            mine = value.get("core") if question == "business" else value.get("support")
            kept = [str(c) for c in (mine or [])]
            kept += categories.codes_in(_cell(row, other))
            cell, _ = categories.settled(cell, kept)
        if field == "reasoning" and isinstance(cell, str):
            # The scratch work and the summary are asked for separately so
            # neither can crowd the other out, and the column shows both —
            # the operator's own sheet prints the two one after the other.
            scratch = value.get("analysis")
            if isinstance(scratch, str) and scratch.strip():
                cell = f"{scratch.strip()}<br>{cell.strip()}" if cell.strip() else scratch.strip()
            # Two questions write this column now, and the second must not
            # erase the first: the working behind the core codes and the
            # working behind the support codes are both what the operator
            # reads here, and either one alone reads as the whole answer.
            already = _cell(row, column)
            if already and cell.strip() and cell.strip() not in already:
                cell = categories.joined(already, cell)
        if field == "activityTags":
            cell = irrigation_activities(_cell(row, "ชื่อกฎหมาย")) or cell
        if field == "documents" and isinstance(cell, list):
            # The sheet joins this column with commas; a number in front of
            # every entry is a second numbering on top of that one.
            cell = unnumbered(cell)
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
            # A judgment or a ruling names the court, not the office that runs
            # it: V19 rule 14.3, and the sheet agrees.
            if _cell(row, "ประเภทกฎหมาย") in kind.NARRATIVE and isinstance(cell, list):
                cell = agency_rule.court_only(cell)
        if field == "localGovernment" and isinstance(cell, str):
            # A judgment against a local politician names their council. The
            # column is for a body the document binds, and this one binds a
            # person — so the name is context, not an answer.
            cell = local_body_of(cell, _cell(row, "ประเภทกฎหมาย"))
            if not cell:
                continue
        row.put(column, cell, f"llm:{question}")


def _deduplicated(questions: list) -> list:
    """The same list with repeats dropped, first mention winning."""
    seen, kept = set(), []
    for question in questions:
        if question.name not in seen:
            seen.add(question.name)
            kept.append(question)
    return kept


#: A message opens with its own code in square brackets, exemption tag and all.
_TAGGED = re.compile(r"\[([A-Z]{1,2}\d{1,2})(?:\[Exempted\])?\]\s*:")


def _prune_alerts(row: Row) -> None:
    """Keep only the messages whose code survived into the code columns."""
    said = _cell(row, "ข้อความแจ้งเตือน (Smart Prompt)")
    if not said:
        return
    keep = set(_notify_codes(row))
    marks = list(_TAGGED.finditer(said))
    if not marks:
        return
    bounds = [m.start() for m in marks] + [len(said)]
    kept = [said[bounds[i]:bounds[i + 1]].strip().strip(",").strip()
            for i, m in enumerate(marks) if m.group(1) in keep]
    if len(kept) == len(marks):
        return
    if kept:
        row.put("ข้อความแจ้งเตือน (Smart Prompt)", ", ".join(kept), "rule:notify")
    else:
        # ``put`` refuses an empty value over a full one — that guard exists so
        # a rule that read nothing cannot erase a model answer. Here the empty
        # value is the answer: every code was rejected, so there is nothing
        # left to announce, and the column has to read the same as it does on
        # a document that never had a code at all.
        row.cells.pop("ข้อความแจ้งเตือน (Smart Prompt)", None)


def _notify_codes(row: Row) -> list[str]:
    """Every code the earlier questions settled on, Core first, no repeats."""
    codes: list[str] = []
    for column in ("กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
                   "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)"):
        for code in categories.codes_in(_cell(row, column)):
            if code not in codes:
                codes.append(code)
    return codes


def _preamble(question: str, row: Row) -> str:
    """Per-document facts a question needs that the document does not carry.

    Only ``notify`` has one: it writes a message per business code and is told
    not to invent any, so the codes the earlier questions settled on have to
    travel with the document. The schema requires the same codes as fields —
    this names them, so the model writes about the right subject rather than
    inferring one from a bare code.
    """
    if question != "notify":
        return ""
    codes = _notify_codes(row)
    if not codes:
        return "รหัสหมวดธุรกิจของเอกสารฉบับนี้: ไม่มี"
    named = [f"{c} = {categories.name_of(c)}".rstrip(" =") for c in codes]
    return "รหัสหมวดธุรกิจของเอกสารฉบับนี้ — เขียนข้อความให้ครบทุกตัว ห้ามเพิ่ม ห้ามข้าม:\n" + "\n".join(named)


def _alerts(value: dict, codes: list[str]) -> dict:
    """The per-code answer flattened into the one list the column expects.

    Kept tolerant of the older shape so a folder of saved answers from before
    the schema changed still rebuilds with ``--reuse``.
    """
    if "alerts" in value:
        return value
    return {"alerts": [value[code].strip() for code in codes
                       if isinstance(value.get(code), str) and value[code].strip()]}


def _honour_rejections(row: Row) -> None:
    """Take out of both code columns anything the working writes off.

    Read from the finished cell rather than from one answer, because the two
    questions settle in turn and only the finished cell holds both verdicts.
    """
    written_off = categories.rejected_in(_cell(row, "AI ให้เหตุผล"))
    if not written_off:
        return
    for column in ("กฎหมายเฉพาะธุรกิจ (Core Business Laws)",
                   "กฎหมายสนับสนุนและกฎหมายทั่วไปที่ต้องปฏิบัติตาม "
                   "(Support & General Compliance)"):
        kept = [c for c in categories.codes_in(_cell(row, column))
                if c not in written_off]
        if kept != categories.codes_in(_cell(row, column)):
            row.put(column, kept, "rule:rejected")


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
        number = re.match(r"(\d{5,7}(?:\.\d+)?)", path.stem)
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
