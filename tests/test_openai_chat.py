"""The second provider: which one answers, and in what shape.

Nothing here calls a network. What is worth testing is the translation layer —
the model name deciding the host and the key, and the schema being rewritten
into the form strict mode accepts. Both are silent when wrong: a key looked up
under the wrong name reads as "no key", and a schema strict mode rejects reads
as a 400 on every document.
"""

import json

from lawscan.llm import client, openai_chat
from lawscan.llm.openai_chat import provider_for, strict_schema
from lawscan.llm.questions import ALL


class TestRouting:
    def test_the_model_name_picks_the_provider(self):
        assert provider_for("gpt-5-nano").name == "openai"
        assert provider_for("deepseek-v4-flash").name == "deepseek"
        assert provider_for("kimi-k2.6").name == "moonshot"

    def test_gemini_keeps_its_own_client(self):
        # None means "not one of these" — the caller falls through to the
        # Gemini path rather than being handed a provider that cannot serve it.
        assert provider_for("gemini-2.5-flash") is None
        assert provider_for("") is None

    def test_each_provider_asks_for_its_own_key(self):
        assert client.key_names("gpt-5-nano") == ("OPENAI_API_KEY",)
        assert client.key_names("deepseek-v4-flash") == ("DEEPSEEK_API_KEY",)
        assert client.key_names("gemini-2.5-flash") == client.KEY_NAMES

    def test_only_openai_is_offered_a_reasoning_setting(self):
        # Sending reasoning_effort to a provider that does not take it is a 400
        # on every document, so the check is on the list rather than on the try.
        assert openai_chat.reasoning_effort("gpt-5-nano", provider_for("gpt-5-nano"))
        assert not openai_chat.reasoning_effort("gpt-4o-mini", provider_for("gpt-4o-mini"))
        assert not openai_chat.reasoning_effort(
            "deepseek-v4-flash", provider_for("deepseek-v4-flash")
        )


class TestStrictSchema:
    def test_every_property_becomes_required(self):
        out = strict_schema({
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["a"],
            "additionalProperties": False,
        })
        assert set(out["required"]) == {"a", "b"}

    def test_an_optional_field_may_answer_null_instead(self):
        # Strict mode has no way to say "may be absent", so the field that was
        # optional says "or null" — which is the same statement to a reader.
        out = strict_schema({
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["a"],
        })
        assert out["properties"]["a"]["type"] == "string"
        assert out["properties"]["b"]["type"] == ["string", "null"]

    def test_nested_objects_and_arrays_are_rewritten_too(self):
        out = strict_schema({
            "type": "object",
            "properties": {
                "parents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"law": {"type": "string"},
                                       "section": {"type": "string"}},
                        "required": ["law"],
                    },
                }
            },
            "required": ["parents"],
        })
        item = out["properties"]["parents"]["items"]
        assert set(item["required"]) == {"law", "section"}
        assert item["additionalProperties"] is False

    def test_every_real_question_survives_the_rewrite(self):
        # The schemas in questions.py are the ones that actually ship. A rule
        # added here that one of them breaks should fail in the suite, not on
        # the first document of a paid run.
        for question in ALL:
            out = strict_schema(question.schema)
            assert out["additionalProperties"] is False, question.name
            assert set(out["required"]) == set(out["properties"]), question.name

    def test_it_is_valid_json_for_the_wire(self):
        for question in ALL:
            json.dumps(strict_schema(question.schema))


class TestRequestShape:
    def test_the_instruction_leads_so_the_prefix_can_be_cached(self):
        # These providers match the request's leading characters. A document in
        # front of the instruction means no two calls share a prefix, and the
        # saving that pays for this pipeline disappears with nothing to see.
        sent = openai_chat.messages("คำสั่ง", "เนื้อเอกสาร")
        assert [m["role"] for m in sent] == ["system", "user"]
        assert sent[0]["content"] == "คำสั่ง"

    def test_a_provider_that_enforces_schemas_is_sent_one(self):
        question = ALL[0]
        shape = openai_chat.response_format(question, provider_for("gpt-5-nano"))
        assert shape["type"] == "json_schema"
        assert shape["json_schema"]["strict"] is True

    def test_a_provider_that_cannot_is_told_the_shape_in_words(self):
        question = ALL[0]
        loose = provider_for("deepseek-v4-flash")
        assert openai_chat.response_format(question, loose) == {"type": "json_object"}
        written = openai_chat.instruction_for(question, "คำสั่ง", loose)
        assert "รูปแบบคำตอบ" in written and "json" in written


class TestCost:
    class _Usage:
        prompt_tokens = 1000
        completion_tokens = 50
        prompt_tokens_details = type("D", (), {"cached_tokens": 800})()

    class _Flat:
        prompt_tokens = 1000
        completion_tokens = 50
        prompt_tokens_details = None
        prompt_cache_hit_tokens = 800

    def test_cached_tokens_are_read_however_the_provider_reports_them(self):
        from lawscan.llm.question import Answer

        for shape in (self._Usage(), self._Flat()):
            answer = Answer(question="q", document="1", ok=False)
            openai_chat.read_cost(answer, type("R", (), {"usage": shape})())
            assert (answer.input_tokens, answer.cached_tokens) == (1000, 800)
            # Cached tokens are part of the prompt total, not extra — the same
            # convention Gemini uses, so billed_input keeps meaning what it did.
            assert answer.billed_input == 200 + 800 * 0.25
