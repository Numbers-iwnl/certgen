"""
Single-shot certificate rendering for the live canvas preview.

Recomputes effective rects fresh on every call, which is fine for a
single page -- batch generation uses GenerationEngine's cached
per-batch precompute (see generate.py's module docstring) instead,
since that's where recomputation-per-record actually mattered.
"""
from typing import Dict, Optional

import pymupdf as fitz

from . import fonts as fontmod
from .color import pick_text_color
from .fields import ALL_FIELDS, FIELD_NAME
from .generate import FieldSettings
from .render import draw_text_centered, draw_text_left
from .snap import SnapContext
from .template_config import TemplateConfig


def render_preview_doc(template_pdf: str, cfg: TemplateConfig,
                        field_settings: Dict[str, FieldSettings],
                        font_path: str, texts: Dict[str, str],
                        common_name_size: Optional[float] = None) -> fitz.Document:
    doc = fitz.open(template_pdf)
    page = doc[0]
    if not font_path:
        return doc

    ctx = SnapContext(page)
    raw_rects = {f: fitz.Rect(*fc.rect) for f, fc in cfg.fields.items() if fc.page_index == 0}

    for field in ALL_FIELDS:
        if field not in raw_rects:
            continue
        text = texts.get(field, "")
        if field != FIELD_NAME and (field not in cfg.required or not text):
            continue

        fs = field_settings.get(field, FieldSettings())
        eff = ctx.effective_rect(raw_rects[field], fs.snap_enabled, fs.snap_tol, fs.offset_x, fs.offset_y)
        color = pick_text_color(page, eff)

        if field == FIELD_NAME:
            if fs.font_override > 0:
                size = fs.font_override
            elif common_name_size is not None:
                size = common_name_size
            else:
                size = fontmod.autosize_font_to_rect(text, eff, font_path)
            draw_text_centered(page, eff, text, font_path, size,
                                baseline_tweak_ems=fs.baseline_tweak_ems, color=color, bold=False)
        else:
            size = fs.font_override if fs.font_override > 0 else fontmod.autosize_font_to_rect(text, eff, font_path)
            draw_text_left(page, eff, text, font_path, size,
                            baseline_tweak_ems=fs.baseline_tweak_ems, color=color, bold=fs.bold)

    return doc
