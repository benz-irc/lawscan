"""What you can do, and nothing else.

    lawscan etl    <folder>         the whole job: PDFs in, checked CSV out

and the steps it is made of, each runnable and inspectable alone:

    lawscan ocr    <folder>         PDFs to text, once, kept
    lawscan read   <pdf>            what the OCR produced
    lawscan rules  <pdf>            what the rules read, with no model involved
    lawscan ask    <question> <pdf> one question to the model, answer printed raw
    lawscan scan   <path>           the whole pipeline to CSV
    lawscan diff   <csv>            that CSV against the expected one
    lawscan record <csv>            keep a run: result and comparison folders
    lawscan clean                   throw kept runs away, so the next one measures

The first three exist so a wrong cell can be traced without running the fourth.
Each stage is inspectable on its own, against one document, in seconds — which
is the thing the previous system could not do and the reason this one is split
the way it is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _pdfs(targets: list[Path]) -> list[Path]:
    """Every PDF named by the arguments, each one once, in the order given.

    Folders expand; files stand for themselves. Taking a list rather than one
    path is what lets a shell glob through — ``lawscan scan pdfs/1000*.pdf`` is
    the obvious way to run ten documents, and before this it was an argparse
    error that sent you off to build a folder of symlinks instead.

    Duplicates are dropped because ``pdfs pdfs/100001.pdf`` is a reasonable
    thing to type and paying twice for one document is not a reasonable thing
    to answer with. A named file that does not exist is returned anyway: the
    reader reports it against the document it belongs to, which is more use
    than a failure here that names no document at all.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        for path in sorted(target.glob("*.pdf")) if target.is_dir() else [target]:
            key = path.resolve() if path.exists() else path.absolute()
            if key not in seen:
                seen.add(key)
                found.append(path)
    return found


def _ocr(args: argparse.Namespace) -> int:
    """Extract every PDF to text and keep it.

    Its own command because it is the one expensive step and the one whose
    answer never changes: the same PDF gives the same text, so paying for it
    more than once buys nothing.
    """
    from lawscan.ocr.read import extract

    files = _pdfs(args.path)
    written = extract(files, args.into, ocr=not args.no_ocr, mode=args.mode)
    if not written:
        return 2

    from lawscan.where import report

    print(report(
        f"ข้อความของ {written} ฉบับ",
        [args.into],
        notes=[f"{written} ไฟล์ .txt สำหรับอ่าน · {written} ไฟล์ .json สำหรับขั้นถัดไป"],
        next_steps=[
            ("เปิดดู", f"open {args.into}"),
            ("รันกฎ", f"lawscan scan {' '.join(str(p) for p in args.path)}"
                      f" --text {args.into} --no-llm --out out/r.csv"),
            ("รันทั้งงาน", f"lawscan etl --text {args.into}"),
        ],
    ))
    return 0


def _read(args: argparse.Namespace) -> int:
    from lawscan.ocr.read import read

    for path in _pdfs(args.path):
        document = read(path, ocr=not args.no_ocr)
        text = document.text()
        print(f"=== {document.number}  {len(document.pages)} หน้า"
              f" · อ่านด้วย OCR {document.scanned_pages} หน้า · {len(text):,} ตัวอักษร")
        if args.full:
            print(text)
        else:
            print(text[: args.chars])
            if len(text) > args.chars:
                print(f"… (อีก {len(text) - args.chars:,} ตัวอักษร — ใช้ --full เพื่อดูทั้งหมด)")
    return 0


def _rules(args: argparse.Namespace) -> int:
    """Everything the deterministic side can say, with no model called."""
    from lawscan.ocr.read import read
    from lawscan.rules import run_all

    for path in _pdfs(args.path):
        document = read(path, ocr=not args.no_ocr)
        found = run_all(document)
        print(f"=== {document.number}")
        width = max(len(k) for k in found) if found else 0
        for field, value in found.items():
            shown = value if value else "—"
            print(f"  {field:<{width}}  {shown}")
    return 0


