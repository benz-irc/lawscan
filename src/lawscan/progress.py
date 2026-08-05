"""What the program is doing, while it does it.

A run of 240 documents takes an hour, and for most of that hour the only
question worth answering is "what is it doing right now, to which file, with
whose help". Before this, the answer was one line per document and everything
else was library noise — httpx announcing a POST, the SDK announcing a feature
flag — none of which says which stage is running or what it cost.

The format is one line per step, indented under the document it belongs to:

    [19/91] 100019.pdf
      อ่าน       pymupdf      6 หน้า · text-layer 4 · ocr 2 · 4,383 ตัวอักษร   0.05 วิ
      กฎ         lawscan      12 ช่อง · ระเบียบ · ⚪️ เทา · ⚠ 2 หน้าเป็นภาพ      0.01 วิ
      identity   gemini-3.5   เข้า 3,258 (cache 1,150) · ออก 55                5.2 วิ
      รวม        merge        21/33 ช่อง · กฎ 9 · โมเดล 12

Every line names the service that did the work, because "slow" and "expensive"
belong to different ones and the log is where a person decides which to chase.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("lawscan.progress")

#: Lines belonging to the document this thread is working on. Without it, ten
#: documents in flight interleave their steps and the log becomes a list of
#: facts with nothing to attach them to. Each thread collects its own and the
#: whole block is printed at once when the document is done.
_pending = threading.local()
_speak = threading.Lock()

#: Libraries that narrate their own internals at INFO. Every one of these lines
#: is about a mechanism the person running a scan did not ask about, and they
#: outnumber the ones that matter about ten to one.
NOISY = ("httpx", "httpcore", "google", "google_genai", "urllib3", "PIL")

_STEP = 10
_SERVICE = 12


def setup(verbose: bool = False, quiet: bool = False) -> None:
    """Send our own lines to the terminal and the libraries' to silence."""
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr, force=True)
    for name in NOISY:
        # WARNING, not CRITICAL: a library that reports a real failure should
        # still be heard. It is the running commentary that is unwanted.
        logging.getLogger(name).setLevel(logging.WARNING)


def document(position: int, total: int, name: str, note: str = "") -> None:
    line = f"[{position}/{total}] {name}" + (f"  {note}" if note else "")
    if getattr(_pending, "lines", None) is None:
        log.info(line)
    else:
        _pending.lines.append(line)


def step(name: str, service: str, detail: str, seconds: float | None = None) -> None:
    """One stage of one document: what ran, who ran it, what came out."""
    timing = f"   {seconds:.2f} วิ" if seconds is not None else ""
    line = f"  {name:<{_STEP}} {service:<{_SERVICE}} {detail}{timing}"
    if getattr(_pending, "lines", None) is None:
        log.info(line)
    else:
        _pending.lines.append(line)


@contextmanager
def grouped():
    """Hold this thread's lines and print them as one block at the end.

    Used only when documents run side by side. On one at a time the lines go
    straight out, because seeing a step start is worth more than seeing the
    document's steps together.
    """
    _pending.lines = []
    try:
        yield
    finally:
        lines, _pending.lines = _pending.lines, None
        if lines:
            with _speak:
                log.info("\n".join(lines))


@contextmanager
def timed(name: str, service: str):
    """Run a step and report it with however long it took.

    The detail is filled in by the step itself, after it knows what it found —
    which is why this yields a list rather than taking a string: the caller
    cannot describe the result before producing it.
    """
    said: list[str] = []
    started = time.perf_counter()
    try:
        yield said
    finally:
        step(name, service, said[0] if said else "", time.perf_counter() - started)
