"""The one place that talks to a model.

Everything model-shaped lives here: the key, the retries, the schema
enforcement, the cache. A question knows its prompt and its schema; it does not
know which provider answers it, and nothing outside this file constructs a
request.

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

from lawscan.llm.question import Answer, Question, Timer
from lawscan.ocr.budget import fit
from lawscan.ocr.read import Document

log = logging.getLogger(__name__)

MODEL = os.environ.get("LAWSCAN_MODEL", "gemini-3.5-flash")

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

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy.txt"


#: Where the key is looked for, in order. The environment first, because that
#: is what a server sets; then a file beside the code, because that is what a
#: person has. Supporting only the first meant a run started from an ordinary
#: shell failed on every document and wrote 51 rows with the file number filled
#: in and nothing else — a result that looks like an answer.
KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def find_key() -> str:
    """The API key, from the environment or from ``.env``.

    Never logged, never printed, never written anywhere by this program.
    """
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


def key_is_available() -> bool:
    """Whether a run that needs the model can start at all.

    Checked once before the first document rather than discovered on each of
    them. The difference matters: a missing key is one message at the top, not
    two hundred warnings scrolling past and a CSV that is mostly empty.
    """
    return bool(find_key())


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
    def taxonomy(self) -> str:
        """The business code list, or nothing if this install has none."""
        return TAXONOMY.read_text(encoding="utf-8") if TAXONOMY.exists() else ""

    def prompt_for(self, question: Question) -> str:
        return question.prompt(self.taxonomy())

    # ------------------------------------------------------------------ ask
    def ask(self, question: Question, document: Document) -> Answer:
        """Put one question to the model about one document."""
        instruction = self.prompt_for(question)
        body = fit(document.text(), head=question.chars, tail=question.tail_chars)
        answer = Answer(question=question.name, document=document.number, ok=False)

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
