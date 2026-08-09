"""Which files a command runs on, and which questions it declines to pay for.

Two savings that look unrelated and are the same shape: the work you asked for
should be the work that happens. One end refused a list of PDFs and made you
build a folder of symlinks; the other paid a model to answer a question the
rules had already answered, then threw the answer away.
"""

import argparse

from lawscan.cli import _pdfs, main
from lawscan.llm.questions import ALL, AUDIENCE, BUSINESS, IDENTITY, PARENT, SUMMARY
from lawscan.pipeline import _answered_by_rules


class TestNamingFiles:
    def test_one_file_is_itself(self, tmp_path):
        pdf = tmp_path / "100001.pdf"
        pdf.touch()
        assert _pdfs([pdf]) == [pdf]

    def test_a_folder_expands_in_order(self, tmp_path):
        for name in ("100003", "100001", "100002"):
            (tmp_path / f"{name}.pdf").touch()
        assert [p.stem for p in _pdfs([tmp_path])] == ["100001", "100002", "100003"]

    def test_several_files_all_run(self, tmp_path):
        # The whole point. Before this, argparse rejected the second path and
        # the way through was a directory of symlinks.
        made = [tmp_path / f"{n}.pdf" for n in ("100001", "100002", "100003")]
        for pdf in made:
            pdf.touch()
        assert _pdfs(made) == made

    def test_a_folder_and_a_loose_file_mix(self, tmp_path):
        folder = tmp_path / "pdfs"
        folder.mkdir()
        (folder / "100001.pdf").touch()
        loose = tmp_path / "100999.pdf"
        loose.touch()
        assert [p.name for p in _pdfs([folder, loose])] == ["100001.pdf", "100999.pdf"]

    def test_the_same_document_twice_is_run_once(self, tmp_path):
        # ``lawscan scan pdfs pdfs/100001.pdf`` is a reasonable thing to type
        # and paying twice for one document is not a reasonable answer.
        folder = tmp_path / "pdfs"
        folder.mkdir()
        inside = folder / "100001.pdf"
        inside.touch()
        assert _pdfs([folder, inside]) == [inside]

    def test_order_follows_the_arguments_not_the_disk(self, tmp_path):
        b = tmp_path / "100002.pdf"
        a = tmp_path / "100001.pdf"
        b.touch()
        a.touch()
        assert [p.stem for p in _pdfs([b, a])] == ["100002", "100001"]

    def test_nothing_named_is_nothing_run(self):
        assert _pdfs([]) == []

    def test_a_missing_file_is_still_returned(self, tmp_path):
        # Failing here would name no document. The reader fails against one.
        missing = tmp_path / "nope.pdf"
        assert _pdfs([missing]) == [missing]


class TestTheCommandLineAcceptsThem:
    def test_scan_parses_three_paths(self, monkeypatch, tmp_path):
        seen = {}

        def fake_scan(paths, **kw):
            seen["paths"] = paths
            return 0

        monkeypatch.setattr("lawscan.pipeline.scan", fake_scan)
        for n in ("1", "2", "3"):
            (tmp_path / f"{n}.pdf").touch()
        main(["scan", *[str(tmp_path / f"{n}.pdf") for n in "123"],
              "--no-llm", "--out", str(tmp_path / "r.csv")])
        assert [p.stem for p in seen["paths"]] == ["1", "2", "3"]


class TestNotPayingTwice:
    """A question is worth asking only where the rules left the columns empty."""

    def test_parent_is_dropped_once_a_rule_filled_it(self):
        # Judgments. Not made under an act, so the type settles the column.
        assert _answered_by_rules(PARENT, {"กฎหมายแม่": "-"})

    def test_parent_is_asked_when_no_rule_filled_it(self):
        assert not _answered_by_rules(PARENT, {"ประเภทกฎหมาย": "กฎกระทรวง"})

    def test_audience_is_dropped_where_the_court_is_the_answer(self):
        assert _answered_by_rules(AUDIENCE, {"กลุ่มเป้าหมาย": "ผู้ดำรงตำแหน่งทางการเมือง"})

    def test_a_dash_counts_as_an_answer(self):
        # A rule writes ``-`` where absence is a fact about the law, and that
        # is an answer the model cannot improve on.
        assert _answered_by_rules(PARENT, {"กฎหมายแม่": "-"})

    def test_a_question_filling_many_columns_survives_one_of_them(self):
        # ``summary`` fills nine and the rules reach ``หมายเหตุ`` alone.
        assert not _answered_by_rules(SUMMARY, {"หมายเหตุ": "เอกสารมีหน้าที่เป็นภาพ"})

    def test_partly_filled_is_not_filled(self):
        assert not _answered_by_rules(IDENTITY, {"หน่วยงานกำกับ": "กรมเจ้าท่า"})

    def test_business_is_never_dropped(self):
        # It fills a column no rule can write, so there is always a reason.
        assert not _answered_by_rules(BUSINESS, {c: "x" for c in BUSINESS.fills[:-1]})

    def test_the_rules_alone_never_silence_every_question(self):
        """A document answered entirely by rules would cost nothing — and would
        also mean the model is doing nothing, which is not true of this corpus.
        """
        found = {"กฎหมายแม่": "-", "กลุ่มเป้าหมาย": "ผู้ดำรงตำแหน่งทางการเมือง"}
        left = [q.name for q in ALL if not _answered_by_rules(q, found)]
        assert left == ["identity", "business", "summary"]
