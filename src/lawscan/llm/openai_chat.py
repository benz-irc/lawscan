"""The other way to ask: any provider that speaks the OpenAI chat API.

Three providers share one implementation because they share one wire format —
OpenAI itself, DeepSeek, and Moonshot's Kimi all accept the same request and
return the same shape. What differs is the host and the key, which is a table,
not a code path. Adding a fourth is a row in ``PROVIDERS``.

Two things work differently here than on Gemini, and both are in our favour:

* **The cache is not a resource.** Gemini wants the instruction uploaded, named,
  and renewed before it lapses; these providers match the prefix of the request
  automatically. So the instruction goes in the system message, the document
  goes after it, and the saving happens without anything to create or expire.
  The one rule that matters is that the stable part must come first, to the
  character — which is the same rule that made the Gemini cache work.

* **The schema is enforced, not requested.** ``strict`` mode guarantees the
  reply matches, so the retry loop is a backstop rather than the mechanism.
  It costs one transform: strict mode requires every property to be listed in
  ``required``, so a field the prompt treats as optional has to be spelled as
  "this type or null" instead. :func:`strict_schema` does that, and it is why
  the schemas in ``questions.py`` do not have to be written twice.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Provider:
    """Where to send a request and what to call the key.

    ``strict`` is a fact about the provider, not a preference: OpenAI enforces
    a JSON Schema, while DeepSeek and Kimi accept only "reply in JSON" and
    leave the shape to the prompt. Asking a provider for enforcement it does
    not have is a 400 on every document, so it is recorded rather than tried.
    """

    name: str
    base_url: str | None
    keys: tuple[str, ...]
    #: Whether ``response_format`` supports a full JSON Schema.
    strict: bool = True


#: Matched on the model name's leading word, because that is the part a person
#: types. Everything unmatched belongs to Gemini, which has its own client.
PROVIDERS: dict[str, Provider] = {
    "gpt": Provider("openai", None, ("OPENAI_API_KEY",)),
    "o": Provider("openai", None, ("OPENAI_API_KEY",)),
    "deepseek": Provider(
        "deepseek", "https://api.deepseek.com", ("DEEPSEEK_API_KEY",), strict=False
    ),
    "kimi": Provider(
        "moonshot", "https://api.moonshot.ai/v1",
        ("MOONSHOT_API_KEY", "KIMI_API_KEY"), strict=False,
    ),
    "moonshot": Provider(
        "moonshot", "https://api.moonshot.ai/v1",
        ("MOONSHOT_API_KEY", "KIMI_API_KEY"), strict=False,
    ),
}


def provider_for(model: str) -> Provider | None:
    """Which provider serves this model name, or None for Gemini's own."""
    head = (model or "").split("-")[0].lower()
    return PROVIDERS.get(head)


#: Keys that are legal JSON Schema and illegal in a strict ``response_format``.
_DROPPED = ("$schema", "title", "default", "examples", "minimum", "maximum",
            "minLength", "maxLength", "pattern", "format", "minItems", "maxItems")


def strict_schema(schema: Any) -> Any:
    """The same schema, in the shape strict mode accepts.

    Strict mode makes two demands the source schemas do not meet. Every
    property must appear in ``required`` — so an optional field is expressed as
    a nullable one, which says the same thing to a reader and to the model.
    And ``additionalProperties`` must be present and false on every object,
    which the source schemas mostly do already.

    Done here rather than in ``questions.py`` so the schema stays readable as a
    statement about the answer, and the provider's requirements stay a fact
    about the provider.
    """
    if not isinstance(schema, dict):
        return schema

    out = {k: v for k, v in schema.items() if k not in _DROPPED}
    if out.get("type") == "object" or "properties" in out:
        properties = {k: strict_schema(v) for k, v in (out.get("properties") or {}).items()}
        required = set(out.get("required") or ())
        for name, field in properties.items():
            if name in required:
                continue
            # Not required by the prompt, and required by strict mode. Nullable
            # is how the two are both satisfied: the model may answer null,
            # which is what "left it out" meant.
            properties[name] = _nullable(field)
        out["properties"] = properties
        out["required"] = list(properties)
        out["additionalProperties"] = False
    if "items" in out:
        out["items"] = strict_schema(out["items"])
    return out


