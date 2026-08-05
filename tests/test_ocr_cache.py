"""Text kept on disk has to be the same text, or keeping it is a bug.

Extraction is the one expensive step and the one whose answer never changes,
so it is done once and read back. That only holds if the round trip is exact —
a rule that counts sections needs to know where one page ended, and a saved
copy that glued the pages together would quietly change every count.
"""

import json

from lawscan.ocr.read import Document, Page, load


def _document(tmp_path):
    return Document(
        path=tmp_path / "100002.pdf",
        pages=[
            Page(1, "คำพิพากษา\nคดีหมายเลขดำที่ อม. 77/2561", "text-layer"),
            Page(2, "มาตรา ๕ วรรคหนึ่ง", "ocr"),
        ],
    )


class TestRoundTrip:
    def test_pages_survive_separately(self, tmp_path):
        original = _document(tmp_path)
        original.save(tmp_path / "text")
        back = load(tmp_path / "text" / "100002.json")

        assert len(back.pages) == len(original.pages)
        assert [p.text for p in back.pages] == [p.text for p in original.pages]
        assert [p.number for p in back.pages] == [1, 2]

    def test_which_pages_were_recognised_survives(self, tmp_path):
        _document(tmp_path).save(tmp_path / "text")
        back = load(tmp_path / "text" / "100002.json")
        assert back.scanned_pages == 1

    def test_the_joined_text_is_identical(self, tmp_path):
        original = _document(tmp_path)
        original.save(tmp_path / "text")
        assert load(tmp_path / "text" / "100002.json").text() == original.text()

    def test_the_document_number_survives(self, tmp_path):
        _document(tmp_path).save(tmp_path / "text")
        assert load(tmp_path / "text" / "100002.json").number == "100002"


class TestFilesWritten:
    def test_a_readable_copy_is_written_too(self, tmp_path):
        original = _document(tmp_path)
        original.save(tmp_path / "text")
        # The .txt is for a person opening it when a cell looks wrong.
        assert (tmp_path / "text" / "100002.txt").read_text(encoding="utf-8") == original.text()

    def test_the_source_pdf_is_recorded(self, tmp_path):
        _document(tmp_path).save(tmp_path / "text")
        stored = json.loads((tmp_path / "text" / "100002.json").read_text(encoding="utf-8"))
        assert stored["source_pdf"].endswith("100002.pdf")
