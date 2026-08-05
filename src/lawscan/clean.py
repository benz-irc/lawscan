"""Throw away kept runs, so the next one measures instead of remembering.

This exists because reuse is the default and reuse is a trap when the thing
being measured has changed. A run that borrows yesterday's answers reports
yesterday's prompt, and the number looks like a measurement.

Two rules govern everything here. It only ever deletes folders matching the
names this program itself creates — a stray path under ``tests/`` is not its
business, and the test files that live in the same folder must survive. And it
does nothing at all unless told twice: once by naming what to clear, once with
``--yes``. Printing the list and stopping is the default because a wrong
guess here costs an hour of paid work.
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: Only these. Written as globs of this program's own naming, so nothing a
#: person happened to leave in the same folder is ever in scope.
RUN_FOLDERS = ("result40-*", "compare40-*")

#: The extracted text. Cleared only when asked for by name: it is the
#: expensive half, it is deterministic, and a changed prompt is no reason to
#: pay for OCR again.
TEXT_FILES = ("*.json", "*.txt")


def _size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def find(tests: Path, text: Path | None = None) -> list[tuple[Path, int]]:
    """What clearing would remove, largest first."""
    found: list[tuple[Path, int]] = []
    if tests.is_dir():
        for pattern in RUN_FOLDERS:
            for folder in tests.glob(pattern):
                if folder.is_dir():
                    found.append((folder, _size(folder)))
    if text is not None and text.is_dir():
        kept = [f for pattern in TEXT_FILES for f in text.glob(pattern)]
        if kept:
            found.append((text, sum(f.stat().st_size for f in kept)))
    return sorted(found, key=lambda pair: -pair[1])


def clear(targets: list[tuple[Path, int]], text: Path | None) -> int:
    """Remove them. Returns how many went."""
    gone = 0
    for path, _ in targets:
        if text is not None and path == text:
            # The text folder is emptied of what this program wrote, not
            # deleted: a person may keep notes in there and the folder itself
            # is not ours to remove.
            for pattern in TEXT_FILES:
                for file in path.glob(pattern):
                    file.unlink()
        else:
            shutil.rmtree(path)
        gone += 1
    return gone


def report(targets: list[tuple[Path, int]]) -> str:
    if not targets:
        return "ไม่มีอะไรให้ล้าง"
    lines = [f"จะลบ {len(targets)} รายการ:"]
    for path, size in targets:
        lines.append(f"  {size / 1_048_576:>7.1f} MB  {path}")
    total = sum(size for _, size in targets)
    lines.append(f"  {total / 1_048_576:>7.1f} MB  รวม")
    return "\n".join(lines)
