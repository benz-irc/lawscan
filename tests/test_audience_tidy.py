"""The two corrections the operator made to กลุ่มเป้าหมาย by hand.

Both were applied to a finished CSV, which means they were lost the next time
the run was rebuilt. They belong in code for the same reason the rules do: a
prompt asks the model for something, and this makes sure the column gets it
whether the model complied or not.
"""

from lawscan.audience import tidy


class TestCitationJoined:
    """`มาตรา 13 และมาตรา 16` names one duty written in two places — but the
    operator reads it as two groups, because a reader checks one section."""

    def test_two_sections_become_two_groups(self):
        assert tidy(["ผู้มีหน้าที่รายงานตามมาตรา 13 และมาตรา 16"]) == [
            "ผู้มีหน้าที่รายงานตามมาตรา 13",
            "ผู้มีหน้าที่รายงานตามมาตรา 16",
        ]

    def test_the_prefix_is_repeated_not_dropped(self):
        assert tidy(["ผู้ได้รับอนุญาตตามข้อ ๗ และข้อ ๙"]) == [
            "ผู้ได้รับอนุญาตตามข้อ ๗",
            "ผู้ได้รับอนุญาตตามข้อ ๙",
        ]

    def test_other_items_keep_their_place(self):
        assert tidy([
            "ผู้มีหน้าที่รายงานตามมาตรา 13 และมาตรา 16",
            "นิติบุคคลผู้จัดการฝึกอบรมที่ได้รับความเห็นชอบ",
        ]) == [
            "ผู้มีหน้าที่รายงานตามมาตรา 13",
            "ผู้มีหน้าที่รายงานตามมาตรา 16",
            "นิติบุคคลผู้จัดการฝึกอบรมที่ได้รับความเห็นชอบ",
        ]


class TestNamesWithAnd:
    """Most `และ` in this column sit inside a real name. Splitting those
    invents two organisations that do not exist."""

    def test_a_court_name_is_left_alone(self):
        name = "ศาลเยาวชนและครอบครัวจังหวัดอ่างทอง"
        assert tidy([name]) == [name]

    def test_a_single_job_is_left_alone(self):
        job = "ผู้ปฏิบัติงานด้านการเงินและบัญชี"
        assert tidy([job]) == [job]

    def test_a_fund_name_is_left_alone(self):
        fund = "กองทุนหมู่บ้านและชุมชนเมืองแห่งชาติ"
        assert tidy([fund]) == [fund]


class TestBareWords:
    """A word that could name anyone names no one. `สำนักงาน` is how a document
    refers to itself, not a group a reader can place themselves in."""

    def test_a_bare_word_goes_when_the_list_has_real_groups(self):
        assert tidy(["ผู้ตรวจการแผ่นดิน", "เลขาธิการ", "เจ้าหน้าที่",
                     "ผู้ช่วยปฏิบัติงาน"]) == [
            "ผู้ตรวจการแผ่นดิน", "เลขาธิการ", "ผู้ช่วยปฏิบัติงาน",
        ]

    def test_the_same_word_qualified_stays(self):
        kept = "เจ้าหน้าที่ผู้รับผิดชอบงานทะเบียน"
        assert tidy([kept]) == [kept]

    def test_a_bare_word_stays_when_it_is_all_there_is(self):
        """An empty column tells the reader nothing at all — worse than a
        vague one, which at least says the document binds somebody."""
        assert tidy(["สำนักงาน"]) == ["สำนักงาน"]

    def test_หน่วยงานของรัฐ_is_not_on_the_list(self):
        """The operator kept it: it is broad, but it draws a real line —
        state bodies are in, private ones are out."""
        assert tidy(["หน่วยงานของรัฐ", "ผู้รับใบอนุญาต"]) == [
            "หน่วยงานของรัฐ", "ผู้รับใบอนุญาต",
        ]


class TestLeavesGoodAnswersAlone:
    def test_an_ordinary_list_is_unchanged(self):
        groups = ["กรมโรงงานอุตสาหกรรม", "ผู้ประกอบกิจการโรงงาน"]
        assert tidy(groups) == groups

    def test_duplicates_created_by_splitting_are_removed(self):
        assert tidy([
            "ผู้ได้รับอนุญาตตามมาตรา 20 และมาตรา 22",
            "ผู้ได้รับอนุญาตตามมาตรา 20",
        ]) == ["ผู้ได้รับอนุญาตตามมาตรา 20", "ผู้ได้รับอนุญาตตามมาตรา 22"]

    def test_empty_in_empty_out(self):
        assert tidy([]) == []


class TestReachesTheColumn:
    """The tidy is worth nothing if the pipeline writes the raw answer."""

    def test_the_pipeline_tidies_before_putting_the_cell(self):
        from lawscan.merge import Row
        from lawscan.pipeline import _apply

        row = Row(document="100014")
        _apply(row, "audience", {
            "split": ["ผู้มีหน้าที่รายงานตามมาตรา 13 และมาตรา 16", "สำนักงาน",
                      "นิติบุคคลผู้จัดการฝึกอบรมที่ได้รับความเห็นชอบ"],
            "merged": "ผู้มีหน้าที่รายงานและสำนักงาน",
        })
        assert row.cells["กลุ่มเป้าหมาย"].value == (
            "ผู้มีหน้าที่รายงานตามมาตรา 13, ผู้มีหน้าที่รายงานตามมาตรา 16, "
            "นิติบุคคลผู้จัดการฝึกอบรมที่ได้รับความเห็นชอบ"
        )
