"""What a run cost, and whether the arithmetic can be believed.

A number with a currency sign in front of it gets believed without being
checked, which is exactly why it needs checking. The specific things that go
wrong: counting cached tokens twice, pricing them at the full rate, or
silently reporting zero because the folder layout moved.
"""

import json

import pytest

from lawscan import usage
from lawscan.usage import PRICE_CACHED, PRICE_INPUT, PRICE_OUTPUT, Usage, read, report


def _answers(folder, *, per_question=(1000, 400, 50), questions=usage.QUESTIONS, chars=0):
    """A document folder as a run leaves it."""
    folder.mkdir(parents=True, exist_ok=True)
    tokens_in, cached, tokens_out = per_question
    for question in questions:
        (folder / f"{question}.json").write_text(
            json.dumps({
                "question": question, "ok": True, "value": {},
                "cost": {"input": tokens_in, "cached": cached, "output": tokens_out},
            }),
            encoding="utf-8",
        )
    if chars:
        (folder / "text.txt").write_text("ก" * chars, encoding="utf-8")
    return folder


class TestCounting:
    def test_adds_up_one_document(self, tmp_path):
        _answers(tmp_path / "100001", chars=5_000)
        spend = read(tmp_path)
        assert spend.documents == 1
        assert spend.input_tokens == 5 * 1000
        assert spend.cached_tokens == 5 * 400
        assert spend.output_tokens == 5 * 50
        assert spend.characters == 5_000

    def test_cached_is_part_of_input_not_extra(self, tmp_path):
        """The provider counts cached tokens inside prompt_token_count.

        Adding them again would inflate every bill this program reports.
        """
        _answers(tmp_path / "100001", per_question=(1000, 400, 50))
        spend = read(tmp_path)
        assert spend.input_tokens == 5000
        assert spend.fresh_tokens == 5000 - 2000

    def test_a_folder_with_no_answers_is_not_a_document(self, tmp_path):
        (tmp_path / "100002").mkdir()
        (tmp_path / "100002" / "text.txt").write_text("ก", encoding="utf-8")
        assert read(tmp_path).documents == 0

    def test_unreadable_json_is_skipped_not_fatal(self, tmp_path):
        folder = _answers(tmp_path / "100001")
        (folder / "identity.json").write_text("{ ไม่ใช่ json", encoding="utf-8")
        assert read(tmp_path).documents == 1

    def test_an_empty_run(self, tmp_path):
        spend = read(tmp_path)
        assert spend.documents == 0
        assert spend.cost == 0


class TestPricing:
    def test_each_kind_is_billed_at_its_own_rate(self, tmp_path):
        # 1M fresh input, 1M cached, 1M output, in one question.
        _answers(
            tmp_path / "100001",
            per_question=(2_000_000, 1_000_000, 1_000_000),
            questions=("identity",),
        )
        spend = read(tmp_path)
        assert spend.cost_input == pytest.approx(PRICE_INPUT)
        assert spend.cost_cached == pytest.approx(PRICE_CACHED)
        assert spend.cost_output == pytest.approx(PRICE_OUTPUT)
        assert spend.cost == pytest.approx(PRICE_INPUT + PRICE_CACHED + PRICE_OUTPUT)

    def test_cache_is_cheaper_than_not_caching(self, tmp_path):
        _answers(tmp_path / "100001", per_question=(1000, 900, 50))
        spend = read(tmp_path)
        assert spend.cost < spend.cost_without_cache

    def test_no_cache_means_no_saving_claimed(self, tmp_path):
        _answers(tmp_path / "100001", per_question=(1000, 0, 50))
        spend = read(tmp_path)
        assert spend.cost == pytest.approx(spend.cost_without_cache)
        assert "ประหยัด" not in report(spend)

    def test_never_negative_when_the_provider_over_reports(self):
        """cached above input would make fresh_tokens negative and the bill a refund."""
        assert Usage(input_tokens=100, cached_tokens=500).fresh_tokens == 0


class TestReport:
    def test_says_which_price_list_it_used(self, tmp_path):
        _answers(tmp_path / "100001", chars=5_000)
        assert usage.PRICE_CHECKED in report(read(tmp_path))

    def test_names_the_extremes_not_only_the_average(self, tmp_path):
        _answers(tmp_path / "100001", per_question=(10_000, 0, 100))
        _answers(tmp_path / "100002", per_question=(100, 0, 10))
        text = report(read(tmp_path))
        assert "100001" in text and "100002" in text

    def test_an_empty_run_says_so_rather_than_zero(self, tmp_path):
        assert "ไม่ได้เรียกโมเดล" in report(read(tmp_path))

    def test_per_document_and_per_thousand_characters(self, tmp_path):
        _answers(tmp_path / "100001", chars=10_000)
        text = report(read(tmp_path))
        assert "ต่อฉบับ" in text
        assert "ต่อ 1,000 ตัวอักษร" in text