def _ask(args: argparse.Namespace) -> int:
    """Put one question to the model and print what came back, unmerged."""
    from lawscan.llm.client import Client
    from lawscan.llm.questions import BY_NAME

    question = BY_NAME.get(args.question)
    if question is None:
        print(f"ไม่รู้จักคำถาม {args.question!r} — มี: {', '.join(BY_NAME)}", file=sys.stderr)
        return 2

    from lawscan.ocr.read import read

    client = Client()
    for path in _pdfs(args.path):
        document = read(path, ocr=not args.no_ocr)
        if args.show_prompt:
            print(client.prompt_for(question))
            print("=" * 72)
        answer = client.ask(question, document)
        print(f"=== {document.number}  {question.name}")
        if not answer.ok:
            print(f"  ล้ม: {answer.error}")
            continue
        print(json.dumps(answer.value, ensure_ascii=False, indent=2))
        print(f"  token เข้า {answer.input_tokens:,} (จาก cache {answer.cached_tokens:,})"
              f" · ออก {answer.output_tokens:,} · จ่ายจริง ~{answer.billed_input:,.0f}"
              f" · {answer.duration_ms:,} ms")
    return 0


def _scan(args: argparse.Namespace) -> int:
    from datetime import datetime

    from lawscan.pipeline import new_run, scan
    from lawscan.where import report

    # `--into` names a place to keep runs, not a file: it makes its own
    # timestamped folder and reuses what earlier runs in there already answered.
    if args.into:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        args.out, args.workdir = new_run(args.into, stamp)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.skip_done is None:
            args.skip_done = [args.into]
        # Two runs started inside the same minute share a folder. The second
        # one should carry on from what the first wrote rather than pay for it
        # again — which is reuse, not borrowing: borrowing from your own folder
        # is copying a file onto itself.
        args.reuse = True
        print(f"รอบนี้เก็บที่ {args.out.parent}")

    # `--skip-done` with no value means the default place runs are kept.
    if args.skip_done == []:
        args.skip_done = [Path("tests")]

    code = scan(
        _pdfs(args.path),
        out=args.out,
        workdir=args.workdir,
        no_ocr=args.no_ocr,
        only=args.only,
        no_llm=args.no_llm,
        reuse=args.reuse,
        skip_done=args.skip_done,
        text_from=args.text,
        batch=args.batch,
    )
    if code == 0:
        print(report(
            "ผลลัพธ์",
            [args.out, args.workdir],
            notes=["CSV กับหลักฐานรายฉบับ — row.json บอกที่มาของทุกช่อง"],
            next_steps=[
                ("เปิดดู", f"open {args.out}"),
                ("เทียบ", f"lawscan diff {args.out}"),
            ],
        ))
    return code


def _with_text(ours: Path, text: Path):
    """(document, its text, its row) for every row whose text was kept."""
    from lawscan import sheet

    for number, row in sorted(sheet.by_document(ours)[1].items()):
        saved = text / f"{number}.json"
        if not saved.exists():
            continue
        pages = json.loads(saved.read_text(encoding="utf-8"))["pages"]
        yield number, "\n".join(page["text"] for page in pages), row


