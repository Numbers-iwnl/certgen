"""Per-template calibration persistence -- ported byte-for-byte from the
baseline app, including backward compatibility with v1/v2 calibration
files a colleague might already have sitting next to an old template."""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .fields import FIELD_NAME

CALIBRATION_SUFFIX = ".calibration.json"


@dataclass
class FieldCalibration:
    page_index: int
    rect: Tuple[float, float, float, float]
    style: Optional[Dict[str, bool]] = None


@dataclass
class TemplateConfig:
    required: List[str]
    fields: Dict[str, FieldCalibration] = field(default_factory=dict)
    version: int = 3


def _load_config(meta_path: str) -> Optional[TemplateConfig]:
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if "fields" in d and "required" in d:
            fields: Dict[str, FieldCalibration] = {}
            for k, v in d["fields"].items():
                style = v.get("style") if isinstance(v, dict) else None
                fields[k] = FieldCalibration(int(v["page_index"]), tuple(v["rect"]), style=style)
            req = list(d.get("required", [FIELD_NAME]))
            ver = int(d.get("version", 2))
            return TemplateConfig(required=req, fields=fields, version=ver)
        if "page_index" in d and "rect" in d:
            fc = FieldCalibration(int(d["page_index"]), tuple(d["rect"]), style=None)
            return TemplateConfig(required=[FIELD_NAME], fields={FIELD_NAME: fc}, version=1)
    except Exception:
        return None
    return None


def load_template_config(template_pdf: str) -> Optional[TemplateConfig]:
    import os
    meta = template_pdf + CALIBRATION_SUFFIX
    if os.path.exists(meta):
        return _load_config(meta)
    return None


def save_template_config(template_pdf: str, cfg: TemplateConfig) -> None:
    meta = template_pdf + CALIBRATION_SUFFIX
    data = {
        "version": cfg.version,
        "required": cfg.required,
        "fields": {
            k: {"page_index": v.page_index, "rect": list(v.rect), "style": (v.style or {})}
            for k, v in cfg.fields.items()
        },
    }
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
