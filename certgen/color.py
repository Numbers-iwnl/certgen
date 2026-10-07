"""Automatic text color selection -- ported byte-for-byte from the
baseline app."""
from typing import Tuple

import pymupdf as fitz
from PIL import Image


def _avg_luminance_from_pixmap(pix: fitz.Pixmap) -> float:
    try:
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        max_side = 200
        if max(img.size) > max_side:
            ratio = max_side / max(img.size)
            img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.BILINEAR)
        g = img.convert("L")
        hist = g.histogram()
        total = float(sum(hist)) or 1.0
        mean = sum(i * count for i, count in enumerate(hist)) / (255.0 * total)
        return float(mean)  # 0=black, 1=white
    except Exception:
        return 1.0


def pick_text_color(page: fitz.Page, rect: fitz.Rect) -> Tuple[float, float, float]:
    try:
        clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False, clip=clip)
        lum = _avg_luminance_from_pixmap(pix)
        return (1, 1, 1) if lum < 0.40 else (0, 0, 0)
    except Exception:
        return (0, 0, 0)
