"""Checks to run on a freshly OCR'd corpus, before paying to scan it.

Each subcommand prints numbers rather than a verdict: the point is to see how
far off the reading is, not to be told it passed.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
NUMBER = re.compile(r"\d+")
#: Spacing the recogniser drops into the middle of one number.
INSIDE = re.compile(r"(?<=\d)\s+(?=\d)")
THAI_LETTER = re.compile(r"[ก-๙]")

#: Faults already met on this corpus. Each one is a shape that cannot be a
#: correct reading, so a hit is a defect and not a judgement call.
FAULTS: dict[str, re.Pattern[str]] = {
    "ตัวอักษรแทนเลข (หน้า ด)": re.compile(r"(?:เล่ม|ตอนที่|หน้า|ข้อ|มาตรา)\s+[ดo](?![ก-ฮะ-๎])"),
    "ปีหายหลักแรกหลังทับ (/๕๖๘)": re.compile(r"(?<=/)[๕๖][๐-๙]{2}(?![๐-๙])|(?<=/)[56]\d{2}(?!\d)"),
    "ตัวเศษหน้าทับหาย (ที่ /๒๕๖๘)": re.compile(r"(?<![๐-๙\d])/[๐-๙\d]"),
    "จุดทศนิยมหาย (๑๐,๐๘๘๘๑)": re.compile(r"[๐-๙\d],[๐-๙\d]{4,}"),
    "เลขนำหน้าข้อเป็นตัวอักษร (ด.)": re.compile(r"(?:^|\n)\s*[ดo]\s*\.\s"),
    "วรรณยุกต์หาย (เลือกตัง)": re.compile(r"เลือกตัง|จัดตัง|เรือง(?!แสง|รอง)|เพิมเติม|ระเบยบ"),
    "ปีรูปผิด (25205)": re.compile(r"(?<!\d)25\d{3,4}(?!\d)"),
}


def _pages(folder: Path):
    for record in sorted(folder.glob("*.json")):
        yield record, json.loads(record.read_text(encoding="utf-8"))["pages"]


def corpus(text_dir: str, pdf_dir: str) -> int:
    """Every PDF read, every page kept, nothing silently short."""
    import fitz

    text, pdfs = Path(text_dir), Path(pdf_dir)
    files = sorted(pdfs.glob("*.pdf"))
    want = {f.stem: fitz.open(f).page_count for f in files}
    seen = {record.stem: len(pages) for record, pages in _pages(text)}
    missing = sorted(set(want) - set(seen))
    short = sorted(n for n in set(want) & set(seen) if seen[n] != want[n])
    thin = []
    for record in sorted(text.glob("*.txt")):
        body = record.read_text(encoding="utf-8")
        if len(body) < 200 or len(THAI_LETTER.findall(body)) / max(1, len(body)) < 0.35:
            thin.append(record.stem)
    print(f"PDF {len(want)} ฉบับ · อ่านแล้ว {len(seen)} ฉบับ")
    print(f"หน้า ต้องการ {sum(want.values()):,} · ได้ {sum(seen.values()):,}")
    print(f"ไม่ได้อ่านเลย   : {len(missing)} {missing[:6]}")
    print(f"หน้าไม่ครบ      : {len(short)} {short[:6]}")
    print(f"อ่านได้น้อยผิดปกติ: {len(thin)} {thin[:6]}")
    return 1 if (missing or short or thin) else 0


def _plain(pdf: Path) -> str | None:
    """The PDF's own text where it is readable, which is truth. Else None."""
    import fitz

    body = "".join(page.get_text() for page in fitz.open(pdf))
    if len(body) < 200 or "ราชกิจจานุเบกษา" not in body:
        return None
    return body if len(THAI_LETTER.findall(body)) / len(body) > 0.55 else None


def digits(pdf_dir: str, out: str = "ocr-misses.csv") -> int:
    """Read the pages whose text is known, and see what the reader loses."""
    import fitz
    from lawscan.ocr import read as reader

    found = lost = 0
    rows: list[tuple[str, int, str, str]] = []
    checked = 0
    for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
        truth = _plain(pdf)
        if truth is None:
            continue
        checked += 1
        for number, page in enumerate(fitz.open(pdf), start=1):
            printed = INSIDE.sub("", page.get_text().translate(THAI_TO_ARABIC))
            want = set(NUMBER.findall(printed))
            if not want:
                continue
            said = reader._recognise(page).translate(THAI_TO_ARABIC)
            got = set(NUMBER.findall(INSIDE.sub("", said)))
            found += len(want & got)
            lost += len(want - got)
            for value in sorted(want - got):
                near = re.search(r".{0,26}(?<!\d)" + re.escape(value) + r"(?!\d).{0,12}", printed)
                rows.append((pdf.stem, number, value,
                             re.sub(r"\s+", " ", near.group(0)) if near else ""))
    if not checked:
        print("ไม่มีฉบับไหนมีชั้นข้อความที่อ่านออก — วัดแบบนี้ไม่ได้กับคลังนี้")
        return 0
    with Path(out).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["เอกสาร", "หน้า", "เลขที่หาย", "บริบทในต้นฉบับ"])
        writer.writerows(rows)
    print(f"เทียบกับ {checked} ฉบับที่ชั้นข้อความอ่านออก")
    print(f"   อ่านเลขเจอ {found} · พลาด {lost} = {found / max(1, found + lost):.1%}")
    print(f"   รายการทุกจุดที่พลาดอยู่ใน {out}")
    print(f"   ฉบับที่พลาดมากสุด: {Counter(r[0] for r in rows).most_common(5)}")
    return 0


def faults(text_dir: str) -> int:
    """The faults already met, counted over the finished corpus."""
    tally: Counter[str] = Counter()
    where: dict[str, list[str]] = {}
    for record, pages in _pages(Path(text_dir)):
        body = "\n".join(page["text"] for page in pages)
        for name, pattern in FAULTS.items():
            hits = len(pattern.findall(body))
            if hits:
                tally[name] += hits
                where.setdefault(name, []).append(record.stem)
    if not tally:
        print("ไม่พบอาการที่รู้จักเลย")
        return 0
    for name, count in tally.most_common():
        print(f"  {count:>5}  {name}   {where[name][:4]}")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
    if len(sys.argv) < 2 or sys.argv[1] not in ("corpus", "digits", "faults"):
        print(__doc__)
        print("ใช้: check.py corpus <ข้อความ> <pdf> | digits <pdf> | faults <ข้อความ>")
        raise SystemExit(2)
    raise SystemExit({"corpus": corpus, "digits": digits, "faults": faults}
                     [sys.argv[1]](*sys.argv[2:]))
