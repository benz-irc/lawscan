"""Where a command put what it made, said the same way every time.

Every command here writes files, and a command whose output cannot be found
has not finished. The rule is one block at the end: the absolute path, what is
in it, and the command that reads it next — so the person running it never has
to guess and never has to scroll back past a hundred progress lines.

Absolute, because a relative path is only meaningful from the directory the
command happened to run in, and the person reading it may be somewhere else.
"""

from __future__ import annotations

from pathlib import Path


def _size(path: Path) -> str:
    if path.is_file():
        total = path.stat().st_size
    else:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if total < 1_048_576:
        return f"{total / 1024:.0f} KB"
    return f"{total / 1_048_576:.1f} MB"


def report(title: str, paths: list[Path], *, notes: list[str] = (), next_steps: list[tuple[str, str]] = ()) -> str:
    """One block naming what was written and what reads it next."""
    lines = ["", title]
    for path in paths:
        if path.exists():
            lines.append(f"  {path.resolve()}   ({_size(path)})")
        else:
            lines.append(f"  {path.resolve()}")
    lines.extend(f"  {note}" for note in notes)
    if next_steps:
        lines.append("")
        width = max(len(label) for label, _ in next_steps)
        lines.extend(f"  {label:<{width}}  {command}" for label, command in next_steps)
    return "\n".join(lines)
