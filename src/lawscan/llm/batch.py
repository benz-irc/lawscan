"""The same questions, sent the slow way for half the price.

Nothing here changes what is asked. The request bodies are built by the same
four functions the live path uses — ``instruction_for``, ``messages``,
``response_format``, ``reasoning_effort`` — so a batched call and a live call
differ in when the answer arrives and in nothing else.

Two things pay for the wait, and they multiply. The provider charges half for
work it may schedule at its own convenience, and a batch is where its prompt
cache does its best work: a live run of four documents at a time has four
copies of the same instruction arriving before any of them has been answered,
and each pays full price for it. Measured over one question and four documents,
the live path cached 67% of its input and the batched path 96%.

The answers land in the run folder in the shape :meth:`Answer.write` leaves
them, which is the shape ``scan --reuse`` reads. So this file does not need to
know how a row is built: it fetches, it writes, and the ordinary pipeline
assembles the CSV afterwards for nothing.
"""

from __future__ import annotations

import io
import json
import logging
import time
from pathlib import Path
from typing import Any

from lawscan.llm import openai_chat
from lawscan.llm.client import Client, fit
from lawscan.llm.question import Answer, Question
from lawscan.ocr.read import Document

log = logging.getLogger(__name__)

#: ``document::question``. Two colons because a document number may carry a
#: suffix — ``1000012.1`` is a sheet belonging to ``1000012`` — and a single
#: separator that also appears inside the name cannot be split back.
_JOIN = "::"

#: The provider takes 50,000 requests or 200MB per file. At five questions a
#: document that is 10,000 documents, and the corpus is smaller than that, but
#: a run over a larger one has to be cut somewhere and this is where.
CHUNK = 40_000


def request_for(client: Client, question: Question, document: Document) -> dict[str, Any]:
    """One line of the batch file: the live request, addressed and boxed."""
    provider = openai_chat.provider_for(client.model)
    instruction = client.prompt_for(question)
    body = fit(document.text(), head=question.chars, tail=question.tail_chars)
    request: dict[str, Any] = {
        "model": client.model,
        "messages": openai_chat.messages(
            openai_chat.instruction_for(question, instruction, provider), body
        ),
        "response_format": openai_chat.response_format(question, provider),
    }
    effort = openai_chat.reasoning_effort(client.model, provider)
    if effort:
        request["reasoning_effort"] = effort
    return {
        "custom_id": f"{document.number}{_JOIN}{question.name}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": request,
    }


def send(client: Client, lines: list[dict[str, Any]]) -> str:
    """Hand the file over and return the job to ask about later."""
    from openai import OpenAI

    provider = openai_chat.provider_for(client.model)
    api = client._openai_client(provider, OpenAI)  # noqa: SLF001 — one client, one place
    if api is None:
        raise RuntimeError(f"ไม่พบ {provider.keys[0]}")
    payload = "\n".join(
        json.dumps(line, ensure_ascii=False) for line in lines
    ).encode("utf-8")
    upload = api.files.create(file=io.BytesIO(payload), purpose="batch")
    job = api.batches.create(
        input_file_id=upload.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    log.info("ส่ง %d คำขอ · %.1f MB · งาน %s", len(lines), len(payload) / 1e6, job.id)
    return job.id


def state(client: Client, job_id: str) -> Any:
    from openai import OpenAI

    api = client._openai_client(openai_chat.provider_for(client.model), OpenAI)  # noqa: SLF001
    return api.batches.retrieve(job_id)


def wait(client: Client, job_id: str, *, every: int = 20, limit: int = 0) -> Any:
    """Poll until the job stops moving, or until ``limit`` seconds have passed.

    ``limit`` of zero waits as long as it takes. A job that outlives the wait
    is not lost — it keeps running, and :func:`collect` will find it.
    """
    started = time.time()
    job = state(client, job_id)
    while job.status in ("validating", "in_progress", "finalizing"):
        if limit and time.time() - started > limit:
            log.warning("ยังไม่เสร็จใน %d วินาที — งานยังทำต่อ เรียก collect ทีหลังได้", limit)
            return job
        time.sleep(every)
        job = state(client, job_id)
        log.info("  %4ds %s %s", int(time.time() - started), job.status, job.request_counts)
    return job


def collect(client: Client, job_id: str, workdir: Path) -> tuple[int, int]:
    """Write every answer where ``scan --reuse`` will find it.

    Returns how many landed and how many the provider could not answer. A
    request that failed leaves no file, which is the same state as a document
    nobody has asked about yet — so a later run picks it up rather than
    carrying a hole into the CSV.
    """
    from openai import OpenAI

    api = client._openai_client(openai_chat.provider_for(client.model), OpenAI)  # noqa: SLF001
    job = api.batches.retrieve(job_id)
    if not job.output_file_id:
        raise RuntimeError(f"งาน {job_id} ยังไม่มีผลลัพธ์ (สถานะ {job.status})")
    kept = lost = 0
    for line in api.files.content(job.output_file_id).text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        number, _, name = row["custom_id"].partition(_JOIN)
        reply = (row.get("response") or {}).get("body") or {}
        choices = reply.get("choices") or []
        if row.get("error") or not choices:
            lost += 1
            log.warning("%s %s: %s", number, name, row.get("error") or "ไม่มีคำตอบ")
            continue
        usage = reply.get("usage") or {}
        answer = Answer(
            question=name,
            document=number,
            ok=True,
            value=json.loads(choices[0]["message"]["content"]),
            model=reply.get("model", client.model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cached_tokens=(usage.get("prompt_tokens_details") or {}).get(
                "cached_tokens", 0
            ),
        )
        answer.write(workdir / number)
        kept += 1
    return kept, lost
