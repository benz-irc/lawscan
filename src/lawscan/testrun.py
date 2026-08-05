"""One run of the forty, kept.

A number on a terminal is gone when the window closes, and a run that cannot be
reopened cannot be argued with. Every run writes a folder: what came out, what
it was compared against, and what the two disagreed about — enough for someone
who was not here to check the claim without rerunning anything.

The folder name carries the time because the point is comparison across runs.
Two folders side by side answer "did that change help", which is the only
question worth asking about a change.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from lawscan import usage
from lawscan.diff import compare, report, write_comparison

csv.field_size_limit(10**8)


def _column_table(result) -> list[list[str]]:
    rows = [["คอลัมน์", "ตรงเป๊ะ", "ตรงบางส่วน", "ไม่ตรง", "ว่างทั้งคู่", "ได้กี่ %"]]
    for column in sorted(
        result.columns.values(), key=lambda c: (-(c.wrong + 0.5 * c.partial), c.name)
    ):
        scored = column.scored
        share = f"{column.credit / scored:.0%}" if scored else "—"
        rows.append([
            column.name.strip(),
            str(column.exact), str(column.partial), str(column.wrong),
            str(column.both_blank), share,
        ])
    return rows


def write(
    ours: Path, expected: Path, result_dir: Path, compare_dir: Path, *,
    note: str = "", workdir: Path | None = None,
) -> str:
    """Both folders, filled. Returns the summary text for printing."""
    result_dir.mkdir(parents=True, exist_ok=True)
    compare_dir.mkdir(parents=True, exist_ok=True)

    outcome = compare(expected, ours)
    summary = report(outcome, examples=False)
    if note:
        summary = f"{note}\n\n{summary}"

    # The reference copy travels with the comparison. A comparison that points
    # at a file which has since been regenerated is not evidence of anything.
    shutil.copy(expected, compare_dir / "expected.csv")
    shutil.copy(ours, compare_dir / "ours.csv")

    cells = write_comparison(expected, ours, compare_dir / "cells.csv")

    with (compare_dir / "columns.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(_column_table(outcome))

    with (compare_dir / "documents.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["เอกสาร", "ช่องที่นับ", "คะแนน", "ได้กี่ %"])
        for document, (credit, scored) in sorted(
            outcome.per_document.items(), key=lambda kv: kv[1][0] / (2 * kv[1][1]) if kv[1][1] else 0
        ):
            share = f"{credit / (2 * scored):.0%}" if scored else "—"
            writer.writerow([document, scored, f"{credit / 2:g}", share])

    # What it cost, every time. A score without a price is half the decision,
    # and the numbers are already on disk in the answer files — nothing has to
    # be measured while the run is happening.
    spend = usage.read(workdir or result_dir / "documents")
    with (compare_dir / "usage.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["เอกสาร", "input token", "output token"])
        for document, tokens_in, tokens_out in sorted(spend.per_document):
            writer.writerow([document, tokens_in, tokens_out])

    text = (
        f"{summary}\n\n{cells:,} ช่องที่ไม่ตรง อยู่ใน cells.csv\n"
        f"\n{'─' * 64}\n{usage.report(spend)}\n"
    )
    (compare_dir / "summary.txt").write_text(text, encoding="utf-8")
    (result_dir / "summary.txt").write_text(text, encoding="utf-8")
    return text
