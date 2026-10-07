"""Text drawing -- ported byte-for-byte from the baseline app."""
from typing import Tuple

import pymupdf as fitz

from . import fonts


def draw_text_repeated(page: fitz.Page, pos: Tuple[float, float], text: str,
                        fontsize: float, fontfile: str, color=(0, 0, 0),
                        bold: bool = False):
    x, y = pos
    if not bold:
        page.insert_text((x, y), text, fontsize=fontsize, fontfile=fontfile,
                          fontname="UserFont", color=color)
        return
    offsets = [(0, 0), (0.35, 0), (0, 0.35), (-0.35, 0), (0, -0.35)]
    for dx, dy in offsets:
        page.insert_text((x + dx, y + dy), text, fontsize=fontsize, fontfile=fontfile,
                          fontname="UserFont", color=color)


def draw_text_centered(page: fitz.Page, rect: fitz.Rect, text: str,
                        ttf_path: str, fontsize: float, baseline_tweak_ems: float = 0.0,
                        color=(0, 0, 0), bold: bool = False):
    w = fonts.advance_width_pdf(page, text, ttf_path, fontsize)
    cx = rect.x0 + rect.width / 2.0
    x = cx - w / 2.0
    asc_em, desc_em = fonts.font_metrics_em(ttf_path)
    cy = rect.y0 + rect.height / 2.0
    y_baseline = cy + (asc_em + desc_em) * fontsize / 2.0 + baseline_tweak_ems * fontsize
    draw_text_repeated(page, (x, y_baseline), text, fontsize, ttf_path, color, bold)


def draw_text_left(page: fitz.Page, rect: fitz.Rect, text: str,
                    ttf_path: str, fontsize: float, baseline_tweak_ems: float = 0.0,
                    color=(0, 0, 0), bold: bool = False):
    asc_em, desc_em = fonts.font_metrics_em(ttf_path)
    cy = rect.y0 + rect.height / 2.0
    y_baseline = cy + (asc_em + desc_em) * fontsize / 2.0 + baseline_tweak_ems * fontsize
    x = rect.x0 + rect.width * 0.02
    draw_text_repeated(page, (x, y_baseline), text, fontsize, ttf_path, color, bold)
