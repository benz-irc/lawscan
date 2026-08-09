"""One reading, one way of writing it, and what happens to the old files.

The audience answer used to carry two: ``split``, one group per item, and
``merged``, the same groups joined with "และ" the way the reference file writes
fourteen of its forty. Both were asked for so the argument could be settled by
measurement rather than preference.

It is settled. "และ" reads as a single group meeting both conditions when it is
two groups meeting one each, and a person opening the file cannot tell which one
is theirs — so ``split`` reaches the column, and ``merged`` was 4.0% of a run's
output tokens produced on every document and discarded on every document.

What survives is the reader: answer files recorded before the change still hold
``merged`` and nothing else, and a rebuild with ``--reuse`` has to keep working
on them.
"""

from lawscan.merge import Row
from lawscan.pipeline import _apply

ANSWER = {"split": ["ผู้รับใบอนุญาตประเภท ก.", "ผู้รับใบอนุญาตประเภท ข."]}


def _cell(value):
    row = Row(document="100001")
    _apply(row, "audience", value)
    return row


class TestWhatReachesTheColumn:
    def test_split_is_written_as_a_comma_list(self):
        assert _cell(ANSWER).value("กลุ่มเป้าหมาย") == (
            "ผู้รับใบอนุญาตประเภท ก., ผู้รับใบอนุญาตประเภท ข."
        )

    def test_the_source_no_longer_names_a_style(self):
        """row.json said ``llm:audience[split]`` while there were two."""
        assert _cell(ANSWER).sources()["กลุ่มเป้าหมาย"] == "llm:audience"

    def test_an_empty_answer_leaves_the_cell_empty(self):
        # Not "-": nothing was read, which is different from "no audience".
        assert _cell({}).value("กลุ่มเป้าหมาย") == ""


class TestAnswerFilesFromBefore:
    def test_a_merged_only_answer_still_fills_the_cell(self):
        """Everything under out/ predates the change and reuses from disk."""
        assert _cell({"merged": "กลุ่ม ก. และ ข."}).value("กลุ่มเป้าหมาย") == "กลุ่ม ก. และ ข."

    def test_split_wins_when_the_old_file_holds_both(self):
        old = {"merged": "กลุ่ม ก. และ ข.", "split": ["กลุ่ม ก.", "กลุ่ม ข."]}
        assert _cell(old).value("กลุ่มเป้าหมาย") == "กลุ่ม ก., กลุ่ม ข."


class TestTheSchema:
    def test_nothing_asks_for_merged_any_more(self):
        from lawscan.llm.questions import AUDIENCE

        properties = AUDIENCE.schema["properties"]
        assert set(properties) == {"split"}
        assert AUDIENCE.schema["required"] == ["split"]

    def test_the_prompt_does_not_describe_it_either(self):
        # A schema without the field and a prompt still asking for it is how a
        # strict-mode request starts failing validation.
        from pathlib import Path

        assert "merged" not in Path("prompts/audience.md").read_text(encoding="utf-8")


class TestPipelineIsUntouched:
    def test_the_column_set_did_not_change(self):
        from lawscan.export.columns import COLUMNS

        assert len(COLUMNS) == 33
        assert "กลุ่มเป้าหมาย" in COLUMNS

    def test_a_rule_still_beats_the_model(self):
        """A judgment's audience is read from which court gave it."""
        row = Row(document="100002")
        row.put("กลุ่มเป้าหมาย", "ผู้ดำรงตำแหน่งทางการเมือง", "rule")
        _apply(row, "audience", ANSWER)
        assert row.value("กลุ่มเป้าหมาย") == "ผู้ดำรงตำแหน่งทางการเมือง"
