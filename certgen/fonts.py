"""Font metrics and autosize math -- ported byte-for-byte from the
baseline app. This is the subtlest, most load-bearing code in the whole
project (see PLAN.md's rationale for keeping PyMuPDF); behavior here is
pinned by tests/test_fonts.py and must not drift."""
from functools import lru_cache
from typing import List, Tuple

import pymupdf as fitz
from PIL import ImageFont


@lru_cache(maxsize=512)
def _pil_font(font_path: str, size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, size_px)


def advance_width(text: str, font_path: str, size_pt: float) -> float:
    size_px = max(1, int(round(size_pt)))
    f = _pil_font(font_path, size_px)
    if hasattr(f, "getlength"):
        return float(f.getlength(text))
    l, t, r, b = f.getbbox(text)
    return float(r - l)


def advance_width_pdf(page: fitz.Page, text: str, ttf_path: str, size_pt: float) -> float:
    try:
        return float(page.get_text_length(text, fontsize=size_pt, fontfile=ttf_path))
    except Exception:
        return advance_width(text, ttf_path, size_pt)


def font_metrics_em(ttf_path: str) -> Tuple[float, float]:
    try:
        f = fitz.Font(file=ttf_path)
        return float(f.ascender), float(f.descender)
    except Exception:
        pass
    try:
        size_px = 100
        f = _pil_font(ttf_path, size_px)
        a, d = f.getmetrics()
        total = max(1.0, float(a + d))
        return float(a) / total, -float(d) / total
    except Exception:
        return 0.9, -0.2


def fits_in_rect(text: str, rect: fitz.Rect, fontfile: str, size_pt: float) -> bool:
    pad_w = rect.width * 0.02
    pad_h = rect.height * 0.06
    target_w = rect.width - 2 * pad_w
    target_h = rect.height - 2 * pad_h
    w = advance_width(text, fontfile, size_pt)
    asc_em, desc_em = font_metrics_em(fontfile)
    line_h_pt = (asc_em - desc_em) * size_pt
    return (w <= target_w) and (line_h_pt <= target_h)


def autosize_font_to_rect(text: str, rect: fitz.Rect, fontfile: str,
                           min_size=8.0, max_size=200.0) -> float:
    if not text:
        return 24.0
    lo, hi = float(min_size), float(max_size)
    best = lo
    while lo <= hi:
        mid = (lo + hi) / 2.0
        if fits_in_rect(text, rect, fontfile, mid):
            best = mid
            lo = mid + 0.5
        else:
            hi = mid - 0.5
    return max(min_size, min(best, max_size))


def common_font_size_for_all(names: List[str], rect: fitz.Rect, fontfile: str,
                              min_size=8.0, max_size=200.0) -> float:
    if not names:
        return 24.0
    lo, hi = float(min_size), float(max_size)
    best = lo
    while lo <= hi:
        mid = (lo + hi) / 2.0
        if all(fits_in_rect(n, rect, fontfile, mid) for n in names):
            best = mid
            lo = mid + 0.5
        else:
            hi = mid - 0.5
    return max(min_size, min(best, max_size))
