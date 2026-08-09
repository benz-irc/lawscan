"""Picking a run back up without paying for it twice.

Both bugs guarded here were found by running the command a second time, which
is the thing a person does when the first one was interrupted — and both
destroyed work rather than reusing it.
"""

import json

from lawscan.llm.question import Answer
from lawscan.pipeline import done_before

QUESTIONS = ("identity", "parent", "audience", "business", "summary")


def _finished(folder, questions=QUESTIONS, ok=True):
    folder.mkdir(parents=True, exist_ok=True)
    for question in questions:
        (folder / f"{question}.json").write_text(
            json.dumps({"question": question, "ok": ok, "value": {"a": 1}}),
            encoding="utf-8",
        )
    return folder


class TestDoneBefore:
    def test_finds_a_complete_document(self, tmp_path):
        _finished(tmp_path / "result40-0101-0900" / "documents" / "100001")
        assert set(done_before([tmp_path], QUESTIONS)) == {"100001"}

    def test_a_missing_answer_means_not_done(self, tmp_path):
        _finished(tmp_path / "result40-0101-0900" / "documents" / "100001", QUESTIONS[:4])
        assert done_before([tmp_path], QUESTIONS) == {}

    def test_a_failed_answer_means_not_done(self, tmp_path):
        _finished(tmp_path / "result40-0101-0900" / "documents" / "100001", ok=False)
        assert done_before([tmp_path], QUESTIONS) == {}

    def test_the_newest_run_wins(self, tmp_path):
        _finished(tmp_path / "result40-0101-0900" / "documents" / "100001")
        _finished(tmp_path / "result40-0202-1500" / "documents" / "100001")
        assert done_before([tmp_path], QUESTIONS)["100001"].parts[-3] == "result40-0202-1500"

    def test_a_run_does_not_borrow_from_itself(self, tmp_path):
        """Two runs in the same minute share a folder.

        Without this the second run finds the first one's answers under its own
        output path and copies every file onto itself, which raises — and a
        raise per document is a CSV with a header and no rows.
        """
        mine = tmp_path / "result40-0101-0900" / "documents"
        _finished(mine / "100001")
        assert done_before([tmp_path], QUESTIONS, exclude=mine) == {}

    def test_another_run_is_still_borrowed_from(self, tmp_path):
        _finished(tmp_path / "result40-0101-0900" / "documents" / "100001")
        mine = tmp_path / "result40-0202-1500" / "documents"
        mine.mkdir(parents=True)
        assert set(done_before([tmp_path], QUESTIONS, exclude=mine)) == {"100001"}


class TestAnswerWrite:
    def test_a_failure_does_not_overwrite_a_success(self, tmp_path):
        """The answers on disk are what a rerun resumes from.

        An expired key on the second run would otherwise wipe the first run's
        paid-for answers on its way past, and nothing afterwards could tell.
        """
        good = Answer(question="identity", document="100001", ok=True, value={"title": "ระเบียบ"})
        good.write(tmp_path)

        bad = Answer(question="identity", document="100001", ok=False)
        bad.error = "ไม่พบ GEMINI_API_KEY"
        bad.write(tmp_path)

        stored = json.loads((tmp_path / "identity.json").read_text(encoding="utf-8"))
        assert stored["ok"] is True
        assert stored["value"] == {"title": "ระเบียบ"}

    def test_a_failure_is_recorded_where_nothing_is(self, tmp_path):
        bad = Answer(question="identity", document="100001", ok=False)
        bad.error = "คำตอบไม่ใช่ JSON"
        bad.write(tmp_path)
        stored = json.loads((tmp_path / "identity.json").read_text(encoding="utf-8"))
        assert stored["ok"] is False
        assert stored["error"] == "คำตอบไม่ใช่ JSON"

    def test_the_model_that_answered_is_written_down(self, tmp_path):
        """An answer whose model is unrecorded cannot be priced afterwards.

        Two runs of the same forty documents on two different models is the
        only way to know whether the cheaper one is good enough, and the
        comparison is only worth reading if each side is priced at its own
        rates.
        """
        answer = Answer(question="identity", document="100001", ok=True,
                        model="gemini-3.5-flash-lite")
        answer.write(tmp_path)
        stored = json.loads((tmp_path / "identity.json").read_text(encoding="utf-8"))
        assert stored["model"] == "gemini-3.5-flash-lite"

    def test_a_success_replaces_an_earlier_failure(self, tmp_path):
        bad = Answer(question="identity", document="100001", ok=False)
        bad.write(tmp_path)
        good = Answer(question="identity", document="100001", ok=True, value={"title": "ก"})
        good.write(tmp_path)
        assert json.loads((tmp_path / "identity.json").read_text(encoding="utf-8"))["ok"] is True
