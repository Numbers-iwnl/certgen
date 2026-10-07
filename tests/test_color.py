import pymupdf as fitz
from certgen.color import pick_text_color


class TestPickTextColor:
    def test_white_on_dark_background(self, tmp_path):
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        rect = fitz.Rect(0, 0, 200, 200)
        page.draw_rect(rect, fill=(0, 0, 0), color=(0, 0, 0))
        color = pick_text_color(page, rect)
        doc.close()
        assert color == (1, 1, 1)

    def test_black_on_light_background(self, tmp_path):
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        rect = fitz.Rect(0, 0, 200, 200)
        page.draw_rect(rect, fill=(1, 1, 1), color=(1, 1, 1))
        color = pick_text_color(page, rect)
        doc.close()
        assert color == (0, 0, 0)