def _diff(args: argparse.Namespace) -> int:
    """How far our CSV is from theirs, per column, worst first."""
    from lawscan.diff import compare, report as score_table

    if not args.expected.exists():
        print(f"ไม่พบไฟล์ที่คาดหวัง: {args.expected}", file=sys.stderr)
        return 2
    result = compare(args.expected, args.ours)
    print(score_table(result, examples=args.examples))

    # The score says which columns are wrong. This says which of them are
    # wrong because the pipeline broke the answer rather than because the
    # model read the document differently — printed every time, because the
    # two it was written for were both found by a person reading the sheet.
    from lawscan import defects, sheet
    from lawscan.diff import UNSCORED
    from lawscan.export.columns import COLUMNS

    found = defects.scan(
        sheet.by_document(args.expected)[1],
        sheet.by_document(args.ours)[1],
        COLUMNS,
        skip=UNSCORED,
    )
    # What the document measured and the row did not keep. Needs no reference
    # file — the two it was written for were found by reading one row by hand.
    if args.thresholds:
        from lawscan import thresholds
        from lawscan.diff import PROSE

        columns = tuple(PROSE - {"AI ให้เหตุผล"}) + ("กลุ่มเป้าหมาย",)
        print()
        print(thresholds.report(
            thresholds.survey(_with_text(args.ours, args.text), columns=columns),
            columns=columns,
        ))

    if found.mechanical_cells or args.defects:
        print()
        print(defects.report(found) if args.defects else
              f"⚠ {found.mechanical_cells:,} ช่องที่ผิดมีลายเซ็นของบั๊กในโค้ด"
              f" — ดูรายละเอียดด้วย lawscan diff {args.ours} --defects")
    if args.out:
        from lawscan.diff import write_comparison
        from lawscan.where import report

        rows = write_comparison(args.expected, args.ours, args.out)
        print(report(
            f"{rows:,} ช่องที่ไม่ตรง",
            [args.out],
            notes=["กรอง ชนิด = ค่าเดียว ก่อน — นั่นคือของที่ผิดจริงและแก้ได้"],
            next_steps=[("เปิดดู", f"open {args.out}")],
        ))
    if args.xlsx:
        from lawscan.export.workbook import write as write_workbook
        from lawscan.where import report

        tally = write_workbook(
            args.expected, args.ours, args.xlsx, workdir=args.workdir
        )
        print(report(
            f"ตรง {tally.exact:,} · ใกล้เคียง {tally.partial:,} · ไม่ตรง {tally.wrong:,}"
            f"  (จาก {tally.scored:,} ช่องที่นับ)",
            [args.xlsx],
            notes=[
                "แผ่น สรุป บอกว่าช่องที่นับว่าตรง ตรงเพราะอะไร — "
                "เว้นวรรค เลขไทย OCR หรือลำดับรายการ",
                "แผ่น รายช่อง กรองคอลัมน์ ผล = ไม่ตรง ก่อน",
            ],
            next_steps=[("เปิดดู", f"open {args.xlsx}")],
        ))
    return 0


def _row(args: argparse.Namespace) -> int:
    """One document against its row in the reference, worst cell first.

    The loop this exists for: read the row, change one sentence in a prompt,
    re-ask that document alone, read the row again. ``--ask`` does the middle
    step so the three are one command instead of three.
    """
    from lawscan.rowcheck import report_rows, worst

    if not args.expected.exists():
        print(f"ไม่พบไฟล์ที่คาดหวัง: {args.expected}", file=sys.stderr)
        return 2

    ours = args.ours
    if args.ask:
        from datetime import datetime

        from lawscan.pipeline import scan

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        here = args.into / f"row-{stamp}"
        ours = here / "result.csv"
        paths = [args.pdfs / f"{number}.pdf" for number in args.documents]
        missing = [p for p in paths if not p.exists()]
        if missing:
            print(f"ไม่พบไฟล์ PDF: {', '.join(p.name for p in missing)}", file=sys.stderr)
            return 2
        code = scan(paths, out=ours, workdir=here / "documents", only=args.only,
                    text_from=args.text, batch=min(len(paths), 8))
        if code != 0:
            return code
        print(f"ถามใหม่แล้ว เก็บที่ {here}\n")

    if not ours.exists():
        print(f"ไม่พบไฟล์ผลลัพธ์: {ours}", file=sys.stderr)
        return 2

    documents = args.documents
    if not documents:
        documents = [number for number, _ in worst(args.expected, ours, args.limit)]
        print(f"ฉบับที่ห่างที่สุด {len(documents)} ฉบับ\n")

    print(report_rows(args.expected, ours, documents, show_all=args.all))
    return 0


