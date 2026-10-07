import pymupdf as fitz
from certgen.snap import SnapContext, compute_snapped_rect


class TestComputeSnappedRect:
    def test_disabled_snap_applies_offset_only(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(100, 100, 200, 150)
        result = compute_snapped_rect(page, rect, snap_enabled=False, tol_pt=10, offset_x=5, offset_y=-3)
        doc.close()
        assert result.x0 == rect.x0 + 5
        assert result.y0 == rect.y0 - 3
        assert result.width == rect.width
        assert result.height == rect.height

    def test_enabled_snap_preserves_dimensions(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(100, 100, 220, 140)
        result = compute_snapped_rect(page, rect, snap_enabled=True, tol_pt=24, offset_x=0, offset_y=0)
        doc.close()
        assert abs(result.width - rect.width) < 1e-6
        assert abs(result.height - rect.height) < 1e-6

    def test_enabled_snap_pulls_toward_center_within_tolerance(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        page_cx = page.rect.width / 2
        rect = fitz.Rect(page_cx - 5 - 50, 100, page_cx - 5 + 50, 140)
        result = compute_snapped_rect(page, rect, snap_enabled=True, tol_pt=24, offset_x=0, offset_y=0)
        doc.close()
        result_cx = (result.x0 + result.x1) / 2
        assert abs(result_cx - page_cx) < 1e-6

    def test_far_rect_untouched_horizontally_with_tiny_tolerance(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(37, 41, 91, 63)
        result = compute_snapped_rect(page, rect, snap_enabled=True, tol_pt=0.01, offset_x=0, offset_y=0)
        doc.close()
        orig_cx = (rect.x0 + rect.x1) / 2
        result_cx = (result.x0 + result.x1) / 2
        assert abs(result_cx - orig_cx) < 1e-6


class TestSnapContext:
    def test_matches_one_shot_compute_snapped_rect(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        rect = fitz.Rect(120, 130, 240, 170)

        expected = compute_snapped_rect(page, rect, snap_enabled=True, tol_pt=24, offset_x=3, offset_y=-2)
        ctx = SnapContext(page)
        actual = ctx.effective_rect(rect, snap_enabled=True, tol_pt=24, offset_x=3, offset_y=-2)
        doc.close()

        assert (round(actual.x0, 4), round(actual.y0, 4)) == (round(expected.x0, 4), round(expected.y0, 4))
        assert (round(actual.x1, 4), round(actual.y1, 4)) == (round(expected.x1, 4), round(expected.y1, 4))

    def test_reusable_across_multiple_calls_without_reopening_page(self, blank_pdf):
        doc = fitz.open(blank_pdf)
        page = doc[0]
        ctx = SnapContext(page)
        r1 = fitz.Rect(10, 10, 50, 30)
        r2 = fitz.Rect(200, 200, 260, 230)
        out1 = ctx.effective_rect(r1, True, 24, 0, 0)
        out2 = ctx.effective_rect(r2, True, 24, 0, 0)
        doc.close()
        assert out1 is not None and out2 is not None
        assert (out1.x0, out1.y0) != (out2.x0, out2.y0)
