"""The sweep that should have found the two a person found by reading.

Its job is triage, not judgement: separate cells that are wrong because the
pipeline mangled the answer from cells that are wrong because the model read
the document differently. The first kind is a bug, usually one line, usually
dozens of cells at once. The second is prompt work.
"""

from lawscan import defects


class TestTellingTheTwoApart:
    def test_a_null_left_in_a_composed_string_is_mechanical(self):
        tag, mechanical = defects.classify("พ.ร.บ. ก. มาตรา 5", "พ.ร.บ. ก. None")
        assert mechanical and "None" in tag

    def test_a_tab_inside_a_value_is_mechanical(self):
        tag, mechanical = defects.classify("ก, ข", "ก\tข")
        assert mechanical and "tab" in tag

    def test_a_prompt_bracket_left_on_the_answer_is_mechanical(self):
        _, mechanical = defects.classify("ทรัพย์สิน", "<ทรัพย์สิน>")
        assert mechanical

    def test_a_code_fence_is_mechanical(self):
        _, mechanical = defects.classify("เอกสาร ก.", "เอกสาร ก.```Let's try again")
        assert mechanical

    def test_a_different_reading_is_not_mechanical(self):
        tag, mechanical = defects.classify("กรมเจ้าท่า", "กรมการขนส่งทางบก")
        assert not mechanical and tag == defects.OTHER

    def test_an_incomplete_answer_is_not_mechanical(self):
        # Real, and worth fixing — but at the prompt, not in the plumbing.
        _, mechanical = defects.classify("ก, ข, ค", "ก, ข")
        assert not mechanical


class TestTheSweep:
    REF = {"1": {"ก": "พ.ร.บ. ก. มาตรา 5"}, "2": {"ก": "กรมเจ้าท่า"}}
    OURS = {"1": {"ก": "พ.ร.บ. ก. None"}, "2": {"ก": "กรมการขนส่งทางบก"}}

    def _found(self):
        return defects.scan(self.REF, self.OURS, ["ก"],
                            verdict=lambda c, e, g: "wrong" if e != g else "exact")

    def test_it_counts_both_kinds_and_separates_them(self):
        found = self._found()
        assert found.total == 2
        assert found.mechanical_cells == 1

    def test_it_names_the_column(self):
        found = self._found()
        assert any("ก" in columns for columns in found.columns.values())

    def test_it_keeps_an_example_to_show(self):
        found = self._found()
        assert any(found.examples[tag] for tag in found.mechanical)

    def test_a_clean_run_says_so(self):
        found = defects.scan(self.REF, self.REF, ["ก"],
                             verdict=lambda c, e, g: "exact")
        assert found.total == 0
        assert defects.report(found) == "ไม่มีช่องที่ผิด"

    def test_a_skipped_column_is_not_swept(self):
        found = defects.scan(self.REF, self.OURS, ["ก"], skip={"ก"},
                             verdict=lambda c, e, g: "wrong")
        assert found.total == 0

    def test_the_report_leads_with_the_fixable_ones(self):
        text = defects.report(self._found())
        assert text.index("แก้ที่โค้ดได้") < text.index("ต้องแก้ที่ prompt")
