import pymupdf as fitz
from certgen import render


def _normalize_extracted(text: str) -> str:
    """PyMuPDF re-maps some characters (space -> U+00A0, hyphen -> U+00AD)
    when reading back glyphs inserted via insert_text() with a custom
    fontfile. That's a round-trip quirk of the library, not app behavior."""
    return text.replace("\xa0", " ").replace("\xad", "-")


class TestDrawTextCentered:
    def test_text_present_on_page(self, blank_pdf, font_regular):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(100, 100, 400, 160)
        render.draw_text_centered(page, rect, "Ana Beatriz", font_regular, 24)
        extracted = _normalize_extracted(page.get_text())
        doc.close()
        assert "Ana Beatriz" in extracted

    def test_horizontally_centered(self, blank_pdf, font_regular):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(100, 100, 400, 160)
        render.draw_text_centered(page, rect, "Ana", font_regular, 24)
        hits = page.search_for("Ana")
        doc.close()
        assert len(hits) == 1
        text_center = (hits[0].x0 + hits[0].x1) / 2
        rect_center = (rect.x0 + rect.x1) / 2
        assert abs(text_center - rect_center) < 2.0

    def test_bold_mode_still_renders(self, blank_pdf, font_regular):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(100, 100, 400, 160)
        render.draw_text_centered(page, rect, "Turma A", font_regular, 24, bold=True)
        extracted = _normalize_extracted(page.get_text())
        doc.close()
        assert "Turma A" in extracted


class TestDrawTextLeft:
    def test_text_present_and_left_aligned(self, blank_pdf, font_regular):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(100, 100, 400, 160)
        render.draw_text_left(page, rect, "123.456.789-00", font_regular, 18)
        hits = page.search_for("123.456.789")
        doc.close()
        assert len(hits) == 1
        assert hits[0].x0 > rect.x0
        assert hits[0].x0 < rect.x0 + rect.width * 0.15