def _nullable(field: Any) -> Any:
    """A field that may also be null, without disturbing what it already says."""
    if not isinstance(field, dict) or "type" not in field:
        return field
    kind = field["type"]
    if isinstance(kind, list):
        return field if "null" in kind else {**field, "type": [*kind, "null"]}
    return {**field, "type": [kind, "null"]}


def find_key(provider: Provider, env_file: Any = None) -> str:
    """The provider's key, from the environment or from ``.env``.

    Never logged, never printed. The same two places the Gemini key is looked
    for, in the same order, because a person who put one key in ``.env`` will
    put the next one there too.
    """
    for name in provider.keys:
        value = os.environ.get(name)
        if value:
            return value
    if env_file is None or not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() in provider.keys:
            return value.strip().strip("\"'")
    return ""


def response_format(question: Any, provider: Provider) -> dict[str, Any]:
    """How to ask this provider for a reply that parses.

    A schema where the provider enforces one; otherwise the weaker request that
    at least guarantees the reply is JSON, leaving the shape to the prompt and
    to the retry loop.
    """
    if not provider.strict:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": question.name,
            "strict": True,
            "schema": strict_schema(copy.deepcopy(question.schema)),
        },
    }


#: Appended to the instruction for providers that cannot enforce a schema. The
#: shape has to reach the model somehow, and the schema is already written.
_SHAPE = (
    "\n\n## รูปแบบคำตอบ\n\n"
    "ตอบเป็น JSON ตามโครงนี้เท่านั้น ห้ามมีข้อความอื่นนอก JSON:\n\n```json\n{schema}\n```"
)


def instruction_for(question: Any, instruction: str, provider: Provider) -> str:
    """The system message, with the schema spelled out where it must be."""
    if provider.strict:
        return instruction
    return instruction + _SHAPE.format(
        schema=json.dumps(question.schema, ensure_ascii=False, indent=2)
    )


#: How hard a reasoning model should think before answering. Every one of
#: these questions is extraction — read the page, copy what it says — and the
#: reasoning tokens are billed as output, at five to six times the input rate.
#: Measured on one document: gpt-5-nano spent 3,303 output tokens to return
#: seven fields, against 918 for all five questions on gemini-2.5-flash. That
#: is the whole cost difference between the two, and it is a setting.
#:
#: ``low`` rather than ``minimal`` because two of the five questions — the
#: business codes and the parent act — are genuinely judgement, and a model
#: told not to think answers them from the first line it recognises.
REASONING_EFFORT = os.environ.get("LAWSCAN_EFFORT", "low")

#: Families that accept ``reasoning_effort``. Sending it to a model that does
#: not is a 400, so the list is checked rather than the parameter tried.
_REASONING = ("gpt-5", "o1", "o3", "o4")


def reasoning_effort(model: str, provider: Provider) -> str:
    """The effort setting for this model, or "" if it takes none."""
    if provider.name != "openai" or not REASONING_EFFORT:
        return ""
    name = (model or "").lower()
    return REASONING_EFFORT if any(name.startswith(f) for f in _REASONING) else ""


def read_cost(answer: Any, response: Any) -> None:
    """The provider's own token counts, including what the prefix cache served.

    Every one of these providers reports cached tokens in the same nested
    place, and reports it as a *part of* the prompt total rather than in
    addition to it — the same convention Gemini uses, so ``billed_input``
    keeps meaning what it meant.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    answer.input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    answer.output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details else None
    if cached is None:
        # DeepSeek reports it flat instead of nested, under its own name.
        cached = getattr(usage, "prompt_cache_hit_tokens", None)
    answer.cached_tokens = int(cached or 0)


def messages(instruction: str, body: str) -> list[dict[str, str]]:
    """System first, document second — the order the prefix cache needs.

    Reversing these costs nothing visible and everything measurable: the cache
    matches on the request's leading characters, and a document in front of the
    instruction means no two calls share a prefix.
    """
    return [
        {"role": "system", "content": instruction},
        {"role": "user", "content": body},
    ]
