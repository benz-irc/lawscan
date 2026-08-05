"""Two ways of writing one reading, and only one of them in the column.

The audience answer carries both because the argument about which is right is
settleable by measurement and was not worth having twice. ``split`` is what the
operator asked for — one group per item, so a person can find their own line.
``merged`` is how their reference file writes fourteen of its forty. Both are
kept, so switching is a rebuild from saved answers rather than another hour of
model calls.
"""

import pytest

from lawscan.merge import Row
from lawscan.pipeline import AUDIENCE_STYLES, _apply

ANSWER = {
    "merged": "ผู้รับใบอนุญาตประเภท ก. และประเภท ข.",
    "split": ["ผู้รับใบอนุญาตประเภท ก.", "ผู้รับใบอนุญาตประเภท ข."],
}


def _cell(value, style):
    row = Row(document="100001")
    _apply(row, "audience", value, audience=style)
    return row


class TestChoosing:
    def test_split_is_written_as_a_comma_list(self):
        row = _cell(ANSWER, "split")
        assert row.value("กลุ่มเป้าหมาย") == (
            "ผู้รับใบอนุญาตประเภท ก., ผู้รับใบอนุญาตประเภท ข."
        )

    def test_merged_is_written_as_the_sentence(self):
        assert _cell(ANSWER, "merged").value("กลุ่มเป้าหมาย") == ANSWER["merged"]

    def test_the_style_is_recorded_in_the_source(self):
        """row.json has to say which of the two produced the cell."""
        assert _cell(ANSWER, "merged").sources()["กลุ่มเป้าหมาย"] == "llm:audience[merged]"

    @pytest.mark.parametrize("style", AUDIENCE_STYLES)
    def test_every_offered_style_produces_something(self, style):
        assert _cell(ANSWER, style).value("กลุ่มเป้าหมาย")


class TestWhenOneIsMissing:
    def test_falls_back_rather_than_emptying_the_cell(self):
        """An older answer file has neither key under these names."""
        row = _cell({"split": ["กลุ่ม ก."]}, "merged")
        assert row.value("กลุ่มเป้าหมาย") == "กลุ่ม ก."

    def test_the_other_way_round_too(self):
        row = _cell({"merged": "กลุ่ม ก. และ ข."}, "split")
        assert row.value("กลุ่มเป้าหมาย") == "กลุ่ม ก. และ ข."

    def test_an_empty_answer_leaves_the_cell_empty(self):
        # Not "-": nothing was read, which is different from "no audience".
        assert _cell({}, "split").value("กลุ่มเป้าหมาย") == ""


class TestPipelineIsUntouched:
    def test_the_column_set_did_not_change(self):
        from lawscan.export.columns import COLUMNS

        assert len(COLUMNS) == 33
        assert "กลุ่มเป้าหมาย" in COLUMNS

    def test_a_rule_still_beats_either_style(self):
        """A judgment's audience is read from which court gave it."""
        row = Row(document="100002")
        row.put("กลุ่มเป้าหมาย", "ผู้ดำรงตำแหน่งทางการเมือง", "rule")
        _apply(row, "audience", ANSWER, audience="split")
        assert row.value("กลุ่มเป้าหมาย") == "ผู้ดำรงตำแหน่งทางการเมือง"
