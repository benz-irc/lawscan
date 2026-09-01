"""Whether a row can be trusted, decided by evidence.

The model was asked and said 0.8 or higher on all 91 documents — including the
one that had lost twelve of its twenty-three pages to pictures nothing read. A
figure that never varies carries no information, so these rules compute it from
things that can be checked instead.

Each test below is one rule and one way a row goes wrong. A rule that cannot be
made to fire, or that fires on a clean row, is worse than no rule: it teaches a
reviewer to ignore the column.
"""

import pytest

from lawscan import confidence
from lawscan.confidence import REVIEW_BELOW, judge
from lawscan.merge import Row
from lawscan.ocr.read import Document, Page


def _document(pages=None, path="100001.pdf"):
    from pathlib import Path

    return Document(Path(path), pages or [Page(1, "ก" * 2_000, "text-layer")])


def _row(**cells):
    row = Row(document="100001")
    base = {
        "ชื่อกฎหมาย": "ระเบียบทดสอบ",
        "ประเภทกฎหมาย": "ระเบียบ",
        "กฎหมายเฉพาะธุรกิจ (Core Business Laws)": "AB2",
    }
    base.update(cells)
    for column, value in base.items():
        if value is not None:
            row.put(column, value, "rule" if column != "กลุ่มเป้าหมาย" else "llm")
    row.put("วันที่ประกาศ", cells.pop("วันที่ประกาศ", "14"), "rule")
    return row


class TestACleanRow:
    def test_scores_full_and_needs_no_review(self):
        verdict = judge(_document(), _row())
        assert verdict.findings == []
        assert verdict.score == 1.0
        assert not verdict.needs_review


class TestWhatCouldNotBeRead:
    def test_pages_lost_to_pictures(self):
        pages = [Page(1, "ก" * 2_000, "text-layer")] + [
            Page(n, "", "text-layer", has_image=True) for n in (2, 3)
        ]
        verdict = judge(_document(pages), _row())
        rules = [f.rule for f in verdict.findings]
        assert "unread-pages" in rules
        assert verdict.needs_review

    def test_the_penalty_scales_with_how_much_went_missing(self):
        def score(total_pages, lost):
            pages = [Page(n, "ก" * 2_000, "text-layer") for n in range(1, total_pages - lost + 1)]
            pages += [Page(n, "", "text-layer", has_image=True) for n in range(99, 99 + lost)]
            return judge(_document(pages), _row()).score

        assert score(20, 1) > score(6, 3)

    def test_a_document_read_mostly_by_ocr(self):
        pages = [Page(n, "ก" * 2_000, "ocr") for n in (1, 2, 3)]
        assert "recognised-not-extracted" in [f.rule for f in judge(_document(pages), _row()).findings]

    def test_almost_no_text_at_all(self):
        pages = [Page(1, "สั้นมาก", "text-layer")]
        assert "almost-no-text" in [f.rule for f in judge(_document(pages), _row()).findings]


class TestWhatTheRulesCouldNotFind:
    def test_no_gazette_header_means_the_dates_came_from_the_model(self):
        row = _row()
        row.cells.pop("วันที่ประกาศ")
        row.put("วันที่ประกาศ", "14", "llm:identity")
        finding = next(f for f in judge(_document(), row).findings if f.rule == "no-gazette-header")
        assert "วันทีมีผลใช้บังคับ" in finding.columns

    def test_a_header_read_by_rule_raises_nothing(self):
        assert "no-gazette-header" not in [f.rule for f in judge(_document(), _row()).findings]

    def test_a_document_that_never_names_its_kind(self):
        row = _row()
        row.cells.pop("ประเภทกฎหมาย")
        assert "no-law-type" in [f.rule for f in judge(_document(), row).findings]


class TestWhetherTheAnswersHoldUp:
    def test_an_audience_that_is_a_named_person(self):
        row = _row(กลุ่มเป้าหมาย="นางระพิพรรณ พงศ์เรืองรอง")
        finding = next(
            f for f in judge(_document(), row).findings if f.rule == "audience-names-a-person"
        )
        assert finding.columns == ("กลุ่มเป้าหมาย",)

    def test_an_audience_that_is_a_group_is_fine(self):
        row = _row(กลุ่มเป้าหมาย="ผู้ดำรงตำแหน่งทางการเมือง")
        assert "audience-names-a-person" not in [f.rule for f in judge(_document(), row).findings]

    def test_a_commencement_date_years_from_publication(self):
        row = _row(ปีที่ประกาศ="2563", **{"วันทีมีผลใช้บังคับ": "28 ตุลาคม 2554"})
        assert "commencement-far-from-publication" in [
            f.rule for f in judge(_document(), row).findings
        ]

    def test_a_delayed_commencement_within_reason_is_fine(self):
        row = _row(ปีที่ประกาศ="2563", **{"วันทีมีผลใช้บังคับ": "13 มิถุนายน 2564"})
        assert "commencement-far-from-publication" not in [
            f.rule for f in judge(_document(), row).findings
        ]

    def test_a_row_that_identifies_nothing(self):
        row = _row(ชื่อกฎหมาย=None, ประเภทกฎหมาย=None)
        finding = next(f for f in judge(_document(), row).findings if f.rule == "missing-identity")
        assert finding.penalty >= 0.3


