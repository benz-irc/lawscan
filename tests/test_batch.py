"""The batched request is the live request, addressed and boxed.

The whole claim of ``llm/batch.py`` is that nothing about the question changes
— only when the answer arrives and what it costs. These tests hold that claim
to the letter: the messages, the schema and the effort must come out of the
same four functions the live path calls, and the answer must land in the shape
``scan --reuse`` reads back.
"""

import json
from pathlib import Path

from lawscan.llm import batch, openai_chat
from lawscan.llm.client import Client, fit
from lawscan.llm.questions import BY_NAME
from lawscan.ocr.read import Document, Page


def _document(text: str = "ระเบียบทดสอบระบบ พ.ศ. 2563 ข้อ 1 ให้ใช้บังคับ") -> Document:
    return Document(Path("pdfs/100001.pdf"), [Page(1, text, "text-layer")])


#: The batch endpoint is OpenAI's, so these tests name an OpenAI model rather
#: than taking whichever model the run happens to default to. The default is a
#: Gemini one — the operator's choice — and ``provider_for`` returns None for
#: it, which is correct and has nothing to say about batching.
BATCHED = "gpt-5.4-mini"


class TestTheRequestIsUnchanged:
    def test_the_messages_are_the_ones_the_live_path_sends(self):
        client = Client(model=BATCHED)
        question = BY_NAME["audience"]
        document = _document()
        line = batch.request_for(client, question, document)

        provider = openai_chat.provider_for(client.model)
        instruction = openai_chat.instruction_for(
            question, client.prompt_for(question), provider
        )
        body = fit(document.text(), head=question.chars, tail=question.tail_chars)
        assert line["body"]["messages"] == openai_chat.messages(instruction, body)
        assert line["body"]["response_format"] == openai_chat.response_format(
            question, provider
        )
        assert line["body"]["model"] == client.model

    def test_it_is_addressed_to_the_chat_endpoint(self):
        line = batch.request_for(Client(model=BATCHED), BY_NAME["audience"], _document())
        assert line["method"] == "POST"
        assert line["url"] == "/v1/chat/completions"


class TestTheAddress:
    """``document::question`` — a number may carry a suffix, so one colon
    would not split back."""

    def test_a_suffixed_document_number_survives_the_round_trip(self):
        document = Document(Path("pdfs/1000012.1.pdf"), [Page(1, "ทดสอบ", "text-layer")])
        line = batch.request_for(Client(model=BATCHED), BY_NAME["audience"], document)
        number, _, name = line["custom_id"].partition("::")
        assert number == "1000012.1"
        assert name == "audience"


class TestWhatCollectWrites:
    def test_the_answer_lands_where_reuse_reads_it(self, tmp_path, monkeypatch):
        from lawscan.pipeline import _saved

        reply = {
            "custom_id": "100001::audience",
            "response": {"body": {
                "model": "gpt-5.4-mini",
                "choices": [{"message": {"content": json.dumps({"split": ["ผู้ประกอบการ"]})}}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 40,
                          "prompt_tokens_details": {"cached_tokens": 850}},
            }},
        }

        class _Files:
            def content(self, _):
                return type("R", (), {"text": json.dumps(reply, ensure_ascii=False)})()

        class _Batches:
            def retrieve(self, _):
                return type("J", (), {"output_file_id": "f", "status": "completed"})()

        class _Api:
            files, batches = _Files(), _Batches()

        client = Client()
        monkeypatch.setattr(Client, "_openai_client", lambda *a, **k: _Api())
        kept, lost = batch.collect(client, "job", tmp_path)

        assert (kept, lost) == (1, 0)
        assert _saved(tmp_path / "100001", "audience") == {"split": ["ผู้ประกอบการ"]}
        cost = json.loads((tmp_path / "100001" / "audience.json").read_text(encoding="utf-8"))["cost"]
        assert cost == {"input": 900, "cached": 850, "output": 40,
                        "billed_input": 262, "ms": 0}

    def test_a_failed_request_leaves_no_file_to_read(self, tmp_path, monkeypatch):
        """A hole is better than a lie: the next run asks again."""
        reply = {"custom_id": "100001::audience", "error": {"message": "rate limit"}}

        class _Api:
            files = type("F", (), {"content": lambda self, _: type(
                "R", (), {"text": json.dumps(reply)})()})()
            batches = type("B", (), {"retrieve": lambda self, _: type(
                "J", (), {"output_file_id": "f", "status": "completed"})()})()

        monkeypatch.setattr(Client, "_openai_client", lambda *a, **k: _Api())
        kept, lost = batch.collect(Client(), "job", tmp_path)
        assert (kept, lost) == (0, 1)
        assert not (tmp_path / "100001").exists()
