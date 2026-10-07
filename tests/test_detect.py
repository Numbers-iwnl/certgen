import pymupdf as fitz
from certgen import detect
from certgen.fields import FIELD_CPF, FIELD_DATE, FIELD_NAME, FIELD_TURMA


class TestFindPlaceholderRect:
    def test_finds_known_variant(self, certificate_pdf):
        doc = fitz.open(certificate_pdf)
        rect = detect._find_placeholder_rect(doc[0])
        doc.close()
        assert rect is not None

    def test_none_when_absent(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        rect = detect._find_placeholder_rect(doc[0])
        doc.close()
        assert rect is None


class TestDefaultCenterRect:
    def test_centered_and_sized(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        page_width = page.rect.width
        rect = detect._default_center_rect(page)
        doc.close()
        page_center_x = page_width / 2
        rect_center_x = (rect.x0 + rect.x1) / 2
        assert abs(rect_center_x - page_center_x) < 1.0
        assert rect.width == page_width * 0.60


class TestComputeAutoAreaFirstpage:
    def test_uses_placeholder_when_found(self, certificate_pdf):
        doc = fitz.open(certificate_pdf)
        rect = detect.compute_auto_area_firstpage(doc)
        doc.close()
        assert rect.get_area() > 0

    def test_falls_back_to_default_center(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        expected = detect._default_center_rect(page)
        rect = detect.compute_auto_area_firstpage(doc)
        doc.close()
        assert (round(rect.x0), round(rect.y0)) == (round(expected.x0), round(expected.y0))


class TestDetectFieldRectsFirstpage:
    def test_detects_all_labels(self, certificate_pdf):
        doc = fitz.open(certificate_pdf)
        result = detect.detect_field_rects_firstpage(doc)
        doc.close()
        assert FIELD_NAME in result
        assert FIELD_CPF in result
        assert FIELD_TURMA in result
        assert FIELD_DATE in result

    def test_cpf_rect_right_of_label(self, certificate_pdf):
        doc = fitz.open(certificate_pdf)
        page = doc[0]
        label_hits = page.search_for("CPF:")
        result = detect.detect_field_rects_firstpage(doc)
        doc.close()
        assert result[FIELD_CPF].x0 >= label_hits[0].x1

    def test_date_fallback_via_slash_heuristic(self, certificate_pdf_date_slashes):
        doc = fitz.open(certificate_pdf_date_slashes)
        result = detect.detect_field_rects_firstpage(doc)
        doc.close()
        assert FIELD_DATE in result

    def test_no_labels_still_returns_name(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        result = detect.detect_field_rects_firstpage(doc)
        doc.close()
        assert FIELD_NAME in result
        assert FIELD_CPF not in result


class TestDetectFieldStylesFirstpage:
    def test_bold_turma_label_detected(self, certificate_pdf):
        doc = fitz.open(certificate_pdf)
        styles = detect.detect_field_styles_firstpage(doc)
        doc.close()
        assert styles[FIELD_TURMA]["bold"] is True

    def test_no_label_gives_false(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        styles = detect.detect_field_styles_firstpage(doc)
        doc.close()
        assert styles[FIELD_TURMA]["bold"] is False


class TestComputeRectRightOf:
    def test_sits_at_or_after_anchor(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        anchor = fitz.Rect(50, 50, 100, 70)
        result = detect.compute_rect_right_of(anchor, page, width_ratio=0.2)
        doc.close()
        assert result.x0 >= anchor.x0

    def test_stays_within_page_bounds(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        page_x1 = page.rect.x1
        anchor = fitz.Rect(page.rect.width - 30, 50, page.rect.width - 10, 70)
        result = detect.compute_rect_right_of(anchor, page, width_ratio=0.5)
        doc.close()
        assert result.x1 <= page_x1
