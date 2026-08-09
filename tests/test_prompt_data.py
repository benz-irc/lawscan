"""Lists a prompt needs live in data/, not pasted into the prompt.

The business question already carries several hundred taxonomy codes this way.
The agency question needs the same thing for a different list, and one hard
coded placeholder was the reason it could not have it — so the substitution is
now a table, and adding a list is adding a row to it.
"""

import pytest

from lawscan.llm.question import Question

SCHEMA = {"type": "object"}


@pytest.fixture
def prompt_file(tmp_path, monkeypatch):
    def write(text: str) -> Question:
        monkeypatch.setattr("lawscan.llm.question.PROMPTS", tmp_path)
        (tmp_path / "sample.md").write_text(text, encoding="utf-8")
        return Question(name="sample", fills=(), schema=SCHEMA)
    return write


class TestFilling:
    def test_a_placeholder_is_replaced(self, prompt_file):
        question = prompt_file("เลือกจากรายการนี้\n{{agencies}}\n")
        assert "กรม ก." in question.prompt({"agencies": "กรม ก.\nกรม ข."})

    def test_two_placeholders_are_both_replaced(self, prompt_file):
        question = prompt_file("{{taxonomy}} และ {{agencies}}")
        text = question.prompt({"taxonomy": "รหัส", "agencies": "หน่วยงาน"})
        assert "รหัส" in text and "หน่วยงาน" in text

    def test_a_prompt_with_no_placeholder_is_untouched(self, prompt_file):
        question = prompt_file("ไม่มีอะไรต้องเติม")
        assert question.prompt({"taxonomy": "รหัส"}) == "ไม่มีอะไรต้องเติม"

    def test_a_placeholder_with_no_data_becomes_empty(self, prompt_file):
        """A missing data file must not leave the braces in the instruction."""
        question = prompt_file("รายการ: {{agencies}} จบ")
        assert "{{" not in question.prompt({})


class TestClientSuppliesTheFiles:
    def test_the_client_reads_each_list_from_data(self, tmp_path, monkeypatch):
        from lawscan.llm import client as client_module

        monkeypatch.setattr(client_module, "DATA", tmp_path)
        (tmp_path / "agencies.txt").write_text("กรมทดสอบ\n", encoding="utf-8")
        assert client_module.Client().lists()["agencies"] == "กรมทดสอบ\n"

    def test_a_list_this_install_does_not_have_leaves_no_braces(
        self, tmp_path, monkeypatch
    ):
        """An install without the operator's lists still sends a clean prompt."""
        from lawscan.llm import client as client_module
        from lawscan.llm import question as question_module

        monkeypatch.setattr(client_module, "DATA", tmp_path / "data")
        monkeypatch.setattr(question_module, "PROMPTS", tmp_path)
        (tmp_path / "sample.md").write_text("รายการ: {{agencies}} จบ", encoding="utf-8")
        question = Question(name="sample", fills=(), schema=SCHEMA)
        assert client_module.Client().prompt_for(question) == "รายการ:  จบ"