def _record(args: argparse.Namespace) -> int:
    """Keep this run under tests/, in two folders stamped with the time."""
    from datetime import datetime

    from lawscan import testrun

    if not args.expected.exists():
        print(f"ไม่พบไฟล์ที่คาดหวัง: {args.expected}", file=sys.stderr)
        return 2

    stamp = args.stamp or datetime.now().strftime("%Y%m%d-%H%M")
    result_dir = args.tests / f"result40-{stamp}"
    compare_dir = args.tests / f"compare40-{stamp}"
    from lawscan.where import report

    print(testrun.write(args.ours, args.expected, result_dir, compare_dir,
                        note=args.note, workdir=args.workdir))
    print(report(
        "เก็บผลรอบนี้แล้ว",
        [result_dir, compare_dir],
        next_steps=[("เปิดดู", f"open {compare_dir}")],
    ))
    return 0


def _etl(args: argparse.Namespace) -> int:
    """Extract, transform, load, check — the ordinary day's command."""
    from lawscan.etl import run

    return run(
        args.path,
        into=args.into,
        expected=None if args.no_compare else args.expected,
        no_ocr=args.no_ocr,
        fresh=args.fresh,
        text=args.text,
        batch=args.batch,
    )


def _clean(args: argparse.Namespace) -> int:
    """Delete kept runs so nothing is reused. Says what it would do first."""
    from lawscan.clean import clear, find, report

    targets = find(args.tests, args.text if args.include_text else None)
    print(report(targets))
    if not targets:
        return 0
    if not args.yes:
        print("\nยังไม่ได้ลบ — ใส่ --yes เพื่อลบจริง")
        return 0
    gone = clear(targets, args.text if args.include_text else None)
    print(f"\nลบแล้ว {gone} รายการ")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lawscan", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("path", type=Path, nargs="+", metavar="PATH",
                       help="ไฟล์ PDF หรือโฟลเดอร์ ใส่ได้หลายอัน")
        p.add_argument("--no-ocr", action="store_true", help="ข้ามหน้าที่ไม่มีชั้นข้อความ")

    p_etl = sub.add_parser("etl", help="รันทั้งงาน: PDF → CSV → เทียบผล")
    p_etl.add_argument("path", type=Path, nargs="?", default=Path("pdfs"),
                       help="โฟลเดอร์ PDF (ค่าเริ่มต้น pdfs)")
    p_etl.add_argument("--into", type=Path, default=Path("tests"),
                       help="ที่เก็บผลแต่ละรอบ (ค่าเริ่มต้น tests)")
    p_etl.add_argument("--expected", type=Path, default=Path("data/expected.csv"))
    p_etl.add_argument("--no-compare", action="store_true", help="ไม่ต้องเทียบ")
    p_etl.add_argument("--fresh", action="store_true",
                       help="ถามโมเดลใหม่ทุกฉบับ ไม่ใช้คำตอบเดิม")
    p_etl.add_argument("--text", type=Path, default=Path("text"),
                       help="ที่เก็บข้อความ แปลงให้เองถ้ายังไม่มี (ค่าเริ่มต้น text)")
    p_etl.add_argument("--no-text-cache", dest="text", action="store_const", const=None,
                       help="อ่าน PDF ใหม่ทุกครั้ง ไม่ใช้ข้อความที่เก็บไว้")
    p_etl.add_argument("--batch", type=int, default=1, metavar="N",
                       help="ทำพร้อมกันครั้งละ N ฉบับ (ค่าเริ่มต้น 1)")
    p_etl.add_argument("--no-ocr", action="store_true")
    p_etl.set_defaults(run=_etl)

    p_ocr = sub.add_parser("ocr", help="แปลง PDF เป็นข้อความ เก็บไว้ใช้ซ้ำ")
    common(p_ocr)
    p_ocr.add_argument("--into", type=Path, default=Path("text"),
                       help="ที่เก็บข้อความ (ค่าเริ่มต้น text)")
    p_ocr.add_argument("--mode", choices=("text", "image"), default="text",
                       help="text = เฉพาะหน้าที่ไม่มีชั้นข้อความ · "
                            "image = อ่านภาพในหน้าด้วย (ช้ากว่า ได้แผนที่ แบบฟอร์ม)")
    p_ocr.set_defaults(run=_ocr)

    p_read = sub.add_parser("read", help="ดูข้อความที่ OCR อ่านได้")
    common(p_read)
    p_read.add_argument("--chars", type=int, default=1500)
    p_read.add_argument("--full", action="store_true")
    p_read.set_defaults(run=_read)

    p_rules = sub.add_parser("rules", help="ดูสิ่งที่กฎอ่านได้ ไม่เรียกโมเดล")
    common(p_rules)
    p_rules.set_defaults(run=_rules)

    p_ask = sub.add_parser("ask", help="ถามโมเดลหนึ่งคำถาม ดูคำตอบดิบ")
    p_ask.add_argument("question", help="identity · parent · audience · business · summary")
    common(p_ask)
    p_ask.add_argument("--show-prompt", action="store_true", help="พิมพ์ prompt ที่ส่งจริง")
    p_ask.set_defaults(run=_ask)

    p_scan = sub.add_parser("scan", help="รันทั้ง pipeline ออกเป็น CSV")
    common(p_scan)
    p_scan.add_argument("--out", type=Path, default=Path("out/result.csv"))
    p_scan.add_argument("--workdir", type=Path, default=Path("out"))
    p_scan.add_argument("--only", help="รันเฉพาะคำถามนี้ คั่นด้วยจุลภาค")
    p_scan.add_argument("--no-llm", action="store_true",
                        help="กฎอย่างเดียว ไม่เรียกโมเดล ไม่เสียเงิน")
    p_scan.add_argument("--reuse", action="store_true",
                        help="ใช้คำตอบโมเดลที่บันทึกไว้แล้ว รันเฉพาะกฎใหม่")
    p_scan.add_argument("--batch", type=int, default=1, metavar="N",
                        help="ทำพร้อมกันครั้งละ N ฉบับ")
    p_scan.add_argument("--text", type=Path, metavar="DIR", default=Path("text"),
                        help="ใช้ข้อความที่ lawscan ocr เก็บไว้ (ค่าเริ่มต้น text) "
                             "ฉบับที่ยังไม่มี จะอ่านจาก PDF ให้เอง")
    p_scan.add_argument("--no-text-cache", dest="text", action="store_const", const=None,
                        help="อ่าน PDF ใหม่ทุกครั้ง")
    p_scan.add_argument("--into", type=Path, metavar="DIR",
                        help="สร้างโฟลเดอร์ result40-<เวลา> ในนี้ และข้ามฉบับที่รอบก่อนทำแล้ว")
    p_scan.add_argument("--skip-done", type=Path, nargs="*", metavar="DIR",
                        help="ข้ามฉบับที่รันไว้แล้วใน tests/result40-* (ไม่ใส่ค่า = tests)")
    p_scan.set_defaults(run=_scan)

    p_diff = sub.add_parser("diff", help="เทียบ CSV ของเรากับไฟล์ที่คาดหวัง")
    p_diff.add_argument("ours", type=Path, nargs="?", default=Path("out/result.csv"))
    p_diff.add_argument("--expected", type=Path, default=Path("data/expected.csv"))
    p_diff.add_argument("--examples", action="store_true", help="แสดงตัวอย่างที่ไม่ตรง")
    p_diff.add_argument("--thresholds", action="store_true",
                        help="เงื่อนไขเชิงตัวเลขที่เอกสารระบุ แต่ตารางไม่ได้เก็บไว้")
    p_diff.add_argument("--text", type=Path, default=Path("text"), metavar="DIR",
                        help="โฟลเดอร์ข้อความสำหรับ --thresholds")
    p_diff.add_argument("--defects", action="store_true",
                        help="จัดกลุ่มช่องที่ผิดตามลายเซ็น แยกบั๊กโค้ดออกจากโมเดลอ่านผิด")
    p_diff.add_argument("--out", type=Path, help="เขียนไฟล์เทียบทีละช่อง")
    p_diff.add_argument("--xlsx", type=Path,
                        help="เขียนสมุดงาน Excel: แผ่นสรุป กับ แผ่นรายช่อง")
    p_diff.add_argument("--workdir", type=Path,
                        help="โฟลเดอร์หลักฐานรายฉบับ ใช้บอกที่มาของแต่ละช่อง")
    p_diff.set_defaults(run=_diff)

    p_row = sub.add_parser("row", help="ดูผลรายฉบับเทียบกับเฉลย ช่องที่ผิดขึ้นก่อน")
    p_row.add_argument("documents", nargs="*", metavar="เลขเอกสาร",
                       help="เช่น 100006 100021 · ไม่ใส่ = เอาฉบับที่ห่างที่สุด")
    p_row.add_argument("--ask", action="store_true",
                       help="ถามโมเดลใหม่เฉพาะฉบับเหล่านี้ก่อนเทียบ")
    p_row.add_argument("--only", help="ถามเฉพาะคำถามนี้ คั่นด้วยจุลภาค (ใช้กับ --ask)")
    p_row.add_argument("--ours", type=Path, default=Path("out/result.csv"),
                       help="CSV ที่จะเทียบ ถ้าไม่ได้ใช้ --ask")
    p_row.add_argument("--expected", type=Path, default=Path("data/expected.csv"))
    p_row.add_argument("--pdfs", type=Path, default=Path("pdfs"))
    p_row.add_argument("--text", type=Path, default=Path("text"))
    p_row.add_argument("--into", type=Path, default=Path("out"),
                       help="ที่เก็บรอบที่ถามใหม่ (ค่าเริ่มต้น out)")
    p_row.add_argument("--limit", type=int, default=5,
                       help="ไม่ระบุเลขเอกสาร จะเอากี่ฉบับที่ห่างที่สุด")
    p_row.set_defaults(run=_row)

    p_rec = sub.add_parser("record", help="เก็บผลรันนี้ไว้เป็นโฟลเดอร์")
    p_rec.add_argument("ours", type=Path, nargs="?", default=Path("out/result.csv"))
    p_rec.add_argument("--expected", type=Path, default=Path("data/expected.csv"))
    p_rec.add_argument("--tests", type=Path, default=Path("tests"))
    p_rec.add_argument("--workdir", type=Path,
                       help="โฟลเดอร์ documents/ ของรอบนั้น สำหรับคิดค่าใช้จ่าย")
    p_rec.add_argument("--stamp", help="ใช้เวลานี้แทนเวลาปัจจุบัน เช่น 20260805-1338")
    p_rec.add_argument("--note", default="", help="บันทึกว่ารันนี้ต่างจากรอบก่อนตรงไหน")
    p_rec.set_defaults(run=_record)

    p_clean = sub.add_parser("clean", help="ล้างผลรันเก่า ให้รอบหน้าไม่ข้ามอะไรเลย")
    p_clean.add_argument("--tests", type=Path, default=Path("tests"))
    p_clean.add_argument("--text", type=Path, default=Path("text"))
    p_clean.add_argument("--include-text", action="store_true",
                         help="ล้างข้อความที่ OCR ไว้ด้วย (ต้องแปลงใหม่)")
    p_clean.add_argument("--yes", action="store_true", help="ลบจริง")
    p_clean.set_defaults(run=_clean)

    parser.add_argument("-v", "--verbose", action="store_true",
                        help="แสดงรายละเอียดของไลบรารีด้วย")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="แสดงเฉพาะคำเตือนและผลลัพธ์")

    args = parser.parse_args(argv)

    from lawscan.progress import setup

    setup(verbose=args.verbose, quiet=args.quiet)
    return int(args.run(args))


if __name__ == "__main__":
    raise SystemExit(main())
