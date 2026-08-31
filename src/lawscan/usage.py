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


@dataclass(frozen=True, slots=True)
class Price:
    """USD per million tokens, one model's standard tier."""

    input: float
    cached: float
    output: float


#: Checked against ai.google.dev/gemini-api/docs/pricing on 2026-08-06. Rates
#: move; when they do this is the one place to change, and every kept run can
#: be repriced by rerunning ``lawscan record`` against it.
#:
#: Priced per model rather than once for all of them because the reason to run
#: a second model is to find out what it costs — and a table with one row
#: answers that question with the price of the model you were already using.
#: The pro tiers charge double above a 200,000-token prompt. The longest
#: document in the corpus sends about 28,000, so the cheaper half of every pro
#: row is the one that applies here — and if that stops being true the bill
#: doubles quietly, which is what this note is for.
PRICES = {
    "gemini-3.6-flash": Price(1.50, 0.15, 7.50),
    "gemini-3.5-flash": Price(1.50, 0.15, 9.00),
    "gemini-3.5-flash-lite": Price(0.30, 0.03, 2.50),
    "gemini-3.1-pro-preview": Price(2.00, 0.20, 12.00),
    "gemini-3.1-flash-lite": Price(0.25, 0.025, 1.50),
    "gemini-3-flash-preview": Price(0.50, 0.05, 3.00),
    "gemini-2.5-pro": Price(1.25, 0.125, 10.00),
    "gemini-2.5-flash": Price(0.30, 0.03, 2.50),
    "gemini-2.5-flash-lite": Price(0.10, 0.01, 0.40),
    "gemini-2.0-flash": Price(0.10, 0.025, 0.40),
    # No context caching on this one. The cached rate is written equal to the
    # input rate rather than left cheap, because the prompt is re-sent in full
    # on every document and billed as if it had never been seen before.
    "gemini-2.0-flash-lite": Price(0.075, 0.075, 0.30),
    # The OpenAI-compatible providers ``llm/openai_chat.py`` can reach. They
    # belong in the same table because the reason to run one is to find out
    # what it costs, and until these rows existed every gpt run was priced at
    # the Gemini default above — 26× the real bill across a day of testing.
    #
    # Checked 2026-08-08 · developers.openai.com/api/docs/pricing
    # Checked against openai.com/api/pricing on 2026-08-19. This row was the
    # one missing while it was the one in use: ``price_of`` falls back to the
    # Gemini default for a name it does not know, so every run of the day was
    # reported at another provider's rates.
    "gpt-5.4-mini": Price(0.75, 0.075, 4.50),
    "gpt-5": Price(1.25, 0.125, 10.00),
    "gpt-5-mini": Price(0.25, 0.025, 2.00),
    "gpt-5-nano": Price(0.05, 0.005, 0.40),
    # Checked 2026-08-08 · api-docs.deepseek.com/quick_start/pricing. The cache
    # hit rate is a fiftieth of the miss rate, the widest gap of any provider
    # here, which matters because 62% of this corpus's input is cached.
    "deepseek-chat": Price(0.14, 0.0028, 0.28),
    "deepseek-reasoner": Price(0.435, 0.003625, 0.87),
    # Checked 2026-08-08 · platform.kimi.ai/docs/pricing/chat-k3
    "kimi-k3": Price(3.00, 0.30, 15.00),
}

#: Held prompts are billed by the hour whether or not anything reads them, and
#: this is not counted above: the five prompts come to 18,589 tokens, so an
#: hour of them is $0.019 — under 2% of a flash run and 8% of a lite one. It is
#: the one cost that does not fall when the model gets cheaper.
PRICE_CACHE_STORAGE = 1.00

#: What answered a run that does not say. Every folder kept before the model
#: was written down was flash, so this is a fact about those runs and not a
#: guess about future ones.
DEFAULT_MODEL = "gemini-3.5-flash"

PRICE_CHECKED = "2026-08-06 · standard tier"
PRICE_INPUT = PRICES[DEFAULT_MODEL].input
PRICE_CACHED = PRICES[DEFAULT_MODEL].cached
PRICE_OUTPUT = PRICES[DEFAULT_MODEL].output

