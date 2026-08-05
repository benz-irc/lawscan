"""Pages whose content is a picture, and saying so.

The failure this guards against is the quiet one. A regulation whose twelve
illustration pages were never read reached the CSV looking exactly like one
that lost nothing — same 33 columns, same confident answers, no sign anywhere
that half the document had not been opened.
"""

from lawscan.ocr.read import Document, Page, load


def _page(number, text, *, image=False):
    return Page(number, text, "text-layer", has_image=image)


class TestOnePage:
    def test_a_picture_with_no_text_is_unread(self):
        # A map annexe: one full-page image, nothing extractable on it.
        assert _page(4, "", image=True).unread

    def test_a_picture_under_a_heading_is_still_unread(self):
        # The uniform pages: a heading in text, the substance in the picture.
        # A threshold at 40 characters — where the OCR route starts — called
        # every one of these an ordinary page.
        heading = "เครื่องแบบปฏิบัติการของ กสทช. เครื่องแบบปฏิบัติการชาย แบบที่ ๒"
        assert _page(9, heading, image=True).unread

    def test_a_full_page_of_text_is_read_even_with_a_picture(self):
        # A crest at the top of a page of statute is not the page.
        assert not _page(1, "ก" * 900, image=True).unread

    def test_a_page_with_no_picture_is_never_unread(self):
        assert not _page(2, "", image=False).unread


class TestDocument:
    def test_lists_the_pages_by_number(self, tmp_path):
        document = Document(
            path=tmp_path / "100019.pdf",
            pages=[
                _page(1, "ก" * 900),
                _page(2, "ก" * 900),
                _page(3, "ก" * 900),
                _page(4, "", image=True),
                _page(5, "", image=True),
                _page(6, "ก" * 400),
            ],
        )
        assert document.unread_pages == (4, 5)

    def test_a_clean_document_reports_nothing(self, tmp_path):
        document = Document(tmp_path / "x.pdf", [_page(1, "ก" * 900)])
        assert document.unread_pages == ()


class TestSurvivesSaving:
    def test_the_flag_is_kept_with_the_text(self, tmp_path):
        document = Document(
            path=tmp_path / "100019.pdf",
            pages=[_page(1, "ก" * 900), _page(2, "", image=True)],
        )
        document.save(tmp_path / "text")
        assert load(tmp_path / "text" / "100019.json").unread_pages == (2,)

    def test_text_saved_before_the_flag_existed_still_loads(self, tmp_path):
        """Older saved text has no has_image key, and must not crash."""
        import json

        folder = tmp_path / "text"
        folder.mkdir()
        (folder / "100002.json").write_text(
            json.dumps({
                "number": "100002",
                "source_pdf": str(tmp_path / "100002.pdf"),
                "pages": [{"number": 1, "source": "text-layer", "text": "เก่า"}],
            }),
            encoding="utf-8",
        )
        back = load(folder / "100002.json")
        assert back.unread_pages == ()
        assert back.text() == "เก่า"
