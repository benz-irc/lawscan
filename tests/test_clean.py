"""Deleting is the one operation with no undo, so it is fenced twice.

The fence is not paranoia. Test files live in the same folder as kept runs,
and the extracted text is the expensive half of the pipeline — a clean that
took either of those with it would be the most costly bug in the program.
"""

from lawscan.clean import clear, find, report


def _run(tests, stamp="20260101-0900", size=100):
    folder = tests / f"result40-{stamp}"
    (folder / "documents" / "100001").mkdir(parents=True)
    (folder / "result.csv").write_text("x" * size, encoding="utf-8")
    compare = tests / f"compare40-{stamp}"
    compare.mkdir(parents=True)
    (compare / "cells.csv").write_text("y" * size, encoding="utf-8")
    return folder, compare


class TestWhatIsFound:
    def test_finds_both_kinds_of_run_folder(self, tmp_path):
        _run(tmp_path)
        assert {p.name for p, _ in find(tmp_path)} == {
            "result40-20260101-0900", "compare40-20260101-0900"
        }

    def test_leaves_test_files_alone(self, tmp_path):
        _run(tmp_path)
        (tmp_path / "test_rules.py").write_text("import pytest", encoding="utf-8")
        (tmp_path / "conftest.py").write_text("", encoding="utf-8")
        found = {p.name for p, _ in find(tmp_path)}
        assert "test_rules.py" not in found
        assert "conftest.py" not in found

    def test_leaves_anything_it_did_not_create(self, tmp_path):
        _run(tmp_path)
        (tmp_path / "notes").mkdir()
        (tmp_path / "notes" / "todo.md").write_text("อย่าลบ", encoding="utf-8")
        assert "notes" not in {p.name for p, _ in find(tmp_path)}

    def test_the_text_cache_is_out_of_scope_unless_asked(self, tmp_path):
        _run(tmp_path)
        text = tmp_path / "text"
        text.mkdir()
        (text / "100001.json").write_text("{}", encoding="utf-8")
        assert text not in {p for p, _ in find(tmp_path)}
        assert text in {p for p, _ in find(tmp_path, text)}

    def test_nothing_to_clean_is_not_an_error(self, tmp_path):
        assert find(tmp_path) == []
        assert report([]) == "ไม่มีอะไรให้ล้าง"


class TestDeleting:
    def test_removes_the_run_folders(self, tmp_path):
        folder, compare = _run(tmp_path)
        clear(find(tmp_path), None)
        assert not folder.exists()
        assert not compare.exists()

    def test_the_test_files_are_still_there_afterwards(self, tmp_path):
        _run(tmp_path)
        keep = tmp_path / "test_rules.py"
        keep.write_text("import pytest", encoding="utf-8")
        clear(find(tmp_path), None)
        assert keep.exists()

    def test_the_text_folder_is_emptied_not_removed(self, tmp_path):
        """A person may keep their own notes in there."""
        text = tmp_path / "text"
        text.mkdir()
        (text / "100001.json").write_text("{}", encoding="utf-8")
        (text / "100001.txt").write_text("ข้อความ", encoding="utf-8")
        (text / "README.md").write_text("ของฉัน", encoding="utf-8")

        clear(find(tmp_path, text), text)
        assert text.is_dir()
        assert not (text / "100001.json").exists()
        assert (text / "README.md").exists()


class TestReport:
    def test_says_what_and_how_much(self, tmp_path):
        _run(tmp_path, size=2_000_000)
        text = report(find(tmp_path))
        assert "result40-20260101-0900" in text
        assert "MB" in text