#: Only for the second column of the report. Nothing is billed in baht.
THB_PER_USD = 36.0


def price_of(model: str) -> Price:
    """The rates for a model, or the default's when the rate is unpublished.

    Guessing is the wrong answer and refusing to price the run is worse — a
    run with no number attached is a run nobody reads. So it is priced, and
    ``report`` says out loud that the rate is borrowed.

    How wrong a borrowed rate can be is worth knowing before trusting one: a
    day of gpt-5-nano runs priced at the default came to 75 baht against a real
    bill of 2.89. The borrowed number is the right order of magnitude only when
    the models are, and models from two providers rarely are.
    """
    return PRICES.get(model) or PRICES[DEFAULT_MODEL]


@dataclass
class Tokens:
    """What one model was asked for, within one run."""

    input: int = 0
    cached: int = 0
    output: int = 0

    @property
    def fresh(self) -> int:
        return max(0, self.input - self.cached)


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
    #: The same tokens split by what answered. A run can hold two models: a
    #: document borrowed from an earlier run keeps the answer it was given.
    by_model: dict[str, Tokens] = field(default_factory=dict)

    @property
    def models(self) -> list[str]:
        return sorted(self.by_model) or [DEFAULT_MODEL]

    def _buckets(self) -> dict[str, Tokens]:
        return self.by_model or {
            DEFAULT_MODEL: Tokens(self.input_tokens, self.cached_tokens, self.output_tokens)
        }

    @property
    def fresh_tokens(self) -> int:
        """Input billed at full rate: everything the cache did not serve."""
        return max(0, self.input_tokens - self.cached_tokens)

    @property
    def cost_input(self) -> float:
        return sum(t.fresh / 1e6 * price_of(m).input for m, t in self._buckets().items())

    @property
    def cost_cached(self) -> float:
        return sum(t.cached / 1e6 * price_of(m).cached for m, t in self._buckets().items())

    @property
    def cost_output(self) -> float:
        return sum(t.output / 1e6 * price_of(m).output for m, t in self._buckets().items())

    @property
    def cost(self) -> float:
        return self.cost_input + self.cost_cached + self.cost_output

    def cost_of(self, model: str) -> float:
        """What one model's share of this run cost."""
        tokens = self._buckets().get(model)
        if tokens is None:
            return 0.0
        price = price_of(model)
        return (tokens.fresh * price.input + tokens.cached * price.cached
                + tokens.output * price.output) / 1e6

    @property
    def cost_without_cache(self) -> float:
        """What the same run would have cost paying full rate throughout."""
        fresh = sum(t.input / 1e6 * price_of(m).input for m, t in self._buckets().items())
        return fresh + self.cost_output

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
                stored = json.loads(answer.read_text(encoding="utf-8"))
            except ValueError:
                continue
            cost = stored.get("cost") or {}
            seen = True
            document_input += cost.get("input", 0)
            usage.cached_tokens += cost.get("cached", 0)
            document_output += cost.get("output", 0)
            tokens = usage.by_model.setdefault(stored.get("model") or DEFAULT_MODEL, Tokens())
            tokens.input += cost.get("input", 0)
            tokens.cached += cost.get("cached", 0)
            tokens.output += cost.get("output", 0)
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
    ]
    for model in usage.models:
        rates = price_of(model)
        lines.append(
            f"  {model:<24}input ${rates.input:.2f} · จาก cache ${rates.cached:.2f} · "
            f"output ${rates.output:.2f} ต่อ 1M token"
        )
        if model not in PRICES:
            lines.append(f"  {'':<24}⚠ ยังไม่มีราคาของรุ่นนี้ คิดด้วยเรตของ {DEFAULT_MODEL}")

    if len(usage.by_model) > 1:
        lines.append("")
        for model in usage.models:
            tokens = usage.by_model[model]
            lines.append(
                f"  {model:<24}{tokens.input + tokens.output:>12,} token"
                f"   ${usage.cost_of(model):>7.3f}"
            )

    lines += [
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
