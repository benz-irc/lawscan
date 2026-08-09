"""One question put to the model, and what came back.

The old system had a single "extraction" that answered everything at once and
was impossible to reason about: a prompt of sixty thousand characters, five
schemas, and no way to see which part of it produced a wrong cell. This is the
opposite. A Question is one file on disk, one schema, one call, and one answer
you can print.

The point is not modularity for its own sake. It is that when a column is
wrong, you can run the one question that fills it, read the prompt that was
actually sent, and see the answer before anything merged it — in seconds,
without a database or a pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parents[3] / "prompts"


@dataclass(frozen=True, slots=True)
class Question:
    """A prompt file, the shape of its answer, and which cells it fills.

    ``fills`` is here so the pipeline can say where a cell came from without
    anyone maintaining a separate map — and so a question that fills nothing is
    visibly dead code rather than quietly wasted money.
    """

    name: str
    #: Column names in the export this question is responsible for.
    fills: tuple[str, ...]
    #: JSON Schema the answer must match.
    schema: dict[str, Any]
    #: How much of the document's opening to send. None sends all of it.
    chars: int | None = None
    #: How much of its ending to send as well. A Thai instrument states its
    #: commencement, its signature and its stated reason at the end, and a
    #: budget that keeps only the opening loses all three on a long document.
    tail_chars: int = 0

    @property
    def path(self) -> Path:
        return PROMPTS / f"{self.name}.md"

    def prompt(self, lists: dict[str, str] | None = None) -> str:
        """The instruction as it will be sent, with any list filled in.

        Read from disk on every call. A prompt is edited far more often than
        the code around it, and requiring a restart to see a change is how a
        person ends up measuring the wrong version.

        A placeholder with no list behind it becomes empty rather than staying
        in the text: an instruction that ships ``{{agencies}}`` to the model
        asks it to guess what was meant, and it will.
        """
        text = self.path.read_text(encoding="utf-8")
        for name in re.findall(r"\{\{(\w+)\}\}", text):
            text = text.replace(f"{{{{{name}}}}}", (lists or {}).get(name, ""))
        return text


@dataclass(slots=True)
class Answer:
    """What one question cost and what it returned."""

    question: str
    document: str
    ok: bool
    value: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    #: Which model produced it. Written down because the answer outlives the
    #: run: a folder kept in June cannot be priced in August unless it says
    #: what answered it, and two models is the only way to find out whether the
    #: cheap one is good enough.
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    duration_ms: int = 0

    @property
    def billed_input(self) -> float:
        """Input tokens at their real weight — cached ones cost about a quarter."""
        return (self.input_tokens - self.cached_tokens) + self.cached_tokens * 0.25

    def write(self, directory: Path) -> Path:
        """Save the raw answer beside the document it came from.

        A failure never overwrites a success. The answers on disk are what a
        rerun resumes from, so an expired key or a dropped connection would
        otherwise destroy an hour of paid work on its way past — and the run
        that comes after has no way to know the good answer was ever there.
        The failure is still written where nothing is, so the gap is visible.
        """
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.question}.json"
        if not self.ok and path.exists():
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("ok"):
                    log.warning(
                        "%s: เก็บคำตอบเดิมที่สำเร็จไว้ ไม่เขียนทับด้วยคำตอบที่ล้ม", path.name
                    )
                    return path
            except ValueError:
                pass
        path.write_text(
            json.dumps(
                {
                    "question": self.question,
                    "model": self.model,
                    "ok": self.ok,
                    "error": self.error,
                    "value": self.value,
                    "cost": {
                        "input": self.input_tokens,
                        "cached": self.cached_tokens,
                        "output": self.output_tokens,
                        "billed_input": round(self.billed_input),
                        "ms": self.duration_ms,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path


class Timer:
    """Wall clock for one call, in milliseconds."""

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = int((time.perf_counter() - self._start) * 1000)
