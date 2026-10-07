"""Auto-detection of field areas on a certificate template -- ported
byte-for-byte from the baseline app."""
from typing import Dict, List, Optional, Tuple

import pymupdf as fitz

from .fields import FIELD_CPF, FIELD_DATE, FIELD_NAME, FIELD_TURMA

PLACEHOLDER_VARIANTS = ["(Seu Nome Aqui)", "Seu Nome Aqui", "( Seu Nome Aqui )",
                         "(NOME)", "NOME", "Nome", "(Nome)"]

_BOLD_TOKENS = ("bold", "black", "heavy", "semibold", "demi", "extrabold", "ultrabold", "medium")


def _get_text_blocks(page: fitz.Page):
    try:
        blocks = page.get_text("blocks") or []
    except Exception:
        blocks = []
    rects = []
    for b in blocks:
        if len(b) >= 5 and isinstance(b[4], str) and b[4].strip():
            x0, y0, x1, y1 = b[:4]
            rects.append(fitz.Rect(x0, y0, x1, y1))
    return rects


def _get_word_rects(page: fitz.Page):
    try:
        words = page.get_text("words") or []
    except Exception:
        words = []
    rects = []
    for w in words:
        try:
            x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
            rects.append(fitz.Rect(x0, y0, x1, y1))
        except Exception:
            pass
    return rects


def get_line_guides(page: fitz.Page) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    try:
        drawings = page.get_drawings()
        for item in drawings:
            for it in item.get("items", []):
                if it[0] == "line":
                    p1, p2 = it[1], it[2]
                    x0, y0 = p1
                    x1, y1 = p2
                    if abs(y1 - y0) < 1.0:
                        ys.append(y0)
                    if abs(x1 - x0) < 1.0:
                        xs.append(x0)
                elif it[0] == "rect":
                    r = it[1]
                    xs.extend([r.x0, r.x1, (r.x0 + r.x1) / 2])
                    ys.extend([r.y0, r.y1, (r.y0 + r.y1) / 2])
    except Exception:
        pass
    return xs, ys


def _find_placeholder_rect(page: fitz.Page) -> Optional[fitz.Rect]:
    for text in PLACEHOLDER_VARIANTS:
        try:
            rects = page.search_for(text, quads=False)
        except Exception:
            rects = []
        if rects:
            return max(rects, key=lambda r: r.get_area())
    return None


def _default_center_rect(page: fitz.Page) -> fitz.Rect:
    pw, ph = page.rect.width, page.rect.height
    w = pw * 0.60
    h = ph * 0.10
    cx, cy = pw / 2.0, ph * 0.55
    return fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def compute_auto_area_firstpage(doc: fitz.Document) -> fitz.Rect:
    page = doc[0]
    r = _find_placeholder_rect(page)
    if r:
        pad_x = r.width * 0.4
        pad_y = r.height * 0.9
        rr = fitz.Rect(r.x0 - pad_x, r.y0 - pad_y, r.x1 + pad_x, r.y1 + pad_y)
        rr.intersect(page.rect)
        return rr
    return _default_center_rect(page)


def compute_rect_right_of(anchor: fitz.Rect, page: fitz.Page, width_ratio: float,
                           height_mult: float = 1.3) -> fitz.Rect:
    pw = page.rect.width
    h = max(anchor.height * height_mult, pw * 0.02)
    w = max(pw * width_ratio, anchor.width * 2.0)
    x0 = min(page.rect.x1 - w - 4, anchor.x1 + anchor.height * 0.3)
    y0 = anchor.y0 - (h - anchor.height) / 2.0
    r = fitz.Rect(x0, y0, x0 + w, y0 + h)
    r.intersect(page.rect)
    return r


def detect_field_rects_firstpage(doc: fitz.Document) -> Dict[str, fitz.Rect]:
    result: Dict[str, fitz.Rect] = {}
    page = doc[0]

    try:
        rr = compute_auto_area_firstpage(doc)
        result[FIELD_NAME] = rr
    except Exception:
        pass

    def search_one(words: List[str]) -> Optional[fitz.Rect]:
        for w in words:
            try:
                rects = page.search_for(w, quads=False) or []
            except Exception:
                rects = []
            if rects:
                return max(rects, key=lambda a: a.get_area())
        return None

    hit = search_one(["CPF", "Cpf", "cpf"])
    if hit:
        try:
            result[FIELD_CPF] = compute_rect_right_of(hit, page, width_ratio=0.35, height_mult=1.25)
        except Exception:
            pass

    hit = search_one(["TURMA", "Turma", "turma"])
    if hit:
        try:
            result[FIELD_TURMA] = compute_rect_right_of(hit, page, width_ratio=0.18, height_mult=1.2)
        except Exception:
            pass

    hit = search_one(["DATA", "Data", "data"])
    if hit:
        try:
            result[FIELD_DATE] = compute_rect_right_of(hit, page, width_ratio=0.22, height_mult=1.2)
        except Exception:
            pass
    else:
        try:
            words = page.get_text("words") or []
            slashes = [fitz.Rect(w[0], w[1], w[2], w[3]) for w in words if "/" in (w[4] or "")]
            if len(slashes) >= 2:
                slashes.sort(key=lambda r: r.y0)
                for j in range(len(slashes) - 1):
                    if abs(slashes[j + 1].y0 - slashes[j].y0) < page.rect.height * 0.02:
                        band_y = (slashes[j].y0 + slashes[j + 1].y0) / 2
                        same = [s for s in slashes if abs(s.y0 - band_y) < page.rect.height * 0.02]
                        if len(same) >= 2:
                            r = same[0]
                            r2 = same[-1]
                            x0 = max(page.rect.x0, r.x0 - page.rect.width * 0.05)
                            x1 = min(page.rect.x1, r2.x1 + page.rect.width * 0.15)
                            h = (r2.y1 - r.y0) * 2.0 or page.rect.height * 0.03
                            y0 = max(page.rect.y0, r.y0 - h * 0.25)
                            result[FIELD_DATE] = fitz.Rect(x0, y0, x1, y0 + h)
                            break
        except Exception:
            pass

    return result


def _detect_style_for_label(page: fitz.Page, label_text: str) -> Dict[str, bool]:
    style = {"bold": False, "italic": False}
    try:
        d = page.get_text("dict")
        label_lc = label_text.lower()
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = (span.get("text") or "").strip()
                    if not txt:
                        continue
                    if label_lc in txt.lower():
                        fname = (span.get("font") or "").lower()
                        if any(tok in fname for tok in _BOLD_TOKENS):
                            style["bold"] = True
                        return style
    except Exception:
        pass
    return style


def detect_field_styles_firstpage(doc: fitz.Document) -> Dict[str, Dict[str, bool]]:
    page = doc[0]
    styles: Dict[str, Dict[str, bool]] = {FIELD_TURMA: _detect_style_for_label(page, "TURMA")}
    return styles
