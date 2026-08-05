"""What a run cost, read back from what it wrote down.

Every answer file already records the tokens that produced it, so this reads
the run rather than instrumenting it: nothing has to be counted while the work
is happening, and a run recorded months ago can still be priced.

Two numbers matter and neither is the token count. Thai costs about 0.36
characters per token where English costs four, so a page of Thai is roughly
eleven times the tokens of the same page in English — which is why caching is
not an optimisation here but most of the bill. And output is billed at six
times input, so it is 3% of the tokens and a quarter of the money; a field in
the answer schema that fills no column is not free, it is expensive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

QUESTIONS = ("identity", "parent", "audience", "business", "summary")

#: USD per million tokens, gemini-3.5-flash standard tier, checked against
#: ai.google.dev/gemini-api/docs/pricing on 2026-08-05. Rates move; when they
#: do this is the one place to change, and every kept run can be repriced by
#: rerunning ``lawscan record`` against it.
PRICE_INPUT = 1.50
PRICE_CACHED = 0.15
PRICE_OUTPUT = 9.00
PRICE_CHECKED = "2026-08-05 · gemini-3.5-flash standard"

#: Only for the second column of the report. Nothing is billed in baht.
THB_PER_USD = 36.0


@dataclass
class Usage:
    """One run's tokens and what they cost."""

    documents: int = 0
    characters: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    #: (document, input_tokens) so the report can name the extremes — an
    #: average alone hides that one document can cost ten times another.
    per_document: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def fresh_tokens(self) -> int:
        """Input billed at full rate: everything the cache did not serve."""
        return max(0, self.input_tokens - self.cached_tokens)

    @property
    def cost_input(self) -> float:
        return self.fresh_tokens / 1e6 * PRICE_INPUT

    @property
    def cost_cached(self) -> float:
        return self.cached_tokens / 1e6 * PRICE_CACHED

    @property
    def cost_output(self) -> float:
        return self.output_tokens / 1e6 * PRICE_OUTPUT

    @property
    def cost(self) -> float:
        return self.cost_input + self.cost_cached + self.cost_output

    @property
    def cost_without_cache(self) -> float:
        """What the same run would have cost paying full rate throughout."""
        return self.input_tokens / 1e6 * PRICE_INPUT + self.cost_output

    def per(self, total: float) -> float:
        return self.cost / total if total else 0.0


def read(workdir: Path) -> Usage:
    """Add up one run's folders. Missing or unreadable files are skipped."""
    usage = Usage()
    for folder in sorted(p for p in workdir.glob("*") if p.is_dir()):
        text = folder / "text.txt"
        document_input = document_output = 0
        seen = False
        for question in QUESTIONS:
            answer = folder / f"{question}.json"
            if not answer.exists():
                continue
            try:
                cost = json.loads(answer.read_text(encoding="utf-8")).get("cost") or {}
            except ValueError:
                continue
            seen = True
            document_input += cost.get("input", 0)
            usage.cached_tokens += cost.get("cached", 0)
            document_output += cost.get("output", 0)
        if not seen:
            continue
        usage.documents += 1
        usage.input_tokens += document_input
        usage.output_tokens += document_output
        if text.exists():
            usage.characters += len(text.read_text(encoding="utf-8"))
        usage.per_document.append((folder.name, document_input, document_output))
    return usage


def report(usage: Usage) -> str:
    """The cost block that goes at the bottom of every run's summary."""
    if not usage.documents:
        return "ไม่มีข้อมูลการใช้งาน — รอบนี้ไม่ได้เรียกโมเดล"

    lines = [
        "การใช้งานและค่าใช้จ่าย",
        f"  ราคาที่ใช้คำนวณ: {PRICE_CHECKED}",
        f"  input ${PRICE_INPUT:.2f} · จาก cache ${PRICE_CACHED:.2f} · "
        f"output ${PRICE_OUTPUT:.2f} ต่อ 1M token",
        "",
        f"  {'input จ่ายเต็ม':<22}{usage.fresh_tokens:>12,} token   ${usage.cost_input:>7.3f}",
        f"  {'input จาก cache':<22}{usage.cached_tokens:>12,} token   ${usage.cost_cached:>7.3f}",
        f"  {'output':<22}{usage.output_tokens:>12,} token   ${usage.cost_output:>7.3f}",
        f"  {'รวม':<22}"
        f"{usage.input_tokens + usage.output_tokens:>12,} token   ${usage.cost:>7.3f}"
        f"   (~{usage.cost * THB_PER_USD:,.2f} บาท)",
        "",
        f"  ต่อฉบับ            ${usage.per(usage.documents):.4f}"
        f"   (~{usage.per(usage.documents) * THB_PER_USD:.2f} บาท)   {usage.documents} ฉบับ",
    ]

    if usage.characters:
        per_k = usage.cost / usage.characters * 1000
        lines.append(
            f"  ต่อ 1,000 ตัวอักษร  ${per_k:.4f}   (~{per_k * THB_PER_USD:.3f} บาท)"
            f"   {usage.characters:,} ตัวอักษร"
        )
        lines.append(
            f"  1 token ต่อ {usage.characters / usage.input_tokens:.2f} ตัวอักษรไทย"
            if usage.input_tokens else ""
        )

    saved = usage.cost_without_cache - usage.cost
    if saved > 0:
        share = saved / usage.cost_without_cache
        lines += [
            "",
            f"  ถ้าไม่มี cache      ${usage.cost_without_cache:.3f}"
            f"   → ประหยัดไป ${saved:.3f} ({share:.0%})",
        ]

    if usage.output_tokens and usage.cost:
        lines.append(
            f"  output เป็น {usage.output_tokens / (usage.input_tokens + usage.output_tokens):.0%}"
            f" ของ token แต่เป็น {usage.cost_output / usage.cost:.0%} ของค่าใช้จ่าย"
        )

    ranked = sorted(usage.per_document, key=lambda row: -row[1])
    if len(ranked) > 1:
        top = ", ".join(f"{name} {tokens:,}" for name, tokens, _ in ranked[:3])
        bottom = ", ".join(f"{name} {tokens:,}" for name, tokens, _ in ranked[-3:])
        lines += ["", f"  แพงสุด  {top}", f"  ถูกสุด  {bottom}"]

    for count in (240, 1_000):
        lines.append(
            f"  ประมาณ {count:,} ฉบับ    ${usage.per(usage.documents) * count:,.2f}"
            f"   (~{usage.per(usage.documents) * count * THB_PER_USD:,.0f} บาท)"
        )
    return "\n".join(line for line in lines if line is not None)
