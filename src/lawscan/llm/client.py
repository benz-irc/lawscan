"""The one place that talks to a model.

Everything model-shaped lives here: the key, the retries, the schema
enforcement, the cache. A question knows its prompt and its schema; it does not
know which provider answers it, and nothing outside this file constructs a
request.

Two providers, chosen by the model's name. Gemini is below, in full, because
its cache is a resource that has to be created and renewed. Everything that
speaks the OpenAI chat API — GPT, DeepSeek, Kimi — is in ``openai_chat``,
where the cache needs no managing and the schema is enforced rather than
requested. ``LAWSCAN_MODEL=gpt-5-nano`` is the whole switch.

Caching is not an optimisation bolted on. The business question carries a
taxonomy of several hundred codes, identical on every call, and re-sending it
per document was two thirds of the whole bill. Cached, the model sees the same
prompt to the character — so the answers do not move — and the instruction is
billed once.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from lawscan.llm import openai_chat
from lawscan.llm.question import Answer, Question, Timer
from lawscan.ocr.budget import fit
from lawscan.ocr.read import Document
from lawscan.rules import agencies

log = logging.getLogger(__name__)

#: Sampling temperature for every provider. Extraction wants the same answer
#: to the same question, and measurement wants the difference between two runs
#: to be the change under test rather than the sampler.
TEMPERATURE = 0.0

#: Chosen by measurement, not by version number. On forty scored documents,
#: one prompt, the same text, the same day:
#:
#:     gpt-5.4-mini   53.2%      $0.056 / 40 documents
#:     gpt-5.5        51.4%      $0.058
#:     gpt-5.4        50.9%      $0.074
#:     gpt-5.6-sol    48.0%      $0.054
#:     gpt-5-nano     42.0%      $0.019
#:
#: Bigger is not better here and newer is not better either: the two models
#: above mini in every list both score below it. Nano is a quarter of the price
#: and eleven points worse, and those eleven points are the columns that need a
#: judgement — business codes, tags, the audience. On the five-question path
#: the same swap moved 63.3% to 68.7%.
#: ``gemini-3.1-flash-lite`` is the default because every run this year has
#: set it on the command line anyway, and the value it was overriding could
#: not answer at all: the OpenAI account has no credits, so a plain
#: ``lawscan scan`` failed on every document with a 429 rather than doing
#: anything. Compared against ``gemini-3.1-pro-preview`` on the same twenty-two
#: documents and the same prompts, pro reads the core column better — 60%
#: against 49%, and 80 of the key's codes against 63 — for 44 baht a run
#: against 5, and about three times the wall clock. The operator chose the
#: cheaper one; pro is a scan away with ``LAWSCAN_MODEL`` when a run is going
#: out for review.
#: ``or`` and not ``get``'s default: ``LAWSCAN_MODEL=`` set to nothing is how
#: a shell says "use the default", and reading it literally asks the provider
#: for a model with no name.
MODEL = os.environ.get("LAWSCAN_MODEL") or "gemini-3.1-flash-lite"

#: Only to skip prompts that obviously cannot be cached. The real floor is the
#: provider's — "Cached content is too small. total_token_count=202,
#: min_total_token_count=1024" — and it is stated in tokens, which this cannot
#: count without asking. So this is set well below where Thai crosses 1,024
#: tokens (about 2.9 characters to the token) and the API is left to decide.
#:
#: A refusal is remembered, so being wrong here costs one failed call per
#: prompt per run and never a wrong answer. Being wrong the other way — a
#: threshold set by guess, above a prompt the API would have accepted — costs
#: full rate on every document, which is what happened: two prompts sat above
#: the provider's floor and below a number picked out of the air, and paid for
#: the same unchanged instruction 91 times each.
CACHE_MIN_CHARS = 2_400

#: An hour covers a run of any size. Renewed as it approaches rather than after
#: it lapses — a name kept past its time is not merely useless, the provider
#: deletes the cache and every request quoting it fails.
CACHE_TTL = 3_600
CACHE_RENEW_MARGIN = 300

#: How many times to ask again when the answer does not fit the schema. The
#: model usually gets it right the second time; a third is rarely different.
RETRIES = 2

#: How long one request may take before it is abandoned, in seconds.
#:
#: There was no timeout here, and the cost of that was a run of 91 documents
#: that stopped at document 19 and sat for forty-two minutes holding an
#: established connection at zero percent CPU, waiting on a read that was never
#: going to return. Nothing in the log said so; the run simply stopped being a
#: run. The value is generous — the business question with its taxonomy takes
#: thirteen seconds on a good day — because the point is to break a stall, not
#: to cut off slow but living work.
REQUEST_TIMEOUT = 180

#: Where the lists a prompt can name live. A prompt writes ``{{agencies}}``
#: and the file ``data/agencies.txt`` fills it — kept out of the prompt itself
#: because these run to tens of kilobytes, and because a list the operator
#: maintains should be editable without touching an instruction.
DATA = Path(__file__).resolve().parents[3] / "data"


#: Where the key is looked for, in order. The environment first, because that
#: is what a server sets; then a file beside the code, because that is what a
#: person has. Supporting only the first meant a run started from an ordinary
#: shell failed on every document and wrote 51 rows with the file number filled
#: in and nothing else — a result that looks like an answer.
KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def find_key(model: str = "") -> str:
    """The API key for whichever provider serves ``model``.

    Never logged, never printed, never written anywhere by this program.

    The model decides which key is wanted, so a machine holding keys for three
    providers at once asks for the right one instead of the first one — and
    switching models never means also remembering to switch an environment
    variable.
    """
    provider = openai_chat.provider_for(model or MODEL)
    if provider is not None:
        return openai_chat.find_key(provider, ENV_FILE)

    for name in KEY_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() in KEY_NAMES:
                return value.strip().strip("\"'")
    return ""


def key_names(model: str = "") -> tuple[str, ...]:
    """What the key for this model is called, for an error message to name."""
    provider = openai_chat.provider_for(model or MODEL)
    return provider.keys if provider is not None else KEY_NAMES


def key_is_available(model: str = "") -> bool:
    """Whether a run that needs the model can start at all.

    Checked once before the first document rather than discovered on each of
    them. The difference matters: a missing key is one message at the top, not
    two hundred warnings scrolling past and a CSV that is mostly empty.
    """
    return bool(find_key(model))


class Client:
    """Ask questions, get validated answers, pay as little as possible."""

    def __init__(self, model: str = MODEL) -> None:
        self.model = model
        self._client: Any = None
        #: prompt hash -> (cache name or None, expiry). None means the provider
        #: refused; remembered so it is asked once, not once per document.
        self._caches: dict[str, tuple[str | None, float]] = {}
        #: Held while a cache is created or the connection is opened. Ten
        #: documents starting at once would otherwise each find no cache, each
        #: create one, and pay nine times for the same thing — the lock makes
        #: the first one do the work and the rest wait for its answer.
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- prompt
    def lists(self) -> dict[str, str]:
        """Every list under data/, by the name a prompt would write.

        Missing files come back empty rather than raising: an install without
        the operator's taxonomy still runs the other four questions, and the
        one that needs it degrades to a prompt with no list rather than to a
        crash on the first document.
        """
        found = {path.stem: path.read_text(encoding="utf-8")
                 for path in sorted(DATA.glob("*.txt"))}
        # The register of regulators is structured, because a rule reads it
        # too. Rendering it here rather than keeping a second flat copy is what
        # stops the prompt and the rule from disagreeing about a name.
        catalogue = agencies.catalogue(DATA / "agencies.json")
        if catalogue:
            found["agencies"] = catalogue
        return found

    def prompt_for(self, question: Question) -> str:
        return question.prompt(self.lists())

    # ------------------------------------------------------------------ ask
    def ask(self, question: Question, document: Document,
            preamble: str = "") -> Answer:
        """Put one question to the model about one document.

        ``preamble`` rides in front of the document text, not in front of the
        instruction. ``notify`` needs the codes the other questions settled on
        — its prompt says "รหัสที่ส่งมาให้พร้อมเอกสารนี้" and forbids inventing
        any — and those differ per document. Putting them in the instruction
        would give every document a different prompt and lose the cache that
        makes this affordable; the body is where per-document facts belong.
        """
        instruction = self.prompt_for(question)
        body = fit(document.text(), head=question.chars, tail=question.tail_chars)
        if preamble:
            body = f"{preamble}\n\n{body}"
        answer = Answer(question=question.name, document=document.number, ok=False,
                        model=self.model)

        provider = openai_chat.provider_for(self.model)
        if provider is not None:
            return self._ask_openai(provider, question, instruction, body, answer)

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            answer.error = "google-genai ยังไม่ได้ติดตั้ง"
            return answer

        client = self._connect(genai)
        if client is None:
            answer.error = "ไม่พบ GEMINI_API_KEY"
            return answer

        cache = self._cache(client, types, instruction)
        config = types.GenerateContentConfig(
            system_instruction=None if cache else instruction,
            cached_content=cache,
            response_mime_type="application/json",
            response_schema=_gemini_schema(question.schema),
            # Zero, because this is extraction and not writing. Left unset, the
            # provider's default sampled: five runs of the same twenty-two
            # documents against the same prompts scored 80.0, 80.1, 80.6, 80.3
            # and 80.3, and single columns moved as much as nineteen points
            # between runs. A change worth a point cannot be seen through that.
            temperature=TEMPERATURE,
            # Milliseconds, and per request rather than per run.
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT * 1000),
        )

        for attempt in range(1, RETRIES + 2):
            with Timer() as timer:
                try:
                    response = client.models.generate_content(
                        model=self.model, contents=body, config=config
                    )
                except Exception as exc:  # noqa: BLE001
                    if _is_timeout(exc) and attempt <= RETRIES:
                        log.warning(
                            "%s %s: ไม่ตอบใน %d วินาที ลองใหม่ (ครั้งที่ %d)",
                            document.number, question.name, REQUEST_TIMEOUT, attempt,
                        )
                        continue
                    # A cache the provider has since dropped takes every call
                    # with it. Forget it, put the instruction back, try once
                    # more — a saving that costs answers is not a saving.
                    if cache and "cache" in f"{type(exc).__name__}{exc}".lower():
                        log.info("cache lost; retrying without it")
                        with self._lock:
                            self._caches.pop(_digest(instruction), None)
                        cache = None
                        config.cached_content = None
                        config.system_instruction = instruction
                        continue
                    answer.error = f"{type(exc).__name__}: {exc}"[:300]
                    return answer

            answer.duration_ms = timer.ms
            _record_cost(answer, response)
            try:
                answer.value = json.loads(response.text or "{}")
                answer.ok = True
                return answer
            except ValueError:
                answer.error = f"คำตอบไม่ใช่ JSON (ครั้งที่ {attempt})"
                log.warning("%s: %s", document.number, answer.error)

        return answer

    # --------------------------------------------------------- openai-shaped
    def _ask_openai(self, provider: Any, question: Question, instruction: str,
                    body: str, answer: Answer) -> Answer:
        """One call to a provider that speaks the OpenAI chat API.

        Shorter than the Gemini path because there is no cache to create: the
        instruction leads the request and the provider matches the prefix on
        its own. The retry loop is the same one, and for the same reason —
        strict mode guarantees the shape but not that the call arrives.
        """
        try:
            from openai import OpenAI
        except ImportError:
            answer.error = "openai ยังไม่ได้ติดตั้ง (pip install openai)"
            return answer

        client = self._openai_client(provider, OpenAI)
        if client is None:
            answer.error = f"ไม่พบ {provider.keys[0]}"
            return answer

        system = openai_chat.instruction_for(question, instruction, provider)
        request: dict[str, Any] = {
            "model": self.model,
            "messages": openai_chat.messages(system, body),
            "response_format": openai_chat.response_format(question, provider),
            "temperature": TEMPERATURE,
        }
        effort = openai_chat.reasoning_effort(self.model, provider)
        if effort:
            request["reasoning_effort"] = effort

        for attempt in range(1, RETRIES + 2):
            with Timer() as timer:
                try:
                    response = client.chat.completions.create(**request)
                except Exception as exc:  # noqa: BLE001
                    if _is_timeout(exc) and attempt <= RETRIES:
                        log.warning(
                            "%s %s: ไม่ตอบใน %d วินาที ลองใหม่ (ครั้งที่ %d)",
                            answer.document, question.name, REQUEST_TIMEOUT, attempt,
                        )
                        continue
                    # A provider that will not enforce the schema still has to
                    # answer. Drop to plain JSON and let the retry loop and the
                    # spelled-out shape carry it, rather than losing the cell.
                    if _rejects_schema(exc) and request["response_format"]["type"] != "json_object":
                        log.info("%s ไม่รับ json_schema — ใช้ json_object แทน", self.model)
                        request["response_format"] = {"type": "json_object"}
                        request["messages"] = openai_chat.messages(
                            openai_chat.instruction_for(
                                question, instruction, _loose(provider)
                            ),
                            body,
                        )
                        continue
                    answer.error = f"{type(exc).__name__}: {exc}"[:300]
                    return answer

            answer.duration_ms = timer.ms
            openai_chat.read_cost(answer, response)
            text = (response.choices[0].message.content or "") if response.choices else ""
            try:
                answer.value = json.loads(text or "{}")
                answer.ok = True
                return answer
            except ValueError:
                answer.error = f"คำตอบไม่ใช่ JSON (ครั้งที่ {attempt})"
                log.warning("%s: %s", answer.document, answer.error)

        return answer

    def _openai_client(self, provider: Any, factory: Any) -> Any:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            key = openai_chat.find_key(provider, ENV_FILE)
            if not key:
                return None
            self._client = factory(
                api_key=key, base_url=provider.base_url, timeout=REQUEST_TIMEOUT,
                max_retries=RETRIES,
            )
        return self._client

    # ---------------------------------------------------------------- inner
    def _connect(self, genai: Any) -> Any:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            key = find_key()
            if not key:
                return None
            self._client = genai.Client(api_key=key)
        return self._client

    def _cache(self, client: Any, types: Any, instruction: str) -> str | None:
        """A provider-side cache of this instruction, created once and reused.

        Keyed on the instruction's own hash, so editing a prompt makes a new
        cache rather than silently serving the old one — the failure that would
        be hardest to notice.
        """
        if len(instruction) < CACHE_MIN_CHARS:
            return None

        key = _digest(instruction)
        with self._lock:
            entry = self._caches.get(key)
            if entry is not None:
                name, expires = entry
                if name is None or time.monotonic() < expires - CACHE_RENEW_MARGIN:
                    return name
            return self._create_cache(client, types, instruction, key)

    def _create_cache(self, client: Any, types: Any, instruction: str, key: str) -> str | None:
        """Make one, under the lock. Called only by ``_cache``."""
        try:
            created = client.caches.create(
                model=self.model,
                config=types.CreateCachedContentConfig(
                    system_instruction=instruction,
                    ttl=f"{CACHE_TTL}s",
                    display_name=f"lawscan-{key}",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            from lawscan import progress

            progress.step("cache", self.model.split("-preview")[0],
                          f"เก็บไม่ได้ ({type(exc).__name__}) ส่งคำสั่งเต็มทุกครั้ง")
            self._caches[key] = (None, float("inf"))
            return None

        # Indented like every other step, and named for what it is: a thing
        # bought once that the next few hundred calls spend.
        from lawscan import progress

        progress.step("cache", self.model.split("-preview")[0],
                      f"เก็บคำสั่ง {len(instruction):,} ตัวอักษรไว้ฝั่งผู้ให้บริการ {CACHE_TTL // 60} นาที")
        self._caches[key] = (created.name, time.monotonic() + CACHE_TTL)
        return created.name


#: Keys the JSON Schema standard defines and this API rejects. Declaring
#: additionalProperties is how a schema says "nothing else may appear", which is
#: exactly what we want of a model answer — the API simply refuses to be told.
_UNSUPPORTED = ("additionalProperties", "$schema", "definitions", "$defs", "title")


def _gemini_schema(schema: dict) -> dict:
    """The same shape, minus the keys the API will not accept."""
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k not in _UNSUPPORTED}
    if "properties" in out:
        out["properties"] = {k: _gemini_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _gemini_schema(out["items"])
    return out


#: Names the transport uses for "it never answered". Matched on the name
#: rather than the class so this file does not have to import httpx to know
#: what a stall looks like.
_TIMEOUT_NAMES = ("timeout", "timedout", "readtimeout", "connecttimeout")


def _is_timeout(exc: BaseException) -> bool:
    seen = f"{type(exc).__name__}".lower().replace("_", "")
    return any(name in seen for name in _TIMEOUT_NAMES)


#: What a provider says when it has heard of ``response_format`` but not of
#: schemas. Matched on the message because the status code is a plain 400,
#: which is also what a genuinely bad request returns.
_NO_SCHEMA = ("json_schema", "response_format", "not supported", "unsupported")


def _rejects_schema(exc: BaseException) -> bool:
    said = f"{exc}".lower()
    return "json_schema" in said and any(word in said for word in _NO_SCHEMA[1:])


def _loose(provider: Any) -> Any:
    """The same provider, recorded as one that cannot enforce a schema."""
    from dataclasses import replace

    return replace(provider, strict=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _record_cost(answer: Answer, response: Any) -> None:
    """The provider's own numbers, including what it served from cache.

    ``cached`` matters: the input count is identical whether a call was cached
    or not, so without it the log cannot tell one from the other.
    """
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return

    def count(name: str) -> int:
        value = getattr(usage, name, None)
        return value if isinstance(value, int) else 0

    answer.input_tokens = count("prompt_token_count")
    answer.cached_tokens = count("cached_content_token_count")
    answer.output_tokens = count("candidates_token_count")