class TestTheVerdict:
    def test_the_note_names_every_reason(self):
        pages = [Page(1, "ก" * 2_000, "text-layer"), Page(2, "", "text-layer", has_image=True)]
        row = _row(กลุ่มเป้าหมาย="นายสมชาย ใจดี")
        note = judge(_document(pages), row).note
        assert "อ่านไม่ได้" in note
        assert "ชื่อบุคคล" in note

    def test_never_reaches_zero(self):
        """A row with a document number and rule-read dates is not worthless."""
        pages = [Page(1, "สั้น", "ocr", has_image=True)]
        row = _row(ชื่อกฎหมาย=None, ประเภทกฎหมาย=None, กลุ่มเป้าหมาย="นายสมชาย ใจดี")
        assert judge(_document(pages), row).score >= 0.1

    def test_findings_can_be_asked_for_by_column(self):
        pages = [Page(1, "ก" * 2_000, "text-layer"), Page(2, "", "text-layer", has_image=True)]
        verdict = judge(_document(pages), _row())
        assert verdict.touching("ใบอนุญาต")
        assert not verdict.touching("ชื่อไฟล์ ")

    @pytest.mark.parametrize("rule", confidence.RULES, ids=lambda r: r.__name__)
    def test_every_rule_leaves_a_clean_row_alone(self, rule):
        """A rule that fires on a good row teaches reviewers to ignore the column."""
        assert rule(_document(), _row()) is None

    def test_the_review_threshold_is_reachable_from_one_bad_thing(self):
        pages = [Page(1, "ก" * 2_000, "text-layer")] + [
            Page(n, "", "text-layer", has_image=True) for n in range(2, 8)
        ]
        assert judge(_document(pages), _row()).score < REVIEW_BELOW


def _doc(sources):
    """A document whose pages carry the given (source, layer) pairs."""
    from pathlib import Path as _Path

    from lawscan.ocr.read import Document, Page

    pages = [Page(i, "เนื้อความ", src, layer=layer)
             for i, (src, layer) in enumerate(sources, start=1)]
    return Document(_Path("ทดสอบ.pdf"), pages)


def test_recognising_a_page_that_kept_its_layer_is_not_a_doubt():
    """The layer lied about the Thai and still holds the numerals."""
    from lawscan.confidence import _mostly_recognised
    from lawscan.merge import Row

    repaired = _doc([("ocr", "เล่ม ๑๓๗ ตอนที่ ๑๔ ก")] * 4)
    assert _mostly_recognised(repaired, Row(document="ทดสอบ")) is None


def test_a_page_with_no_layer_at_all_still_counts_against_confidence():
    from lawscan.confidence import _mostly_recognised
    from lawscan.merge import Row

    scanned = _doc([("ocr", "")] * 4)
    finding = _mostly_recognised(scanned, Row(document="ทดสอบ"))
    assert finding is not None
    assert finding.penalty == 0.15


class TestACommencementThatPrecedesPublication:
    """The year check let two documents past that start before they exist.

    It compares years and allows a gap of -1, because signing in one year and
    publishing early the next is ordinary. 124840 commences three months before
    its own publication and 105800 a year — inside the tolerance, so neither
    was reported. Both may be real; a tax measure may reach backwards. So this
    reports and does not correct.
    """

    def _row(self, day, month, year, effective):
        from lawscan.merge import Row

        row = Row(document="ทดสอบ")
        row.put("วันที่ประกาศ", day, "rule")
        row.put("เดือนที่ประกาศ", month, "rule")
        row.put("ปีที่ประกาศ", year, "rule")
        row.put("วันทีมีผลใช้บังคับ", effective, "rule")
        return row

    def _find(self, row):
        from lawscan.confidence import _effective_before_publication

        return _effective_before_publication(None, row)

    def test_a_date_inside_the_same_year_is_reported(self):
        got = self._find(self._row("7", "สิงหาคม", "2569", "9 พฤษภาคม 2569"))
        assert got is not None and "มาก่อนวันประกาศ" in got.why

    def test_a_year_back_is_reported(self):
        assert self._find(self._row("19", "กุมภาพันธ์", "2569", "20 มีนาคม 2568")) is not None

    def test_the_ordinary_case_is_silent(self):
        assert self._find(self._row("7", "สิงหาคม", "2569", "8 สิงหาคม 2569")) is None
        assert self._find(self._row("7", "สิงหาคม", "2569", "7 สิงหาคม 2569")) is None

    def test_a_gap_of_years_is_left_to_the_check_that_owns_it(self):
        assert self._find(self._row("5", "กุมภาพันธ์", "2569", "20 มกราคม 2525")) is None
