"""
Snap-to-layout math -- ported byte-for-byte from the baseline app, plus a
SnapContext that fixes baseline Known Issue #4.

The baseline recomputed _collect_snap_candidates (two full-page text
extractions plus a vector-drawing scan) from scratch for every field of
every record -- identical work repeated up to 4x per record, thousands of
times per batch. But the candidates only depend on the (fixed) template
page, not on the (per-record) text being drawn -- and since offsets/snap-
enabled/tolerance are also constant for a given field across a whole
batch, the EFFECTIVE RECT for a field is the same for every record. Both
opportunities are captured by SnapContext: it collects candidates once
per page and computes the effective rect once per field, and the caller
reuses that single result for the whole batch instead of recomputing it
per record.
"""
from typing import List, Tuple

import pymupdf as fitz

from .detect import _get_text_blocks, _get_word_rects, get_line_guides


def collect_snap_candidates(page: fitz.Page) -> Tuple[List[fitz.Rect], List[float], List[float]]:
    rects = _get_text_blocks(page) + _get_word_rects(page)
    xs, ys = get_line_guides(page)
    pw, ph = page.rect.width, page.rect.height
    grid_x = [pw * 0.05, pw * 0.10, pw * 0.25, pw * 0.33, pw * 0.5, pw * 0.66, pw * 0.75, pw * 0.90, pw * 0.95]
    grid_y = [ph * 0.10, ph * 0.20, ph * 0.33, ph * 0.50, ph * 0.66, ph * 0.80, ph * 0.90]
    xs = list(xs) + grid_x + [pw / 2]
    ys = list(ys) + grid_y + [ph / 2]
    return rects, xs, ys


def compute_snapped_rect_from_candidates(page_rect: fitz.Rect, rect: fitz.Rect,
                                          rects: List[fitz.Rect], xs: List[float], ys: List[float],
                                          snap_enabled: bool, tol_pt: float,
                                          offset_x: float, offset_y: float) -> fitz.Rect:
    w, h = rect.width, rect.height
    cx, cy = rect.x0 + w / 2, rect.y0 + h / 2
    if not snap_enabled:
        return fitz.Rect(cx - w / 2 + offset_x, cy - h / 2 + offset_y,
                          cx + w / 2 + offset_x, cy + h / 2 + offset_y)

    cx_cands = [page_rect.width / 2]
    for r in rects:
        if abs(((r.y0 + r.y1) / 2) - cy) <= tol_pt * 2:
            cx_cands.append((r.x0 + r.x1) / 2)
    cy_cands = [page_rect.height / 2]
    for r in rects:
        if abs(((r.x0 + r.x1) / 2) - cx) <= tol_pt * 2:
            cy_cands.append((r.y0 + r.y1) / 2)
    cx_cands += xs
    cy_cands += ys

    best_cx = min(cx_cands, key=lambda x: abs(x - cx))
    best_cy = min(cy_cands, key=lambda y: abs(y - cy))

    snapped_cx = cx if abs(best_cx - cx) > tol_pt else best_cx
    snapped_cy = cy if abs(best_cy - cy) > tol_pt else best_cy

    snapped_cx += offset_x
    snapped_cy += offset_y
    return fitz.Rect(snapped_cx - w / 2, snapped_cy - h / 2, snapped_cx + w / 2, snapped_cy + h / 2)


def compute_snapped_rect(page: fitz.Page, rect: fitz.Rect, snap_enabled: bool,
                          tol_pt: float, offset_x: float, offset_y: float) -> fitz.Rect:
    """Single-shot version matching the baseline signature exactly (used
    for the live preview, where recomputing once per keystroke is fine).
    Batch generation should use SnapContext instead -- see module docstring."""
    rects, xs, ys = collect_snap_candidates(page)
    return compute_snapped_rect_from_candidates(page.rect, rect, rects, xs, ys,
                                                 snap_enabled, tol_pt, offset_x, offset_y)


class SnapContext:
    """Collects snap candidates for a page exactly once, then answers any
    number of effective_rect() calls against them in O(candidates) each
    instead of re-extracting the page every time."""

    def __init__(self, page: fitz.Page):
        self.page_rect = page.rect
        self.rects, self.xs, self.ys = collect_snap_candidates(page)

    def effective_rect(self, rect: fitz.Rect, snap_enabled: bool, tol_pt: float,
                        offset_x: float, offset_y: float) -> fitz.Rect:
        return compute_snapped_rect_from_candidates(
            self.page_rect, rect, self.rects, self.xs, self.ys,
            snap_enabled, tol_pt, offset_x, offset_y,
        )
